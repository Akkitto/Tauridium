#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod audit;
mod backup;
mod icons;
mod local_profile;
mod portable;
mod recipes;

// Tauridium — lightweight Ferdium client (Tauri v2).
//
// Phase 1: connect to the Ferdium server (JWT login, services, workspaces).
// Phase 2: render each service in an ISOLATED child webview overlaid on
//           the area to the right of the sidebar. Isolation uses
//           `data_store_identifier` = the 16 bytes of the service UUID
//           (data_directory is ignored by WKWebView on macOS; see Phase 0).

use base64::Engine;
use local_profile::{validate_recipe_id, LocalProfile};
use recipes::RecipeDraft;
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::sync::{
    atomic::{AtomicU64, Ordering},
    LazyLock, Mutex,
};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::menu::{IsMenuItem, Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::webview::{
    DownloadEvent, NewWindowFeatures, NewWindowResponse, PageLoadEvent, WebviewBuilder,
};
#[cfg(target_os = "macos")]
use tauri::RunEvent;
use tauri::{
    AppHandle, Emitter, LogicalPosition, LogicalSize, Manager, State, Url, WebviewUrl, WindowEvent,
    Wry,
};
use tauri_plugin_autostart::ManagerExt;
use tauri_plugin_notification::{NotificationExt, PermissionState};
use tauri_plugin_window_state::{AppHandleExt as _, StateFlags};

// Shared HTTP client with connection pooling AND timeouts: without a timeout, a server
// that accepts a connection but never responds can hang login/show_service indefinitely.
static HTTP: LazyLock<reqwest::Client> = LazyLock::new(|| {
    reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(10))
        .timeout(Duration::from_secs(20))
        .build()
        .unwrap_or_default()
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
// Modern Safari UA WITH the `Version/` token: WhatsApp requires Safari >= 15, while the webview
// Native WKWebView does not always expose this token (which can trigger an unsupported-browser warning). Keep
// a Safari identity rather than Chrome to avoid breaking services that depend on the Safari path
// (for example Synology Chat, which breaks with a Chrome UA). Per-recipe overrides can come later.
const SERVICE_UA: &str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15";

// Versionless Chrome UA for sensitive Google hosts (login, Gmail,
// Google Chat); works around Google's unsupported-browser check (adapted from ferx).
const GOOGLE_CHROMELESS_UA: &str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari/537.36";

// Google compatibility shim (spoof userAgentData / window.chrome / plugins / vendor, etc.) injected into
// non-sensitive Google services. Defensive by design (try/catch throughout). Adapted from ferx.
const GOOGLE_AUTH_COMPAT_JS: &str = r#"(function() {
  document.addEventListener('securitypolicyviolation', function(e) {
    if (e.blockedURI && (e.blockedURI.indexOf('ipc:') !== -1 || e.blockedURI.indexOf('tauri:') !== -1)) { e.stopImmediatePropagation(); }
  }, true);
  try { Object.defineProperty(navigator, 'vendor', { get: function() { return 'Google Inc.'; }, configurable: true }); } catch(_) {}
  try { Object.defineProperty(navigator, 'webdriver', { get: function() { return false; }, configurable: true }); } catch(_) {}
  try { Object.defineProperty(navigator, 'pdfViewerEnabled', { get: function() { return true; }, configurable: true }); } catch(_) {}
  var pluginNames = ['PDF Viewer','Chrome PDF Viewer','Chromium PDF Viewer','Microsoft Edge PDF Viewer','WebKit built-in PDF'];
  var fakePlugins = { length: pluginNames.length, item: function(i) { return this[i] || null; }, namedItem: function(n) { for (var i = 0; i < this.length; i++) { if (this[i] && this[i].name === n) return this[i]; } return null; }, refresh: function() {} };
  for (var i = 0; i < pluginNames.length; i++) fakePlugins[i] = Object.freeze({ name: pluginNames[i], filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 1 });
  try { Object.defineProperty(navigator, 'plugins', { get: function() { return fakePlugins; }, configurable: true }); } catch(_) {}
  if (!window.chrome) {
    try { Object.defineProperty(window, 'chrome', { value: { app: { isInstalled: false }, runtime: {}, csi: function(){return {};}, loadTimes: function(){return {};} }, writable: true, configurable: true }); } catch(_) {}
  }
  if (!navigator.userAgentData) {
    var isMac = !(navigator.platform && navigator.platform.startsWith('Win'));
    var brands = Object.freeze([ Object.freeze({ brand: 'Google Chrome', version: '135' }), Object.freeze({ brand: 'Not-A.Brand', version: '8' }), Object.freeze({ brand: 'Chromium', version: '135' }) ]);
    try { Object.defineProperty(navigator, 'userAgentData', { value: Object.freeze({ brands: brands, mobile: false, platform: isMac ? 'macOS' : 'Windows', getHighEntropyValues: function() { return Promise.resolve({ brands: brands, mobile: false, platform: isMac ? 'macOS' : 'Windows', platformVersion: isMac ? '15.0.0' : '10.0.0', architecture: isMac ? 'arm' : 'x86', model: '', uaFullVersion: '135.0.0.0', fullVersionList: [{ brand: 'Google Chrome', version: '135.0.0.0' }, { brand: 'Chromium', version: '135.0.0.0' }] }); }, toJSON: function() { return { brands: brands, mobile: false, platform: isMac ? 'macOS' : 'Windows' }; } }), configurable: true, enumerable: true }); } catch(_) {}
  }
})();"#;

fn host_matches(host: &str, domain: &str) -> bool {
    host == domain || host.ends_with(&format!(".{domain}"))
}

// Sensitive Google hosts (login/Gmail/Chat) use the versionless Chrome UA.
fn is_google_auth_host(host: &str) -> bool {
    [
        "gmail.com",
        "googlemail.com",
        "mail.google.com",
        "chat.google.com",
        "accounts.google.com",
    ]
    .iter()
    .any(|d| host_matches(host, d))
}

// Generic Google services receive the compatibility script.
fn is_google_host(host: &str) -> bool {
    ["google.com", "gmail.com", "youtube.com", "googlevideo.com"]
        .iter()
        .any(|d| host_matches(host, d))
}

#[derive(Default)]
struct AppState {
    server: Mutex<Option<String>>,
    token: Mutex<Option<String>>,
    local_mode: Mutex<bool>,
    local_profile: Mutex<LocalProfile>,
    created: Mutex<HashSet<String>>, // service IDs for webviews already created
    active: Mutex<Option<String>>,   // service ID currently displayed
    unread: Mutex<HashMap<String, i64>>, // unread count per service (for the dock badge)
    flags: Mutex<HashMap<String, ServiceFlags>>, // per-service settings (notification/mute/badge)
    settings: Mutex<Value>,          // app settings cache (read by the poller, etc.)
    settings_write: Mutex<()>,       // serializes app-settings read/modify/write transactions
    sidebar_w: Mutex<f64>,           // sidebar width (initialized during setup, default 240)
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
        &[&project_homepage, &project_source, &author_homepage],
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
}

impl Default for ServiceFlags {
    fn default() -> Self {
        // Defaults: notifications and badge enabled, not muted (matching Ferdium).
        ServiceFlags {
            notif: true,
            muted: false,
            badge: true,
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

// Replace a file written to a temporary path. Unix can replace the target directly;
// Windows requires an intermediate step when the target already exists. The backup can restore the
// last version if the second rename fails.
pub(crate) fn replace_file(tmp: &Path, path: &Path) -> std::io::Result<()> {
    #[cfg(not(windows))]
    {
        std::fs::rename(tmp, path)
    }

    #[cfg(windows)]
    {
        if !path.exists() {
            return std::fs::rename(tmp, path);
        }

        let backup = path.with_extension("bak");
        if backup.exists() {
            std::fs::remove_file(&backup)?;
        }
        std::fs::rename(path, &backup)?;
        match std::fs::rename(tmp, path) {
            Ok(()) => {
                let _ = std::fs::remove_file(backup);
                Ok(())
            }
            Err(error) => {
                let _ = std::fs::rename(&backup, path);
                Err(error)
            }
        }
    }
}

// Atomic write: write .tmp, then replace. Prevents a truncated file if the app crashes
// during the write (otherwise session.json / app_settings.json could become unreadable).
pub(crate) fn write_atomic(path: &Path, contents: &str) -> std::io::Result<()> {
    let tmp = path.with_extension("tmp");
    std::fs::write(&tmp, contents)?;
    replace_file(&tmp, path)
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
    res.json()
        .await
        .map_err(|e| format!("Unable to parse response from {path}: {e}"))
}

// Persist the session in app_data_dir/session.json (permissions 600).
// macOS Keychain hardening is planned for the signed build (Phase 4).
fn save_session(app: &AppHandle, server: &str, token: &str) {
    let Ok(dir) = app.path().app_data_dir() else {
        return;
    };
    let _ = std::fs::create_dir_all(&dir);
    let path = dir.join("session.json");
    let data =
        serde_json::json!({ "mode": "server", "server": server, "token": token }).to_string();
    if write_atomic(&path, &data).is_ok() {
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let _ = std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600));
        }
    }
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

fn save_local_session(app: &AppHandle) -> Result<(), String> {
    let dir = app
        .path()
        .app_data_dir()
        .map_err(|error| error.to_string())?;
    std::fs::create_dir_all(&dir).map_err(|error| error.to_string())?;
    let path = dir.join("session.json");
    let data = serde_json::json!({ "mode": "local", "version": 1 }).to_string();
    write_atomic(&path, &data).map_err(|error| error.to_string())?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))
            .map_err(|error| error.to_string())?;
    }
    Ok(())
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

fn clear_session(app: &AppHandle) {
    if let Ok(dir) = app.path().app_data_dir() {
        let session = dir.join("session.json");
        let _ = std::fs::remove_file(&session);
        let _ = std::fs::remove_file(session.with_extension("bak"));
        let _ = std::fs::remove_file(session.with_extension("tmp"));
    }
}

#[tauri::command]
async fn login(
    app: AppHandle,
    state: State<'_, AppState>,
    server: String,
    email: String,
    password: String,
) -> Result<Value, String> {
    let base = normalize_server(&server);
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
            let body = res.text().await.unwrap_or_default();
            return Err(format!("Credentials rejected. {body}"));
        }
        return Err(format!("transient: server error (HTTP {status})"));
    }

    let body: Value = res
        .json()
        .await
        .map_err(|e| format!("Unable to parse login response: {e}"))?;
    let token = body
        .get("token")
        .and_then(Value::as_str)
        .ok_or("Login response did not contain a token")?
        .to_string();

    {
        let local_profile = load_local_profile(&app)?;
        *state.server.lock().unwrap() = Some(base.clone());
        *state.token.lock().unwrap() = Some(token.clone());
        *state.local_mode.lock().unwrap() = false;
        *state.local_profile.lock().unwrap() = local_profile;
    }
    save_session(&app, &base, &token);
    api_get(&base, &token, "/v1/me").await
}

#[tauri::command]
fn start_local_session(app: AppHandle, state: State<'_, AppState>) -> Result<Value, String> {
    let profile = load_local_profile(&app)?;
    save_local_session(&app)?;
    {
        *state.server.lock().unwrap() = None;
        *state.token.lock().unwrap() = None;
        *state.local_mode.lock().unwrap() = true;
        *state.local_profile.lock().unwrap() = profile;
    }
    Ok(local_user())
}

// Restore a saved session at startup. Local mode does not contact any server;
// server mode always validates its token through /v1/me.
#[tauri::command]
async fn restore_session(app: AppHandle, state: State<'_, AppState>) -> Result<Value, String> {
    let dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    let path = dir.join("session.json");
    let text = read_persistent(&path).map_err(|_| "No saved session".to_string())?;
    let v: Value = serde_json::from_str(&text).map_err(|e| e.to_string())?;
    if v.get("mode").and_then(Value::as_str) == Some("local") {
        let profile = load_local_profile(&app)?;
        *state.server.lock().unwrap() = None;
        *state.token.lock().unwrap() = None;
        *state.local_mode.lock().unwrap() = true;
        *state.local_profile.lock().unwrap() = profile;
        return Ok(local_user());
    }
    let server = v
        .get("server")
        .and_then(Value::as_str)
        .ok_or("Invalid session")?
        .to_string();
    let token = v
        .get("token")
        .and_then(Value::as_str)
        .ok_or("Invalid session")?
        .to_string();

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
            let me: Value = r
                .json()
                .await
                .map_err(|e| format!("Unable to parse /v1/me response: {e}"))?;
            let local_profile = load_local_profile(&app)?;
            *state.server.lock().unwrap() = Some(server);
            *state.token.lock().unwrap() = Some(token);
            *state.local_mode.lock().unwrap() = false;
            *state.local_profile.lock().unwrap() = local_profile;
            Ok(me)
        }
        Ok(r) if r.status().as_u16() == 401 || r.status().as_u16() == 403 => {
            // Genuinely invalid or expired token: clear the session.
            let _ = std::fs::remove_file(&path);
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

#[tauri::command]
async fn get_services(state: State<'_, AppState>) -> Result<Value, String> {
    if is_local_mode(&state) {
        return Ok(state.local_profile.lock().unwrap().services_value());
    }
    let local = state
        .local_profile
        .lock()
        .unwrap()
        .local_recipe_services_value();
    let (base, token) = current(&state)?;
    let server = api_get(&base, &token, "/v1/me/services").await?;
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
async fn recipe_config(app: &AppHandle, app_data: &Path, recipe_id: &str) -> Result<Value, String> {
    validate_recipe_id(recipe_id)?;
    if let Some(local) = recipes::local_recipe_config(app, recipe_id)? {
        return Ok(local);
    }

    let dir = app_data.join("recipes");
    let _ = std::fs::create_dir_all(&dir);
    let cache = dir.join(format!("{recipe_id}.json"));

    if let Ok(text) = std::fs::read_to_string(&cache) {
        if let Ok(v) = serde_json::from_str::<Value>(&text) {
            return Ok(v);
        }
    }

    let url = format!(
        "https://raw.githubusercontent.com/ferdium/ferdium-recipes/main/recipes/{recipe_id}/package.json"
    );
    let res = HTTP
        .clone()
        .get(&url)
        .header(reqwest::header::USER_AGENT, API_UA)
        .send()
        .await
        .map_err(|e| format!("Recipe {recipe_id} download failed: {e}"))?;
    if !res.status().is_success() {
        return Err(format!(
            "Recipe {recipe_id} not found (HTTP {})",
            res.status()
        ));
    }
    let text = res
        .text()
        .await
        .map_err(|e| format!("Unable to parse recipe {recipe_id}: {e}"))?;
    let _ = write_atomic(&cache, &text);
    serde_json::from_str(&text).map_err(|e| format!("Invalid package.json for {recipe_id}: {e}"))
}

fn ensure_scheme(u: &str) -> String {
    if u.starts_with("http://") || u.starts_with("https://") {
        u.to_string()
    } else {
        format!("https://{u}")
    }
}

// Replicate the `url` getter from ferdium-app's Service model.
#[derive(Clone, Debug, Default)]
struct CustomUrlTemplateValues {
    enabled: bool,
    custom_id_1: String,
    custom_id_2: String,
}

fn service_custom_url_template_values(
    settings: &Value,
    service_id: &str,
) -> CustomUrlTemplateValues {
    let global = settings
        .get("customUrlTemplatesEnabled")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let entry = settings
        .get("serviceCustomUrlTemplates")
        .and_then(Value::as_object)
        .and_then(|entries| entries.get(service_id))
        .and_then(Value::as_object);
    CustomUrlTemplateValues {
        enabled: global
            || entry
                .and_then(|value| value.get("enabled"))
                .and_then(Value::as_bool)
                .unwrap_or(false),
        custom_id_1: entry
            .and_then(|value| value.get("customId1"))
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        custom_id_2: entry
            .and_then(|value| value.get("customId2"))
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
    }
}

fn apply_custom_url_templates(
    url: &str,
    values: &CustomUrlTemplateValues,
) -> Result<String, String> {
    if !values.enabled {
        return Ok(url.to_string());
    }
    let mut resolved = url.to_string();
    for (placeholder, value, label) in [
        ("{{custom_id_1}}", values.custom_id_1.trim(), "custom ID 1"),
        ("{{custom_id_2}}", values.custom_id_2.trim(), "custom ID 2"),
    ] {
        if resolved.contains(placeholder) {
            if value.is_empty() {
                return Err(format!(
                    "Custom URL uses {placeholder} but {label} is empty"
                ));
            }
            resolved = resolved.replace(placeholder, value);
        }
    }
    if resolved.contains("{{custom_id_") {
        return Err("Custom URL contains an unsupported custom ID placeholder".into());
    }
    Ok(resolved)
}

fn resolve_url(
    cfg: &Value,
    custom_url: Option<&str>,
    team: Option<&str>,
    templates: &CustomUrlTemplateValues,
) -> Result<String, String> {
    let config = cfg.get("config").ok_or("Recipe has no config block")?;
    let service_url = config
        .get("serviceURL")
        .and_then(Value::as_str)
        .unwrap_or("");
    let has_custom = config
        .get("hasCustomUrl")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let has_team = config
        .get("hasTeamId")
        .and_then(Value::as_bool)
        .unwrap_or(false);

    if has_custom {
        if let Some(u) = custom_url.map(str::trim).filter(|u| !u.is_empty()) {
            let mut resolved = ensure_scheme(u);
            if has_team {
                if let Some(t) = team.map(str::trim).filter(|t| !t.is_empty()) {
                    resolved = resolved.replace("{teamId}", t);
                }
            }
            return apply_custom_url_templates(&resolved, templates);
        }
    }
    if has_team {
        if let Some(t) = team.map(str::trim).filter(|t| !t.is_empty()) {
            let team_url = config
                .get("teamURL")
                .and_then(Value::as_str)
                .filter(|value| !value.is_empty())
                .unwrap_or(service_url);
            return Ok(team_url.replace("{teamId}", t));
        }
    }
    if service_url.is_empty() {
        return Err("Recipe has no serviceURL".into());
    }
    Ok(service_url.to_string())
}

// --- Recipe runtime (webview.js -> unread counts) -------------------------

// Minimal `Ferdium` API shim exposed to recipe webview.js files. It executes the
// recipe DOM-scraping code; `setBadge` updates window.__pakeUnread (read by the
// poller). injectCSS/notifications can come later; everything is wrapped in try/catch
// so an incompatible recipe can never break the page.
// Dark Reader (vendored standalone UMD build), injected per service when dark mode
// is enabled so the page is actually darkened (previously the option had no local effect).
const DARK_READER_JS: &str = include_str!("../assets/darkreader.js");

// Per-service Dark Reader options (defaults aligned with the UI: 100/90/10).
#[derive(Clone, Copy)]
struct DarkOpts {
    brightness: i64,
    contrast: i64,
    sepia: i64,
}

// Dark-mode settings received from the frontend (via showService/preloadService).
#[derive(serde::Deserialize)]
struct DarkSettings {
    enabled: bool,
    brightness: Option<i64>,
    contrast: Option<i64>,
    sepia: Option<i64>,
}

impl DarkSettings {
    fn into_opts(self) -> Option<DarkOpts> {
        if !self.enabled {
            return None;
        }
        Some(DarkOpts {
            brightness: self.brightness.unwrap_or(100),
            contrast: self.contrast.unwrap_or(90),
            sepia: self.sepia.unwrap_or(10),
        })
    }
}

// Dark Reader activation script: load the library, then apply the dark theme.
fn dark_reader_init(o: DarkOpts) -> String {
    format!(
        "{DARK_READER_JS}\ntry{{DarkReader.enable({{brightness:{},contrast:{},sepia:{}}});}}catch(e){{}}",
        o.brightness, o.contrast, o.sepia
    )
}

const RECIPE_PREAMBLE: &str = r#"(function(){
  try {
    var module = { exports: {} };
    var exports = module.exports;
    var __dirname = '';
    function require(m){ if(m==='path') return { join: function(){ return Array.prototype.slice.call(arguments).join('/'); } }; return {}; }
    var Ferdium = {
      setBadge: function(direct, indirect){ var d=parseInt(direct,10)||0, i=parseInt(indirect,10)||0; window.__pakeUnread = Math.max(0, d+i); },
      safeParseInt: function(v){ var n=parseInt(v,10); return isNaN(n)?0:n; },
      injectCSS: function(){}, injectJSUnsafe: function(){},
      setDialogTitle: function(){}, handleDarkMode: function(){},
      loop: function(cb){ try{cb();}catch(e){} setInterval(function(){ try{cb();}catch(e){} }, 1000); }
    };
    window.Ferdium = Ferdium;
"#;
const RECIPE_SUFFIX: &str = r#"
    if (typeof module.exports === 'function') module.exports(Ferdium, {});
  } catch(e){ console.warn('[pakeFerdium] recipe runtime error', e); }
})();"#;

