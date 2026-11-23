#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod app_settings;
mod audit;
mod backup;
mod browser_privacy;
mod credentials;
mod distribution;
mod download_notifications;
mod download_toast;
#[cfg(all(target_os = "linux", feature = "flatpak"))]
mod flatpak_portal;
mod gtk_security;
mod http_security;
mod icons;
mod ipc_security;
#[cfg(target_os = "linux")]
mod linux_overlay;
mod local_profile;
#[cfg(all(
    target_os = "linux",
    feature = "nix",
    not(feature = "desktop-integration"),
    not(feature = "flatpak")
))]
mod nix_autostart;
mod notification_security;
#[cfg(any(windows, test))]
mod pipe_security;
mod portable;
mod privacy;
mod private_file;
mod proton_compat;
mod recipe_source;
mod recipes;
mod service_badges;
mod service_export;
mod service_menu;
mod services;
mod single_instance;
mod startup_diagnostics;
mod storage_security;
mod window_chrome;
use window_chrome::{focus_window_content, get_window_chrome, open_window_menu};
#[cfg(windows)]
mod windows_security;

// Tauridium — lightweight Ferdium client (Tauri v2).
//
// Phase 1: connect to the Ferdium server (JWT login, services, workspaces).
// Phase 2: render each service in an ISOLATED child webview overlaid on
//           the area to the right of the sidebar. Isolation uses
//           `data_store_identifier` = the 16 bytes of the service UUID
//           (data_directory is ignored by WKWebView on macOS; see Phase 0).

use app_settings::validation::{
    merge_app_settings_value, resolve_startup_sidebar_collapsed, validate_order_ids,
};
use app_settings::{
    apply_autostart_setting, effective_app_settings_value, persist_app_settings,
    read_app_settings_value,
};
use base64::Engine;
use local_profile::{validate_recipe_id, LocalProfile};
use recipes::RecipeDraft;
use serde::Deserialize;
#[cfg(all(feature = "native-distribution", not(feature = "flatpak")))]
use serde::Serialize;
use serde_json::Value;
use services::navigation::{recipe_config, resolve_url, service_custom_url_template_values};
use services::{
    hide_service_webviews, service_rect, service_toast_overlay_script, start_badge_poller,
};
use sha2::{Digest, Sha256};
#[cfg(windows)]
use single_instance::{
    show_existing_main_window, windows_instance_preflight, WindowsInstancePreflight,
};
use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::sync::{LazyLock, Mutex};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::menu::{IsMenuItem, Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::tray::TrayIconBuilder;
#[cfg(not(target_os = "linux"))]
use tauri::tray::{MouseButton, MouseButtonState, TrayIconEvent};
#[cfg(target_os = "macos")]
use tauri::RunEvent;
use tauri::{AppHandle, Emitter, Manager, State, Url, WindowEvent, Wry};
#[cfg(all(
    any(
        feature = "native-distribution",
        all(target_os = "linux", any(feature = "nix", feature = "system-package"))
    ),
    not(feature = "flatpak")
))]
use tauri_plugin_notification::{NotificationExt, PermissionState};
#[cfg(all(feature = "native-distribution", not(feature = "flatpak")))]
use tauri_plugin_updater::UpdaterExt;
use tauri_plugin_window_state::{AppHandleExt as _, StateFlags};

// Shared HTTP client with connection pooling AND timeouts: without a timeout, a server
// that accepts a connection but never responds can hang login/show_service indefinitely.
static HTTP: LazyLock<reqwest::Client> = LazyLock::new(|| {
    reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(10))
        .timeout(Duration::from_secs(20))
        .redirect(http_security::redirect_policy())
        .build()
        .expect("Unable to initialize the HTTP client without weakening its security policy")
});

// User agent for Ferdium server API calls and recipe retrieval.
const API_UA: &str = concat!("Tauridium/", env!("CARGO_PKG_VERSION"));
const PROJECT_HOMEPAGE: &str = "https://github.com/Akkitto/Tauridium";
const PROJECT_SOURCE_CODE: &str = "https://github.com/Akkitto/Tauridium/tree/master";
const AUTHOR_HOMEPAGE: &str = "https://brani.dev";
const IDENTITY_MIGRATION_MARKER: &str = ".tauridium-identity-v1";
const IDENTITY_DIRECTORY_MARKERS: [&str; 8] = [
    "app_settings.json",
    "local_profile.json",
    "session.json",
    "sessions",
    "service-icons",
    "recipes",
    "audit",
    "backups",
];

fn identity_directory_suffix(current: &Path) -> &'static str {
    if current
        .file_name()
        .and_then(|name| name.to_str())
        .is_some_and(|name| name.ends_with(".dev"))
    {
        ".tauridium.dev"
    } else {
        ".tauridium"
    }
}

fn identity_directory_has_project_data(path: &Path) -> bool {
    IDENTITY_DIRECTORY_MARKERS
        .iter()
        .any(|marker| path.join(marker).exists())
}

fn legacy_identity_candidate(current: &Path) -> Result<Option<PathBuf>, String> {
    let Some(parent) = current.parent() else {
        return Ok(None);
    };
    let suffix = identity_directory_suffix(current);
    let mut candidates = Vec::<(usize, PathBuf)>::new();
    let entries = match std::fs::read_dir(parent) {
        Ok(entries) => entries,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => {
            return Err(format!(
                "Unable to inspect the application data parent directory: {error}"
            ))
        }
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path == current || !entry.file_type().is_ok_and(|kind| kind.is_dir()) {
            continue;
        }
        let Some(name) = path.file_name().and_then(|name| name.to_str()) else {
            continue;
        };
        if !name.ends_with(suffix) {
            continue;
        }
        let score = IDENTITY_DIRECTORY_MARKERS
            .iter()
            .filter(|marker| path.join(marker).exists())
            .count();
        if score > 0 {
            candidates.push((score, path));
        }
    }
    candidates.sort_by(|left, right| {
        right
            .0
            .cmp(&left.0)
            .then_with(|| left.1.as_os_str().cmp(right.1.as_os_str()))
    });
    let Some((score, candidate)) = candidates.first() else {
        return Ok(None);
    };
    if candidates.get(1).is_some_and(|other| other.0 == *score) {
        return Ok(None);
    }
    Ok(Some(candidate.clone()))
}

fn copy_identity_directory_contents(source: &Path, target: &Path) -> Result<(), String> {
    std::fs::create_dir_all(target).map_err(|error| {
        format!("Unable to create the current Tauridium application data directory: {error}")
    })?;
    let entries = std::fs::read_dir(source)
        .map_err(|error| format!("Unable to read legacy Tauridium application data: {error}"))?;
    for entry in entries {
        let entry = entry
            .map_err(|error| format!("Unable to read legacy Tauridium data entry: {error}"))?;
        let file_type = entry
            .file_type()
            .map_err(|error| format!("Unable to inspect legacy Tauridium data entry: {error}"))?;
        let destination = target.join(entry.file_name());
        if file_type.is_dir() {
            copy_identity_directory_contents(&entry.path(), &destination)?;
        } else if file_type.is_file() && !destination.exists() {
            std::fs::copy(entry.path(), &destination).map_err(|error| {
                format!("Unable to migrate Tauridium application data file: {error}")
            })?;
        }
    }
    Ok(())
}

fn migrate_identity_directory(current: &Path) -> Result<bool, String> {
    if current.join(IDENTITY_MIGRATION_MARKER).exists() {
        return Ok(false);
    }
    if identity_directory_has_project_data(current) {
        return Ok(false);
    }
    let Some(source) = legacy_identity_candidate(current)? else {
        return Ok(false);
    };
    copy_identity_directory_contents(&source, current)?;
    std::fs::write(current.join(IDENTITY_MIGRATION_MARKER), b"1\n")
        .map_err(|error| format!("Unable to finalize Tauridium identity migration: {error}"))?;
    Ok(true)
}

fn migrate_legacy_application_identity(app: &AppHandle) -> Result<bool, String> {
    let mut roots = Vec::new();
    if let Ok(path) = app.path().app_data_dir() {
        roots.push(path);
    }
    if let Ok(path) = app.path().app_config_dir() {
        roots.push(path);
    }
    roots.sort();
    roots.dedup();

    let mut migrated = false;
    for root in roots {
        migrated |= migrate_identity_directory(&root)?;
    }
    Ok(migrated)
}

// Logical sidebar width; must match the shell CSS.
const SIDEBAR_W: f64 = 240.0;
const COLLAPSED_SIDEBAR_W: f64 = 52.0;
const MIN_RUNTIME_SIDEBAR_W: f64 = COLLAPSED_SIDEBAR_W;
const MAX_SIDEBAR_W: f64 = 1200.0;
#[derive(Default)]
struct AppState {
    server: Mutex<Option<String>>,
    token: Mutex<Option<String>>,
    local_mode: Mutex<bool>,
    local_profile: Mutex<LocalProfile>,
    created: Mutex<HashSet<String>>, // service IDs for webviews already created
    known_services: Mutex<HashSet<String>>, // validated server/local identities, not renderer claims
    active: Mutex<Option<String>>,          // service ID currently displayed
    unread: Mutex<HashMap<String, i64>>,    // unread count per service (for the dock badge)
    flags: Mutex<HashMap<String, ServiceFlags>>, // per-service settings (notification/mute/badge)
    notification_budget: Mutex<notification_security::Budget>,
    settings: Mutex<Value>, // app settings cache (read by the poller, etc.)
    #[cfg(windows)]
    tracking_prevention_startup: Mutex<Value>, // immutable after setup; profile options require restart
    settings_write: Mutex<()>, // serializes app-settings read/modify/write transactions
    sidebar_w: Mutex<f64>,     // sidebar width (initialized during setup, default 240)
    desired_active: Mutex<Option<String>>, // last requested service (prevents focus stealing during switches)
    inflight: Mutex<HashSet<String>>,      // webviews being created (prevents duplicate add_child)
    preloading: Mutex<HashSet<String>>, // off-screen webviews that must stay visible until initial load finishes
    download_workspaces: Mutex<HashMap<String, Option<String>>>, // active workspace context per service download
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct NativeServiceMenuEntry {
    id: String,
    name: String,
    enabled: bool,
}

fn native_service_menu_label(service: &NativeServiceMenuEntry) -> String {
    let raw = service.name.trim();
    let raw = if raw.is_empty() {
        service.id.trim()
    } else {
        raw
    };
    let mut label: String = raw.chars().take(80).collect();
    if raw.chars().count() > 80 {
        label.push('…');
    }
    // Native menu backends use '&' for mnemonic markers. Escape it so service names
    // are rendered literally and cannot accidentally change keyboard navigation.
    label.replace('&', "&&")
}

fn native_menu_accelerator(binding: &str) -> Option<String> {
    let binding = binding.trim();
    if binding.is_empty() || binding.contains(char::is_whitespace) {
        return None;
    }
    let mut parts: Vec<&str> = binding.split('+').collect();
    let key = parts.pop()?;
    if key.is_empty() {
        return None;
    }
    let key = match key {
        "," => "Comma",
        "." => "Period",
        "-" => "Minus",
        "=" => "Equal",
        ";" => "Semicolon",
        "'" => "Quote",
        "[" => "BracketLeft",
        "]" => "BracketRight",
        "\\" => "Backslash",
        "`" => "Backquote",
        other => other,
    };
    parts.push(key);
    Some(parts.join("+"))
}

fn build_native_application_menu(
    app: &AppHandle,
    services: &[NativeServiceMenuEntry],
) -> tauri::Result<Menu<Wry>> {
    let settings = read_app_settings_value(app);
    let shortcut = |action: &str| -> Option<String> {
        settings
            .get("keybindings")
            .and_then(Value::as_object)
            .and_then(|bindings| bindings.get(action))
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|binding| !binding.is_empty() && !binding.contains(char::is_whitespace))
            .and_then(native_menu_accelerator)
    };
    let settings_item = MenuItem::with_id(
        app,
        "open-settings",
        "Settings",
        true,
        shortcut("openSettings"),
    )?;
    let add_service_item = MenuItem::with_id(
        app,
        "open-add-service",
        "Add Service",
        true,
        shortcut("addService"),
    )?;
    let add_workspace_item = MenuItem::with_id(
        app,
        "open-add-workspace",
        "Add Workspace",
        true,
        shortcut("addWorkspace"),
    )?;
    let signed_in = {
        let state = app.state::<AppState>();
        *state.local_mode.lock().unwrap() || state.token.lock().unwrap().is_some()
    };
    let sign_out_item = MenuItem::with_id(app, "sign-out", "Sign out", signed_in, None::<&str>)?;
    let app_sub = Submenu::with_items(
        app,
        "Tauridium",
        true,
        &[
            &settings_item,
            &add_service_item,
            &add_workspace_item,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::hide(app, None)?,
            &PredefinedMenuItem::hide_others(app, None)?,
            &PredefinedMenuItem::show_all(app, None)?,
            &PredefinedMenuItem::separator(app)?,
            &sign_out_item,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::quit(app, None)?,
        ],
    )?;
    let edit = Submenu::with_items(
        app,
        "Edit",
        true,
        &[
            &PredefinedMenuItem::undo(app, None)?,
            &PredefinedMenuItem::redo(app, None)?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::cut(app, None)?,
            &PredefinedMenuItem::copy(app, None)?,
            &PredefinedMenuItem::paste(app, None)?,
            &PredefinedMenuItem::select_all(app, None)?,
        ],
    )?;
    let reload_svc = MenuItem::with_id(
        app,
        "reload-service",
        "Reload Service",
        true,
        shortcut("reloadService"),
    )?;
    let reload_app_item = MenuItem::with_id(
        app,
        "reload-app",
        "Reload Tauridium",
        true,
        shortcut("reloadApp"),
    )?;
    let zoom_in = MenuItem::with_id(app, "shortcut:zoomIn", "Zoom In", true, shortcut("zoomIn"))?;
    let zoom_out = MenuItem::with_id(
        app,
        "shortcut:zoomOut",
        "Zoom Out",
        true,
        shortcut("zoomOut"),
    )?;
    let reset_zoom = MenuItem::with_id(
        app,
        "shortcut:resetZoom",
        "Actual Size",
        true,
        shortcut("resetZoom"),
    )?;
    let toggle_sidebar = MenuItem::with_id(
        app,
        "toggle-sidebar",
        "Toggle Sidebar",
        true,
        shortcut("toggleSidebar"),
    )?;
    let devtools = MenuItem::with_id(
        app,
        "toggle-devtools",
        "Toggle Developer Tools",
        true,
        shortcut("toggleDevtools"),
    )?;
    let view = Submenu::with_items(
        app,
        "View",
        true,
        &[
            &reload_svc,
            &reload_app_item,
            &PredefinedMenuItem::separator(app)?,
            &zoom_in,
            &zoom_out,
            &reset_zoom,
            &PredefinedMenuItem::separator(app)?,
            &toggle_sidebar,
            &devtools,
        ],
    )?;