// Retrieve and cache a recipe's webview.js; return None if it has none.
async fn recipe_webview_js(app: &AppHandle, app_data: &Path, recipe_id: &str) -> Option<String> {
    if validate_recipe_id(recipe_id).is_err() {
        return None;
    }
    if let Some(local) = recipes::local_webview_js(app, recipe_id) {
        return Some(local);
    }
    if recipes::local_recipe_config(app, recipe_id)
        .ok()
        .flatten()
        .is_some()
    {
        return None;
    }
    let dir = app_data.join("recipes");
    let _ = std::fs::create_dir_all(&dir);
    let cache = dir.join(format!("{recipe_id}.webview.js"));
    if let Ok(s) = std::fs::read_to_string(&cache) {
        return Some(s);
    }
    let url = format!(
        "https://raw.githubusercontent.com/ferdium/ferdium-recipes/main/recipes/{recipe_id}/webview.js"
    );
    let res = HTTP
        .clone()
        .get(&url)
        .header(reqwest::header::USER_AGENT, API_UA)
        .send()
        .await
        .ok()?;
    if !res.status().is_success() {
        return None;
    }
    let text = res.text().await.ok()?;
    let _ = write_atomic(&cache, &text);
    Some(text)
}

// --- Service webviews ----------------------------------------------------

// The service UUID's 16 bytes become the WKWebView data-store identifier.
#[cfg(any(target_os = "macos", test))]
fn uuid_to_bytes(s: &str) -> Option<[u8; 16]> {
    let hex: String = s.chars().filter(|c| *c != '-').collect();
    if hex.len() != 32 {
        return None;
    }
    let mut out = [0u8; 16];
    for i in 0..16 {
        out[i] = u8::from_str_radix(&hex[i * 2..i * 2 + 2], 16).ok()?;
    }
    Some(out)
}

fn sandbox_for_service(settings: &Value, service_id: &str) -> Option<String> {
    settings
        .get("serviceSandboxes")
        .and_then(Value::as_object)
        .and_then(|assignments| assignments.get(service_id))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|sandbox_id| !sandbox_id.is_empty())
        .map(str::to_string)
}

fn sandbox_storage_name(sandbox_id: &str) -> String {
    let digest = Sha256::digest(format!("tauridium-sandbox:{sandbox_id}").as_bytes());
    let suffix = digest[..12]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    format!("sandbox-{suffix}")
}

#[cfg(any(target_os = "macos", test))]
fn storage_identifier(service_id: &str, sandbox_id: Option<&str>) -> Option<[u8; 16]> {
    if let Some(sandbox_id) = sandbox_id {
        let digest = Sha256::digest(format!("tauridium-sandbox:{sandbox_id}").as_bytes());
        let mut identifier = [0u8; 16];
        identifier.copy_from_slice(&digest[..16]);
        Some(identifier)
    } else {
        uuid_to_bytes(service_id)
    }
}

fn storage_directory(app_data: &Path, service_id: &str, sandbox_id: Option<&str>) -> PathBuf {
    let name = sandbox_id
        .map(sandbox_storage_name)
        .unwrap_or_else(|| service_id.to_string());
    app_data.join("sessions").join(name)
}

// Purge a service's persistent storage (cookies, localStorage, session). Call this
// AFTER closing its webview. macOS: delete the WKWebsiteDataStore by identifier
// (wry API, main thread required); elsewhere delete the data_directory folder.
#[cfg(target_os = "macos")]
fn purge_service_storage(app: &AppHandle, service_id: &str, sandbox_id: Option<&str>) {
    use wry::WebViewExtDarwin;
    if let Some(uuid) = storage_identifier(service_id, sandbox_id) {
        let _ = app.run_on_main_thread(move || {
            <wry::WebView as WebViewExtDarwin>::remove_data_store(&uuid, |_| {});
        });
    }
}

#[cfg(not(target_os = "macos"))]
fn purge_service_storage(app: &AppHandle, service_id: &str, sandbox_id: Option<&str>) {
    if let Ok(dir) = app.path().app_data_dir() {
        let _ = std::fs::remove_dir_all(storage_directory(&dir, service_id, sandbox_id));
    }
}

// Logical rectangle for the service area: everything to the right of the sidebar.
fn service_rect(
    win: &tauri::window::Window<Wry>,
    sidebar_w: f64,
) -> Result<(LogicalPosition<f64>, LogicalSize<f64>), String> {
    let phys = win.inner_size().map_err(|e| e.to_string())?;
    let scale = win.scale_factor().map_err(|e| e.to_string())?;
    let w = phys.width as f64 / scale;
    let h = phys.height as f64 / scale;
    Ok((
        LogicalPosition::new(sidebar_w, 0.0),
        LogicalSize::new((w - sidebar_w).max(0.0), h),
    ))
}

// Some services (for example Synology Chat) read the global `ipc` (= window.ipc) and
// call Electron's IPC API (ipc.on / ipc.sendToHost). However, `window.ipc` is defined
// by wry for ITS own IPC ({postMessage}) without .on/.sendToHost, causing those services
// crash. wry created window.ipc as frozen/non-configurable, so Tauridium patches wry
// (vendor/wry) to make it mutable, then AUGMENTS it here by adding Electron
// methods as no-ops without changing postMessage. The full bridge (sendToHost routed to
// native badge/notification routing plus recipe webview.js support comes in Phase 3.
// Tauri injects its runtime marker and IPC internals into every webview, including remote
// service pages. Some hosted apps also ship a Tauri build and therefore detect Tauridium as
// their own native shell. Keep Tauridium's remote-service ACL closed, but make their request
// to toggle *their* devtools a harmless no-op instead of an unhandled rejected Promise.
// Never broaden this list to privileged filesystem/process/window commands.
const REMOTE_TAURI_COMPAT_JS: &str = r#"(function(){
  try {
    var internals = window.__TAURI_INTERNALS__;
    if (!internals || typeof internals.invoke !== 'function' || internals.__tauridiumRemoteCompat) return;
    var invoke = internals.invoke.bind(internals);
    internals.invoke = function(cmd, args, options){
      if (cmd === 'plugin:webview|internal_toggle_devtools') return Promise.resolve(null);
      return invoke(cmd, args, options);
    };
    internals.__tauridiumRemoteCompat = true;
  } catch(e){}
})();"#;

// Build a one-shot Tauridium-owned notification layer inside a native service child webview.
// The shell DOM sits below those child webviews, so a normal shell toast would be covered while
// a service is visible. Keep the rendering code private to native eval instead of exposing a page
// global that a hosted website could call to impersonate Tauridium notifications.
fn service_toast_overlay_script(message: &str, duration_ms: u64) -> Result<String, String> {
    let encoded = serde_json::to_string(message)
        .map_err(|error| format!("Unable to encode service overlay toast: {error}"))?;
    let duration_ms = duration_ms.clamp(500, 10_000);
    Ok(format!(
        r#"(function(message,duration){{
  try {{
    var previous = document.getElementById('__tauridium-toast-overlay');
    if (previous) previous.remove();
    var host = document.createElement('div');
    host.id = '__tauridium-toast-overlay';
    host.style.cssText = 'all:initial!important;position:fixed!important;z-index:2147483647!important;left:50%!important;bottom:24px!important;transform:translateX(-50%)!important;pointer-events:none!important;';
    var shadow = host.attachShadow({{mode:'closed'}});
    var toast = document.createElement('div');
    toast.setAttribute('role', 'status');
    toast.style.cssText = 'all:initial;box-sizing:border-box;display:block;max-width:min(520px,calc(100vw - 32px));padding:10px 14px;border:1px solid rgba(255,255,255,.18);border-radius:9px;background:#20242b;color:#f6f7f9;box-shadow:0 10px 34px rgba(0,0,0,.42);font:13px/1.4 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;overflow-wrap:anywhere;';
    toast.textContent = String(message || '');
    shadow.appendChild(toast);
    (document.documentElement || document.body).appendChild(host);
    window.setTimeout(function(){{ if (host && host.isConnected) host.remove(); }}, duration);
  }} catch(e){{}}
}})({encoded},{duration_ms});"#
    ))
}

const SHORTCUT_ACTIONS: [&str; 13] = [
    "quickWorkspaceSwitch",
    "quickServiceSwitch",
    "openSettings",
    "addService",
    "addWorkspace",
    "toggleSidebar",
    "nextService",
    "previousService",
    "nextWorkspace",
    "previousWorkspace",
    "reloadService",
    "reloadApp",
    "toggleDevtools",
];

static SERVICE_SHORTCUT_NONCE_COUNTER: AtomicU64 = AtomicU64::new(0);

fn next_service_shortcut_nonce(service_id: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(service_id.as_bytes());
    hasher.update(std::process::id().to_le_bytes());
    hasher.update(
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
            .to_le_bytes(),
    );
    hasher.update(
        SERVICE_SHORTCUT_NONCE_COUNTER
            .fetch_add(1, Ordering::Relaxed)
            .to_le_bytes(),
    );
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let digest = hasher.finalize();
    let mut nonce = String::with_capacity(digest.len() * 2);
    for byte in digest.iter().copied() {
        nonce.push(char::from(HEX[(byte >> 4) as usize]));
        nonce.push(char::from(HEX[(byte & 0x0f) as usize]));
    }
    nonce
}

fn service_shortcut_action_from_url(url: &Url, expected_nonce: &str) -> Option<String> {
    if url.scheme() != "tauridium-shortcut" || url.host_str() != Some("bridge") {
        return None;
    }
    let mut segments = url.path_segments()?;
    let nonce = segments.next()?;
    let action = segments.next()?;
    if segments.next().is_some() || nonce != expected_nonce || !SHORTCUT_ACTIONS.contains(&action) {
        return None;
    }
    Some(action.to_string())
}

fn effective_service_shortcut_capture(settings: &Value, service_id: &str) -> bool {
    let global = settings
        .get("captureServiceShortcuts")
        .and_then(Value::as_bool)
        .unwrap_or(true);
    settings
        .get("serviceShortcutCaptureOverrides")
        .and_then(Value::as_object)
        .and_then(|overrides| overrides.get(service_id))
        .and_then(Value::as_bool)
        .unwrap_or(global)
}

fn service_shortcut_bridge_js(settings: &Value, service_id: &str, nonce: &str) -> Option<String> {
    if !effective_service_shortcut_capture(settings, service_id) {
        return None;
    }
    let bindings = settings.get("keybindings").and_then(Value::as_object)?;
    let mut captured = serde_json::Map::new();
    for action in SHORTCUT_ACTIONS {
        if let Some(binding) = bindings
            .get(action)
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|binding| !binding.is_empty())
        {
            captured.insert(action.to_string(), Value::String(binding.to_string()));
        }
    }
    if captured.is_empty() {
        return None;
    }
    let bindings_json = serde_json::to_string(&captured).ok()?;
    let nonce_json = serde_json::to_string(nonce).ok()?;
    Some(format!(
        r#"(function(){{
  var bindings = {bindings_json};
  var token = {nonce_json};
  var pending = null;
  var pendingAt = 0;
  var timeoutMs = 1800;
  function strokes(binding){{ return String(binding || '').trim().split(/\s+/).filter(Boolean).slice(0, 2); }}
  function stroke(e){{
    if (['Control','Shift','Alt','Meta'].indexOf(e.key) !== -1) return null;
    var parts = [];
    if (e.ctrlKey) parts.push('Ctrl');
    if (e.altKey) parts.push('Alt');
    if (e.shiftKey) parts.push('Shift');
    if (e.metaKey) parts.push('Meta');
    var code = String(e.code || '');
    var codeKeys = {{Comma:',',Period:'.',Minus:'-',Equal:'=',Semicolon:';',Quote:"'",BracketLeft:'[',BracketRight:']',Backslash:'\\',Backquote:'`',Space:'Space',Tab:'Tab',ArrowDown:'ArrowDown',ArrowUp:'ArrowUp',ArrowLeft:'ArrowLeft',ArrowRight:'ArrowRight'}};
    var key = /^Key[A-Z]$/.test(code) ? code.slice(3) : (/^Digit[0-9]$/.test(code) ? code.slice(5) : codeKeys[code]);
    if (!key) key = e.key === ' ' ? 'Space' : (e.key && e.key.length === 1 ? e.key.toUpperCase() : e.key);
    if (!key) return null;
    parts.push(key);
    return parts.join('+');
  }}
  function dispatch(action){{
    try {{
      window.location.href = 'tauridium-shortcut://bridge/' + token + '/' + action;
    }} catch (_) {{}}
  }}
  window.addEventListener('keydown', function(e){{
    if (!e.isTrusted) return;
    var current = stroke(e);
    if (!current) return;
    var entries = Object.entries(bindings);
    var now = Date.now();
    if (pending && now - pendingAt >= timeoutMs) pending = null;
    if (pending) {{
      var chord = entries.find(function(entry){{ var seq = strokes(entry[1]); return seq.length === 2 && seq[0] === pending && seq[1] === current; }});
      pending = null;
      if (chord) {{
        e.preventDefault();
        e.stopImmediatePropagation();
        dispatch(chord[0]);
        return;
      }}
    }}
    var hasPrefix = entries.some(function(entry){{ var seq = strokes(entry[1]); return seq.length === 2 && seq[0] === current; }});
    if (hasPrefix) {{
      e.preventDefault();
      e.stopImmediatePropagation();
      pending = current;
      pendingAt = now;
      return;
    }}
    var single = entries.find(function(entry){{ var seq = strokes(entry[1]); return seq.length === 1 && seq[0] === current; }});
    if (single) {{
      e.preventDefault();
      e.stopImmediatePropagation();
      dispatch(single[0]);
    }}
  }}, true);
}})();"#
    ))
}