    let quick_workspace = MenuItem::with_id(
        app,
        "shortcut:quickWorkspaceSwitch",
        "Quick Workspace Switcher…",
        true,
        shortcut("quickWorkspaceSwitch"),
    )?;
    let quick_service = MenuItem::with_id(
        app,
        "shortcut:quickServiceSwitch",
        "Quick Service Switcher…",
        true,
        shortcut("quickServiceSwitch"),
    )?;
    let next_service = MenuItem::with_id(
        app,
        "shortcut:nextService",
        "Next Service",
        true,
        shortcut("nextService"),
    )?;
    let previous_service = MenuItem::with_id(
        app,
        "shortcut:previousService",
        "Previous Service",
        true,
        shortcut("previousService"),
    )?;
    let next_workspace = MenuItem::with_id(
        app,
        "shortcut:nextWorkspace",
        "Next Workspace",
        true,
        shortcut("nextWorkspace"),
    )?;
    let previous_workspace = MenuItem::with_id(
        app,
        "shortcut:previousWorkspace",
        "Previous Workspace",
        true,
        shortcut("previousWorkspace"),
    )?;
    let navigate = Submenu::with_items(
        app,
        "Navigate",
        true,
        &[
            &quick_workspace,
            &quick_service,
            &PredefinedMenuItem::separator(app)?,
            &next_service,
            &previous_service,
            &next_workspace,
            &previous_workspace,
        ],
    )?;

    let mut service_items: Vec<MenuItem<Wry>> = Vec::new();
    if services.is_empty() {
        service_items.push(MenuItem::with_id(
            app,
            "service-menu-empty",
            "No services configured",
            false,
            None::<&str>,
        )?);
    } else {
        for (index, service) in services.iter().enumerate() {
            let accelerator = (index < 9).then(|| format!("CmdOrCtrl+{}", index + 1));
            service_items.push(MenuItem::with_id(
                app,
                format!("goto-service:{}", service.id),
                native_service_menu_label(service),
                service.enabled,
                accelerator,
            )?);
        }
    }
    let service_refs: Vec<&dyn IsMenuItem<Wry>> = service_items
        .iter()
        .map(|item| item as &dyn IsMenuItem<Wry>)
        .collect();
    let services_menu = Submenu::with_items(app, "Services", true, &service_refs)?;

    let about_item = MenuItem::with_id(app, "open-about", "About", true, None::<&str>)?;
    let project_homepage = MenuItem::with_id(
        app,
        "open-project-homepage",
        "Project Homepage",
        true,
        None::<&str>,
    )?;
    let project_source = MenuItem::with_id(
        app,
        "open-project-source",
        "Project Source Code",
        true,
        None::<&str>,
    )?;
    let author_homepage = MenuItem::with_id(
        app,
        "open-author-homepage",
        "Author Homepage",
        true,
        None::<&str>,
    )?;
    let about_menu = Submenu::with_items(
        app,
        "About",
        true,
        &[
            &about_item,
            &PredefinedMenuItem::separator(app)?,
            &project_homepage,
            &project_source,
            &author_homepage,
        ],
    )?;

    Menu::with_items(
        app,
        &[
            &app_sub,
            &edit,
            &view,
            &navigate,
            &services_menu,
            &about_menu,
        ],
    )
}

#[derive(Clone, Copy)]
struct ServiceFlags {
    notif: bool,
    muted: bool,
    badge: bool,
    indirect_badge: bool,
}

impl Default for ServiceFlags {
    fn default() -> Self {
        // Defaults: notifications and badge enabled, not muted (matching Ferdium).
        ServiceFlags {
            notif: true,
            muted: false,
            badge: true,
            indirect_badge: false,
        }
    }
}

// --- Auth ---------------------------------------------------------------

// The Ferdium client sends base64(sha256(password)) (see ferdium-app UserApi.ts).
fn ferdium_password_hash(password: &str) -> String {
    let digest = Sha256::digest(password.as_bytes());
    base64::engine::general_purpose::STANDARD.encode(digest)
}

fn normalize_server(server: &str) -> String {
    server.trim().trim_end_matches('/').to_string()
}

// All persistent writes use creation-time privacy and exclusive, verified staging.
pub(crate) fn write_atomic(path: &Path, contents: &str) -> std::io::Result<()> {
    private_file::write(path, contents.as_bytes())
}

// Read a persistent file and restore a Windows backup left by an interruption
// between the two renames in replace_file. On other platforms this path is normally
// never used, but remains safe.
fn read_persistent(path: &Path) -> std::io::Result<String> {
    match std::fs::read_to_string(path) {
        Ok(text) => Ok(text),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            let backup = path.with_extension("bak");
            let text = std::fs::read_to_string(&backup)?;
            if std::fs::rename(&backup, path).is_err() {
                // The backup remains readable even if atomic restoration is denied.
                return Ok(text);
            }
            Ok(text)
        }
        Err(error) => Err(error),
    }
}

async fn api_get(base: &str, token: &str, path: &str) -> Result<Value, String> {
    let res = HTTP
        .clone()
        .get(format!("{base}{path}"))
        .bearer_auth(token)
        .header(reqwest::header::USER_AGENT, API_UA)
        .send()
        .await
        .map_err(|e| format!("Request {path} failed: {e}"))?;
    if !res.status().is_success() {
        return Err(format!("{path} : HTTP {}", res.status()));
    }
    http_security::json(res)
        .await
        .map_err(|e| format!("Unable to parse response from {path}: {e}"))
}

fn session_path(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Session directory unavailable: {error}"))?;
    std::fs::create_dir_all(&dir)
        .map_err(|error| format!("Unable to create session directory: {error}"))?;
    Ok(dir.join("session.json"))
}

fn session_warning(mut user: Value, warning: Option<String>) -> Value {
    user["sessionSecurityWarning"] = warning.map_or(Value::Null, Value::String);
    user
}

fn local_profile_path(app: &AppHandle) -> Result<PathBuf, String> {
    app.path()
        .app_data_dir()
        .map(|dir| dir.join("local_profile.json"))
        .map_err(|error| format!("Local data directory unavailable: {error}"))
}

fn load_local_profile(app: &AppHandle) -> Result<LocalProfile, String> {
    LocalProfile::load(&local_profile_path(app)?)
}

fn save_local_profile(app: &AppHandle, profile: &LocalProfile) -> Result<(), String> {
    profile.save(&local_profile_path(app)?)
}

fn save_local_session(app: &AppHandle) -> Result<Option<String>, String> {
    credentials::save(
        &session_path(app)?,
        None,
        None,
        false,
        false,
        &credentials::NativeVault,
    )
}

fn local_user() -> Value {
    serde_json::json!({
        "email": "local@tauridium.invalid",
        "firstname": "Local",
        "lastname": "",
        "id": "local",
        "local": true
    })
}

fn is_local_mode(state: &State<'_, AppState>) -> bool {
    *state.local_mode.lock().unwrap()
}

fn clear_session(app: &AppHandle) -> Result<(), String> {
    credentials::clear(&session_path(app)?, &credentials::NativeVault)
}

#[tauri::command]
async fn login(
    app: AppHandle,
    state: State<'_, AppState>,
    server: String,
    email: String,
    password: String,
    remember_session: Option<bool>,
    allow_insecure_server: Option<bool>,
) -> Result<Value, String> {
    let allow_insecure = allow_insecure_server.unwrap_or(false);
    let base = credentials::validate_server(&normalize_server(&server), allow_insecure)?;
    let password_hash = ferdium_password_hash(&password);

    let res = HTTP
        .clone()
        .post(format!("{base}/v1/auth/login"))
        .basic_auth(&email, Some(&password_hash))
        .header(reqwest::header::USER_AGENT, API_UA)
        .send()
        .await
        // Network error: transient (the UI recognizes the prefix and retries).
        .map_err(|e| format!("transient: server unreachable ({e})"))?;

    let status = res.status();
    if !status.is_success() {
        // 401/403 means credentials were genuinely rejected (do not retry); everything else (5xx, server
        // malfunction, etc.) is transient and the UI will retry.
        if status.as_u16() == 401 || status.as_u16() == 403 {
            return Err(format!(
                "Credentials rejected. Server returned HTTP {status}."
            ));
        }
        return Err(format!("transient: server error (HTTP {status})"));
    }

    let body: Value = http_security::json(res)
        .await
        .map_err(|e| format!("Unable to parse login response: {e}"))?;
    let token = body
        .get("token")
        .and_then(Value::as_str)
        .ok_or("Login response did not contain a token")?
        .to_string();

    let me = api_get(&base, &token, "/v1/me").await?;
    if !me.is_object() {
        return Err("Account response is invalid".into());
    }
    let local_profile = load_local_profile(&app)?;
    let warning = credentials::save(
        &session_path(&app)?,
        Some(&base),
        Some(&token),
        remember_session.unwrap_or(true),
        allow_insecure,
        &credentials::NativeVault,
    )?;
    {
        state.known_services.lock().unwrap().clear();
        *state.server.lock().unwrap() = Some(base.clone());
        *state.token.lock().unwrap() = Some(token.clone());
        *state.local_mode.lock().unwrap() = false;
        *state.local_profile.lock().unwrap() = local_profile;
    }
    Ok(session_warning(me, warning))
}

#[tauri::command]
async fn start_local_session(app: AppHandle, state: State<'_, AppState>) -> Result<Value, String> {
    let profile = load_local_profile(&app)?;
    let warning = save_local_session(&app)?;
    {
        state.known_services.lock().unwrap().clear();
        *state.server.lock().unwrap() = None;
        *state.token.lock().unwrap() = None;
        *state.local_mode.lock().unwrap() = true;
        *state.local_profile.lock().unwrap() = profile;
    }
    Ok(session_warning(local_user(), warning))
}