const IPC_SHIM_JS: &str = r#"(function(){
  window.__PAKE_SHIM__ = (window.__PAKE_SHIM__ || 0) + 1;
  window.__pakeUnread = window.__pakeUnread || 0;
  // Note: Telegram Web A is a Tauri app that calls low-level IPC (fetch ipc:// +
  // postMessage); it cannot be cleanly disabled from injected JavaScript. Its console errors
  // are harmless noise (Telegram still works). Telegram badge support is not implemented.
  // Intercept the web Notification API (WKWebView does not fully support it): queue
  // service notifications for the Rust poller to drain into native system notifications.
  (function(){
    window.__pakeNotifQueue = window.__pakeNotifQueue || [];
    function N(title, options){
      options = options || {};
      try { window.__pakeNotifQueue.push({
        title: String(title == null ? '' : title),
        body: String(options.body == null ? '' : options.body)
      }); } catch(e){}
      this.title = title; this.body = options.body;
      this.onclick = this.onclose = this.onerror = this.onshow = null;
    }
    N.prototype.close = function(){};
    N.prototype.addEventListener = function(t, cb){ this['on' + t] = cb; };
    N.prototype.removeEventListener = function(){};
    N.prototype.dispatchEvent = function(){ return true; };
    N.permission = 'granted';
    N.requestPermission = function(cb){ if (typeof cb === 'function') cb('granted'); return Promise.resolve('granted'); };
    try { window.Notification = N; } catch(e){}
  })();
  var noop = function(){};
  // Capture unread counts emitted through sendToHost by Electron-aware services.
  function captureUnread(channel){
    try {
      if (channel === 'updateUnread' || channel === 'message-counts' || channel === 'updateBadge') {
        var v = arguments[1];
        var n = (typeof v === 'number') ? v
              : (v && typeof v.count === 'number') ? v.count
              : parseInt(v, 10);
        if (!isNaN(n)) window.__pakeUnread = Math.max(0, n);
      }
    } catch(e){}
  }
  var extra = {
    on: noop, once: noop, off: noop, addListener: noop,
    removeListener: noop, removeAllListeners: noop,
    send: noop, sendToHost: captureUnread,
    sendSync: function(){ return null; },
    invoke: function(){ return Promise.resolve(); }
  };
  function augment(v){
    if (!v || typeof v.on === 'function') return v;
    // 1) try to mutate the object in place
    try { for (var k in extra) if (typeof v[k] !== 'function') v[k] = extra[k]; } catch(e){}
    if (typeof v.on === 'function') return v;
    // 2) locked object: rebuild it while preserving postMessage (Tauri IPC)
    var out = {};
    try { for (var k in v) out[k] = v[k]; } catch(e){}
    try { if (v.postMessage) out.postMessage = v.postMessage.bind(v); } catch(e){}
    for (var k in extra) if (typeof out[k] !== 'function') out[k] = extra[k];
    return out;
  }
  var real = augment(window.ipc);
  try {
    // intercept Tauri's assignment so the shim augments window.ipc exactly when Tauri sets it
    Object.defineProperty(window, 'ipc', {
      configurable: true,
      get: function(){ return real; },
      set: function(v){ real = augment(v); }
    });
  } catch(e){
    // repli : polling
    var n = 0, iv = setInterval(function(){
      window.ipc = augment(window.ipc);
      if (typeof (window.ipc||{}).on === 'function' || ++n > 400) clearInterval(iv);
    }, 25);
  }
})();"#;

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

fn open_external(url: &str) {
    #[cfg(target_os = "macos")]
    let _ = std::process::Command::new("open").arg(url).spawn();
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
            eprintln!("Unable to open external URL through the Windows shell (code {result})");
        }
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    let _ = std::process::Command::new("xdg-open").arg(url).spawn();
}

#[tauri::command]
fn open_external_url(url: String) -> Result<(), String> {
    let parsed = Url::parse(&url).map_err(|error| format!("Invalid external URL: {error}"))?;
    if !matches!(parsed.scheme(), "http" | "https") {
        return Err("External links must use HTTP or HTTPS".to_string());
    }
    open_external(parsed.as_str());
    Ok(())
}

// Download filename derived from the URL (last path segment; the
// query is ignored). Sanitize separators to prevent path traversal.
fn download_filename(url: &Url) -> String {
    let raw = url
        .path_segments()
        .and_then(|mut segs| segs.next_back())
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .unwrap_or("download");
    let clean: String = raw.replace(['/', '\\', '\0'], "_");
    if clean.is_empty() {
        "download".to_string()
    } else {
        clean
    }
}

// Choose a non-existing destination path in `dir` (WKDownload fails if the file exists):
// append (1), (2), etc. before the extension when a collision occurs.
fn unique_download_path(dir: &Path, name: &str) -> PathBuf {
    let candidate = dir.join(name);
    if !candidate.exists() {
        return candidate;
    }
    let p = Path::new(name);
    let stem = p.file_stem().and_then(|s| s.to_str()).unwrap_or("download");
    let ext = p.extension().and_then(|s| s.to_str());
    for i in 1..10_000 {
        let fname = match ext {
            Some(e) => format!("{stem} ({i}).{e}"),
            None => format!("{stem} ({i})"),
        };
        let candidate = dir.join(fname);
        if !candidate.exists() {
            return candidate;
        }
    }
    dir.join(name)
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct EffectiveDownloadPreferences {
    directory: String,
    ask_each_download: bool,
}

fn download_preferences_from_map(
    settings: &Value,
    key: &str,
    id: Option<&str>,
) -> Option<EffectiveDownloadPreferences> {
    let id = id?.trim();
    if id.is_empty() {
        return None;
    }
    let value = settings.get(key)?.as_object()?.get(id)?.as_object()?;
    Some(EffectiveDownloadPreferences {
        directory: value.get("directory")?.as_str()?.to_string(),
        ask_each_download: value.get("askEachDownload")?.as_bool()?,
    })
}

fn effective_download_preferences(
    settings: &Value,
    service_id: &str,
    workspace_id: Option<&str>,
) -> EffectiveDownloadPreferences {
    if let Some(preferences) =
        download_preferences_from_map(settings, "serviceDownloadSettings", Some(service_id))
    {
        return preferences;
    }
    if let Some(preferences) =
        download_preferences_from_map(settings, "workspaceDownloadSettings", workspace_id)
    {
        return preferences;
    }
    EffectiveDownloadPreferences {
        directory: settings
            .get("downloadDirectory")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string(),
        ask_each_download: settings
            .get("askEachDownload")
            .and_then(Value::as_bool)
            .unwrap_or(false),
    }
}

fn sanitize_download_filename(value: &str) -> String {
    let mut clean: String = value
        .trim()
        .chars()
        .map(|character| {
            if character.is_control()
                || matches!(
                    character,
                    '/' | '\\' | '<' | '>' | ':' | '"' | '|' | '?' | '*'
                )
            {
                '_'
            } else {
                character
            }
        })
        .collect();
    while clean.ends_with(' ') || clean.ends_with('.') {
        clean.pop();
    }
    if clean.is_empty() || clean == "." || clean == ".." {
        return "download".into();
    }
    let reserved_stem = Path::new(&clean)
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_uppercase();
    if matches!(
        reserved_stem.as_str(),
        "CON"
            | "PRN"
            | "AUX"
            | "NUL"
            | "COM1"
            | "COM2"
            | "COM3"
            | "COM4"
            | "COM5"
            | "COM6"
            | "COM7"
            | "COM8"
            | "COM9"
            | "LPT1"
            | "LPT2"
            | "LPT3"
            | "LPT4"
            | "LPT5"
            | "LPT6"
            | "LPT7"
            | "LPT8"
            | "LPT9"
    ) {
        clean.insert(0, '_');
    }
    if clean.chars().count() > 240 {
        let path = Path::new(&clean);
        let extension = path
            .extension()
            .and_then(|value| value.to_str())
            .unwrap_or("");
        let extension_len = if extension.is_empty() {
            0
        } else {
            extension.chars().count() + 1
        };
        let stem_limit = 240usize.saturating_sub(extension_len);
        let stem: String = path
            .file_stem()
            .and_then(|value| value.to_str())
            .unwrap_or("download")
            .chars()
            .take(stem_limit.max(1))
            .collect();
        clean = if extension.is_empty() {
            stem
        } else {
            format!("{stem}.{extension}")
        };
    }
    clean
}

fn suggested_download_filename(destination: &Path, url: &Url) -> String {
    destination
        .file_name()
        .and_then(|value| value.to_str())
        .map(sanitize_download_filename)
        .unwrap_or_else(|| sanitize_download_filename(&download_filename(url)))
}

fn effective_download_directory(app: &AppHandle, configured: &str) -> PathBuf {
    let configured = configured.trim();
    if !configured.is_empty() {
        let path = PathBuf::from(configured);
        if path.is_absolute() && std::fs::create_dir_all(&path).is_ok() {
            return path;
        }
    }
    app.path()
        .download_dir()
        .or_else(|_| app.path().home_dir())
        .unwrap_or_else(|_| PathBuf::from("."))
}

fn ask_download_destination(
    parent: &tauri::Window<Wry>,
    directory: &Path,
    suggested_name: &str,
) -> Option<PathBuf> {
    // Wry requires the final absolute destination synchronously from its download-started
    // callback. Use rfd's synchronous native dialog directly on that callback thread. The
    // tauri-plugin-dialog blocking wrapper cannot be used here: it dispatches back to the main
    // thread and would deadlock while the synchronous download callback is waiting. rfd is
    // already Tauridium's native dialog backend through tauri-plugin-dialog; declaring it
    // directly lets us use the correct synchronous API without changing dialog technology.
    rfd::FileDialog::new()
        .set_parent(parent)
        .set_title("Save download")
        .set_directory(directory)
        .set_file_name(suggested_name)
        .save_file()
}

// Duplicate-keystroke fix (macOS/WKWebView child webviews): WebKit dispatches legacy
// `textInput` events REDUNDANT with the real insertion. Two cases were observed in
// Discord :
//  a) normal keystroke -> TWO identical `textInput` events for one keystroke (Draft.js search);
//  b) composition (dead key / accent) -> one legacy `textInput` IN ADDITION to the
//     `beforeinput[insertFromComposition]` standard (compositeur Slate).
// Both produce a duplicated character.
//
// Important detail: Draft.js search RELIES on composition `textInput` (suppressing it
// would lose the accented character), while Slate composer duplicates it. Opposite needs for the SAME
// event mean behavior must depend on the target editor:
//  - outside composition: suppress the second identical `textInput` for the keystroke (case a);
//  - during composition: suppress legacy `textInput` only inside a **Slate** editor
//    (`[data-slate-editor]`), never in Draft.js (case b).
// Diagnostic switches: `window.__pakeDedup=false` (all), `__pakeDedupComp=false`
// (composition handling only).
const KEY_DEDUP_JS: &str = r#"(function(){
  var token = 0, seenTok = -1, seenData = null, composing = false;
  document.addEventListener('keydown', function(){ token++; }, true);
  document.addEventListener('compositionstart', function(){ composing = true; }, true);
  document.addEventListener('compositionend', function(){ composing = false; }, true);
  function targetEl(e){
    var t = e.target;
    if (t && t.nodeType === 3) t = t.parentElement;   // text node -> parent element
    return (t && t.closest) ? t : null;
  }
  document.addEventListener('textInput', function(e){
    if (window.__pakeDedup === false) return;
    if (!e.isTrusted || typeof e.data !== 'string' || e.data.length !== 1) return;
    if (composing) {
      if (window.__pakeDedupComp === false) return;
      // Only inside a Slate editor (composer), never in Draft.js (search).
      var el = targetEl(e);
      if (el && el.closest('[data-slate-editor="true"]') && !el.closest('[class*="DraftEditor"]')) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
      return;
    }
    // Outside composition: a second identical `textInput` for the SAME keystroke is a native duplicate.
    if (seenTok === token && seenData === e.data) {
      e.preventDefault();
      e.stopImmediatePropagation();
    } else {
      seenTok = token;
      seenData = e.data;
    }
  }, true);
})();"#;

#[tauri::command]
// Create a service webview if absent at the requested position/size. Recipe fetches for
// config + webview.js happen ONLY HERE during creation, not on every switch.
#[allow(clippy::too_many_arguments)]
async fn create_service_webview(
    state: &State<'_, AppState>,
    win: &tauri::window::Window<Wry>,
    app_data: &Path,
    service_id: &str,
    recipe_id: &str,
    custom_url: Option<&str>,
    team: Option<&str>,
    user_agent_pref: Option<&str>,
    open_links_externally: bool,
    sandbox_id: Option<&str>,
    dark: Option<DarkOpts>,
    pos: LogicalPosition<f64>,
    size: LogicalSize<f64>,
) -> Result<(), String> {
    let cfg = recipe_config(win.app_handle(), app_data, recipe_id).await?;
    let template_values =
        service_custom_url_template_values(&state.settings.lock().unwrap(), service_id);
    let url_str = resolve_url(&cfg, custom_url, team, &template_values)?;
    let url = Url::parse(&url_str).map_err(|e| format!("Invalid URL {url_str}: {e}"))?;
    let host = url.host_str().unwrap_or("").to_ascii_lowercase();
    // Recipe runtime (DOM unread-count scraping -> __pakeUnread), best effort.
    let runtime = recipe_webview_js(win.app_handle(), app_data, recipe_id)
        .await
        .map(|js| format!("{RECIPE_PREAMBLE}{js}{RECIPE_SUFFIX}"));
    let label = format!("svc-{service_id}");

    // User agent precedence: per-service override, global setting, Google compatibility UA,
    // then the platform default. On Windows, leave the UA unset so WebView2 reports its native
    // browser identity. Anti-bot systems such as Cloudflare Turnstile can reject a Chromium
    // WebView2 engine that falsely identifies as Safari. Other platforms retain Tauridium's
    // established compatibility UA unless explicitly overridden.
    let ua = {
        let per_service = user_agent_pref.map(str::trim).filter(|s| !s.is_empty());
        if let Some(p) = per_service {
            Some(p.to_string())
        } else {
            let global = state
                .settings
                .lock()
                .unwrap()
                .get("userAgentPref")
                .and_then(Value::as_str)
                .unwrap_or("")
                .trim()
                .to_string();
            if !global.is_empty() {
                Some(global)
            } else if is_google_auth_host(&host) {
                Some(GOOGLE_CHROMELESS_UA.to_string())
            } else if cfg!(windows) {
                None
            } else {
                Some(SERVICE_UA.to_string())
            }
        }
    };

    // Remote pages are intentionally not granted Tauri IPC permissions. Tauri 2.11+
    // enforces ACL checks for remote origins, including application commands, so captured
    // shortcuts use a private per-webview navigation nonce instead. The navigation handler
    // below consumes only that exact internal URL and cancels the navigation before the
    // hosted service can leave its page.
    let service_shortcut_nonce = next_service_shortcut_nonce(service_id);
    let service_shortcut_bridge = service_shortcut_bridge_js(
        &state.settings.lock().unwrap(),
        service_id,
        &service_shortcut_nonce,
    );

    // IPC shim injected into ALL services (Synology Chat and others depend on it).
    let shortcut_app = win.app_handle().clone();
    let shortcut_nonce_for_navigation = service_shortcut_nonce.clone();
    let new_window_app = win.app_handle().clone();
    let new_window_label = label.clone();
    let mut builder = WebviewBuilder::new(label, WebviewUrl::External(url))
        // Creation never takes focus. The active service is focused only after the latest
        // requested switch wins the desired-active race.
        .focused(false)
        .on_navigation(move |url| {
            if url.scheme() != "tauridium-shortcut" {
                return true;
            }
            if let Some(action) =
                service_shortcut_action_from_url(url, &shortcut_nonce_for_navigation)
            {
                let _ = shortcut_app.emit("shortcut-action", action);
            }
            false
        })
        .initialization_script(IPC_SHIM_JS)
        .initialization_script(REMOTE_TAURI_COMPAT_JS)
        // Prevent duplicated keystrokes caused by duplicate native WKWebView `textInput` events (see Discord search).
        .initialization_script(KEY_DEDUP_JS)
        // `target="_blank"` links / `window.open`: sized popups are typically authentication
        // flows and retain the platform's in-app popup behavior. Ordinary HTTP(S) content links
        // follow the per-service preference: navigate this service webview by default, or open
        // through the OS browser when "Open links externally" is enabled. mailto remains an
        // external protocol because an embedded service webview cannot handle it usefully.
        .on_new_window(
            move |url: Url, features: NewWindowFeatures| -> NewWindowResponse<Wry> {
                if features.size().is_some() {
                    return NewWindowResponse::Allow;
                }
                if url.scheme() == "mailto"
                    || (open_links_externally && matches!(url.scheme(), "http" | "https"))
                {
                    open_external(url.as_str());
                    return NewWindowResponse::Deny;
                }
                if matches!(url.scheme(), "http" | "https") {
                    if let Some(webview) = new_window_app.get_webview(&new_window_label) {
                        if let Err(error) = webview.navigate(url) {
                            eprintln!("Unable to navigate service link in place: {error}");
                        }
                    }
                }
                NewWindowResponse::Deny
            },
        );
    if let Some(ua) = ua.as_deref() {
        builder = builder.user_agent(ua);
    }
    if let Some(script) = service_shortcut_bridge {
        builder = builder.initialization_script(script);
    }
    // Emit loading state to the shell (spinner transitions from loading to ready).
    // Preloaded/inactive services remain visible off-screen instead of being hidden. Browser
    // engines may throttle hidden documents; Tauridium hibernation is a separate, explicit
    // close operation controlled by the global timer and the per-service opt-in.
    let sid_evt = service_id.to_string();
    builder = builder.on_page_load(move |wv, payload| {
        let status = match payload.event() {
            PageLoadEvent::Started => "loading",
            PageLoadEvent::Finished => {
                wv.app_handle()
                    .state::<AppState>()
                    .preloading
                    .lock()
                    .unwrap()
                    .remove(&sid_evt);
                "ready"
            }
        };
        let _ = wv.app_handle().emit(
            "svc-status",
            serde_json::json!({ "id": sid_evt.as_str(), "status": status }),
        );
    });
    // Preserve the filename suggested by the webview engine/server (for example an HTTP
    // Content-Disposition filename) instead of rebuilding it from an opaque attachment URL.
    // Destination preferences are resolved at download time, so global/workspace/service
    // changes apply immediately without recreating this webview.
    let download_service_id = service_id.to_string();
    builder = builder.on_download(move |webview, event| match event {
        DownloadEvent::Requested { url, destination } => {
            let app = webview.app_handle().clone();
            let state = app.state::<AppState>();
            let workspace_id = state
                .download_workspaces
                .lock()
                .unwrap()
                .get(&download_service_id)
                .cloned()
                .flatten();
            let preferences = effective_download_preferences(
                &state.settings.lock().unwrap(),
                &download_service_id,
                workspace_id.as_deref(),
            );
            let suggested_name = suggested_download_filename(destination, &url);
            let directory = effective_download_directory(&app, &preferences.directory);

            if preferences.ask_each_download {
                let parent = webview.window();
                let Some(path) = ask_download_destination(&parent, &directory, &suggested_name)
                else {
                    return false;
                };
                *destination = path;
            } else {
                *destination = unique_download_path(&directory, &suggested_name);
            }
            true
        }
        DownloadEvent::Finished {
            url,
            path,
            success: true,
        } => {
            let filename = path
                .as_deref()
                .and_then(Path::file_name)
                .and_then(|value| value.to_str())
                .map(sanitize_download_filename)
                .unwrap_or_else(|| sanitize_download_filename(&download_filename(&url)));
            let _ = webview
                .app_handle()
                .notification()
                .builder()
                .title("Tauridium")
                .body(format!("Downloaded \"{filename}\""))
                .show();
            true
        }
        _ => true,
    });
    // Per-service storage isolation: macOS -> data_store_identifier (data_directory
    // ignored); Windows/Linux use a dedicated data_directory to avoid shared sessions.
    #[cfg(target_os = "macos")]
    {
        let store = storage_identifier(service_id, sandbox_id)
            .ok_or("serviceId is not a UUID and no sandbox is assigned")?;
        builder = builder.data_store_identifier(store);
    }
    #[cfg(not(target_os = "macos"))]
    {
        let dir = storage_directory(app_data, service_id, sandbox_id);
        let _ = std::fs::create_dir_all(&dir);
        builder = builder.data_directory(dir);
    }
    // Google compatibility (userAgentData / window.chrome, etc.) for generic Google services.
    if is_google_host(&host) && !is_google_auth_host(&host) {
        builder = builder.initialization_script(GOOGLE_AUTH_COMPAT_JS);
    }
    if let Some(rt) = runtime {
        builder = builder.initialization_script(rt);
    }
    // Per-service dark mode: inject and enable Dark Reader (best effort).
    if let Some(o) = dark {
        builder = builder.initialization_script(dark_reader_init(o));
    }
    win.add_child(builder, pos, size)
        .map_err(|e| format!("Failed to create service webview: {e}"))?;
    state.created.lock().unwrap().insert(service_id.to_string());
    Ok(())
}