// Restore a saved session at startup. Local mode does not contact any server;
// server mode always validates its token through /v1/me.
#[tauri::command]
async fn restore_session(app: AppHandle, state: State<'_, AppState>) -> Result<Value, String> {
    let path = session_path(&app)?;
    let (server, token, warning) = match credentials::load(&path, &credentials::NativeVault)? {
        credentials::SavedSession::Local { warning } => {
            let profile = load_local_profile(&app)?;
            state.known_services.lock().unwrap().clear();
            *state.server.lock().unwrap() = None;
            *state.token.lock().unwrap() = None;
            *state.local_mode.lock().unwrap() = true;
            *state.local_profile.lock().unwrap() = profile;
            return Ok(session_warning(local_user(), warning));
        }
        credentials::SavedSession::Server {
            server,
            token,
            warning,
        } => (server, token, warning),
    };

    // Validate the token, but delete the session ONLY if the server rejects it
    // only genuine authentication failures (401/403) invalidate it. A transient network/server error (5xx, reload blip)
    // MUST NOT sign the user out, otherwise a simple reload could erase a valid session.
    let res = HTTP
        .clone()
        .get(format!("{server}/v1/me"))
        .bearer_auth(&token)
        .header(reqwest::header::USER_AGENT, API_UA)
        .send()
        .await;
    match res {
        Ok(r) if r.status().is_success() => {
            let me: Value = http_security::json(r)
                .await
                .map_err(|e| format!("Unable to parse /v1/me response: {e}"))?;
            let local_profile = load_local_profile(&app)?;
            if !me.is_object() {
                return Err("Account response is invalid".into());
            }
            state.known_services.lock().unwrap().clear();
            *state.server.lock().unwrap() = Some(server);
            *state.token.lock().unwrap() = Some(token);
            *state.local_mode.lock().unwrap() = false;
            *state.local_profile.lock().unwrap() = local_profile;
            Ok(session_warning(me, warning))
        }
        Ok(r) if r.status().as_u16() == 401 || r.status().as_u16() == 403 => {
            // Genuinely invalid or expired token: clear the session.
            credentials::clear(&path, &credentials::NativeVault).map_err(|error| {
                format!("expired: session rejected; credential cleanup needs attention: {error}")
            })?;
            Err("expired: session rejected by server".into())
        }
        Ok(r) => {
            // Transient server error: KEEP the session (retry in the UI).
            Err(format!(
                "transient: server unreachable (HTTP {})",
                r.status()
            ))
        }
        Err(e) => {
            // Network error: KEEP the session.
            Err(format!("transient: network unavailable ({e})"))
        }
    }
}

fn current(state: &State<'_, AppState>) -> Result<(String, String), String> {
    if is_local_mode(state) {
        return Err("Local mode is active".into());
    }
    let base = state.server.lock().unwrap().clone();
    let token = state.token.lock().unwrap().clone();
    match (base, token) {
        (Some(b), Some(t)) => Ok((b, t)),
        _ => Err("Not signed in".into()),
    }
}

fn merge_server_and_local_services(server: Value, local: Value) -> Value {
    let mut server_services = server.as_array().cloned().unwrap_or_default();
    let local_services = local.as_array().cloned().unwrap_or_default();
    let known_ids = server_services
        .iter()
        .filter_map(|service| service.get("id").and_then(Value::as_str))
        .map(str::to_string)
        .collect::<HashSet<_>>();
    let max_order = server_services
        .iter()
        .filter_map(|service| service.get("order").and_then(Value::as_i64))
        .max()
        .unwrap_or(-1);
    for (index, mut service) in local_services.into_iter().enumerate() {
        let Some(id) = service.get("id").and_then(Value::as_str) else {
            continue;
        };
        if known_ids.contains(id) {
            continue;
        }
        service["order"] = Value::from(max_order + 1 + index as i64);
        service["isLocalRecipe"] = Value::Bool(true);
        server_services.push(service);
    }
    Value::Array(server_services)
}

fn remember_services(state: &AppState, services: &Value) -> Result<(), String> {
    let services = services
        .as_array()
        .ok_or("Service response must be an array")?;
    let mut ids = HashSet::new();
    let mut storage_ids = HashSet::new();
    for service in services {
        let id = service
            .get("id")
            .and_then(Value::as_str)
            .ok_or("Service response has no string id")?;
        storage_security::validate_service_id(id)?;
        if !ids.insert(id.to_string()) || !storage_ids.insert(id.to_ascii_lowercase()) {
            return Err("Service response contains duplicate identifiers".into());
        }
    }
    state.known_services.lock().unwrap().extend(ids);
    Ok(())
}

fn require_known_service(state: &AppState, id: &str) -> Result<(), String> {
    storage_security::validate_service_id(id)?;
    if state.known_services.lock().unwrap().contains(id)
        || state
            .local_profile
            .lock()
            .unwrap()
            .services_value()
            .as_array()
            .is_some_and(|services| {
                services
                    .iter()
                    .any(|service| service.get("id").and_then(Value::as_str) == Some(id))
            })
    {
        Ok(())
    } else {
        Err("Service is not registered in this session".into())
    }
}

#[tauri::command]
async fn get_services(state: State<'_, AppState>) -> Result<Value, String> {
    if is_local_mode(&state) {
        let services = state.local_profile.lock().unwrap().services_value();
        remember_services(&state, &services)?;
        return Ok(services);
    }
    let local = state
        .local_profile
        .lock()
        .unwrap()
        .local_recipe_services_value();
    let (base, token) = current(&state)?;
    let server = api_get(&base, &token, "/v1/me/services").await?;
    remember_services(&state, &server)?;
    Ok(merge_server_and_local_services(server, local))
}

#[tauri::command]
async fn get_workspaces(state: State<'_, AppState>) -> Result<Value, String> {
    if is_local_mode(&state) {
        return Ok(state.local_profile.lock().unwrap().workspaces_value());
    }
    let (base, token) = current(&state)?;
    api_get(&base, &token, "/v1/workspace").await
}

// --- Recipes and URL resolution -----------------------------------------

// Retrieve a recipe package.json (disk-cached) from the ferdium-recipes repository.
// Open a URL in the system's default browser outside the app. The caller filters the scheme.
// Windows uses ShellExecuteW directly so opening a link never flashes a cmd.exe console window.
#[cfg(target_os = "windows")]
#[link(name = "shell32")]
unsafe extern "system" {
    fn ShellExecuteW(
        hwnd: *mut std::ffi::c_void,
        operation: *const u16,
        file: *const u16,
        parameters: *const u16,
        directory: *const u16,
        show_command: i32,
    ) -> isize;
}

fn open_external(url: &str) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg(url)
            .spawn()
            .map(|_| ())
            .map_err(|error| format!("Unable to open external URL through macOS: {error}"))
    }
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::ffi::OsStrExt;

        let operation: Vec<u16> = std::ffi::OsStr::new("open")
            .encode_wide()
            .chain(std::iter::once(0))
            .collect();
        let file: Vec<u16> = std::ffi::OsStr::new(url)
            .encode_wide()
            .chain(std::iter::once(0))
            .collect();
        let result = unsafe {
            ShellExecuteW(
                std::ptr::null_mut(),
                operation.as_ptr(),
                file.as_ptr(),
                std::ptr::null(),
                std::ptr::null(),
                1,
            )
        };
        if result <= 32 {
            Err(format!(
                "Unable to open external URL through the Windows shell (code {result})"
            ))
        } else {
            Ok(())
        }
    }
    #[cfg(all(target_os = "linux", feature = "flatpak"))]
    {
        flatpak_portal::open_uri(url)
    }
    #[cfg(all(
        target_os = "linux",
        any(
            feature = "native-distribution",
            feature = "nix",
            feature = "system-package"
        ),
        not(feature = "flatpak")
    ))]
    {
        // Native Linux retains the ordinary host launcher path. Flatpak builds compile this
        // branch out entirely and use org.freedesktop.portal.OpenURI instead.
        match std::process::Command::new("xdg-open").arg(url).spawn() {
            Ok(_) => Ok(()),
            Err(xdg_error) => std::process::Command::new("gio")
                .arg("open")
                .arg(url)
                .spawn()
                .map(|_| ())
                .map_err(|gio_error| {
                    format!(
                        "Unable to open external URL on Linux: xdg-open failed ({xdg_error}); gio open failed ({gio_error})"
                    )
                }),
        }
    }
    #[cfg(all(unix, not(target_os = "macos"), not(target_os = "linux")))]
    {
        std::process::Command::new("xdg-open")
            .arg(url)
            .spawn()
            .map(|_| ())
            .map_err(|error| format!("Unable to open external URL: {error}"))
    }
}

#[tauri::command]
fn open_external_url(url: String) -> Result<(), String> {
    let parsed = Url::parse(&url).map_err(|error| format!("Invalid external URL: {error}"))?;
    if !matches!(parsed.scheme(), "http" | "https") {
        return Err("External links must use HTTP or HTTPS".to_string());
    }
    open_external(parsed.as_str())
}

fn show_system_notification(
    app: &AppHandle,
    title: &str,
    body: Option<&str>,
) -> Result<(), String> {
    // `app` is used by the native notification plugin; Flatpak notifications go directly
    // through the portal and deliberately do not initialize that plugin.
    let _ = app;
    #[cfg(all(
        any(
            feature = "native-distribution",
            all(target_os = "linux", any(feature = "nix", feature = "system-package"))
        ),
        not(feature = "flatpak")
    ))]
    {
        let builder = app.notification().builder().title(title);
        let builder = if let Some(body) = body.filter(|body| !body.is_empty()) {
            builder.body(body)
        } else {
            builder
        };
        builder
            .show()
            .map_err(|error| format!("Unable to show system notification: {error}"))
    }
    #[cfg(all(target_os = "linux", feature = "flatpak"))]
    {
        flatpak_portal::add_notification(title, body)
    }
    #[cfg(all(not(target_os = "linux"), feature = "flatpak"))]
    {
        let _ = (app, title, body);
        Err("Flatpak distribution mode is supported only on Linux".to_string())
    }
}

#[derive(serde::Deserialize)]
#[serde(rename_all = "camelCase")]
struct ServiceIconRequest {
    service_id: String,
    recipe_id: String,
    custom_url: Option<String>,
    team: Option<String>,
    #[serde(default)]
    prefer_website_icon: bool,
}

#[tauri::command]
async fn get_service_icon(
    app: AppHandle,
    state: State<'_, AppState>,
    request: ServiceIconRequest,
    force: bool,
) -> Result<Option<String>, String> {
    validate_recipe_id(&request.recipe_id)?;
    if request.service_id.trim().is_empty() {
        return Err("Service icon request is missing a service id".into());
    }
    let app_data = app
        .path()
        .app_data_dir()
        .map_err(|error| error.to_string())?;
    let cfg = recipe_config(&app, &app_data, &request.recipe_id).await?;
    let templates =
        service_custom_url_template_values(&state.settings.lock().unwrap(), &request.service_id);
    let page_url = resolve_url(
        &cfg,
        request.custom_url.as_deref(),
        request.team.as_deref(),
        &templates,
    )?;
    let should_fetch = request.prefer_website_icon;
    let result = icons::cached_or_fetch(
        &app,
        &HTTP,
        &request.service_id,
        &page_url,
        force,
        should_fetch,
    )
    .await;
    match &result {
        Ok(icons::ServiceIconLoad::Fetched(_)) => audit::best_effort(
            &app,
            "info",
            "service-icon",
            if force { "refetch" } else { "fetch" },
            "success",
            if force {
                "Website icon refetched and cached"
            } else {
                "Website icon fetched and cached"
            },
            serde_json::json!({ "serviceId": request.service_id, "recipeId": request.recipe_id }),
        ),
        Err(error) if force => audit::best_effort(
            &app,
            "warning",
            "service-icon",
            "refetch",
            "failure",
            "Website icon refetch failed",
            serde_json::json!({ "serviceId": request.service_id, "recipeId": request.recipe_id, "error": error }),
        ),
        _ => {}
    }
    result.map(icons::ServiceIconLoad::icon)
}

#[tauri::command]
fn copy_service_icon_cache(
    app: AppHandle,
    source_service_id: String,
    target_service_id: String,
) -> Result<(), String> {
    icons::copy_cached(&app, &source_service_id, &target_service_id)
}

#[tauri::command]
async fn fetch_workspace_icon_url(url: String) -> Result<String, String> {
    icons::fetch_workspace_icon_url(&HTTP, &url).await
}

#[tauri::command]
async fn fetch_service_icon_url(
    app: AppHandle,
    service_id: String,
    url: String,
) -> Result<String, String> {
    if service_id.trim().is_empty() {
        return Err("Custom service icon request is missing a service id".into());
    }

    let result = icons::fetch_service_icon_url(&app, &HTTP, &service_id, &url).await;
    match &result {
        Ok(_) => audit::best_effort(
            &app,
            "info",
            "service-icon",
            "custom-source",
            "success",
            "Custom service icon fetched and cached",
            serde_json::json!({ "serviceId": service_id }),
        ),
        Err(error) => audit::best_effort(
            &app,
            "warning",
            "service-icon",
            "custom-source",
            "failure",
            "Custom service icon source failed; default icon fallback selected",
            serde_json::json!({ "serviceId": service_id, "error": error }),
        ),
    }
    result
}

fn recipe_cache_directory(app: &AppHandle) -> Result<PathBuf, String> {
    app.path()
        .app_cache_dir()
        .map(|dir| recipe_source::cache_directory(&dir))
        .map_err(|error| format!("Recipe cache directory unavailable: {error}"))
}

fn recipe_catalog_cache_path(app: &AppHandle) -> Result<PathBuf, String> {
    recipe_cache_directory(app).map(|dir| dir.join("catalog.json"))
}

fn cached_recipe_catalog(app: &AppHandle) -> Option<Value> {
    let path = recipe_catalog_cache_path(app).ok()?;
    let app_data = app.path().app_data_dir().ok()?;
    let text = recipe_source::read_cache_with_legacy(
        &path,
        &recipe_source::legacy_cache_directory(&app_data).join("catalog.json"),
        http_security::MAX_API_BYTES,
    )?;
    let value = serde_json::from_str::<Value>(&text).ok()?;
    value.as_array().filter(|recipes| !recipes.is_empty())?;
    Some(value)
}