#[derive(serde::Deserialize)]
#[serde(rename_all = "camelCase")]
struct ServiceViewRequest {
    service_id: String,
    recipe_id: String,
    custom_url: Option<String>,
    team: Option<String>,
    user_agent_pref: Option<String>,
    #[serde(default)]
    open_links_externally: bool,
    workspace_id: Option<String>,
    dark: Option<DarkSettings>,
}

fn activate_service_webview(
    app: &AppHandle,
    state: &AppState,
    service_id: &str,
    pos: LogicalPosition<f64>,
    size: LogicalSize<f64>,
) -> bool {
    let offscreen = LogicalPosition::new(-30000.0, 0.0);
    let created: Vec<String> = state.created.lock().unwrap().iter().cloned().collect();
    let mut activated = false;
    for sid in created {
        if let Some(wv) = app.get_webview(&format!("svc-{sid}")) {
            if sid == service_id {
                let _ = wv.set_position(pos);
                let _ = wv.set_size(size);
                let _ = wv.show();
                let _ = wv.set_focus();
                activated = true;
            } else {
                let _ = wv.set_position(offscreen);
                let _ = wv.set_size(size);
                let _ = wv.show();
            }
        }
    }
    if activated {
        state.preloading.lock().unwrap().remove(service_id);
        *state.active.lock().unwrap() = Some(service_id.to_string());
    }
    activated
}

#[tauri::command]
async fn show_service(
    app: AppHandle,
    state: State<'_, AppState>,
    request: ServiceViewRequest,
) -> Result<(), String> {
    let ServiceViewRequest {
        service_id,
        recipe_id,
        custom_url,
        team,
        user_agent_pref,
        open_links_externally,
        workspace_id,
        dark,
    } = request;
    let dark = dark.and_then(DarkSettings::into_opts);
    let sandbox_id = sandbox_for_service(&state.settings.lock().unwrap(), &service_id);
    state.download_workspaces.lock().unwrap().insert(
        service_id.clone(),
        workspace_id.filter(|id| !id.trim().is_empty()),
    );
    let win = app.get_window("main").ok_or("Main window not found")?;
    let label = format!("svc-{service_id}");
    let sw = *state.sidebar_w.lock().unwrap();
    let (pos, size) = service_rect(&win, sw)?;

    // Record the requested service BEFORE any await so it guards against focus stealing
    // if a newer switch arrives while this service is loading.
    *state.desired_active.lock().unwrap() = Some(service_id.clone());

    let exists = state.created.lock().unwrap().contains(&service_id);
    if exists {
        // Already loaded (or preloaded): only reposition it; no network fetch.
        if let Some(wv) = app.get_webview(&label) {
            let _ = wv.set_position(pos);
            let _ = wv.set_size(size);
        }
    } else {
        // Reserve creation: two rapid switches to the same new service would otherwise perform
        // two add_child calls with the same label (an error). If already in progress, do not restart it.
        let claim = {
            let mut infl = state.inflight.lock().unwrap();
            if infl.contains(&service_id) {
                false
            } else {
                infl.insert(service_id.clone());
                true
            }
        };
        if claim {
            let app_data = app.path().app_data_dir().map_err(|e| e.to_string())?;
            let res = create_service_webview(
                &state,
                &win,
                &app_data,
                &service_id,
                &recipe_id,
                custom_url.as_deref(),
                team.as_deref(),
                user_agent_pref.as_deref(),
                open_links_externally,
                sandbox_id.as_deref(),
                dark,
                pos,
                size,
            )
            .await;
            state.inflight.lock().unwrap().remove(&service_id);
            res?;
        }
    }

    // A newer switch may have superseded this one while loading; in that case
    // do NOT display this service, or it would steal focus from the currently requested service.
    if state.desired_active.lock().unwrap().as_deref() != Some(service_id.as_str()) {
        return Ok(());
    }

    // Display the requested service and park every other loaded service off-screen while
    // keeping it alive. If a background preload still owns creation, it will activate the
    // webview on completion only when this service remains the latest requested target.
    let _ = activate_service_webview(&app, &state, &service_id, pos, size);
    Ok(())
}

// Preload a service IN THE BACKGROUND: create its webview off-screen so it loads the page
// without becoming active. Switching to it later is then nearly instantaneous.
#[tauri::command]
async fn preload_service(
    app: AppHandle,
    state: State<'_, AppState>,
    request: ServiceViewRequest,
) -> Result<(), String> {
    let ServiceViewRequest {
        service_id,
        recipe_id,
        custom_url,
        team,
        user_agent_pref,
        open_links_externally,
        workspace_id: _,
        dark,
    } = request;
    let dark = dark.and_then(DarkSettings::into_opts);
    let sandbox_id = sandbox_for_service(&state.settings.lock().unwrap(), &service_id);
    if state.created.lock().unwrap().contains(&service_id) {
        return Ok(());
    }
    // Reserve creation (see show_service) to prevent preload + switch from creating
    // the same webview twice. If creation is already in progress, let the other operation finish.
    {
        let mut infl = state.inflight.lock().unwrap();
        if infl.contains(&service_id) {
            return Ok(());
        }
        infl.insert(service_id.clone());
    }
    let win = match app.get_window("main") {
        Some(w) => w,
        None => {
            state.inflight.lock().unwrap().remove(&service_id);
            return Err("Main window not found".into());
        }
    };
    let sw = *state.sidebar_w.lock().unwrap();
    let (_, size) = match service_rect(&win, sw) {
        Ok(r) => r,
        Err(e) => {
            state.inflight.lock().unwrap().remove(&service_id);
            return Err(e);
        }
    };
    let app_data = match app.path().app_data_dir() {
        Ok(d) => d,
        Err(e) => {
            state.inflight.lock().unwrap().remove(&service_id);
            return Err(e.to_string());
        }
    };
    // Off-screen and unfocused: keep the webview visible so its initial page load and
    // background runtime can progress until it is selected or explicitly hibernated.
    state.preloading.lock().unwrap().insert(service_id.clone());
    let offscreen = LogicalPosition::new(-30000.0, 0.0);
    let res = create_service_webview(
        &state,
        &win,
        &app_data,
        &service_id,
        &recipe_id,
        custom_url.as_deref(),
        team.as_deref(),
        user_agent_pref.as_deref(),
        open_links_externally,
        sandbox_id.as_deref(),
        dark,
        offscreen,
        size,
    )
    .await;
    state.inflight.lock().unwrap().remove(&service_id);
    if let Err(error) = res {
        state.preloading.lock().unwrap().remove(&service_id);
        return Err(error);
    }
    // A user can select this service while its background creation is in flight. In that
    // race, show_service records desired_active and returns; complete the switch here without
    // recreating or reloading the preloaded webview.
    if state.desired_active.lock().unwrap().as_deref() == Some(service_id.as_str()) {
        let sw = *state.sidebar_w.lock().unwrap();
        let (pos, size) = service_rect(&win, sw)?;
        let _ = activate_service_webview(&app, &state, &service_id, pos, size);
    }
    Ok(())
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
        Ok(Some(_)) => audit::best_effort(
            &app,
            "info",
            "service-icon",
            if force { "refetch" } else { "fetch" },
            "success",
            "Website icon cached",
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
    result
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

fn hide_service_webviews(app: &AppHandle, state: &AppState) {
    let active = state.active.lock().unwrap().clone();
    let created: Vec<String> = state.created.lock().unwrap().iter().cloned().collect();
    let offscreen = LogicalPosition::new(-30000.0, 0.0);
    for sid in created {
        if let Some(wv) = app.get_webview(&format!("svc-{sid}")) {
            if active.as_deref() == Some(sid.as_str()) {
                // Hide only the focused/active child so the shell regains input for settings,
                // add-service, quick-switcher, and similar full-screen panels.
                let _ = wv.hide();
            } else {
                let _ = wv.set_position(offscreen);
                let _ = wv.show();
            }
        }
    }
    *state.active.lock().unwrap() = None;
}

// Hide all service webviews so the shell can display a full-screen panel.
#[tauri::command]
fn hide_all_services(app: AppHandle, state: State<'_, AppState>) {
    hide_service_webviews(&app, &state);
}

// Close ONE service webview so it can be recreated with new parameters.
#[tauri::command]
fn close_service(app: AppHandle, state: State<'_, AppState>, service_id: String) {
    if let Some(wv) = app.get_webview(&format!("svc-{service_id}")) {
        let _ = wv.close();
    }
    state.created.lock().unwrap().remove(&service_id);
    state.preloading.lock().unwrap().remove(&service_id);
    state
        .download_workspaces
        .lock()
        .unwrap()
        .remove(&service_id);
    state.unread.lock().unwrap().remove(&service_id);
    if state.active.lock().unwrap().as_deref() == Some(service_id.as_str()) {
        *state.active.lock().unwrap() = None;
    }
}

// Change the sidebar width and reposition the active service webview.
#[tauri::command]
fn set_sidebar_width(app: AppHandle, state: State<'_, AppState>, width: f64) {
    *state.sidebar_w.lock().unwrap() = width.clamp(MIN_RUNTIME_SIDEBAR_W, MAX_SIDEBAR_W);
    reposition_active(&app);
}

#[tauri::command]
fn close_services(app: AppHandle, state: State<'_, AppState>) {
    let created: Vec<String> = state.created.lock().unwrap().drain().collect();
    for sid in created {
        if let Some(wv) = app.get_webview(&format!("svc-{sid}")) {
            let _ = wv.close();
        }
    }
    *state.active.lock().unwrap() = None;
    state.preloading.lock().unwrap().clear();
    state.download_workspaces.lock().unwrap().clear();
    state.unread.lock().unwrap().clear();
    if let Some(win) = app.get_window("main") {
        let _ = win.set_badge_count(None);
    }
}

// Save per-service settings (notification/mute/badge) used by the poller.
#[tauri::command]
fn set_service_flags(
    state: State<'_, AppState>,
    service_id: String,
    notif: bool,
    muted: bool,
    badge: bool,
) {
    state.flags.lock().unwrap().insert(
        service_id,
        ServiceFlags {
            notif,
            muted,
            badge,
        },
    );
}

// Update a service. In local mode, persist the mutation in local_profile.json;
// in server mode keep it synchronized via PUT /v1/service/:id.
fn finish_service_update(
    app: &AppHandle,
    service_id: &str,
    patch: &Value,
    result: Result<Value, String>,
) -> Result<Value, String> {
    match result {
        Ok(updated) => {
            audit::best_effort(
                app,
                "info",
                "settings",
                "service-change",
                "success",
                "Service settings changed",
                serde_json::json!({ "serviceId": service_id, "changes": patch }),
            );
            Ok(updated)
        }
        Err(error) => {
            audit::best_effort(
                app,
                "error",
                "settings",
                "service-change",
                "failure",
                "Service settings change failed",
                serde_json::json!({
                    "serviceId": service_id,
                    "changes": patch,
                    "error": &error
                }),
            );
            Err(error)
        }
    }
}

#[tauri::command]
async fn update_service(
    app: AppHandle,
    state: State<'_, AppState>,
    service_id: String,
    patch: Value,
) -> Result<Value, String> {
    let local_service = state
        .local_profile
        .lock()
        .unwrap()
        .has_local_recipe_service(&service_id);
    if is_local_mode(&state) || local_service {
        let operation = (|| -> Result<Value, String> {
            let mut profile = state.local_profile.lock().unwrap();
            let mut next = profile.clone();
            let updated = next.update_service(&service_id, &patch)?;
            save_local_profile(&app, &next)?;
            *profile = next;
            Ok(updated)
        })();
        return finish_service_update(&app, &service_id, &patch, operation);
    }

    let operation = async {
        let (base, token) = current(&state)?;
        let res = HTTP
            .clone()
            .put(format!("{base}/v1/service/{service_id}"))
            .bearer_auth(&token)
            .header(reqwest::header::USER_AGENT, API_UA)
            .json(&patch)
            .send()
            .await
            .map_err(|error| error.to_string())?;
        if !res.status().is_success() {
            return Err(format!("Service update failed: HTTP {}", res.status()));
        }
        res.json().await.map_err(|error| error.to_string())
    }
    .await;
    finish_service_update(&app, &service_id, &patch, operation)
}

// Create a service locally or through POST /v1/service depending on session mode.
#[tauri::command]
async fn create_service(
    app: AppHandle,
    state: State<'_, AppState>,
    name: String,
    recipe_id: String,
) -> Result<Value, String> {
    let local_recipe = recipes::local_recipe_config(&app, &recipe_id)?.is_some();
    if is_local_mode(&state) || local_recipe {
        let icon_url = if local_recipe {
            recipes::local_icon_url(&app, &recipe_id)
        } else {
            None
        };
        let prefer_website_icon = local_recipe && !recipes::is_bundled_recipe(&recipe_id);
        let mut profile = state.local_profile.lock().unwrap();
        let mut next = profile.clone();
        let mut service = next.create_service(name, recipe_id, icon_url, local_recipe)?;
        if prefer_website_icon {
            let service_id = service
                .get("id")
                .and_then(Value::as_str)
                .ok_or_else(|| "Created custom-recipe service has no id".to_string())?
                .to_string();
            service =
                next.update_service(&service_id, &serde_json::json!({ "useFavicon": true }))?;
        }
        save_local_profile(&app, &next)?;
        *profile = next;
        return Ok(service);
    }
    let (base, token) = current(&state)?;
    let res = HTTP
        .clone()
        .post(format!("{base}/v1/service"))
        .bearer_auth(&token)
        .header(reqwest::header::USER_AGENT, API_UA)
        .json(&serde_json::json!({ "name": name, "recipeId": recipe_id }))
        .send()
        .await
        .map_err(|e| e.to_string())?;
    if !res.status().is_success() {
        return Err(format!("Service creation failed: HTTP {}", res.status()));
    }
    res.json().await.map_err(|e| e.to_string())
}

#[tauri::command]
fn create_custom_website_service(
    app: AppHandle,
    state: State<'_, AppState>,
    name: String,
    url: String,
) -> Result<Value, String> {
    let url = ensure_scheme(url.trim());
    let parsed = Url::parse(&url).map_err(|error| format!("Invalid website URL: {error}"))?;
    if parsed.scheme() != "http" && parsed.scheme() != "https" {
        return Err("Custom websites must use http:// or https://".into());
    }
    let display_name = if name.trim().is_empty() {
        parsed.host_str().unwrap_or("Custom Website").to_string()
    } else {
        name.trim().to_string()
    };
    let mut profile = state.local_profile.lock().unwrap();
    let mut next = profile.clone();
    let mut service = next.create_service(
        display_name,
        "custom-website".into(),
        recipes::local_icon_url(&app, "custom-website"),
        true,
    )?;
    let service_id = service
        .get("id")
        .and_then(Value::as_str)
        .ok_or_else(|| "Created custom website service has no id".to_string())?
        .to_string();
    service = next.update_service(
        &service_id,
        &serde_json::json!({ "customUrl": url, "useFavicon": true }),
    )?;
    save_local_profile(&app, &next)?;
    *profile = next;
    Ok(service)
}

// Delete a service -> DELETE /v1/service/:id and close its webview.
#[tauri::command]
async fn delete_service(
    app: AppHandle,
    state: State<'_, AppState>,
    service_id: String,
) -> Result<(), String> {
    let sandbox_id = sandbox_for_service(&state.settings.lock().unwrap(), &service_id);
    let local_service = state
        .local_profile
        .lock()
        .unwrap()
        .has_local_recipe_service(&service_id);
    if is_local_mode(&state) || local_service {
        let mut profile = state.local_profile.lock().unwrap();
        let mut next = profile.clone();
        next.delete_service(&service_id)?;
        save_local_profile(&app, &next)?;
        *profile = next;
    } else {
        let (base, token) = current(&state)?;
        let res = HTTP
            .clone()
            .delete(format!("{base}/v1/service/{service_id}"))
            .bearer_auth(&token)
            .header(reqwest::header::USER_AGENT, API_UA)
            .send()
            .await
            .map_err(|e| e.to_string())?;
        if !res.status().is_success() {
            return Err(format!("Service deletion failed: HTTP {}", res.status()));
        }
    }
    if let Some(wv) = app.get_webview(&format!("svc-{service_id}")) {
        let _ = wv.close();
    }
    state.created.lock().unwrap().remove(&service_id);
    state.unread.lock().unwrap().remove(&service_id);
    state.flags.lock().unwrap().remove(&service_id);
    icons::remove_cached(&app, &service_id);
    // Isolated services own their storage and can be purged safely. Shared sandbox data
    // belongs to the sandbox, so deleting one member must not sign out the remaining members.
    if sandbox_id.is_none() {
        purge_service_storage(&app, &service_id, None);
    }
    Ok(())
}

// Clear a service cache/session WITHOUT deleting it from the server: close its webview
// and purge its storage. The service will reopen cleanly and signed out on next access.
#[tauri::command]
fn clear_service_cache(app: AppHandle, state: State<'_, AppState>, service_id: String) {
    let sandbox_id = sandbox_for_service(&state.settings.lock().unwrap(), &service_id);
    let service_ids = if let Some(ref sandbox_id) = sandbox_id {
        services_in_sandbox(&state.settings.lock().unwrap(), sandbox_id)
    } else {
        vec![service_id.clone()]
    };
    close_service_ids(&app, &state, &service_ids);
    purge_service_storage(&app, &service_id, sandbox_id.as_deref());
}

fn services_in_sandbox(settings: &Value, sandbox_id: &str) -> Vec<String> {
    settings
        .get("serviceSandboxes")
        .and_then(Value::as_object)
        .map(|assignments| {
            assignments
                .iter()
                .filter(|(_, value)| value.as_str() == Some(sandbox_id))
                .map(|(service_id, _)| service_id.clone())
                .collect()
        })
        .unwrap_or_default()
}

fn close_service_ids(app: &AppHandle, state: &AppState, service_ids: &[String]) {
    let ids: HashSet<&str> = service_ids.iter().map(String::as_str).collect();
    for service_id in service_ids {
        if let Some(wv) = app.get_webview(&format!("svc-{service_id}")) {
            let _ = wv.close();
        }
        state.created.lock().unwrap().remove(service_id);
        state.unread.lock().unwrap().remove(service_id);
    }
    if state
        .active
        .lock()
        .unwrap()
        .as_deref()
        .is_some_and(|active| ids.contains(active))
    {
        *state.active.lock().unwrap() = None;
    }
    if state
        .desired_active
        .lock()
        .unwrap()
        .as_deref()
        .is_some_and(|active| ids.contains(active))
    {
        *state.desired_active.lock().unwrap() = None;
    }
}

#[tauri::command]
fn clear_sandbox(
    app: AppHandle,
    state: State<'_, AppState>,
    sandbox_id: String,
) -> Result<(), String> {
    let sandbox_id = sandbox_id.trim();
    if sandbox_id.is_empty() {
        return Err("Sandbox id is empty".into());
    }
    let settings = state.settings.lock().unwrap().clone();
    let known = settings
        .get("sandboxes")
        .and_then(Value::as_array)
        .is_some_and(|sandboxes| {
            sandboxes
                .iter()
                .any(|sandbox| sandbox.get("id").and_then(Value::as_str) == Some(sandbox_id))
        });
    if !known {
        return Err(format!("Unknown sandbox: {sandbox_id}"));
    }
    let service_ids = services_in_sandbox(&settings, sandbox_id);
    close_service_ids(&app, &state, &service_ids);
    purge_service_storage(&app, "sandbox", Some(sandbox_id));
    Ok(())
}

fn recipe_catalog_cache_path(app: &AppHandle) -> Result<PathBuf, String> {
    app.path()
        .app_data_dir()
        .map(|dir| dir.join("recipe_catalog.json"))
        .map_err(|error| format!("Recipe cache directory unavailable: {error}"))
}

fn cached_recipe_catalog(app: &AppHandle) -> Option<Value> {
    let path = recipe_catalog_cache_path(app).ok()?;
    let text = std::fs::read_to_string(path).ok()?;
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
        .get("https://api.github.com/repos/ferdium/ferdium-recipes/contents/recipes?ref=main")
        .header(reqwest::header::USER_AGENT, API_UA)
        .header(reqwest::header::ACCEPT, "application/vnd.github+json")
        .send()
        .await
    {
        Ok(response) if response.status().is_success() => match response.json::<Value>().await {
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
                                "svg": format!(
                                    "https://raw.githubusercontent.com/ferdium/ferdium-recipes/main/recipes/{recipe_id}/icon.svg"
                                )
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
        },
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
            Ok(response) if response.status().is_success() => response.json::<Value>().await.ok(),
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
fn import_custom_recipe(app: AppHandle, path: String) -> Result<Value, String> {
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
    res.json().await.map_err(|e| e.to_string())
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
    res.json().await.map_err(|e| e.to_string())
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
fn logout(app: AppHandle, state: State<'_, AppState>) {
    *state.server.lock().unwrap() = None;
    *state.token.lock().unwrap() = None;
    *state.local_mode.lock().unwrap() = false;
    *state.local_profile.lock().unwrap() = LocalProfile::default();
    clear_session(&app);
}

// Reposition the active webview over the service area (called on resize).
fn reposition_active(app: &AppHandle) {
    let st = app.state::<AppState>();
    let active = st.active.lock().unwrap().clone();
    let Some(sid) = active else { return };
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
}

// Dock-badge poller: read window.__pakeUnread from each service webview,
// aggregate unread counts and update the macOS dock badge (set_badge_count).
fn start_badge_poller(app: AppHandle) {
    std::thread::spawn(move || loop {
        std::thread::sleep(std::time::Duration::from_secs(2));
        let services: Vec<String> = app
            .state::<AppState>()
            .created
            .lock()
            .unwrap()
            .iter()
            .cloned()
            .collect();
        for sid in services {
            let Some(wv) = app.get_webview(&format!("svc-{sid}")) else {
                continue;
            };
            let app2 = app.clone();
            let _ = wv.eval_with_callback(
                "(function(){return {u: Math.max(0, parseInt(window.__pakeUnread)||0), n: (window.__pakeNotifQueue||[]).splice(0)};})()",
                move |res| {
                    let v: serde_json::Value =
                        serde_json::from_str(&res).unwrap_or(serde_json::Value::Null);
                    let unread = v.get("u").and_then(|x| x.as_i64()).unwrap_or(0);
                    let st = app2.state::<AppState>();
                    let flags = st.flags.lock().unwrap().get(&sid).copied().unwrap_or_default();

                    // Notifications: honor mute and disabled-notification settings.
                    if flags.notif && !flags.muted {
                        let private = st
                            .settings
                            .lock()
                            .unwrap()
                            .get("privateNotifications")
                            .and_then(Value::as_bool)
                            .unwrap_or(false);
                        if let Some(arr) = v.get("n").and_then(|x| x.as_array()) {
                            for notif in arr {
                                let title = notif
                                    .get("title")
                                    .and_then(|x| x.as_str())
                                    .unwrap_or("")
                                    .trim();
                                let body = notif.get("body").and_then(|x| x.as_str()).unwrap_or("");
                                if title.is_empty() && body.is_empty() {
                                    continue;
                                }
                                let b = app2.notification().builder();
                                let _ = if private {
                                    b.title("New message").show()
                                } else {
                                    b.title(if title.is_empty() { "Message" } else { title })
                                        .body(body)
                                        .show()
                                };
                            }
                        }
                    }

                    // Store raw counts per service for the sidebar and calculate the dock total
                    // with flags applied and emit the unread-count map to the shell.
                    // The service may have been closed/hibernated/deleted between the snapshot and this
                    // async callback; in that case do NOT reinsert it, otherwise it would remain
                    // in the total forever and create a phantom dock badge.
                    let still_exists = st.created.lock().unwrap().contains(&sid);
                    let (map, total) = {
                        let mut m = st.unread.lock().unwrap();
                        if still_exists {
                            m.insert(sid.clone(), unread);
                        } else {
                            m.remove(&sid);
                        }
                        let f = st.flags.lock().unwrap();
                        let total: i64 = m
                            .iter()
                            .map(|(id, &u)| {
                                let fl = f.get(id).copied().unwrap_or_default();
                                if fl.badge && !fl.muted {
                                    u
                                } else {
                                    0
                                }
                            })
                            .sum();
                        (m.clone(), total)
                    };
                    let _ = app2.emit("unread", &map);
                    if let Some(win) = app2.get_window("main") {
                        let _ = win.set_badge_count(if total > 0 { Some(total) } else { None });
                    }
                },
            );
        }
    });
}

// --- App settings (app_settings.json) ------------------------------------

fn app_settings_path(app: &AppHandle) -> Option<PathBuf> {
    app.path()
        .app_data_dir()
        .ok()
        .map(|d| d.join("app_settings.json"))
}

fn default_app_settings_value() -> Value {
    // Keep the defaults as direct map inserts rather than one large `json!` invocation.
    // `json!` is recursive for every object entry and eventually exceeds rustc's default
    // macro recursion limit as settings are added. Direct construction scales without a
    // crate-wide recursion-limit override and keeps the serialized shape unchanged.
    let mut settings = serde_json::Map::<String, Value>::new();
    settings.insert("autostart".into(), false.into());
    settings.insert("startMinimized".into(), false.into());
    settings.insert("theme".into(), "system".into());
    settings.insert("accentColor".into(), "#ffc131".into());
    settings.insert("customAccentColors".into(), Value::Array(Vec::new()));
    settings.insert("closeToSystemTray".into(), true.into());
    settings.insert("privateNotifications".into(), false.into());
    settings.insert("showDisabledServices".into(), true.into());
    settings.insert("showServiceName".into(), true.into());
    settings.insert("showMessageBadgeWhenMuted".into(), true.into());
    settings.insert("showWorkspaceInWindowTitle".into(), true.into());
    settings.insert("showWorkspaceInTaskbarTitle".into(), false.into());
    settings.insert("customTitleTemplatesEnabled".into(), false.into());
    settings.insert("windowTitleTemplate".into(), "{app} ~ {workspace}".into());
    settings.insert("taskbarTitleTemplate".into(), "{app} ~ {workspace}".into());
    settings.insert("userAgentPref".into(), "".into());
    settings.insert("sidebarWidth".into(), 240.into());
    settings.insert("sidebarWidthMode".into(), "pixels".into());
    settings.insert("sidebarWidthPercent".into(), 20.into());
    settings.insert("sidebarCollapsed".into(), false.into());
    settings.insert("defaultSidebarCollapsed".into(), false.into());
    settings.insert("restoreLastSidebarStateOnStartup".into(), true.into());
    settings.insert("customSidebarWidths".into(), Value::Array(Vec::new()));
    settings.insert("collapsedServiceSpacing".into(), 2.into());
    settings.insert("expandedServiceSpacing".into(), 2.into());
    settings.insert("iconSize".into(), 24.into());
    settings.insert("grayscaleServices".into(), false.into());
    settings.insert("grayscaleDim".into(), 50.into());
    settings.insert("sidebarServicesLocation".into(), "top".into());
    settings.insert("hibernationTimer".into(), 0.into());
    settings.insert("preloadServices".into(), true.into());
    settings.insert("fetchMissingServiceIcons".into(), true.into());
    settings.insert("reloadToasts".into(), true.into());
    settings.insert("prettyServiceContextMenu".into(), true.into());
    settings.insert("sidebarServiceDragReorder".into(), true.into());
    settings.insert("captureServiceShortcuts".into(), true.into());
    settings.insert(
        "serviceShortcutCaptureOverrides".into(),
        Value::Object(serde_json::Map::new()),
    );
    settings.insert("customUrlTemplatesEnabled".into(), false.into());
    settings.insert(
        "serviceCustomUrlTemplates".into(),
        Value::Object(serde_json::Map::new()),
    );
    settings.insert(
        "serviceIconInversions".into(),
        Value::Object(serde_json::Map::new()),
    );
    settings.insert("serviceOrder".into(), Value::Array(Vec::new()));
    settings.insert("workspaceOrder".into(), Value::Array(Vec::new()));
    settings.insert("workspaceQuickSwitchOrder".into(), "custom".into());
    settings.insert("defaultWorkspaceId".into(), "".into());
    settings.insert("restoreLastWorkspaceOnStartup".into(), false.into());
    settings.insert("lastWorkspaceId".into(), "".into());
    settings.insert(
        "workspaceLastUsed".into(),
        Value::Object(serde_json::Map::new()),
    );
    settings.insert(
        "workspaceIcons".into(),
        Value::Object(serde_json::Map::new()),
    );
    settings.insert("downloadDirectory".into(), "".into());
    settings.insert("askEachDownload".into(), false.into());
    settings.insert(
        "serviceDownloadSettings".into(),
        Value::Object(serde_json::Map::new()),
    );
    settings.insert(
        "workspaceDownloadSettings".into(),
        Value::Object(serde_json::Map::new()),
    );
    let mut keybindings = serde_json::Map::<String, Value>::new();
    keybindings.insert("quickWorkspaceSwitch".into(), "Ctrl+D".into());
    keybindings.insert("quickServiceSwitch".into(), "Ctrl+S".into());
    keybindings.insert("openSettings".into(), "Ctrl+,".into());
    keybindings.insert("addService".into(), "Ctrl+N".into());
    keybindings.insert("addWorkspace".into(), "Ctrl+Shift+N".into());
    keybindings.insert("toggleSidebar".into(), "Ctrl+Shift+B".into());
    keybindings.insert("nextService".into(), "Ctrl+Tab".into());
    keybindings.insert("previousService".into(), "Ctrl+Shift+Tab".into());
    keybindings.insert("nextWorkspace".into(), "Ctrl+Alt+ArrowDown".into());
    keybindings.insert("previousWorkspace".into(), "Ctrl+Alt+ArrowUp".into());
    keybindings.insert("reloadService".into(), "Ctrl+R".into());
    keybindings.insert("reloadApp".into(), "Ctrl+Shift+R".into());
    keybindings.insert("toggleDevtools".into(), "Ctrl+Alt+I".into());
    settings.insert("keybindings".into(), Value::Object(keybindings));
    settings.insert("sandboxes".into(), Value::Array(Vec::new()));
    settings.insert(
        "serviceSandboxes".into(),
        Value::Object(serde_json::Map::new()),
    );
    settings.insert("automaticBackupSchedule".into(), "off".into());
    settings.insert("automaticBackupDirectory".into(), "".into());
    settings.insert("automaticBackupRetentionMode".into(), "count".into());
    settings.insert("automaticBackupRetention".into(), 10.into());
    settings.insert("automaticBackupMaxAgeDays".into(), 90.into());
    settings.insert("lastAutomaticBackupAt".into(), 0.into());
    Value::Object(settings)
}

fn is_hex_color(value: &str) -> bool {
    value.len() == 7
        && value.starts_with('#')
        && value.as_bytes()[1..]
            .iter()
            .all(|byte| byte.is_ascii_hexdigit())
}

fn validate_keybindings(value: Option<&Value>) -> Result<(), String> {
    let bindings = value
        .and_then(Value::as_object)
        .ok_or_else(|| "App setting keybindings must be an object".to_string())?;
    for action in SHORTCUT_ACTIONS {
        let binding = bindings
            .get(action)
            .and_then(Value::as_str)
            .ok_or_else(|| format!("App keybinding {action} must be a string"))?
            .trim();
        if binding.len() > 80 {
            return Err(format!("App keybinding {action} is too long"));
        }
        if !binding.is_empty() && binding.split_whitespace().count() > 2 {
            return Err(format!("App keybinding {action} has more than two strokes"));
        }
    }
    Ok(())
}

fn validate_sandboxes(
    sandboxes: Option<&Value>,
    assignments: Option<&Value>,
) -> Result<(), String> {
    let sandboxes = sandboxes
        .and_then(Value::as_array)
        .ok_or_else(|| "App setting sandboxes must be an array".to_string())?;
    if sandboxes.len() > 256 {
        return Err("App setting sandboxes contains too many entries".into());
    }
    let mut ids = HashSet::with_capacity(sandboxes.len());
    for sandbox in sandboxes {
        let object = sandbox
            .as_object()
            .ok_or_else(|| "Sandbox entries must be objects".to_string())?;
        let id = object
            .get("id")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|id| !id.is_empty() && id.len() <= 80)
            .ok_or_else(|| "Sandbox id is invalid".to_string())?;
        if !id
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
        {
            return Err(format!("Sandbox id contains unsupported characters: {id}"));
        }
        if !ids.insert(id.to_string()) {
            return Err(format!("Duplicate sandbox id: {id}"));
        }
        let name = object
            .get("name")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|name| !name.is_empty() && name.chars().count() <= 80)
            .ok_or_else(|| format!("Sandbox {id} has an invalid name"))?;
        if name.chars().any(char::is_control) {
            return Err(format!("Sandbox {id} name contains control characters"));
        }
    }

    let assignments = assignments
        .and_then(Value::as_object)
        .ok_or_else(|| "App setting serviceSandboxes must be an object".to_string())?;
    if assignments.len() > 10_000 {
        return Err("App setting serviceSandboxes contains too many entries".into());
    }
    for (service_id, sandbox_id) in assignments {
        if service_id.trim().is_empty() {
            return Err("App setting serviceSandboxes contains an empty service id".into());
        }
        let sandbox_id = sandbox_id
            .as_str()
            .ok_or_else(|| "App setting serviceSandboxes values must be strings".to_string())?;
        if !ids.contains(sandbox_id) {
            return Err(format!(
                "Service {service_id} references unknown sandbox: {sandbox_id}"
            ));
        }
    }
    Ok(())
}

fn validate_download_settings_map(value: Option<&Value>, label: &str) -> Result<(), String> {
    let map = value
        .and_then(Value::as_object)
        .ok_or_else(|| format!("App setting {label} must be an object"))?;
    if map.len() > 10_000 {
        return Err(format!("App setting {label} contains too many entries"));
    }
    for (id, preferences) in map {
        if id.trim().is_empty() || id.len() > 256 {
            return Err(format!("App setting {label} contains an invalid id"));
        }
        let preferences = preferences
            .as_object()
            .ok_or_else(|| format!("App setting {label} values must be objects"))?;
        let directory = preferences
            .get("directory")
            .and_then(Value::as_str)
            .ok_or_else(|| format!("App setting {label} directory must be a string"))?;
        if directory.len() > 4096 || directory.chars().any(char::is_control) {
            return Err(format!("App setting {label} directory is invalid"));
        }
        if !preferences
            .get("askEachDownload")
            .is_some_and(Value::is_boolean)
        {
            return Err(format!(
                "App setting {label} askEachDownload must be boolean"
            ));
        }
    }
    Ok(())
}

fn validate_app_settings_value(settings: &Value) -> Result<(), String> {
    let object = settings
        .as_object()
        .ok_or_else(|| "App settings must be a JSON object".to_string())?;
    for key in [
        "autostart",
        "startMinimized",
        "closeToSystemTray",
        "privateNotifications",
        "showDisabledServices",
        "showServiceName",
        "showMessageBadgeWhenMuted",
        "showWorkspaceInWindowTitle",
        "showWorkspaceInTaskbarTitle",
        "customTitleTemplatesEnabled",
        "grayscaleServices",
        "preloadServices",
        "fetchMissingServiceIcons",
        "reloadToasts",
        "prettyServiceContextMenu",
        "askEachDownload",
        "sidebarServiceDragReorder",
        "captureServiceShortcuts",
        "customUrlTemplatesEnabled",
        "restoreLastWorkspaceOnStartup",
        "sidebarCollapsed",
        "defaultSidebarCollapsed",
        "restoreLastSidebarStateOnStartup",
    ] {
        if !object.get(key).is_some_and(Value::is_boolean) {
            return Err(format!("App setting {key} must be boolean"));
        }
    }
    for key in ["windowTitleTemplate", "taskbarTitleTemplate"] {
        let template = object
            .get(key)
            .and_then(Value::as_str)
            .ok_or_else(|| format!("App setting {key} must be a string"))?;
        if template.chars().count() > 240 || template.chars().any(char::is_control) {
            return Err(format!("App setting {key} is invalid"));
        }
    }
    let theme = object
        .get("theme")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !matches!(theme, "system" | "dark" | "oled" | "light") {
        return Err("App setting theme is invalid".into());
    }
    let location = object
        .get("sidebarServicesLocation")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !matches!(location, "top" | "center" | "bottom") {
        return Err("App setting sidebarServicesLocation is invalid".into());
    }
    let sidebar_width_mode = object
        .get("sidebarWidthMode")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !matches!(sidebar_width_mode, "pixels" | "percent") {
        return Err("App setting sidebarWidthMode is invalid".into());
    }
    let workspace_quick_switch_order = object
        .get("workspaceQuickSwitchOrder")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !matches!(
        workspace_quick_switch_order,
        "custom"
            | "customReverse"
            | "alphabetical"
            | "alphabeticalReverse"
            | "recent"
            | "recentReverse"
    ) {
        return Err("App setting workspaceQuickSwitchOrder is invalid".into());
    }
    for key in ["defaultWorkspaceId", "lastWorkspaceId"] {
        let workspace_id = object
            .get(key)
            .and_then(Value::as_str)
            .ok_or_else(|| format!("App setting {key} must be a string"))?;
        if workspace_id.len() > 256
            || workspace_id.chars().any(char::is_control)
            || (!workspace_id.is_empty() && workspace_id.trim().is_empty())
        {
            return Err(format!("App setting {key} is invalid"));
        }
    }
    let workspace_last_used = object
        .get("workspaceLastUsed")
        .and_then(Value::as_object)
        .ok_or_else(|| "App setting workspaceLastUsed must be an object".to_string())?;
    if workspace_last_used.len() > 10_000 {
        return Err("App setting workspaceLastUsed contains too many entries".into());
    }
    for (workspace_id, timestamp) in workspace_last_used {
        if workspace_id.trim().is_empty()
            || !timestamp
                .as_f64()
                .is_some_and(|number| number.is_finite() && number >= 0.0)
        {
            return Err("App setting workspaceLastUsed is invalid".into());
        }
    }
    let workspace_icons = object
        .get("workspaceIcons")
        .and_then(Value::as_object)
        .ok_or_else(|| "App setting workspaceIcons must be an object".to_string())?;
    if workspace_icons.len() > 10_000 {
        return Err("App setting workspaceIcons contains too many entries".into());
    }
    let mut workspace_icon_bytes = 0usize;
    for (workspace_id, icon) in workspace_icons {
        let icon = icon
            .as_str()
            .ok_or_else(|| "App setting workspaceIcons values must be strings".to_string())?;
        workspace_icon_bytes = workspace_icon_bytes.saturating_add(icon.len());
        let supported = icon.starts_with("https://")
            || icon.starts_with("http://")
            || icon.starts_with("data:image/");
        if workspace_id.trim().is_empty()
            || workspace_id.len() > 256
            || icon.is_empty()
            || icon.len() > 768 * 1024
            || !supported
        {
            return Err("App setting workspaceIcons is invalid".into());
        }
    }
    if workspace_icon_bytes > 16 * 1024 * 1024 {
        return Err("App setting workspaceIcons exceeds the supported total size".into());
    }
    let download_directory = object
        .get("downloadDirectory")
        .and_then(Value::as_str)
        .ok_or_else(|| "App setting downloadDirectory must be a string".to_string())?;
    if download_directory.len() > 4096 || download_directory.chars().any(char::is_control) {
        return Err("App setting downloadDirectory is invalid".into());
    }
    validate_download_settings_map(
        object.get("serviceDownloadSettings"),
        "serviceDownloadSettings",
    )?;
    validate_download_settings_map(
        object.get("workspaceDownloadSettings"),
        "workspaceDownloadSettings",
    )?;
    let backup_schedule = object
        .get("automaticBackupSchedule")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !matches!(
        backup_schedule,
        "off" | "startup" | "daily" | "weekly" | "monthly"
    ) {
        return Err("App setting automaticBackupSchedule is invalid".into());
    }
    let backup_retention_mode = object
        .get("automaticBackupRetentionMode")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !matches!(
        backup_retention_mode,
        "count" | "age" | "countAndAge" | "tiered"
    ) {
        return Err("App setting automaticBackupRetentionMode is invalid".into());
    }
    let backup_directory = object
        .get("automaticBackupDirectory")
        .and_then(Value::as_str)
        .ok_or_else(|| "App setting automaticBackupDirectory must be a string".to_string())?;
    if backup_directory.len() > 4096 || backup_directory.chars().any(char::is_control) {
        return Err("App setting automaticBackupDirectory is invalid".into());
    }
    if !object.get("accentColor").is_some_and(Value::is_string)
        || !object.get("userAgentPref").is_some_and(Value::is_string)
    {
        return Err("App string settings are invalid".into());
    }
    let accent_color = object
        .get("accentColor")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !is_hex_color(accent_color) {
        return Err("App setting accentColor must be a #RRGGBB color".into());
    }
    let custom_colors = object
        .get("customAccentColors")
        .and_then(Value::as_array)
        .ok_or_else(|| "App setting customAccentColors must be an array".to_string())?;
    if custom_colors.len() > 32
        || custom_colors
            .iter()
            .any(|color| !color.as_str().is_some_and(is_hex_color))
    {
        return Err("App setting customAccentColors is invalid".into());
    }
    for (key, min, max) in [
        ("sidebarWidth", 160.0, 420.0),
        ("sidebarWidthPercent", 10.0, 40.0),
        ("collapsedServiceSpacing", 2.0, 24.0),
        ("expandedServiceSpacing", 2.0, 24.0),
        ("iconSize", 12.0, 64.0),
        ("grayscaleDim", 0.0, 100.0),
        ("hibernationTimer", 0.0, 86_400.0),
    ] {
        let number = object
            .get(key)
            .and_then(Value::as_f64)
            .ok_or_else(|| format!("App setting {key} must be numeric"))?;
        if !(min..=max).contains(&number) {
            return Err(format!("App setting {key} is outside its supported range"));
        }
    }
    let custom_widths = object
        .get("customSidebarWidths")
        .and_then(Value::as_array)
        .ok_or_else(|| "App setting customSidebarWidths must be an array".to_string())?;
    if custom_widths.len() > 16
        || custom_widths.iter().any(|width| {
            !width
                .as_f64()
                .is_some_and(|number| (160.0..=420.0).contains(&number))
        })
    {
        return Err("App setting customSidebarWidths is invalid".into());
    }
    let shortcut_overrides = object
        .get("serviceShortcutCaptureOverrides")
        .and_then(Value::as_object)
        .ok_or_else(|| {
            "App setting serviceShortcutCaptureOverrides must be an object".to_string()
        })?;
    if shortcut_overrides.len() > 10_000
        || shortcut_overrides.iter().any(|(service_id, capture)| {
            service_id.trim().is_empty()
                || service_id.len() > 256
                || service_id.chars().any(char::is_control)
                || !capture.is_boolean()
        })
    {
        return Err("App setting serviceShortcutCaptureOverrides is invalid".into());
    }

    let service_templates = object
        .get("serviceCustomUrlTemplates")
        .and_then(Value::as_object)
        .ok_or_else(|| "App setting serviceCustomUrlTemplates must be an object".to_string())?;
    if service_templates.len() > 10_000 {
        return Err("App setting serviceCustomUrlTemplates contains too many entries".into());
    }
    for (service_id, entry) in service_templates {
        if service_id.trim().is_empty() {
            return Err(
                "App setting serviceCustomUrlTemplates contains an empty service id".into(),
            );
        }
        let entry = entry.as_object().ok_or_else(|| {
            format!("Custom URL template settings for {service_id} must be an object")
        })?;
        if !entry.get("enabled").is_some_and(Value::is_boolean) {
            return Err(format!(
                "Custom URL template enabled flag for {service_id} must be boolean"
            ));
        }
        for key in ["customId1", "customId2"] {
            let value = entry.get(key).and_then(Value::as_str).ok_or_else(|| {
                format!("Custom URL template {key} for {service_id} must be a string")
            })?;
            if value.len() > 2048 || value.chars().any(char::is_control) {
                return Err(format!(
                    "Custom URL template {key} for {service_id} is invalid"
                ));
            }
        }
    }
    let icon_inversions = object
        .get("serviceIconInversions")
        .and_then(Value::as_object)
        .ok_or_else(|| "App setting serviceIconInversions must be an object".to_string())?;
    if icon_inversions.len() > 10_000
        || icon_inversions.iter().any(|(service_id, inverted)| {
            service_id.trim().is_empty()
                || service_id.len() > 256
                || service_id.chars().any(char::is_control)
                || !inverted.is_boolean()
        })
    {
        return Err("App setting serviceIconInversions is invalid".into());
    }
    validate_keybindings(object.get("keybindings"))?;
    validate_sandboxes(object.get("sandboxes"), object.get("serviceSandboxes"))?;
    let backup_retention = object
        .get("automaticBackupRetention")
        .and_then(Value::as_u64)
        .ok_or_else(|| "App setting automaticBackupRetention must be an integer".to_string())?;
    if !(1..=365).contains(&backup_retention) {
        return Err("App setting automaticBackupRetention is outside its supported range".into());
    }
    let backup_max_age = object
        .get("automaticBackupMaxAgeDays")
        .and_then(Value::as_u64)
        .ok_or_else(|| "App setting automaticBackupMaxAgeDays must be an integer".to_string())?;
    if !(1..=3650).contains(&backup_max_age) {
        return Err("App setting automaticBackupMaxAgeDays is outside its supported range".into());
    }
    if !object
        .get("lastAutomaticBackupAt")
        .is_some_and(|value| value.as_f64().is_some_and(|number| number >= 0.0))
    {
        return Err("App setting lastAutomaticBackupAt must be a non-negative number".into());
    }
    for (key, label) in [("serviceOrder", "Service"), ("workspaceOrder", "Workspace")] {
        let values = object
            .get(key)
            .and_then(Value::as_array)
            .ok_or_else(|| format!("App setting {key} must be an array"))?;
        let ids = values
            .iter()
            .map(|value| {
                value
                    .as_str()
                    .map(str::to_string)
                    .ok_or_else(|| format!("App setting {key} contains a non-string id"))
            })
            .collect::<Result<Vec<_>, _>>()?;
        validate_order_ids(&ids, label)?;
    }
    Ok(())
}

fn resolve_startup_sidebar_collapsed(settings: &Value) -> bool {
    let default_collapsed = settings
        .get("defaultSidebarCollapsed")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let restore_last = settings
        .get("restoreLastSidebarStateOnStartup")
        .and_then(Value::as_bool)
        .unwrap_or(true);
    let last_collapsed = settings
        .get("sidebarCollapsed")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    if restore_last {
        last_collapsed
    } else {
        default_collapsed
    }
}

fn merge_app_settings_value(stored: &Value) -> Result<Value, String> {
    let stored = stored
        .as_object()
        .ok_or_else(|| "App settings must be a JSON object".to_string())?;
    let mut value = default_app_settings_value();
    let base = value
        .as_object_mut()
        .ok_or_else(|| "Internal app settings defaults are invalid".to_string())?;
    for (key, setting) in stored {
        if key == "keybindings" {
            let stored_bindings = setting
                .as_object()
                .ok_or_else(|| "App setting keybindings must be an object".to_string())?;
            let default_bindings = base
                .get_mut("keybindings")
                .and_then(Value::as_object_mut)
                .ok_or_else(|| "Internal app keybinding defaults are invalid".to_string())?;
            for (action, binding) in stored_bindings {
                default_bindings.insert(action.clone(), binding.clone());
            }
        } else {
            base.insert(key.clone(), setting.clone());
        }
    }
    validate_app_settings_value(&value)?;
    Ok(value)
}

fn read_app_settings_value(app: &AppHandle) -> Value {
    let stored = app_settings_path(app)
        .and_then(|path| std::fs::read_to_string(path).ok())
        .and_then(|text| serde_json::from_str::<Value>(&text).ok());
    stored
        .as_ref()
        .and_then(|value| merge_app_settings_value(value).ok())
        .unwrap_or_else(default_app_settings_value)
}

fn effective_app_settings_value(app: &AppHandle) -> Value {
    let mut value = read_app_settings_value(app);
    if let Ok(enabled) = app.autolaunch().is_enabled() {
        if let Some(object) = value.as_object_mut() {
            object.insert("autostart".into(), Value::Bool(enabled));
        }
    }
    value
}

fn autostart_needs_update(current: bool, desired: bool) -> bool {
    current != desired
}

fn apply_autostart_setting(app: &AppHandle, settings: &Value) -> Result<(), String> {
    let Some(enabled) = settings.get("autostart").and_then(Value::as_bool) else {
        return Ok(());
    };
    let current = app
        .autolaunch()
        .is_enabled()
        .map_err(|error| format!("Unable to inspect autostart state: {error}"))?;
    if !autostart_needs_update(current, enabled) {
        return Ok(());
    }
    let result = if enabled {
        app.autolaunch().enable()
    } else {
        app.autolaunch().disable()
    };
    result.map_err(|error| format!("Unable to update autostart: {error}"))
}

fn persist_app_settings(app: &AppHandle, state: &AppState, settings: &Value) -> Result<(), String> {
    if let Some(path) = app_settings_path(app) {
        if let Some(dir) = path.parent() {
            std::fs::create_dir_all(dir)
                .map_err(|error| format!("Unable to create settings directory: {error}"))?;
        }
        let text = serde_json::to_string_pretty(settings)
            .map_err(|error| format!("Unable to serialize app settings: {error}"))?;
        write_atomic(&path, &format!("{text}\n"))
            .map_err(|error| format!("Unable to persist app settings: {error}"))?;
    }
    *state.settings.lock().unwrap() = settings.clone();
    Ok(())
}

#[tauri::command]
fn get_app_settings(app: AppHandle) -> Value {
    effective_app_settings_value(&app)
}

fn validate_order_ids(ids: &[String], label: &str) -> Result<(), String> {
    if ids.len() > 10_000 {
        return Err(format!("Too many {label} ids in order state"));
    }
    let mut seen = HashSet::with_capacity(ids.len());
    for id in ids {
        let id = id.trim();
        if id.is_empty() {
            return Err(format!("{label} order contains an empty id"));
        }
        if !seen.insert(id) {
            return Err(format!("{label} order contains duplicate id: {id}"));
        }
    }
    Ok(())
}

fn persist_order_setting(
    app: &AppHandle,
    state: &AppState,
    key: &str,
    label: &str,
    ids: Vec<String>,
) -> Result<Value, String> {
    validate_order_ids(&ids, label)?;
    let _settings_write = state.settings_write.lock().unwrap();
    let count = ids.len();
    let mut settings = read_app_settings_value(app);
    let object = settings
        .as_object_mut()
        .ok_or_else(|| "Internal app settings state is invalid".to_string())?;
    object.insert(key.to_string(), serde_json::json!(ids));
    persist_app_settings(app, state, &settings)?;
    audit::best_effort(
        app,
        "info",
        "settings",
        "reorder",
        "success",
        format!("{label} order changed"),
        serde_json::json!({ "setting": key, "count": count }),
    );
    Ok(settings)
}

#[tauri::command]
fn set_service_order(
    app: AppHandle,
    state: State<'_, AppState>,
    service_ids: Vec<String>,
) -> Result<Value, String> {
    persist_order_setting(&app, &state, "serviceOrder", "Service", service_ids)
}

#[tauri::command]
fn set_workspace_order(
    app: AppHandle,
    state: State<'_, AppState>,
    workspace_ids: Vec<String>,
) -> Result<Value, String> {
    persist_order_setting(&app, &state, "workspaceOrder", "Workspace", workspace_ids)
}

#[tauri::command]
fn sync_services_menu(app: AppHandle, services: Vec<NativeServiceMenuEntry>) -> Result<(), String> {
    let service_ids: Vec<String> = services.iter().map(|service| service.id.clone()).collect();
    validate_order_ids(&service_ids, "Native service menu")?;
    let menu = build_native_application_menu(&app, &services)
        .map_err(|error| format!("Unable to build native application menu: {error}"))?;
    app.set_menu(menu)
        .map_err(|error| format!("Unable to install native application menu: {error}"))?;
    Ok(())
}

#[tauri::command]
fn set_app_settings(
    app: AppHandle,
    state: State<'_, AppState>,
    patch: Value,
) -> Result<Value, String> {
    let patch = patch
        .as_object()
        .ok_or_else(|| "App settings patch must be a JSON object".to_string())?
        .clone();
    let _settings_write = state.settings_write.lock().unwrap();
    let previous = read_app_settings_value(&app);
    let autostart_changed = patch.contains_key("autostart");
    let operation = (|| -> Result<Value, String> {
        let mut value = previous.clone();
        let base = value
            .as_object_mut()
            .ok_or_else(|| "Internal app settings state is invalid".to_string())?;
        for (key, setting) in &patch {
            base.insert(key.clone(), setting.clone());
        }
        validate_app_settings_value(&value)?;
        if autostart_changed {
            apply_autostart_setting(&app, &value)?;
        }
        if let Err(error) = persist_app_settings(&app, &state, &value) {
            if autostart_changed {
                let _ = apply_autostart_setting(&app, &previous);
            }
            return Err(error);
        }
        Ok(value)
    })();

    match operation {
        Ok(value) => {
            let changes = patch
                .iter()
                .map(|(key, after)| {
                    (
                        key.clone(),
                        serde_json::json!({
                            "before": previous.get(key).cloned().unwrap_or(Value::Null),
                            "after": after
                        }),
                    )
                })
                .collect::<serde_json::Map<_, _>>();
            audit::best_effort(
                &app,
                "info",
                "settings",
                "change",
                "success",
                format!("Updated {} application setting(s)", patch.len()),
                serde_json::json!({ "changes": changes }),
            );
            Ok(value)
        }
        Err(error) => {
            audit::best_effort(
                &app,
                "error",
                "settings",
                "change",
                "failure",
                error.clone(),
                serde_json::json!({ "keys": patch.keys().collect::<Vec<_>>() }),
            );
            Err(error)
        }
    }
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
    let configured = settings
        .get("automaticBackupDirectory")
        .and_then(Value::as_str)
        .map(str::trim)
        .unwrap_or_default();
    if !configured.is_empty() {
        return Ok(PathBuf::from(configured));
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
    if let Err(error) = apply_autostart_setting(app, &app_settings) {
        summary = summary.with_warning(format!(
            "Backup data restored successfully, but the operating-system autostart integration could not be synchronized: {error}"
        ));
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
fn get_audit_log(app: AppHandle, limit: Option<usize>) -> Result<Vec<audit::AuditEntry>, String> {
    audit::read(&app, limit.unwrap_or(500).clamp(1, 10_000))
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
    if let Some(window) = app.get_window("main") {
        // The window-state plugin restores the hidden main window exactly once from its
        // on_window_ready hook. Replaying restore_state here causes a second maximized/fullscreen
        // transition on Windows 11; only reveal the already-restored window.
        if !start_minimized {
            let _ = window.show();
            let _ = window.set_focus();
        }
    }
}

fn show_main(app: &AppHandle) {
    if let Some(w) = app.get_window("main") {
        // Hiding a live window does not discard its geometry/window mode. Restoring again before
        // every tray/menu reveal can replay maximized/fullscreen transitions on Windows.
        let _ = w.show();
        let _ = w.set_focus();
    }
}

fn toggle_main(app: &AppHandle) {
    if let Some(w) = app.get_window("main") {
        if w.is_visible().unwrap_or(false) {
            save_main_window_state(app);
            let _ = w.hide();
        } else {
            let _ = w.show();
            let _ = w.set_focus();
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

    // Windows and most Linux desktops derive taskbar button text from the native window title,
    // so they cannot expose an independent per-window taskbar string while retaining the OS
    // title bar. Keep the separately requested taskbar/app-icon label on the independently
    // addressable tray surface; platforms that mirror the window title still behave natively.
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
    let script = service_toast_overlay_script(message, 2600)?;
    webview
        .eval(script)
        .map_err(|error| format!("Unable to show service overlay toast: {error}"))
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
        }))
        .map_err(|error| format!("Unable to serialize build information: {error}"))?;
        std::fs::write(PathBuf::from(path), payload)
            .map_err(|error| format!("Unable to write build information: {error}"))?;
        return Ok(true);
    }
    Ok(false)
}

fn main() {
    match write_build_info_if_requested() {
        Ok(true) => return,
        Ok(false) => {}
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(2);
        }
    }

    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(
            tauri_plugin_window_state::Builder::new()
                .with_state_flags(persisted_window_state_flags())
                .with_filter(|label| label == "main")
                .with_filename("window-state.json")
                .build(),
        )
        .manage(AppState::default())
        .setup(|app| {
            if let Err(error) = migrate_legacy_application_identity(app.handle()) {
                eprintln!("Unable to migrate Tauridium application data to the current application identity: {error}");
            }

            // Cache app settings in memory for the poller, shutdown handling, and related logic.
            *app.state::<AppState>().settings.lock().unwrap() =
                read_app_settings_value(app.handle());
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
            if let Some(win) = app.get_window("main") {
                win.on_window_event(move |event| match event {
                    WindowEvent::Resized(_) => reposition_active(&handle),
                    // When focus returns (for example after closing devtools), reapply the
                    // layout because the service webview may have been resized and
                    // overlapped the sidebar.
                    WindowEvent::Focused(true) => reposition_active(&handle),
                    WindowEvent::CloseRequested { api, .. } => {
                        // Persist geometry/state before either hiding to tray or allowing a real close.
                        save_main_window_state(&handle);
                        // Close to tray: hide instead of quitting; otherwise quit.
                        let close_to_tray = handle
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

            // Menu-bar/tray icon: show/quit; left click toggles the window.
            let show = MenuItem::with_id(app, "show", "Show Tauridium", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &quit])?;
            let mut tray = TrayIconBuilder::with_id("main-tray")
                .tooltip("Tauridium")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => show_main(app),
                    "quit" => {
                        save_main_window_state(app);
                        app.exit(0);
                    }
                    _ => {}
                })
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
            if let Some(icon) = app.default_window_icon().cloned() {
                tray = tray.icon(icon);
            }
            tray.build(app)?;

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
                        "open-project-homepage" => open_external(PROJECT_HOMEPAGE),
                        "open-project-source" => open_external(PROJECT_SOURCE_CODE),
                        "open-author-homepage" => open_external(AUTHOR_HOMEPAGE),
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

            // Request notification permission at startup.
            // Note: no-op on macOS desktop (the OS manages permission itself); effective
            // on mobile, Windows, and signed .app builds.
            if let Ok(state) = app.notification().permission_state() {
                if state != PermissionState::Granted {
                    let _ = app.notification().request_permission();
                }
            }
            // The main window is configured hidden so fullscreen/maximized restoration happens
            // off-screen. Reveal it only after restoration unless startup-in-background is enabled.
            let start_minimized = read_app_settings_value(app.handle())
                .get("startMinimized")
                .and_then(Value::as_bool)
                .unwrap_or(false);
            reveal_main_window_after_startup_restore(app.handle(), start_minimized);

            start_badge_poller(app.handle().clone());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            login,
            start_local_session,
            restore_session,
            get_services,
            get_workspaces,
            show_service,
            preload_service,
            get_service_icon,
            copy_service_icon_cache,
            fetch_workspace_icon_url,
            hide_all_services,
            close_service,
            set_sidebar_width,
            set_presentation_titles,
            close_services,
            logout,
            set_service_flags,
            update_service,
            create_service,
            create_custom_website_service,
            delete_service,
            clear_service_cache,
            clear_sandbox,
            list_recipes,
            get_recipe_storage_info,
            save_custom_recipe,
            import_custom_recipe,
            create_workspace,
            update_workspace,
            delete_workspace,
            get_app_settings,
            set_service_order,
            set_workspace_order,
            sync_services_menu,
            set_app_settings,
            export_backup,
            create_automatic_backup,
            restore_backup,
            export_portable_bundle,
            get_audit_log,
            export_audit_log,
            clear_audit_log,
            open_external_url,
            get_app_metadata,
            reload_active_service_command,
            reload_app_command,
            show_service_toast_overlay,
            toggle_devtools_command
        ])
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
    fn patch_0504_hibernation_remains_disabled_by_default() {
        let defaults = default_app_settings_value();
        assert_eq!(defaults["hibernationTimer"], json!(0));
        assert_eq!(defaults["preloadServices"], json!(true));
    }

    #[test]
    fn service_toast_overlay_script_encodes_untrusted_text_without_page_global() {
        let message = "quote \" and newline\n);alert(1)//";
        let encoded = serde_json::to_string(message).unwrap();
        let script = service_toast_overlay_script(message, 2600).unwrap();

        assert!(script.contains(&format!(")({encoded},2600);")));
        assert!(!script.contains(message));
        assert!(!script.contains("window.__tauridiumShowToast"));
        assert!(script.contains("attachShadow"));
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
    fn automatic_backup_settings_accept_only_supported_schedule_and_retention() {
        let mut settings = default_app_settings_value();
        assert!(validate_app_settings_value(&settings).is_ok());
        settings["automaticBackupSchedule"] = json!("hourly");
        assert!(validate_app_settings_value(&settings).is_err());
        settings["automaticBackupSchedule"] = json!("daily");
        settings["automaticBackupRetention"] = json!(0);
        assert!(validate_app_settings_value(&settings).is_err());
        settings["automaticBackupRetention"] = json!(365);
        assert!(validate_app_settings_value(&settings).is_ok());
    }

    #[test]
    fn feature_0413_settings_validate_workspace_quick_switch_order_and_recency() {
        let mut settings = default_app_settings_value();
        settings["workspaceQuickSwitchOrder"] = json!("recent");
        settings["workspaceLastUsed"] = json!({"workspace-a": 1_766_000_000_000_f64});
        assert!(validate_app_settings_value(&settings).is_ok());

        settings["workspaceQuickSwitchOrder"] = json!("unsupported");
        assert!(validate_app_settings_value(&settings).is_err());
        settings["workspaceQuickSwitchOrder"] = json!("custom");
        settings["workspaceLastUsed"] = json!({"": 1});
        assert!(validate_app_settings_value(&settings).is_err());
        settings["workspaceLastUsed"] = json!({"workspace-a": -1});
        assert!(validate_app_settings_value(&settings).is_err());
    }

    #[test]
    fn feature_0503_settings_validate_workspace_startup_preferences() {
        let mut settings = default_app_settings_value();
        assert_eq!(settings["defaultWorkspaceId"], json!(""));
        assert_eq!(settings["restoreLastWorkspaceOnStartup"], json!(false));
        assert_eq!(settings["lastWorkspaceId"], json!(""));

        settings["defaultWorkspaceId"] = json!("workspace-a");
        settings["restoreLastWorkspaceOnStartup"] = json!(true);
        settings["lastWorkspaceId"] = json!("workspace-b");
        assert!(validate_app_settings_value(&settings).is_ok());

        settings["restoreLastWorkspaceOnStartup"] = json!("yes");
        assert!(validate_app_settings_value(&settings).is_err());
        settings["restoreLastWorkspaceOnStartup"] = json!(true);
        settings["lastWorkspaceId"] = json!("   ");
        assert!(validate_app_settings_value(&settings).is_err());
    }

    #[test]
    fn feature_0424_settings_validate_workspace_icons() {
        let mut settings = default_app_settings_value();
        settings["workspaceIcons"] = json!({
            "workspace-a": "https://example.com/icon.svg",
            "workspace-b": "data:image/svg+xml;base64,PHN2Zy8+"
        });
        assert!(validate_app_settings_value(&settings).is_ok());

        settings["workspaceIcons"] = json!({ "workspace-a": "javascript:alert(1)" });
        assert!(validate_app_settings_value(&settings).is_err());
        settings["workspaceIcons"] = json!({ "": "https://example.com/icon.svg" });
        assert!(validate_app_settings_value(&settings).is_err());
    }

    #[test]
    fn feature_0428_settings_validate_service_icon_inversions() {
        let mut settings = default_app_settings_value();
        settings["serviceIconInversions"] = json!({
            "service-a": true,
            "service-b": false
        });
        assert!(validate_app_settings_value(&settings).is_ok());

        settings["serviceIconInversions"] = json!({ "": true });
        assert!(validate_app_settings_value(&settings).is_err());
        settings["serviceIconInversions"] = json!({ "service-a": "yes" });
        assert!(validate_app_settings_value(&settings).is_err());
    }

    #[test]
    fn feature_0425_download_settings_validate_and_resolve_precedence() {
        let mut settings = default_app_settings_value();
        settings["downloadDirectory"] = json!(r"C:\Users\Akito\Downloads");
        settings["askEachDownload"] = json!(false);
        settings["workspaceDownloadSettings"] = json!({
            "workspace-a": { "directory": r"D:\Workspace", "askEachDownload": true }
        });
        settings["serviceDownloadSettings"] = json!({
            "service-a": { "directory": r"E:\Service", "askEachDownload": false }
        });
        assert!(validate_app_settings_value(&settings).is_ok());

        assert_eq!(
            effective_download_preferences(&settings, "service-a", Some("workspace-a")),
            EffectiveDownloadPreferences {
                directory: r"E:\Service".into(),
                ask_each_download: false
            },
        );
        assert_eq!(
            effective_download_preferences(&settings, "service-b", Some("workspace-a")),
            EffectiveDownloadPreferences {
                directory: r"D:\Workspace".into(),
                ask_each_download: true
            },
        );
        assert_eq!(
            effective_download_preferences(&settings, "service-b", None),
            EffectiveDownloadPreferences {
                directory: r"C:\Users\Akito\Downloads".into(),
                ask_each_download: false
            },
        );

        settings["serviceDownloadSettings"] =
            json!({ "service-a": { "directory": 3, "askEachDownload": false } });
        assert!(validate_app_settings_value(&settings).is_err());
        settings["serviceDownloadSettings"] =
            json!({ "service-a": { "directory": "", "askEachDownload": "yes" } });
        assert!(validate_app_settings_value(&settings).is_err());
    }

    #[test]
    fn feature_0425_download_uses_server_suggested_filename_and_sanitizes_safely() {
        let opaque =
            Url::parse("https://mail.example.test/api/attachments/download?id=123").unwrap();
        assert_eq!(
            suggested_download_filename(Path::new("/tmp/quarterly-report.zip"), &opaque),
            "quarterly-report.zip",
        );
        assert_eq!(
            sanitize_download_filename("../bad:name?.zip"),
            ".._bad_name_.zip"
        );
        assert_eq!(sanitize_download_filename("NUL.txt"), "_NUL.txt");
        assert_eq!(sanitize_download_filename("report.zip. "), "report.zip");
        assert_eq!(
            suggested_download_filename(Path::new(""), &opaque),
            "download"
        );
    }

    #[test]
    fn autostart_application_is_idempotent_when_os_state_already_matches() {
        assert!(!autostart_needs_update(false, false));
        assert!(!autostart_needs_update(true, true));
        assert!(autostart_needs_update(false, true));
        assert!(autostart_needs_update(true, false));
    }

    #[test]
    fn feature_0404_settings_validate_backup_retention_and_relative_sidebar_width() {
        let mut settings = default_app_settings_value();
        settings["sidebarWidthMode"] = json!("percent");
        settings["sidebarWidthPercent"] = json!(28);
        settings["automaticBackupDirectory"] = json!(r"C:\Backups\Tauridium");
        settings["automaticBackupRetentionMode"] = json!("tiered");
        settings["automaticBackupMaxAgeDays"] = json!(3650);
        assert!(validate_app_settings_value(&settings).is_ok());

        settings["sidebarWidthPercent"] = json!(50);
        assert!(validate_app_settings_value(&settings).is_err());
        settings["sidebarWidthPercent"] = json!(20);
        settings["automaticBackupRetentionMode"] = json!("unknown");
        assert!(validate_app_settings_value(&settings).is_err());
        settings["automaticBackupRetentionMode"] = json!("age");
        settings["automaticBackupMaxAgeDays"] = json!(0);
        assert!(validate_app_settings_value(&settings).is_err());
    }

    #[test]
    fn app_settings_merge_preserves_existing_keybindings_and_adds_new_defaults() {
        let merged = merge_app_settings_value(&json!({
            "keybindings": {
                "addService": "Alt+N",
                "quickWorkspaceSwitch": "Ctrl+K Ctrl+W"
            }
        }))
        .unwrap();

        assert_eq!(merged["keybindings"]["addService"], json!("Alt+N"));
        assert_eq!(
            merged["keybindings"]["quickWorkspaceSwitch"],
            json!("Ctrl+K Ctrl+W")
        );
        assert_eq!(merged["keybindings"]["addWorkspace"], json!("Ctrl+Shift+N"));
        assert_eq!(
            merged["keybindings"]["toggleSidebar"],
            json!("Ctrl+Shift+B")
        );
        assert_eq!(merged["sidebarCollapsed"], json!(false));
        assert!(validate_app_settings_value(&merged).is_ok());
    }

    #[test]
    fn patch_0605_title_settings_default_and_validate_safely() {
        let defaults = merge_app_settings_value(&json!({})).unwrap();
        assert_eq!(defaults["showWorkspaceInWindowTitle"], json!(true));
        assert_eq!(defaults["showWorkspaceInTaskbarTitle"], json!(false));
        assert_eq!(defaults["customTitleTemplatesEnabled"], json!(false));
        assert_eq!(
            defaults["windowTitleTemplate"],
            json!("{app} ~ {workspace}")
        );
        assert_eq!(
            defaults["taskbarTitleTemplate"],
            json!("{app} ~ {workspace}")
        );
        assert!(validate_app_settings_value(&defaults).is_ok());
        assert!(validate_native_title("Tauridium ~ Engineering", "Window title").is_ok());
        assert!(validate_native_title("", "Window title").is_err());

        let mut invalid = defaults.clone();
        invalid["windowTitleTemplate"] = json!("x".repeat(241));
        assert!(validate_app_settings_value(&invalid).is_err());
        invalid = defaults;
        invalid["taskbarTitleTemplate"] = json!("bad\nvalue");
        assert!(validate_app_settings_value(&invalid).is_err());
    }

    #[test]
    fn patch_0602_sidebar_spacing_defaults_and_bounds_are_safe() {
        let defaults = merge_app_settings_value(&json!({})).unwrap();
        assert_eq!(defaults["collapsedServiceSpacing"], json!(2));
        assert_eq!(defaults["expandedServiceSpacing"], json!(2));

        let mut settings = defaults.clone();
        settings["collapsedServiceSpacing"] = json!(24);
        settings["expandedServiceSpacing"] = json!(24);
        assert!(validate_app_settings_value(&settings).is_ok());

        settings["collapsedServiceSpacing"] = json!(1);
        assert!(validate_app_settings_value(&settings).is_err());
        settings["collapsedServiceSpacing"] = json!(2);
        settings["expandedServiceSpacing"] = json!(25);
        assert!(validate_app_settings_value(&settings).is_err());
    }

    #[test]
    fn patch_0601_sidebar_startup_preferences_default_and_restore_last() {
        let defaults = merge_app_settings_value(&json!({})).unwrap();
        assert_eq!(defaults["defaultSidebarCollapsed"], json!(false));
        assert_eq!(defaults["restoreLastSidebarStateOnStartup"], json!(true));
        assert!(!resolve_startup_sidebar_collapsed(&defaults));

        let restore_last = merge_app_settings_value(&json!({
            "defaultSidebarCollapsed": false,
            "restoreLastSidebarStateOnStartup": true,
            "sidebarCollapsed": true
        }))
        .unwrap();
        assert!(resolve_startup_sidebar_collapsed(&restore_last));

        let use_default = merge_app_settings_value(&json!({
            "defaultSidebarCollapsed": true,
            "restoreLastSidebarStateOnStartup": false,
            "sidebarCollapsed": false
        }))
        .unwrap();
        assert!(resolve_startup_sidebar_collapsed(&use_default));
    }

    #[test]
    fn sidebar_service_drag_reorder_defaults_on_and_preserves_saved_opt_out() {
        let defaults = merge_app_settings_value(&json!({})).unwrap();
        assert_eq!(defaults["sidebarServiceDragReorder"], json!(true));

        let opted_out = merge_app_settings_value(&json!({
            "sidebarServiceDragReorder": false
        }))
        .unwrap();
        assert_eq!(opted_out["sidebarServiceDragReorder"], json!(false));
        assert!(validate_app_settings_value(&opted_out).is_ok());

        let mut invalid = default_app_settings_value();
        invalid["sidebarServiceDragReorder"] = json!("yes");
        assert!(validate_app_settings_value(&invalid).is_err());
    }

    #[test]
    fn feature_0400_settings_validate_oled_colors_keybindings_and_sandboxes() {
        let mut settings = default_app_settings_value();
        settings["theme"] = json!("oled");
        settings["accentColor"] = json!("#123abc");
        settings["customAccentColors"] = json!(["#000000", "#ffffff"]);
        settings["customSidebarWidths"] = json!([180, 276, 320]);
        settings["keybindings"]["quickServiceSwitch"] = json!("Ctrl+K Ctrl+S");
        settings["sandboxes"] = json!([{ "id": "proton", "name": "Proton" }]);
        settings["serviceSandboxes"] = json!({ "service-a": "proton", "service-b": "proton" });
        assert!(validate_app_settings_value(&settings).is_ok());

        settings["customAccentColors"] = json!(["black"]);
        assert!(validate_app_settings_value(&settings).is_err());
        settings["customAccentColors"] = json!([]);
        settings["keybindings"]["quickServiceSwitch"] = json!("Ctrl+K Ctrl+S Ctrl+P");
        assert!(validate_app_settings_value(&settings).is_err());
        settings["keybindings"]["quickServiceSwitch"] = json!("Ctrl+S");
        settings["serviceSandboxes"] = json!({ "service-a": "missing" });
        assert!(validate_app_settings_value(&settings).is_err());
    }

    #[test]
    fn shared_sandbox_storage_identifier_is_stable_and_distinct() {
        let isolated = storage_identifier("00112233-4455-6677-8899-aabbccddeeff", None).unwrap();
        let shared_a = storage_identifier("service-a", Some("proton")).unwrap();
        let shared_b = storage_identifier("service-b", Some("proton")).unwrap();
        let other = storage_identifier("service-a", Some("other")).unwrap();
        assert_eq!(shared_a, shared_b);
        assert_ne!(shared_a, isolated);
        assert_ne!(shared_a, other);
    }

    #[test]
    fn shared_sandbox_storage_is_stable_and_distinct_from_isolated_storage() {
        let root = Path::new("/tmp/tauridium-test");
        let isolated = storage_directory(root, "service-a", None);
        let shared_a = storage_directory(root, "service-a", Some("proton"));
        let shared_b = storage_directory(root, "service-b", Some("proton"));
        let other = storage_directory(root, "service-a", Some("other"));
        assert_eq!(isolated, root.join("sessions").join("service-a"));
        assert_eq!(shared_a, shared_b);
        assert_ne!(shared_a, isolated);
        assert_ne!(shared_a, other);
        assert!(shared_a
            .file_name()
            .unwrap()
            .to_string_lossy()
            .starts_with("sandbox-"));
    }

    #[test]
    fn service_shortcut_bridge_captures_all_configured_bindings_and_honours_overrides() {
        let settings = json!({
            "captureServiceShortcuts": true,
            "serviceShortcutCaptureOverrides": { "website-first": false, "forced": true },
            "keybindings": {
                "toggleDevtools": "Ctrl+Alt+I",
                "quickServiceSwitch": "Ctrl+K Ctrl+S"
            }
        });
        let nonce = "0123456789abcdef";
        let script = service_shortcut_bridge_js(&settings, "default", nonce)
            .expect("global shortcut capture should inject the bridge");
        assert!(script.contains("Ctrl+Alt+I"));
        assert!(script.contains("Ctrl+K Ctrl+S"));
        assert!(script.contains("tauridium-shortcut://bridge/"));
        assert!(script.contains(nonce));
        assert!(script.contains("stopImmediatePropagation"));
        assert!(!script.contains("__TAURI_INTERNALS__"));
        assert!(service_shortcut_bridge_js(&settings, "website-first", nonce).is_none());
        assert!(service_shortcut_bridge_js(&settings, "forced", nonce).is_some());

        let valid = Url::parse(&format!(
            "tauridium-shortcut://bridge/{nonce}/toggleDevtools"
        ))
        .unwrap();
        assert_eq!(
            service_shortcut_action_from_url(&valid, nonce).as_deref(),
            Some("toggleDevtools")
        );
        let wrong_nonce =
            Url::parse("tauridium-shortcut://bridge/not-the-nonce/toggleDevtools").unwrap();
        assert!(service_shortcut_action_from_url(&wrong_nonce, nonce).is_none());
        let unsupported = Url::parse(&format!(
            "tauridium-shortcut://bridge/{nonce}/deleteEverything"
        ))
        .unwrap();
        assert!(service_shortcut_action_from_url(&unsupported, nonce).is_none());

        let global_off = json!({
            "captureServiceShortcuts": false,
            "serviceShortcutCaptureOverrides": { "forced": true },
            "keybindings": { "reloadService": "Ctrl+R" }
        });
        assert!(service_shortcut_bridge_js(&global_off, "default", nonce).is_none());
        assert!(service_shortcut_bridge_js(&global_off, "forced", nonce).is_some());
    }

    #[test]
    fn service_shortcut_nonces_are_unique_and_fixed_width() {
        let first = next_service_shortcut_nonce("service-a");
        let second = next_service_shortcut_nonce("service-a");
        assert_eq!(first.len(), 64);
        assert_eq!(second.len(), 64);
        assert!(first.bytes().all(|byte| byte.is_ascii_hexdigit()));
        assert!(second.bytes().all(|byte| byte.is_ascii_hexdigit()));
        assert_ne!(first, second);
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
    fn ensure_scheme_prepends_https_when_missing() {
        assert_eq!(ensure_scheme("example.com"), "https://example.com");
        assert_eq!(ensure_scheme("https://example.com"), "https://example.com");
        assert_eq!(ensure_scheme("http://example.com"), "http://example.com");
    }

    #[test]
    fn resolve_url_uses_plain_service_url() {
        let cfg = json!({ "config": { "serviceURL": "https://web.whatsapp.com" } });
        assert_eq!(
            resolve_url(&cfg, None, None, &CustomUrlTemplateValues::default()).unwrap(),
            "https://web.whatsapp.com"
        );
    }

    #[test]
    fn resolve_url_honours_custom_url_only_when_allowed() {
        let cfg = json!({ "config": { "serviceURL": "https://default", "hasCustomUrl": true } });
        assert_eq!(
            resolve_url(
                &cfg,
                Some("chat.example.fr"),
                None,
                &CustomUrlTemplateValues::default()
            )
            .unwrap(),
            "https://chat.example.fr"
        );
        // Empty custom URL falls back to serviceURL.
        assert_eq!(
            resolve_url(&cfg, Some(""), None, &CustomUrlTemplateValues::default()).unwrap(),
            "https://default"
        );
        // A recipe without hasCustomUrl ignores the custom URL.
        let cfg2 = json!({ "config": { "serviceURL": "https://default" } });
        assert_eq!(
            resolve_url(
                &cfg2,
                Some("chat.example.fr"),
                None,
                &CustomUrlTemplateValues::default()
            )
            .unwrap(),
            "https://default"
        );
    }

    #[test]
    fn resolve_url_substitutes_team_id() {
        let cfg =
            json!({ "config": { "serviceURL": "https://{teamId}.slack.com", "hasTeamId": true } });
        assert_eq!(
            resolve_url(
                &cfg,
                None,
                Some("acme"),
                &CustomUrlTemplateValues::default()
            )
            .unwrap(),
            "https://acme.slack.com"
        );
    }

    #[test]
    fn resolve_url_uses_recipe_team_url_and_custom_placeholders() {
        let cfg = json!({
            "config": {
                "serviceURL": "https://opencode.ai/go",
                "teamURL": "https://opencode.ai/workspace/{teamId}/go",
                "hasTeamId": true,
                "hasCustomUrl": true
            }
        });
        assert_eq!(
            resolve_url(
                &cfg,
                None,
                Some("wrk_01ABC123EXAMPLE"),
                &CustomUrlTemplateValues::default(),
            )
            .unwrap(),
            "https://opencode.ai/workspace/wrk_01ABC123EXAMPLE/go"
        );

        let templates = CustomUrlTemplateValues {
            enabled: true,
            custom_id_1: "alpha".into(),
            custom_id_2: "beta".into(),
        };
        assert_eq!(
            resolve_url(
                &cfg,
                Some("https://example.com/{{custom_id_1}}/go?slot={{custom_id_2}}"),
                None,
                &templates,
            )
            .unwrap(),
            "https://example.com/alpha/go?slot=beta"
        );
    }

    #[test]
    fn custom_url_placeholders_require_values_when_enabled() {
        let cfg = json!({ "config": { "serviceURL": "https://default", "hasCustomUrl": true } });
        let templates = CustomUrlTemplateValues {
            enabled: true,
            custom_id_1: String::new(),
            custom_id_2: String::new(),
        };
        assert!(resolve_url(
            &cfg,
            Some("https://example.com/{{custom_id_1}}"),
            None,
            &templates,
        )
        .is_err());
    }

    #[test]
    fn resolve_url_errors_without_service_url() {
        assert!(resolve_url(
            &json!({ "config": {} }),
            None,
            None,
            &CustomUrlTemplateValues::default()
        )
        .is_err());
        assert!(resolve_url(&json!({}), None, None, &CustomUrlTemplateValues::default()).is_err());
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

    #[test]
    fn uuid_to_bytes_parses_valid_and_rejects_bad() {
        let b = uuid_to_bytes("00112233-4455-6677-8899-aabbccddeeff").unwrap();
        assert_eq!(b[0], 0x00);
        assert_eq!(b[1], 0x11);
        assert_eq!(b[15], 0xff);
        // 32 hexadecimal characters without hyphens are accepted too.
        assert!(uuid_to_bytes("00112233445566778899aabbccddeeff").is_some());
        // wrong length / invalid hexadecimal.
        assert!(uuid_to_bytes("abc").is_none());
        assert!(uuid_to_bytes("zz112233-4455-6677-8899-aabbccddeeff").is_none());
    }
}