fn recipe_display_name(recipe_id: &str) -> String {
    recipe_id
        .split(['-', '_'])
        .filter(|part| !part.is_empty())
        .map(|part| {
            let mut chars = part.chars();
            match chars.next() {
                Some(first) => first.to_uppercase().collect::<String>() + chars.as_str(),
                None => String::new(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

async fn local_recipe_catalog(app: &AppHandle) -> Result<Value, String> {
    // Remote discovery is best-effort. Bundled and custom recipes remain available offline.
    let remote = match HTTP
        .clone()
        .get(recipe_source::catalog_url())
        .header(reqwest::header::USER_AGENT, API_UA)
        .header(reqwest::header::ACCEPT, "application/vnd.github+json")
        .send()
        .await
    {
        Ok(response) if response.status().is_success() => {
            match http_security::json::<Value>(response).await {
                Ok(listing) => {
                    let recipes = listing
                        .as_array()
                        .into_iter()
                        .flatten()
                        .filter(|entry| entry.get("type").and_then(Value::as_str) == Some("dir"))
                        .filter_map(|entry| entry.get("name").and_then(Value::as_str))
                        .filter(|recipe_id| validate_recipe_id(recipe_id).is_ok())
                        .map(|recipe_id| {
                            serde_json::json!({
                                "id": recipe_id,
                                "name": recipe_display_name(recipe_id),
                                "icons": {
                                    "svg": recipe_source::asset_url(recipe_id, "icon.svg")
                                }
                            })
                        })
                        .collect::<Vec<_>>();
                    let catalog = Value::Array(recipes);
                    if let Ok(path) = recipe_catalog_cache_path(app) {
                        if let Some(parent) = path.parent() {
                            let _ = std::fs::create_dir_all(parent);
                        }
                        let _ = write_atomic(&path, &catalog.to_string());
                    }
                    Some(catalog)
                }
                Err(_) => cached_recipe_catalog(app),
            }
        }
        _ => cached_recipe_catalog(app),
    };

    recipes::merge_catalog(app, remote)
}

// Complete recipe catalog: Ferdium server in connected mode, GitHub in local mode.
#[tauri::command]
async fn list_recipes(app: AppHandle, state: State<'_, AppState>) -> Result<Value, String> {
    if is_local_mode(&state) {
        return local_recipe_catalog(&app).await;
    }
    let remote = match current(&state) {
        Ok((base, token)) => match HTTP
            .clone()
            .get(format!("{base}/v1/recipes"))
            .bearer_auth(&token)
            .header(reqwest::header::USER_AGENT, API_UA)
            .send()
            .await
        {
            Ok(response) if response.status().is_success() => {
                http_security::json::<Value>(response).await.ok()
            }
            _ => None,
        },
        Err(_) => None,
    };
    recipes::merge_catalog(&app, remote)
}

#[tauri::command]
fn get_recipe_storage_info(app: AppHandle) -> Result<recipes::RecipeStorageInfo, String> {
    recipes::storage_info(&app)
}

#[tauri::command]
fn save_custom_recipe(app: AppHandle, draft: RecipeDraft) -> Result<Value, String> {
    recipes::save_custom_recipe(&app, draft)
}

#[tauri::command]
fn import_custom_recipe(
    app: AppHandle,
    path: String,
    trusted_code: Option<bool>,
) -> Result<Value, String> {
    if trusted_code != Some(true) {
        return Err(
            "Review and explicitly trust the recipe's executable code before importing".into(),
        );
    }
    recipes::import_custom_recipe(&app, Path::new(&path))
}

// --- Workspaces -----------------------------------------------------------

#[tauri::command]
async fn create_workspace(
    app: AppHandle,
    state: State<'_, AppState>,
    name: String,
) -> Result<Value, String> {
    if is_local_mode(&state) {
        let mut profile = state.local_profile.lock().unwrap();
        let mut next = profile.clone();
        let workspace = next.create_workspace(name);
        save_local_profile(&app, &next)?;
        *profile = next;
        return Ok(workspace);
    }
    let (base, token) = current(&state)?;
    let res = HTTP
        .clone()
        .post(format!("{base}/v1/workspace"))
        .bearer_auth(&token)
        .header(reqwest::header::USER_AGENT, API_UA)
        .json(&serde_json::json!({ "name": name }))
        .send()
        .await
        .map_err(|e| e.to_string())?;
    if !res.status().is_success() {
        return Err(format!("Workspace creation failed: HTTP {}", res.status()));
    }
    http_security::json(res).await
}

#[tauri::command]
async fn update_workspace(
    app: AppHandle,
    state: State<'_, AppState>,
    workspace_id: String,
    name: String,
    services: Vec<String>,
) -> Result<Value, String> {
    if is_local_mode(&state) {
        let mut profile = state.local_profile.lock().unwrap();
        let mut next = profile.clone();
        let workspace = next.update_workspace(&workspace_id, name, services)?;
        save_local_profile(&app, &next)?;
        *profile = next;
        return Ok(workspace);
    }
    let (base, token) = current(&state)?;
    let res = HTTP
        .clone()
        .put(format!("{base}/v1/workspace/{workspace_id}"))
        .bearer_auth(&token)
        .header(reqwest::header::USER_AGENT, API_UA)
        .json(&serde_json::json!({ "name": name, "services": services }))
        .send()
        .await
        .map_err(|e| e.to_string())?;
    if !res.status().is_success() {
        return Err(format!("Workspace update failed: HTTP {}", res.status()));
    }
    http_security::json(res).await
}

#[tauri::command]
async fn delete_workspace(
    app: AppHandle,
    state: State<'_, AppState>,
    workspace_id: String,
) -> Result<(), String> {
    if is_local_mode(&state) {
        let mut profile = state.local_profile.lock().unwrap();
        let mut next = profile.clone();
        next.delete_workspace(&workspace_id)?;
        save_local_profile(&app, &next)?;
        *profile = next;
        return Ok(());
    }
    let (base, token) = current(&state)?;
    let res = HTTP
        .clone()
        .delete(format!("{base}/v1/workspace/{workspace_id}"))
        .bearer_auth(&token)
        .header(reqwest::header::USER_AGENT, API_UA)
        .send()
        .await
        .map_err(|e| e.to_string())?;
    if !res.status().is_success() {
        return Err(format!("Workspace deletion failed: HTTP {}", res.status()));
    }
    Ok(())
}

#[tauri::command]
async fn logout(app: AppHandle, state: State<'_, AppState>) -> Result<(), String> {
    state.known_services.lock().unwrap().clear();
    *state.server.lock().unwrap() = None;
    *state.token.lock().unwrap() = None;
    *state.local_mode.lock().unwrap() = false;
    *state.local_profile.lock().unwrap() = LocalProfile::default();
    clear_session(&app)
}

// Reposition the active webview over the service area (called on resize).
fn reposition_active(app: &AppHandle) {
    if let Err(error) = window_chrome::layout(app) {
        startup_diagnostics::log("primary", "titlebar.layout.error", &error);
    }
    let st = app.state::<AppState>();
    let active = st.active.lock().unwrap().clone();
    let Some(sid) = active else {
        download_toast::reposition(app);
        return;
    };
    let sw = *st.sidebar_w.lock().unwrap();
    let Some(win) = app.get_window("main") else {
        return;
    };
    if let Ok((pos, size)) = service_rect(&win, sw) {
        if let Some(wv) = app.get_webview(&format!("svc-{sid}")) {
            let _ = wv.set_position(pos);
            let _ = wv.set_size(size);
        }
    }
    // Service bounds can remap native GTK child windows. Raise the toast only
    // after those service allocations, including late root-content resizing.
    download_toast::reposition(app);
}

// --- App settings (app_settings.json) ------------------------------------

#[tauri::command]
fn get_distribution_info() -> distribution::DistributionInfo {
    distribution::info()
}

#[tauri::command]
fn sync_services_menu(app: AppHandle, services: Vec<NativeServiceMenuEntry>) -> Result<(), String> {
    let service_ids: Vec<String> = services.iter().map(|service| service.id.clone()).collect();
    validate_order_ids(&service_ids, "Native service menu")?;
    let menu = build_native_application_menu(&app, &services)
        .map_err(|error| format!("Unable to build native application menu: {error}"))?;
    app.set_menu(menu)
        .map_err(|error| format!("Unable to install native application menu: {error}"))?;
    window_chrome::keep_menu_unified(&app)?;
    Ok(())
}

#[tauri::command]
fn export_backup(
    app: AppHandle,
    state: State<'_, AppState>,
    path: String,
) -> Result<backup::BackupSummary, String> {
    let operation = (|| -> Result<backup::BackupSummary, String> {
        let app_settings = effective_app_settings_value(&app);
        let local_profile = serde_json::to_value(state.local_profile.lock().unwrap().clone())
            .map_err(|error| format!("Unable to serialize local profile for backup: {error}"))?;
        let custom_recipes = recipes::backup_custom_recipes(&app)?;
        let document = backup::BackupDocument::new(
            env!("CARGO_PKG_VERSION"),
            app_settings,
            local_profile,
            custom_recipes,
        );
        backup::save(Path::new(&path), &document)
    })();
    match operation {
        Ok(summary) => {
            audit::best_effort(
                &app,
                "info",
                "backup",
                "export",
                "success",
                "Manual backup exported and integrity verified",
                serde_json::json!({ "path": path, "schema": summary.schema }),
            );
            Ok(summary)
        }
        Err(error) => {
            audit::best_effort(
                &app,
                "error",
                "backup",
                "export",
                "failure",
                error.clone(),
                serde_json::json!({ "path": path }),
            );
            Err(error)
        }
    }
}

fn automatic_backup_root(app: &AppHandle, settings: &Value) -> Result<PathBuf, String> {
    // Flatpak scheduled backups stay in sandbox-private storage. A directory selected through
    // FileChooser/Documents is not assumed to grant permanent recursive access across restarts.
    if !distribution::is_flatpak() {
        let configured = settings
            .get("automaticBackupDirectory")
            .and_then(Value::as_str)
            .map(str::trim)
            .unwrap_or_default();
        if !configured.is_empty() {
            return Ok(PathBuf::from(configured));
        }
    }
    app.path()
        .app_config_dir()
        .map(|root| root.join("backups").join("automatic"))
        .map_err(|error| format!("Tauridium configuration directory unavailable: {error}"))
}

fn parse_automatic_backup_number(value: &str) -> Option<u32> {
    if value.is_empty() || !value.bytes().all(|byte| byte.is_ascii_digit()) {
        return None;
    }
    value.parse::<u32>().ok()
}

fn is_leap_year(year: u32) -> bool {
    year.is_multiple_of(4) && (!year.is_multiple_of(100) || year.is_multiple_of(400))
}

fn days_in_month(year: u32, month: u32) -> Option<u32> {
    match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => Some(31),
        4 | 6 | 9 | 11 => Some(30),
        2 if is_leap_year(year) => Some(29),
        2 => Some(28),
        _ => None,
    }
}

fn validate_automatic_backup_filename(filename: &str) -> Result<(), String> {
    const PREFIX: &str = "tauridium-auto-backup-";
    const SUFFIX: &str = ".json";
    let stamp = filename
        .strip_prefix(PREFIX)
        .and_then(|value| value.strip_suffix(SUFFIX))
        .ok_or_else(|| "Automatic backup filename is invalid".to_string())?;
    if stamp.len() != 21
        || !stamp.is_ascii()
        || stamp.as_bytes().get(4) != Some(&b'-')
        || stamp.as_bytes().get(7) != Some(&b'-')
        || stamp.as_bytes().get(10) != Some(&b'-')
        || stamp.as_bytes().get(17) != Some(&b'-')
    {
        return Err("Automatic backup filename is invalid".into());
    }

    let year = parse_automatic_backup_number(&stamp[0..4]);
    let month = parse_automatic_backup_number(&stamp[5..7]);
    let day = parse_automatic_backup_number(&stamp[8..10]);
    let hour = parse_automatic_backup_number(&stamp[11..13]);
    let minute = parse_automatic_backup_number(&stamp[13..15]);
    let second = parse_automatic_backup_number(&stamp[15..17]);
    let millis = parse_automatic_backup_number(&stamp[18..21]);
    let valid = match (year, month, day, hour, minute, second, millis) {
        (
            Some(year),
            Some(month),
            Some(day),
            Some(hour),
            Some(minute),
            Some(second),
            Some(millis),
        ) => {
            year >= 1
                && days_in_month(year, month).is_some_and(|limit| (1..=limit).contains(&day))
                && hour <= 23
                && minute <= 59
                && second <= 59
                && millis <= 999
        }
        _ => false,
    };
    if valid {
        Ok(())
    } else {
        Err("Automatic backup filename is invalid".into())
    }
}

fn prune_automatic_backups(
    root: &Path,
    mode: backup::RetentionMode,
    retention: usize,
    max_age_days: u64,
    protected_path: &Path,
) -> Result<usize, String> {
    let candidates = std::fs::read_dir(root)
        .map_err(|error| format!("Unable to read automatic backup directory: {error}"))?
        .filter_map(Result::ok)
        .filter(|entry| entry.file_type().is_ok_and(|kind| kind.is_file()))
        .filter(|entry| {
            entry
                .file_name()
                .to_str()
                .is_some_and(|name| validate_automatic_backup_filename(name).is_ok())
        })
        .filter_map(|entry| {
            let modified = entry.metadata().ok()?.modified().ok()?;
            Some(backup::RetentionCandidate {
                path: entry.path(),
                modified,
            })
        })
        .collect::<Vec<_>>();
    let expired = backup::retention_paths_to_delete(
        candidates,
        mode,
        retention,
        max_age_days,
        SystemTime::now(),
        Some(protected_path),
    );
    let count = expired.len();
    for path in expired {
        std::fs::remove_file(&path).map_err(|error| {
            format!(
                "Unable to remove expired automatic backup {}: {error}",
                path.display()
            )
        })?;
    }
    Ok(count)
}

#[tauri::command]
fn create_automatic_backup(
    app: AppHandle,
    state: State<'_, AppState>,
    filename: String,
) -> Result<backup::BackupSummary, String> {
    let operation = (|| -> Result<backup::BackupSummary, String> {
        validate_automatic_backup_filename(&filename)?;
        let app_settings = effective_app_settings_value(&app);
        let retention = app_settings
            .get("automaticBackupRetention")
            .and_then(Value::as_u64)
            .unwrap_or(10)
            .clamp(1, 365) as usize;
        let max_age_days = app_settings
            .get("automaticBackupMaxAgeDays")
            .and_then(Value::as_u64)
            .unwrap_or(90)
            .clamp(1, 3650);
        let retention_mode = backup::RetentionMode::parse(
            app_settings
                .get("automaticBackupRetentionMode")
                .and_then(Value::as_str)
                .unwrap_or("count"),
        )?;
        let root = automatic_backup_root(&app, &app_settings)?;
        std::fs::create_dir_all(&root)
            .map_err(|error| format!("Unable to create automatic backup directory: {error}"))?;
        let path = root.join(&filename);
        let local_profile = serde_json::to_value(state.local_profile.lock().unwrap().clone())
            .map_err(|error| format!("Unable to serialize local profile for backup: {error}"))?;
        let custom_recipes = recipes::backup_custom_recipes(&app)?;
        let document = backup::BackupDocument::new(
            env!("CARGO_PKG_VERSION"),
            app_settings,
            local_profile,
            custom_recipes,
        );
        let mut summary = backup::save(&path, &document)?;
        match prune_automatic_backups(&root, retention_mode, retention, max_age_days, &path) {
            Ok(removed) => {
                audit::best_effort(
                    &app,
                    "info",
                    "backup",
                    "retention",
                    "success",
                    format!("Automatic backup retention removed {removed} expired backup(s)"),
                    serde_json::json!({ "mode": format!("{retention_mode:?}"), "removed": removed }),
                );
            }
            Err(error) => {
                let warning = format!(
                    "Backup was created and verified, but retention cleanup failed: {error}"
                );
                audit::best_effort(
                    &app,
                    "warning",
                    "backup",
                    "retention",
                    "warning",
                    warning.clone(),
                    serde_json::json!({ "directory": root }),
                );
                summary = summary.with_warning(warning);
            }
        }
        Ok(summary)
    })();
    match operation {
        Ok(summary) => {
            audit::best_effort(
                &app,
                if summary.warnings.is_empty() {
                    "info"
                } else {
                    "warning"
                },
                "backup",
                "automatic",
                if summary.warnings.is_empty() {
                    "success"
                } else {
                    "warning"
                },
                "Automatic backup created and integrity verified",
                serde_json::json!({ "path": &summary.path, "warnings": &summary.warnings }),
            );
            Ok(summary)
        }
        Err(error) => {
            audit::best_effort(
                &app,
                "error",
                "backup",
                "automatic",
                "failure",
                error.clone(),
                serde_json::json!({ "filename": filename }),
            );
            Err(error)
        }
    }
}

fn restore_recovery_backup_path(app: &AppHandle) -> Result<PathBuf, String> {
    let root = app
        .path()
        .app_config_dir()
        .map_err(|error| format!("Tauridium configuration directory unavailable: {error}"))?;
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    Ok(root
        .join("backups")
        .join(format!("pre-restore-{stamp}.json")))
}

fn perform_restore_backup(
    app: &AppHandle,
    state: &AppState,
    path: &Path,
) -> Result<backup::BackupSummary, String> {
    let document = backup::load(path)?;
    let _settings_write = state.settings_write.lock().unwrap();

    // Phase 1: validate and prepare every owned component before the first mutation.
    let app_settings = merge_app_settings_value(&document.app_settings())?;
    let local_profile = LocalProfile::from_value(document.local_profile())?;
    recipes::validate_custom_recipe_backups(document.custom_recipes())?;
    let previous_settings = effective_app_settings_value(app);
    let previous_profile = state.local_profile.lock().unwrap().clone();
    let previous_recipes = recipes::backup_custom_recipes(app)?;
    let restored_recipes =
        recipes::merge_custom_recipe_backups(&previous_recipes, document.custom_recipes())?;

    // Create and verify the pre-restore recovery point before any persistent mutation.
    let recovery_path = restore_recovery_backup_path(app)?;
    let previous_profile_value = serde_json::to_value(previous_profile.clone())
        .map_err(|error| format!("Unable to serialize pre-restore local profile: {error}"))?;
    let recovery_document = backup::BackupDocument::new(
        env!("CARGO_PKG_VERSION"),
        previous_settings.clone(),
        previous_profile_value,
        previous_recipes.clone(),
    );
    backup::save(&recovery_path, &recovery_document)
        .map_err(|error| format!("Unable to create pre-restore safety backup: {error}"))?;

    // Phase 2: commit Tauridium-owned files. Autostart is an external OS integration and is
    // deliberately applied only after this transaction succeeds, so a missing Windows startup
    // entry can never roll back otherwise-valid backup data.
    let commit = (|| -> Result<(), String> {
        recipes::replace_custom_recipes_exact(app, &restored_recipes)?;
        save_local_profile(app, &local_profile)?;
        persist_app_settings(app, state, &app_settings)?;
        Ok(())
    })();

    if let Err(error) = commit {
        let mut rollback_errors = Vec::new();
        if let Err(rollback) = recipes::replace_custom_recipes_exact(app, &previous_recipes) {
            rollback_errors.push(format!("recipes: {rollback}"));
        }
        if let Err(rollback) = save_local_profile(app, &previous_profile) {
            rollback_errors.push(format!("local profile: {rollback}"));
        }
        if let Err(rollback) = persist_app_settings(app, state, &previous_settings) {
            rollback_errors.push(format!("app settings: {rollback}"));
        }
        *state.local_profile.lock().unwrap() = previous_profile;
        if rollback_errors.is_empty() {
            return Err(format!(
                "Backup restore failed and the previous Tauridium state was restored: {error}"
            ));
        }
        return Err(format!(
            "Backup restore failed: {error}. Rollback also reported: {}",
            rollback_errors.join("; ")
        ));
    }

    *state.local_profile.lock().unwrap() = local_profile;
    let mut summary = document
        .summary(path)
        .with_recovery_backup_path(&recovery_path);
    match apply_autostart_setting(app, &app_settings) {
        Ok(actual) => {
            if app_settings.get("autostart").and_then(Value::as_bool) != Some(actual) {
                let mut corrected = app_settings.clone();
                if let Some(object) = corrected.as_object_mut() {
                    object.insert("autostart".into(), Value::Bool(actual));
                }
                if let Err(error) = persist_app_settings(app, state, &corrected) {
                    summary = summary.with_warning(format!(
                        "Backup data restored, but Tauridium could not persist the autostart state returned by the operating system: {error}"
                    ));
                } else {
                    summary = summary.with_warning(
                        "The operating system did not grant the requested Launch at Login state; Tauridium stored the effective state instead."
                            .to_string(),
                    );
                }
            }
        }
        Err(error) => {
            summary = summary.with_warning(format!(
                "Backup data restored successfully, but the operating-system autostart integration could not be synchronized: {error}"
            ));
        }
    }
    Ok(summary)
}

#[tauri::command]
fn restore_backup(
    app: AppHandle,
    state: State<'_, AppState>,
    path: String,
) -> Result<backup::BackupSummary, String> {
    let operation = perform_restore_backup(&app, &state, Path::new(&path));
    match operation {
        Ok(summary) => {
            audit::best_effort(
                &app,
                if summary.warnings.is_empty() {
                    "info"
                } else {
                    "warning"
                },
                "backup",
                "restore",
                if summary.warnings.is_empty() {
                    "success"
                } else {
                    "warning"
                },
                "Backup restore completed",
                serde_json::json!({
                    "path": path,
                    "recoveryBackupPath": &summary.recovery_backup_path,
                    "warnings": &summary.warnings
                }),
            );
            Ok(summary)
        }
        Err(error) => {
            audit::best_effort(
                &app,
                "error",
                "backup",
                "restore",
                "failure",
                error.clone(),
                serde_json::json!({ "path": path }),
            );
            Err(error)
        }
    }
}

#[tauri::command]
fn export_portable_bundle(
    app: AppHandle,
    path: String,
    kind: String,
    payload: portable::PortablePayload,
) -> Result<portable::PortableSummary, String> {
    let operation = (|| -> Result<portable::PortableSummary, String> {
        let custom_recipes = recipes::backup_custom_recipes(&app)?;
        portable::save(
            Path::new(&path),
            env!("CARGO_PKG_VERSION"),
            &kind,
            payload,
            &custom_recipes,
        )
    })();
    match operation {
        Ok(summary) => {
            audit::best_effort(
                &app,
                "info",
                "export",
                "portable",
                "success",
                format!("Exported portable Tauridium {} bundle", summary.kind),
                serde_json::json!({ "path": path, "kind": &summary.kind }),
            );
            Ok(summary)
        }
        Err(error) => {
            audit::best_effort(
                &app,
                "error",
                "export",
                "portable",
                "failure",
                error.clone(),
                serde_json::json!({ "path": path, "kind": kind }),
            );
            Err(error)
        }
    }
}

#[tauri::command]
fn export_service_bundle(
    app: AppHandle,
    state: State<'_, AppState>,
    path: String,
    request: service_export::ServiceExportRequest,
) -> Result<service_export::ServiceExportSummary, String> {
    let operation = (|| -> Result<service_export::ServiceExportSummary, String> {
        let custom_recipes = recipes::backup_custom_recipes(&app)?;
        let local_services = state
            .local_profile
            .lock()
            .unwrap()
            .local_recipe_services_value();
        let local_services = local_services.as_array().cloned().unwrap_or_default();
        service_export::save(
            &app,
            Path::new(&path),
            env!("CARGO_PKG_VERSION"),
            request,
            &custom_recipes,
            &local_services,
        )
    })();
    match operation {
        Ok(summary) => {
            audit::best_effort(
                &app,
                "info",
                "export",
                "services",
                "success",
                "Exported Tauridium service bundle",
                serde_json::json!({
                    "path": path,
                    "serviceCount": summary.service_count,
                    "portableRecipeCount": summary.portable_recipe_count,
                    "serviceIconCount": summary.service_icon_count,
                    "includeAllPersonalRecipes": summary.include_all_personal_recipes,
                    "archiveSha256": summary.archive_sha256,
                }),
            );
            Ok(summary)
        }
        Err(error) => {
            audit::best_effort(
                &app,
                "error",
                "export",
                "services",
                "failure",
                error.clone(),
                serde_json::json!({ "path": path }),
            );
            Err(error)
        }
    }
}

#[cfg(all(feature = "native-distribution", not(feature = "flatpak")))]
#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct NativeUpdateInfo {
    version: String,
    body: Option<String>,
    date: Option<String>,
}

#[cfg(all(feature = "native-distribution", not(feature = "flatpak")))]
#[tauri::command]
async fn check_native_update(app: AppHandle) -> Result<Option<NativeUpdateInfo>, String> {
    let updater = app
        .updater()
        .map_err(|error| format!("Unable to initialize updater: {error}"))?;
    let update = updater
        .check()
        .await
        .map_err(|error| format!("Unable to check for updates: {error}"))?;
    Ok(update.map(|update| NativeUpdateInfo {
        version: update.version,
        body: update.body,
        date: update.date.map(|date| date.to_string()),
    }))
}

#[cfg(all(feature = "native-distribution", not(feature = "flatpak")))]
#[tauri::command]
async fn install_native_update(app: AppHandle, expected_version: String) -> Result<(), String> {
    let update = app
        .updater()
        .map_err(|error| format!("Unable to initialize updater: {error}"))?
        .check()
        .await
        .map_err(|error| format!("Unable to check for updates before installation: {error}"))?
        .ok_or_else(|| "No update is currently available".to_string())?;
    if update.version != expected_version {
        return Err(format!(
            "Available update changed from {expected_version} to {}; check again before installing",
            update.version
        ));
    }
    update
        .download_and_install(|_, _| {}, || {})
        .await
        .map_err(|error| format!("Unable to download or install update: {error}"))?;
    app.restart();
}

#[tauri::command]
fn record_updater_error(app: AppHandle, action: String, message: String) -> Result<(), String> {
    let action = action.trim();
    if !matches!(action, "check" | "install") {
        return Err("Unsupported updater audit action".into());
    }
    let message = message.trim();
    if message.is_empty() {
        return Err("Updater audit message must not be empty".into());
    }
    let message = message.chars().take(4096).collect::<String>();
    audit::record(
        &app,
        "error",
        "updater",
        action,
        "failure",
        format!("Update {action} failed: {message}"),
        serde_json::json!({ "applicationVersion": env!("CARGO_PKG_VERSION") }),
    )
}

#[tauri::command]
fn get_audit_log(app: AppHandle, limit: Option<usize>) -> Result<Vec<audit::AuditEntry>, String> {
    audit::read(&app, limit.unwrap_or(500).clamp(1, 10_000))
}

#[tauri::command]
fn get_audit_log_page(
    app: AppHandle,
    cursor: Option<String>,
    limit: Option<usize>,
) -> Result<audit::AuditLogPage, String> {
    audit::read_page(
        &app,
        cursor.as_deref(),
        limit
            .unwrap_or(audit::AUDIT_PAGE_DEFAULT)
            .clamp(1, audit::AUDIT_PAGE_MAX),
    )
}

#[tauri::command]
fn export_audit_log(app: AppHandle, path: String) -> Result<usize, String> {
    let count = audit::export(&app, Path::new(&path))?;
    audit::best_effort(
        &app,
        "info",
        "audit",
        "export",
        "success",
        format!("Exported {count} audit event(s)"),
        serde_json::json!({ "path": path, "count": count }),
    );
    Ok(count)
}

#[tauri::command]
fn clear_audit_log(app: AppHandle) -> Result<(), String> {
    audit::clear(&app)?;
    audit::record(
        &app,
        "warning",
        "audit",
        "clear",
        "success",
        "Audit history was cleared by the user",
        serde_json::json!({}),
    )
}

fn persisted_window_state_flags() -> StateFlags {
    StateFlags::SIZE | StateFlags::POSITION | StateFlags::MAXIMIZED | StateFlags::FULLSCREEN
}

fn save_main_window_state(app: &AppHandle) {
    if let Err(error) = app.save_window_state(persisted_window_state_flags()) {
        eprintln!("Unable to save Tauridium window state: {error}");
    }
}

fn reveal_main_window_after_startup_restore(app: &AppHandle, start_minimized: bool) {
    startup_diagnostics::log(
        "primary",
        "window.startup_visibility",
        &format!("start_minimized={start_minimized}"),
    );
    if let Some(window) = app.get_window("main") {
        // The window-state plugin restores the hidden main window exactly once from its
        // on_window_ready hook. Replaying restore_state here causes a second maximized/fullscreen
        // transition on Windows 11; only reveal the already-restored window.
        if !start_minimized {
            if let Err(error) = window.show() {
                startup_diagnostics::log(
                    "primary",
                    "window.startup_show_error",
                    &error.to_string(),
                );
            }
            if let Err(error) = window.set_focus() {
                startup_diagnostics::log(
                    "primary",
                    "window.startup_focus_error",
                    &error.to_string(),
                );
            }
        }
    } else {
        startup_diagnostics::log(
            "primary",
            "window.startup_missing",
            "main window was unavailable during startup visibility restoration",
        );
    }
}

fn show_main(app: &AppHandle) {
    #[cfg(windows)]
    if let Err(error) = show_existing_main_window(app) {
        startup_diagnostics::log("primary", "window.show_main_error", &error);
    }

    #[cfg(not(windows))]
    if let Some(w) = app.get_window("main") {
        // Hiding a live window does not discard its geometry/window mode. Restoring again before
        // every tray/menu reveal can replay maximized/fullscreen transitions on Windows.
        let _ = w.show();
        let _ = w.set_focus();
    }
}

#[cfg(not(target_os = "linux"))]
fn toggle_main(app: &AppHandle) {
    if let Some(w) = app.get_window("main") {
        if w.is_visible().unwrap_or(false) {
            save_main_window_state(app);
            let _ = w.hide();
        } else {
            show_main(app);
        }
    }
}

// Open/close devtools on the active service webview for debugging, then reapply the layout.
fn toggle_devtools(app: &AppHandle) {
    // Available in release builds through Tauri's `devtools` feature (see Cargo.toml).
    let active = app.state::<AppState>().active.lock().unwrap().clone();
    if let Some(sid) = active {
        if let Some(wv) = app.get_webview(&format!("svc-{sid}")) {
            #[cfg(target_os = "windows")]
            wv.open_devtools();
            #[cfg(not(target_os = "windows"))]
            if wv.is_devtools_open() {
                wv.close_devtools();
            } else {
                wv.open_devtools();
            }
        }
    }
    reposition_active(app);
}

// Reload the active service webview, equivalent to Ferdium's Reload service action.
fn reload_active_service(app: &AppHandle) {
    let active = app.state::<AppState>().active.lock().unwrap().clone();
    if let Some(sid) = active {
        if let Some(wv) = app.get_webview(&format!("svc-{sid}")) {
            let _ = wv.reload();
        }
    }
}

// Reload the shell (the app UI), equivalent to Reload Ferdium. First hide the
// services (the shell reappears and then reselects the active service on mount).
fn reload_app(app: &AppHandle) {
    let created: Vec<String> = app
        .state::<AppState>()
        .created
        .lock()
        .unwrap()
        .iter()
        .cloned()
        .collect();
    for sid in created {
        if let Some(wv) = app.get_webview(&format!("svc-{sid}")) {
            let _ = wv.hide();
        }
    }
    if let Some(wv) = app.get_webview("main") {
        let _ = wv.reload();
    }
}

fn validate_native_title(value: &str, label: &str) -> Result<(), String> {
    if value.trim().is_empty() {
        return Err(format!("{label} must not be empty"));
    }
    if value.chars().count() > 240 || value.chars().any(char::is_control) {
        return Err(format!("{label} is invalid"));
    }
    Ok(())
}

#[tauri::command]
fn set_presentation_titles(
    app: AppHandle,
    window_title: String,
    taskbar_title: String,
) -> Result<(), String> {
    validate_native_title(&window_title, "Window title")?;
    validate_native_title(&taskbar_title, "Taskbar title")?;
    let window = app
        .get_window("main")
        .ok_or_else(|| "Main Tauridium window is unavailable".to_string())?;
    window
        .set_title(&window_title)
        .map_err(|error| format!("Unable to update Tauridium window title: {error}"))?;
    window_chrome::refresh(&app);

    // Windows taskbar buttons use the native window title, so Windows cannot expose an
    // independent taskbar-button string while retaining the native title bar. Keep the
    // separately requested taskbar/app-icon label on the independently addressable tray
    // surface; platforms that expose a separate label can still use it.
    if let Some(tray) = app.tray_by_id("main-tray") {
        #[cfg(target_os = "linux")]
        tray.set_title(Some(&taskbar_title))
            .map_err(|error| format!("Unable to update Tauridium app-icon title: {error}"))?;
        #[cfg(not(target_os = "linux"))]
        tray.set_tooltip(Some(&taskbar_title))
            .map_err(|error| format!("Unable to update Tauridium app-icon title: {error}"))?;
    }
    Ok(())
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct AppMetadata {
    name: &'static str,
    version: &'static str,
    description: &'static str,
    repository: &'static str,
    license: &'static str,
    author: &'static str,
}

#[tauri::command]
fn get_app_metadata() -> AppMetadata {
    AppMetadata {
        name: "Tauridium",
        version: env!("CARGO_PKG_VERSION"),
        description: env!("CARGO_PKG_DESCRIPTION"),
        repository: env!("CARGO_PKG_REPOSITORY"),
        license: env!("CARGO_PKG_LICENSE"),
        author: env!("CARGO_PKG_AUTHORS"),
    }
}

#[tauri::command]
fn reload_active_service_command(app: AppHandle) {
    reload_active_service(&app);
}

#[tauri::command]
fn reload_app_command(app: AppHandle) {
    reload_app(&app);
}

#[tauri::command]
fn show_service_toast_overlay(
    app: AppHandle,
    service_id: String,
    message: String,
) -> Result<(), String> {
    let message = message.trim();
    if message.is_empty() {
        return Ok(());
    }
    if message.chars().count() > 240 {
        return Err("Service overlay toast is too long".into());
    }
    let Some(webview) = app.get_webview(&format!("svc-{service_id}")) else {
        return Ok(());
    };
    let height = download_toast::visible_height(&app);
    let bottom = if height > 0.0 { height + 36.0 } else { 24.0 };
    let script = service_toast_overlay_script(message, 2600)?
        .replace("bottom:24px", &format!("bottom:{bottom}px"));
    webview
        .eval(script)
        .map_err(|error| format!("Unable to show service overlay toast: {error}"))
}

fn reposition_generic_toast(app: &AppHandle, height: f64) -> Result<(), String> {
    let active = app.state::<AppState>().active.lock().unwrap().clone();
    let Some(webview) = active.and_then(|id| app.get_webview(&format!("svc-{id}"))) else {
        return Ok(());
    };
    let bottom = if height > 0.0 { height + 36.0 } else { 24.0 };
    webview.eval(format!("(function(){{var host=document.getElementById('__tauridium-toast-overlay');if(host)host.style.setProperty('bottom','{bottom}px','important');}})();"))
        .map_err(|error| format!("Unable to position existing service feedback: {error}"))
}

#[tauri::command]
fn toggle_devtools_command(app: AppHandle) {
    toggle_devtools(&app);
}

const TAURIDIUM_BUILD_MODE: &str = env!("TAURIDIUM_BUILD_MODE");
const TAURIDIUM_TARGET: &str = env!("TAURIDIUM_TARGET");

fn write_build_info_if_requested() -> Result<bool, String> {
    let mut args = std::env::args_os().skip(1);
    while let Some(arg) = args.next() {
        if arg.as_os_str() != std::ffi::OsStr::new("--build-info-file") {
            continue;
        }
        let path = args
            .next()
            .ok_or_else(|| "--build-info-file requires an output path".to_string())?;
        let payload = serde_json::to_vec(&serde_json::json!({
            "name": "Tauridium",
            "version": env!("CARGO_PKG_VERSION"),
            "buildMode": TAURIDIUM_BUILD_MODE,
            "target": TAURIDIUM_TARGET,
            "distribution": distribution::info(),
        }))
        .map_err(|error| format!("Unable to serialize build information: {error}"))?;
        std::fs::write(PathBuf::from(path), payload)
            .map_err(|error| format!("Unable to write build information: {error}"))?;
        return Ok(true);
    }
    Ok(false)
}

fn main() {
    if let Err(error) = startup_diagnostics::initialize_from_args() {
        startup_diagnostics::report_fatal("launch", "diagnostics.initialization_error", &error);
        std::process::exit(2);
    }
    startup_diagnostics::log(
        "launch",
        "boot.begin",
        "starting Tauridium process initialization",
    );

    match write_build_info_if_requested() {
        Ok(true) => {
            startup_diagnostics::log(
                "launch",
                "build_info.completed",
                "build-information probe completed",
            );
            return;
        }
        Ok(false) => {}
        Err(error) => {
            startup_diagnostics::report_fatal("launch", "build_info.error", &error);
            std::process::exit(2);
        }
    }

    #[cfg(windows)]
    let mut windows_instance_coordinator = match windows_instance_preflight() {
        Ok(WindowsInstancePreflight::ActivatedExisting) => {
            startup_diagnostics::log(
                "secondary",
                "process.exit_secondary",
                "existing Tauridium session was activated; exiting secondary process",
            );
            return;
        }
        Ok(WindowsInstancePreflight::Primary(coordinator)) => coordinator,
        Err(error) => {
            startup_diagnostics::report_fatal("launch", "instance.preflight_error", &error);
            std::process::exit(2);
        }
    };
    #[cfg(windows)]
    if let Err(error) = windows_instance_coordinator.start_activation_listener() {
        startup_diagnostics::report_fatal("launch", "instance.listener_error", &error);
        std::process::exit(2);
    }
    #[cfg(windows)]
    let windows_activation_target = windows_instance_coordinator.activation_target();

    startup_diagnostics::log(
        "primary",
        "tauri.builder",
        &format!(
            "initializing {} distribution plugins, dialog, window-state, application state, menus, tray, and webviews",
            distribution::mode().as_str()
        ),
    );

    let builder = tauri::Builder::default();
    #[cfg(all(feature = "desktop-integration", not(feature = "flatpak")))]
    let builder =
        builder
            .plugin(tauri_plugin_notification::init())
            .plugin(tauri_plugin_autostart::init(
                tauri_plugin_autostart::MacosLauncher::LaunchAgent,
                None,
            ));
    #[cfg(all(feature = "native-distribution", not(feature = "flatpak")))]
    let builder = builder.plugin(tauri_plugin_updater::Builder::new().build());
    #[cfg(all(
        target_os = "linux",
        feature = "nix",
        not(feature = "desktop-integration"),
        not(feature = "flatpak")
    ))]
    let builder = builder.plugin(tauri_plugin_notification::init());

    builder
        .plugin(tauri_plugin_dialog::init())
        .plugin(
            tauri_plugin_window_state::Builder::new()
                .with_outer_size(cfg!(windows))
                .with_state_flags(persisted_window_state_flags())
                .with_filter(|label| label == "main")
                .with_filename("window-state.json")
                .build(),
        )
        .manage(AppState::default())
        .manage(download_toast::DownloadToastState::default())
        .manage(service_menu::ServiceMenuState::default())
        .manage(window_chrome::WindowChromeState::default())
        .setup(move |app| {
            startup_diagnostics::log("primary", "tauri.setup.begin", "Tauri setup callback entered");

            match migrate_legacy_application_identity(app.handle()) {
                Ok(migrated) => startup_diagnostics::log(
                    "primary",
                    "identity.migration",
                    &format!("completed migrated={migrated}"),
                ),
                Err(error) => {
                    startup_diagnostics::log("primary", "identity.migration_error", &error);
                    eprintln!("Unable to migrate Tauridium application data to the current application identity: {error}");
                }
            }

            // Cache app settings in memory for the poller, shutdown handling, and related logic.
            *app.state::<AppState>().settings.lock().unwrap() =
                read_app_settings_value(app.handle());
            #[cfg(windows)]
            {
                let state = app.state::<AppState>();
                *state.tracking_prevention_startup.lock().unwrap() = state.settings.lock().unwrap()
                    .get("trackingPreventionExceptions").cloned().unwrap_or_else(|| serde_json::json!({}));
            }
            startup_diagnostics::log("primary", "settings.loaded", "application settings loaded into memory");
            {
                let st = app.state::<AppState>();
                let settings = st.settings.lock().unwrap();
                let collapsed = resolve_startup_sidebar_collapsed(&settings);
                let w = if collapsed {
                    COLLAPSED_SIDEBAR_W
                } else {
                    settings
                        .get("sidebarWidth")
                        .and_then(Value::as_f64)
                        .unwrap_or(SIDEBAR_W)
                        .clamp(160.0, MAX_SIDEBAR_W)
                };
                *st.sidebar_w.lock().unwrap() = w;
            }

            let handle = app.handle().clone();
            download_toast::install_layout_hook(app.handle())?;
            #[cfg(target_os = "linux")]
            if let Some(owner) = app.get_webview("main") {
                service_menu::watch_input(&owner)?;
            }
            if let Some(win) = app.get_window("main") {
                startup_diagnostics::log("primary", "window.events", "main window event handler registered");
                win.on_window_event(move |event| match event {
                    WindowEvent::Resized(_) => { service_menu::close(&handle); reposition_active(&handle); },
                    // When focus returns (for example after closing devtools), reapply the
                    // layout because the service webview may have been resized and
                    // overlapped the sidebar.
                    WindowEvent::Focused(true) => {
                        reposition_active(&handle);
                        download_toast::refresh(&handle);
                        window_chrome::refresh(&handle);
                    },
                    WindowEvent::Focused(false) => {
                        service_menu::focus_lost(&handle);
                        download_toast::refresh(&handle);
                        window_chrome::refresh(&handle);
                    },
                    WindowEvent::ThemeChanged(_) => { service_menu::close(&handle); window_chrome::refresh(&handle); },
                    WindowEvent::ScaleFactorChanged { .. } => { service_menu::close(&handle); reposition_active(&handle); },
                    WindowEvent::CloseRequested { api, .. } => {
                        service_menu::close(&handle);
                        // Persist geometry/state before either hiding to tray or allowing a real close.
                        save_main_window_state(&handle);
                        // Close to tray: hide instead of quitting; otherwise quit.
                        let close_to_tray = !distribution::is_flatpak()
                            && handle
                                .state::<AppState>()
                                .settings
                                .lock()
                                .unwrap()
                                .get("closeToSystemTray")
                                .and_then(Value::as_bool)
                                .unwrap_or(true);
                        if close_to_tray {
                            api.prevent_close();
                            if let Some(w) = handle.get_window("main") {
                                let _ = w.hide();
                            }
                        }
                    }
                    _ => {}
                });
            }

            // Menu-bar/tray icon. Linux tray implementations do not emit tray click events
            // and do not support controlling left-click menu behavior, so Linux relies on
            // the explicit Show Tauridium / Quit menu. Other desktop platforms retain the
            // convenient left-click window toggle.
            let show = MenuItem::with_id(app, "show", "Show Tauridium", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &quit])?;
            let mut tray = TrayIconBuilder::with_id("main-tray")
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => show_main(app),
                    "quit" => {
                        save_main_window_state(app);
                        app.exit(0);
                    }
                    _ => {}
                });
            #[cfg(not(target_os = "linux"))]
            {
                tray = tray
                    .tooltip("Tauridium")
                    .show_menu_on_left_click(false)
                    .on_tray_icon_event(|tray, event| {
                        if let TrayIconEvent::Click {
                            button: MouseButton::Left,
                            button_state: MouseButtonState::Up,
                            ..
                        } = event
                        {
                            toggle_main(tray.app_handle());
                        }
                    });
            }
            #[cfg(target_os = "linux")]
            {
                let tray_cache = app.path().app_cache_dir()?.join("tray-icon");
                std::fs::create_dir_all(&tray_cache)?;
                tray = tray.temp_dir_path(tray_cache);
            }
            if let Some(icon) = app.default_window_icon().cloned() {
                tray = tray.icon(icon);
            }
            tray.build(app)?;
            startup_diagnostics::log("primary", "tray.ready", "system tray icon and menu created");

            // Native application menu: App / Edit / View / Navigate / Services / About. The Services submenu
            // starts empty and is rebuilt from the canonical ordered service list after auth.
            {
                app.set_menu(build_native_application_menu(app.handle(), &[])?)?;
                app.on_menu_event(|app, event| {
                    let id = event.id.as_ref();
                    match id {
                        "open-settings" => {
                            let state = app.state::<AppState>();
                            hide_service_webviews(app, &state);
                            show_main(app);
                            let _ = app.emit("open-settings", ());
                        }
                        "open-add-service" => {
                            let state = app.state::<AppState>();
                            hide_service_webviews(app, &state);
                            show_main(app);
                            let _ = app.emit("open-add-service", ());
                        }
                        "open-add-workspace" => {
                            let state = app.state::<AppState>();
                            hide_service_webviews(app, &state);
                            show_main(app);
                            let _ = app.emit("open-add-workspace", ());
                        }
                        "open-about" => {
                            let state = app.state::<AppState>();
                            hide_service_webviews(app, &state);
                            show_main(app);
                            let _ = app.emit("open-about", ());
                        }
                        "open-project-homepage" => { let _ = open_external(PROJECT_HOMEPAGE); },
                        "open-project-source" => { let _ = open_external(PROJECT_SOURCE_CODE); },
                        "open-author-homepage" => { let _ = open_external(AUTHOR_HOMEPAGE); },
                        "sign-out" => {
                            let state = app.state::<AppState>();
                            hide_service_webviews(app, &state);
                            show_main(app);
                            let _ = app.emit("sign-out", ());
                        }
                        "toggle-sidebar" => {
                            let _ = app.emit("shortcut-action", "toggleSidebar".to_string());
                        }
                        "toggle-devtools" => toggle_devtools(app),
                        "reload-service" => {
                            let _ = app.emit("shortcut-action", "reloadService".to_string());
                        }
                        "reload-app" => reload_app(app),
                        "shortcut:zoomIn" | "shortcut:zoomOut" | "shortcut:resetZoom" => {
                            let _ = app.emit(
                                "shortcut-action",
                                id.trim_start_matches("shortcut:").to_string(),
                            );
                        }
                        _ => {
                            if let Some(action) = id.strip_prefix("shortcut:") {
                                let state = app.state::<AppState>();
                                hide_service_webviews(app, &state);
                                show_main(app);
                                let _ = app.emit("shortcut-action", action.to_string());
                            } else if let Some(service_id) = id.strip_prefix("goto-service:") {
                                if !service_id.is_empty() {
                                    let _ = app.emit("select-service-id", service_id.to_string());
                                }
                            }
                        }
                    }
                });
            }
            startup_diagnostics::log("primary", "menu.ready", "native application menu installed");
            window_chrome::install(app.handle())?;

            // Native packages retain Tauri's notification permission flow. Flatpak builds
            // use the XDG Notification portal directly and need no plugin permission request.
            #[cfg(all(any(feature = "native-distribution", all(target_os = "linux", any(feature = "nix", feature = "system-package"))), not(feature = "flatpak")))]
            if let Ok(state) = app.notification().permission_state() {
                if state != PermissionState::Granted {
                    let _ = app.notification().request_permission();
                }
            }
            // The main window is configured hidden so fullscreen/maximized restoration happens
            // off-screen. Flatpak keeps the main window recoverable even on desktops without
            // StatusNotifier support, so start-minimized is intentionally disabled there.
            let start_minimized = !distribution::is_flatpak()
                && read_app_settings_value(app.handle())
                    .get("startMinimized")
                    .and_then(Value::as_bool)
                    .unwrap_or(false);
            reveal_main_window_after_startup_restore(app.handle(), start_minimized);

            // Bind activation only after startup visibility restoration. A repeated launch
            // arriving during setup can therefore not be shown and then hidden again by the
            // start-minimized/window-state startup path. Pending requests are completed here
            // synchronously on the UI thread before their secondary receives an ACK.
            #[cfg(windows)]
            if let Err(error) = windows_activation_target.bind(app.handle().clone()) {
                startup_diagnostics::log("primary", "activation.bind_error", &error);
                return Err(std::io::Error::other(error).into());
            }

            start_badge_poller(app.handle().clone());
            startup_diagnostics::log("primary", "tauri.setup.completed", "Tauri setup completed successfully");
            Ok(())
        })
        .invoke_handler(|invoke| {
            if !ipc_security::command_allowed(
                invoke.message.webview_ref().label(),
                invoke.message.command(),
            ) {
                invoke.resolver.reject("This renderer is not authorized to invoke application commands");
                return true;
            }
            let handler: fn(tauri::ipc::Invoke<Wry>) -> bool = tauri::generate_handler![
            login,
            start_local_session,
            restore_session,
            get_services,
            get_workspaces,
            services::lifecycle::show_service,
            services::lifecycle::preload_service,
            get_service_icon,
            copy_service_icon_cache,
            fetch_workspace_icon_url,
            fetch_service_icon_url,
            services::lifecycle::hide_all_services,
            services::lifecycle::close_service,
            services::lifecycle::set_sidebar_width,
            set_presentation_titles,
            services::lifecycle::close_services,
            logout,
            services::commands::set_service_flags,
            services::commands::update_service,
            services::commands::create_service,
            services::commands::create_custom_website_service,
            services::commands::delete_service,
            services::commands::clear_service_cache,
            services::commands::clear_sandbox,
            list_recipes,
            get_recipe_storage_info,
            save_custom_recipe,
            import_custom_recipe,
            create_workspace,
            update_workspace,
            delete_workspace,
            app_settings::get_app_settings,
            app_settings::set_service_order,
            app_settings::set_workspace_order,
            sync_services_menu,
            app_settings::set_app_settings,
            get_distribution_info,
            export_backup,
            create_automatic_backup,
            restore_backup,
            export_portable_bundle,
            export_service_bundle,
            record_updater_error,
            #[cfg(all(feature = "native-distribution", not(feature = "flatpak")))]
            check_native_update,
            #[cfg(all(feature = "native-distribution", not(feature = "flatpak")))]
            install_native_update,
            get_audit_log,
            get_audit_log_page,
            export_audit_log,
            clear_audit_log,
            open_external_url,
            get_app_metadata,
            get_window_chrome,
            open_window_menu,
            focus_window_content,
            reload_active_service_command,
            reload_app_command,
            show_service_toast_overlay,
            service_menu::prepare_service_menu,
            service_menu::present_service_menu,
            service_menu::close_service_menu,
            service_menu::get_service_menu,
            service_menu::measure_service_menu,
            service_menu::dismiss_service_menu,
            service_menu::choose_service_menu,
            download_toast::get_download_toast,
            download_toast::dismiss_download_toast,
            download_toast::resize_download_toast,
            app_settings::set_service_zoom,
            toggle_devtools_command
            ];
            handler(invoke)
        })
        .build(tauri::generate_context!())
        .expect("failed to launch the Tauri application")
        .run(|_app, _event| {
            // Clicking the dock icon on macOS shows the window again.
            // RunEvent::Reopen exists only on macOS, so gate it to compile elsewhere.
            #[cfg(target_os = "macos")]
            if let RunEvent::Reopen { .. } = _event {
                show_main(_app);
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn unsafe_and_unknown_services_cannot_reach_cache_deletion() {
        let state = AppState::default();
        assert!(require_known_service(&state, "service-a").is_err());
        assert!(remember_services(&state, &json!([{ "id": "/tmp/canary" }])).is_err());
        assert!(remember_services(
            &state,
            &json!([{ "id": "service-a" }, { "id": "service-a" }])
        )
        .is_err());
        assert!(state.known_services.lock().unwrap().is_empty());
        remember_services(&state, &json!([{ "id": "service-a" }])).unwrap();
        assert!(require_known_service(&state, "service-a").is_ok());
        assert!(require_known_service(&state, "../service-a").is_err());
        let profile =
            json!({ "version": 1, "services": [{ "id": "/tmp/canary" }], "workspaces": [] });
        assert!(LocalProfile::from_value(profile).is_err());
    }

    fn identity_migration_test_root() -> PathBuf {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("test clock must be after the Unix epoch")
            .as_nanos();
        std::env::temp_dir().join(format!(
            "tauridium-identity-migration-{}-{unique}",
            std::process::id()
        ))
    }

    #[test]
    fn feature_0500_identity_migration_preserves_existing_profile_data() {
        let root = identity_migration_test_root();
        let legacy = root.join("legacy.tauridium");
        let current = root.join("dev.brani.tauridium");
        let nested = legacy.join("recipes").join("custom");

        std::fs::create_dir_all(&nested).unwrap();
        std::fs::write(legacy.join("app_settings.json"), b"{\"theme\":\"dark\"}\n").unwrap();
        std::fs::write(nested.join("recipe.json"), b"{}\n").unwrap();

        assert_eq!(identity_directory_suffix(&current), ".tauridium");
        assert_eq!(
            identity_directory_suffix(Path::new("dev.brani.tauridium.dev")),
            ".tauridium.dev"
        );
        assert_eq!(legacy_identity_candidate(&current).unwrap(), Some(legacy));
        assert!(migrate_identity_directory(&current).unwrap());
        assert_eq!(
            std::fs::read_to_string(current.join("app_settings.json")).unwrap(),
            "{\"theme\":\"dark\"}\n"
        );
        assert_eq!(
            std::fs::read_to_string(current.join("recipes/custom/recipe.json")).unwrap(),
            "{}\n"
        );
        assert!(current.join(IDENTITY_MIGRATION_MARKER).exists());
        assert!(!migrate_identity_directory(&current).unwrap());

        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn patch_0504_native_shortcut_accelerators_canonicalize_default_punctuation() {
        assert_eq!(
            native_menu_accelerator("Ctrl+,"),
            Some("Ctrl+Comma".to_string())
        );
        assert_eq!(
            native_menu_accelerator("Ctrl+Shift+Tab"),
            Some("Ctrl+Shift+Tab".to_string())
        );
        assert_eq!(native_menu_accelerator("Ctrl+K Ctrl+S"), None);
    }

    #[test]
    fn persisted_window_state_tracks_geometry_without_visibility() {
        let flags = persisted_window_state_flags();
        assert!(flags.contains(StateFlags::SIZE));
        assert!(flags.contains(StateFlags::POSITION));
        assert!(flags.contains(StateFlags::MAXIMIZED));
        assert!(flags.contains(StateFlags::FULLSCREEN));
        assert!(!flags.contains(StateFlags::VISIBLE));
        assert!(!flags.contains(StateFlags::DECORATIONS));
    }

    #[test]
    fn canonical_order_validation_rejects_empty_duplicate_and_excessive_ids() {
        assert!(validate_order_ids(&["a".into(), "b".into()], "Service").is_ok());
        assert!(validate_order_ids(&["".into()], "Service").is_err());
        assert!(validate_order_ids(&["a".into(), "a".into()], "Service").is_err());
        assert!(validate_order_ids(&vec!["id".into(); 10_001], "Service").is_err());
    }

    #[test]
    fn automatic_backup_filenames_require_exact_generated_timestamp_shape() {
        for valid in [
            "tauridium-auto-backup-2026-08-19-001122-003.json",
            "tauridium-auto-backup-2024-02-29-235959-999.json",
        ] {
            assert!(validate_automatic_backup_filename(valid).is_ok(), "{valid}");
        }
        for invalid in [
            "../tauridium-auto-backup-2026-08-19-001122-003.json",
            "tauridium-auto-backup-2026-08-19-001122-003.json.bak",
            "tauridium-auto-backup-2026-08-19-001122.json",
            "tauridium-auto-backup-2026-8-19-001122-003.json",
            "tauridium-auto-backup-2026-02-29-001122-003.json",
            "tauridium-auto-backup-2026-13-01-001122-003.json",
            "tauridium-auto-backup-2026-08-32-001122-003.json",
            "tauridium-auto-backup-2026-08-19-241122-003.json",
            "tauridium-auto-backup-2026-08-19-006022-003.json",
            "tauridium-auto-backup-2026-08-19-001160-003.json",
            "tauridium-auto-backup-0000-01-01-000000-000.json",
            "tauridium-auto-backup-x/evil.json",
            "backup.json",
        ] {
            assert!(
                validate_automatic_backup_filename(invalid).is_err(),
                "unexpectedly accepted {invalid}"
            );
        }
    }

    #[test]
    fn automatic_backup_filename_unicode_never_panics_in_any_timestamp_segment() {
        let valid = "2026-10-16-001122-003";
        for (begin, end) in [(0, 4), (5, 7), (8, 10), (11, 17), (18, 21)] {
            for character in [
                '\u{e9}',
                '\u{20ac}',
                '\u{1f642}',
                '\u{4e2d}',
                '\u{df}',
                '\u{202e}',
            ] {
                for index in begin..end {
                    let next = index + character.len_utf8();
                    if next > end {
                        continue;
                    }
                    let stamp = format!("{}{}{}", &valid[..index], character, &valid[next..]);
                    assert_eq!(stamp.len(), 21);
                    let name = format!("tauridium-auto-backup-{stamp}.json");
                    assert!(validate_automatic_backup_filename(&name).is_err());
                }
            }
        }
    }

    #[test]
    fn automatic_backup_retention_preserves_malformed_names_and_unrelated_files() {
        let root = identity_migration_test_root();
        std::fs::create_dir(&root).unwrap();
        let protected = root.join("tauridium-auto-backup-2026-10-16-001122-003.json");
        let unrelated = root.join("unrelated.json");
        let unicode = root.join("tauridium-auto-backup-2026-10-16-0€00-001.json");
        for path in [&protected, &unrelated, &unicode] {
            std::fs::write(path, b"Harmless synthetic retention canary").unwrap();
        }
        assert_eq!(
            prune_automatic_backups(&root, backup::RetentionMode::Count, 1, 90, &protected)
                .unwrap(),
            0
        );
        for path in [&protected, &unrelated, &unicode] {
            assert!(path.is_file());
            std::fs::remove_file(path).unwrap();
        }
        std::fs::remove_dir(root).unwrap();
    }

    #[test]
    fn password_hash_is_base64_of_sha256() {
        // sha256("password") encoded as base64 (see ferdium-app UserApi.ts).
        assert_eq!(
            ferdium_password_hash("password"),
            "XohImNooBHFR0OVvjcYpJ3NgPQ1qq73WKhHvch0VQtg="
        );
        // 32 bytes become 44 base64 characters regardless of input.
        assert_eq!(ferdium_password_hash("").len(), 44);
        assert_eq!(ferdium_password_hash("\u{e9}&@ 123").len(), 44);
    }

    #[test]
    fn normalize_server_trims_and_strips_trailing_slashes() {
        assert_eq!(
            normalize_server("  https://api.ferdium.org/  "),
            "https://api.ferdium.org"
        );
        assert_eq!(normalize_server("https://x.y"), "https://x.y");
        assert_eq!(normalize_server("https://x.y///"), "https://x.y");
    }

    #[test]
    fn server_services_merge_only_distinct_local_recipe_services_after_server_order() {
        let server = json!([
            { "id": "server-a", "order": 4, "name": "Server A" },
            { "id": "same", "order": 7, "name": "Server copy" }
        ]);
        let local = json!([
            { "id": "local-a", "order": 0, "name": "Local A" },
            { "id": "same", "order": 0, "name": "Local duplicate" }
        ]);

        let merged = merge_server_and_local_services(server, local);
        let services = merged.as_array().unwrap();
        assert_eq!(services.len(), 3);
        assert_eq!(services[2]["id"], "local-a");
        assert_eq!(services[2]["order"], 8);
        assert_eq!(services[2]["isLocalRecipe"], true);
    }
}
