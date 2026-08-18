#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backup;
mod local_profile;
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
use std::sync::{LazyLock, Mutex};
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
use tauri_plugin_window_state::{AppHandleExt as _, StateFlags, WindowExt as _};

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
// Logical sidebar width; must match the shell CSS.
const SIDEBAR_W: f64 = 240.0;
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
    sidebar_w: Mutex<f64>,           // sidebar width (initialized during setup, default 240)
    desired_active: Mutex<Option<String>>, // last requested service (prevents focus stealing during switches)
    inflight: Mutex<HashSet<String>>,      // webviews being created (prevents duplicate add_child)
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

fn build_native_application_menu(
    app: &AppHandle,
    services: &[NativeServiceMenuEntry],
) -> tauri::Result<Menu<Wry>> {
    let settings_item = MenuItem::with_id(app, "open-settings", "Settings…", true, None::<&str>)?;
    let add_service_item = MenuItem::with_id(
        app,
        "open-add-service",
        "Add Service…",
        true,
        Some("CmdOrCtrl+N"),
    )?;
    let app_sub = Submenu::with_items(
        app,
        "Tauridium",
        true,
        &[
            &settings_item,
            &add_service_item,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::hide(app, None)?,
            &PredefinedMenuItem::hide_others(app, None)?,
            &PredefinedMenuItem::show_all(app, None)?,
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
        Some("CmdOrCtrl+R"),
    )?;
    let reload_app_item = MenuItem::with_id(
        app,
        "reload-app",
        "Reload Tauridium",
        true,
        Some("CmdOrCtrl+Shift+R"),
    )?;
    let devtools = MenuItem::with_id(
        app,
        "toggle-devtools",
        "Toggle Developer Tools",
        true,
        Some("CmdOrCtrl+Alt+I"),
    )?;
    let view = Submenu::with_items(
        app,
        "View",
        true,
        &[
            &reload_svc,
            &reload_app_item,
            &PredefinedMenuItem::separator(app)?,
            &devtools,
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
    Menu::with_items(app, &[&app_sub, &edit, &view, &services_menu])
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
fn write_atomic(path: &Path, contents: &str) -> std::io::Result<()> {
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
fn resolve_url(
    cfg: &Value,
    custom_url: Option<&str>,
    team: Option<&str>,
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
        if let Some(u) = custom_url.filter(|u| !u.is_empty()) {
            return Ok(ensure_scheme(u));
        }
    }
    if has_team {
        if let Some(t) = team.filter(|t| !t.is_empty()) {
            return Ok(service_url.replace("{teamId}", t));
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

// Purge a service's persistent storage (cookies, localStorage, session). Call this
// AFTER closing its webview. macOS: delete the WKWebsiteDataStore by identifier
// (wry API, main thread required); elsewhere delete the data_directory folder.
#[cfg(target_os = "macos")]
fn purge_service_storage(app: &AppHandle, service_id: &str) {
    use wry::WebViewExtDarwin;
    if let Some(uuid) = uuid_to_bytes(service_id) {
        let _ = app.run_on_main_thread(move || {
            <wry::WebView as WebViewExtDarwin>::remove_data_store(&uuid, |_| {});
        });
    }
}

#[cfg(not(target_os = "macos"))]
fn purge_service_storage(app: &AppHandle, service_id: &str) {
    if let Ok(dir) = app.path().app_data_dir() {
        let _ = std::fs::remove_dir_all(dir.join("sessions").join(service_id));
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

// Open a URL in the system's default browser outside the app. Best effort:
// ignore failure (no browser, spawn denied, etc.). The caller already filters the scheme.
fn open_external(url: &str) {
    #[cfg(target_os = "macos")]
    let _ = std::process::Command::new("open").arg(url).spawn();
    #[cfg(target_os = "windows")]
    let _ = std::process::Command::new("cmd")
        .args(["/C", "start", "", url])
        .spawn();
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
    dark: Option<DarkOpts>,
    pos: LogicalPosition<f64>,
    size: LogicalSize<f64>,
) -> Result<(), String> {
    let cfg = recipe_config(win.app_handle(), app_data, recipe_id).await?;
    let url_str = resolve_url(&cfg, custom_url, team)?;
    let url = Url::parse(&url_str).map_err(|e| format!("Invalid URL {url_str}: {e}"))?;
    let host = url.host_str().unwrap_or("").to_ascii_lowercase();
    // Recipe runtime (DOM unread-count scraping -> __pakeUnread), best effort.
    let runtime = recipe_webview_js(win.app_handle(), app_data, recipe_id)
        .await
        .map(|js| format!("{RECIPE_PREAMBLE}{js}{RECIPE_SUFFIX}"));
    let label = format!("svc-{service_id}");

    // User agent precedence: per-service override, global setting, Google compatibility UA, then SERVICE_UA.
    let ua = {
        let per_service = user_agent_pref.map(str::trim).filter(|s| !s.is_empty());
        if let Some(p) = per_service {
            p.to_string()
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
                global
            } else if is_google_auth_host(&host) {
                GOOGLE_CHROMELESS_UA.to_string()
            } else {
                SERVICE_UA.to_string()
            }
        }
    };

    // IPC shim injected into ALL services (Synology Chat and others depend on it).
    let mut builder = WebviewBuilder::new(label, WebviewUrl::External(url))
        .user_agent(&ua)
        .initialization_script(IPC_SHIM_JS)
        // Prevent duplicated keystrokes caused by duplicate native WKWebView `textInput` events (see Discord search).
        .initialization_script(KEY_DEDUP_JS)
        // `target="_blank"` links / `window.open`: without a handler WKWebView ignores them
        // silently (the click appears to do nothing). Reproduce Ferdium behavior:
        //  - sized popup (window.open with width/height, typically an OAuth login)
        //    -> real in-app window with shared session/cookies so the flow is not broken;
        //  - content link (without dimensions) -> system browser, webview unchanged.
        .on_new_window(
            |url: Url, features: NewWindowFeatures| -> NewWindowResponse<Wry> {
                if features.size().is_some() {
                    return NewWindowResponse::Allow;
                }
                if matches!(url.scheme(), "http" | "https" | "mailto") {
                    open_external(url.as_str());
                }
                NewWindowResponse::Deny
            },
        );
    // Emit loading state to the shell (spinner transitions from loading to ready).
    let sid_evt = service_id.to_string();
    builder = builder.on_page_load(move |wv, payload| {
        let status = match payload.event() {
            PageLoadEvent::Started => "loading",
            PageLoadEvent::Finished => "ready",
        };
        let _ = wv.app_handle().emit(
            "svc-status",
            serde_json::json!({ "id": sid_evt, "status": status }),
        );
    });
    // Downloads (Download context action, `download` links, etc.): WKWebView has no
    // default handler, so otherwise nothing happens. Save into the Downloads directory
    // and notify when complete (on macOS the API does not expose the final path).
    builder = builder.on_download(|webview, event| {
        match event {
            DownloadEvent::Requested { url, destination } => {
                let dir = webview
                    .app_handle()
                    .path()
                    .download_dir()
                    .or_else(|_| webview.app_handle().path().home_dir())
                    .unwrap_or_else(|_| PathBuf::from("."));
                *destination = unique_download_path(&dir, &download_filename(&url));
            }
            DownloadEvent::Finished {
                url, success: true, ..
            } => {
                let _ = webview
                    .app_handle()
                    .notification()
                    .builder()
                    .title("Tauridium")
                    .body(format!("Downloaded \"{}\"", download_filename(&url)))
                    .show();
            }
            _ => {}
        }
        true // Allow the download.
    });
    // Per-service storage isolation: macOS -> data_store_identifier (data_directory
    // ignored); Windows/Linux use a dedicated data_directory to avoid shared sessions.
    #[cfg(target_os = "macos")]
    {
        let store = uuid_to_bytes(service_id).ok_or("serviceId is not a UUID")?;
        builder = builder.data_store_identifier(store);
    }
    #[cfg(not(target_os = "macos"))]
    {
        let dir = app_data.join("sessions").join(service_id);
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
    dark: Option<DarkSettings>,
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
        dark,
    } = request;
    let dark = dark.and_then(DarkSettings::into_opts);
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

    // Display the requested service and hide the others.
    let created: Vec<String> = state.created.lock().unwrap().iter().cloned().collect();
    for sid in created {
        if let Some(wv) = app.get_webview(&format!("svc-{sid}")) {
            if sid == service_id {
                let _ = wv.show();
            } else {
                let _ = wv.hide();
            }
        }
    }
    *state.active.lock().unwrap() = Some(service_id);
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
        dark,
    } = request;
    let dark = dark.and_then(DarkSettings::into_opts);
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
    // Off-screen: the webview loads the page without covering the active service.
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
        dark,
        offscreen,
        size,
    )
    .await;
    state.inflight.lock().unwrap().remove(&service_id);
    res?;
    if let Some(wv) = app.get_webview(&format!("svc-{service_id}")) {
        let _ = wv.hide();
    }
    Ok(())
}

fn hide_service_webviews(app: &AppHandle, state: &AppState) {
    let created: Vec<String> = state.created.lock().unwrap().iter().cloned().collect();
    for sid in created {
        if let Some(wv) = app.get_webview(&format!("svc-{sid}")) {
            let _ = wv.hide();
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
    state.unread.lock().unwrap().remove(&service_id);
    if state.active.lock().unwrap().as_deref() == Some(service_id.as_str()) {
        *state.active.lock().unwrap() = None;
    }
}

// Change the sidebar width and reposition the active service webview.
#[tauri::command]
fn set_sidebar_width(app: AppHandle, state: State<'_, AppState>, width: f64) {
    *state.sidebar_w.lock().unwrap() = width.clamp(160.0, 420.0);
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
        let mut profile = state.local_profile.lock().unwrap();
        let mut next = profile.clone();
        let updated = next.update_service(&service_id, &patch)?;
        save_local_profile(&app, &next)?;
        *profile = next;
        return Ok(updated);
    }
    let (base, token) = current(&state)?;
    let res = HTTP
        .clone()
        .put(format!("{base}/v1/service/{service_id}"))
        .bearer_auth(&token)
        .header(reqwest::header::USER_AGENT, API_UA)
        .json(&patch)
        .send()
        .await
        .map_err(|e| e.to_string())?;
    if !res.status().is_success() {
        return Err(format!("Service update failed: HTTP {}", res.status()));
    }
    res.json().await.map_err(|e| e.to_string())
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
        let mut profile = state.local_profile.lock().unwrap();
        let mut next = profile.clone();
        let service = next.create_service(name, recipe_id, icon_url, local_recipe)?;
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
    service = next.update_service(&service_id, &serde_json::json!({ "customUrl": url }))?;
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
    // Purge the service session/cookies from disk to avoid stale data and privacy leakage.
    purge_service_storage(&app, &service_id);
    Ok(())
}

// Clear a service cache/session WITHOUT deleting it from the server: close its webview
// and purge its storage. The service will reopen cleanly and signed out on next access.
#[tauri::command]
fn clear_service_cache(app: AppHandle, state: State<'_, AppState>, service_id: String) {
    if let Some(wv) = app.get_webview(&format!("svc-{service_id}")) {
        let _ = wv.close();
    }
    state.created.lock().unwrap().remove(&service_id);
    state.unread.lock().unwrap().remove(&service_id);
    if state.active.lock().unwrap().as_deref() == Some(service_id.as_str()) {
        *state.active.lock().unwrap() = None;
    }
    if state.desired_active.lock().unwrap().as_deref() == Some(service_id.as_str()) {
        *state.desired_active.lock().unwrap() = None;
    }
    purge_service_storage(&app, &service_id);
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
    serde_json::json!({
        "autostart": false,
        "startMinimized": false,
        "theme": "system",
        "accentColor": "#ffc131",
        "closeToSystemTray": true,
        "privateNotifications": false,
        "showDisabledServices": true,
        "showServiceName": true,
        "showMessageBadgeWhenMuted": true,
        "userAgentPref": "",
        "sidebarWidth": 240,
        "iconSize": 24,
        "grayscaleServices": false,
        "grayscaleDim": 50,
        "sidebarServicesLocation": "top",
        "hibernationTimer": 0,
        "preloadServices": true,
        "serviceOrder": [],
        "workspaceOrder": []
    })
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
        "grayscaleServices",
        "preloadServices",
    ] {
        if !object.get(key).is_some_and(Value::is_boolean) {
            return Err(format!("App setting {key} must be boolean"));
        }
    }
    let theme = object
        .get("theme")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !matches!(theme, "system" | "dark" | "light") {
        return Err("App setting theme is invalid".into());
    }
    let location = object
        .get("sidebarServicesLocation")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !matches!(location, "top" | "center" | "bottom") {
        return Err("App setting sidebarServicesLocation is invalid".into());
    }
    if !object.get("accentColor").is_some_and(Value::is_string)
        || !object.get("userAgentPref").is_some_and(Value::is_string)
    {
        return Err("App string settings are invalid".into());
    }
    for (key, min, max) in [
        ("sidebarWidth", 160.0, 420.0),
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

fn merge_app_settings_value(stored: &Value) -> Result<Value, String> {
    let stored = stored
        .as_object()
        .ok_or_else(|| "App settings must be a JSON object".to_string())?;
    let mut value = default_app_settings_value();
    let base = value
        .as_object_mut()
        .ok_or_else(|| "Internal app settings defaults are invalid".to_string())?;
    for (key, setting) in stored {
        base.insert(key.clone(), setting.clone());
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

fn apply_autostart_setting(app: &AppHandle, settings: &Value) -> Result<(), String> {
    let Some(enabled) = settings.get("autostart").and_then(Value::as_bool) else {
        return Ok(());
    };
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
    let mut settings = read_app_settings_value(app);
    let object = settings
        .as_object_mut()
        .ok_or_else(|| "Internal app settings state is invalid".to_string())?;
    object.insert(key.to_string(), serde_json::json!(ids));
    persist_app_settings(app, state, &settings)?;
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
        .ok_or_else(|| "App settings patch must be a JSON object".to_string())?;
    let mut value = read_app_settings_value(&app);
    let base = value
        .as_object_mut()
        .ok_or_else(|| "Internal app settings state is invalid".to_string())?;
    for (key, setting) in patch {
        base.insert(key.clone(), setting.clone());
    }
    validate_app_settings_value(&value)?;
    apply_autostart_setting(&app, &value)?;
    persist_app_settings(&app, &state, &value)?;
    Ok(value)
}

#[tauri::command]
fn export_backup(
    app: AppHandle,
    state: State<'_, AppState>,
    path: String,
) -> Result<backup::BackupSummary, String> {
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

#[tauri::command]
fn restore_backup(
    app: AppHandle,
    state: State<'_, AppState>,
    path: String,
) -> Result<backup::BackupSummary, String> {
    let document = backup::load(Path::new(&path))?;

    // Phase 1: validate and prepare the complete restore without changing persistent state.
    let app_settings = merge_app_settings_value(&document.app_settings())?;
    let local_profile = LocalProfile::from_value(document.local_profile())?;
    recipes::validate_custom_recipe_backups(document.custom_recipes())?;
    let previous_settings = effective_app_settings_value(&app);
    let previous_profile = state.local_profile.lock().unwrap().clone();
    let previous_recipes = recipes::backup_custom_recipes(&app)?;
    let restored_recipes =
        recipes::merge_custom_recipe_backups(&previous_recipes, document.custom_recipes())?;

    // Always create a validated recovery snapshot before the first persistent mutation. If this
    // cannot be written, abort the restore without changing any Tauridium state.
    let recovery_path = restore_recovery_backup_path(&app)?;
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

    // Phase 2: commit. Each component is atomic on its own; if any later component fails,
    // restore every prior component from the snapshot above so a backup restore is all-or-nothing.
    let commit = (|| -> Result<(), String> {
        recipes::replace_custom_recipes_exact(&app, &restored_recipes)?;
        save_local_profile(&app, &local_profile)?;
        apply_autostart_setting(&app, &app_settings)?;
        persist_app_settings(&app, &state, &app_settings)?;
        Ok(())
    })();

    if let Err(error) = commit {
        let mut rollback_errors = Vec::new();
        if let Err(rollback) = recipes::replace_custom_recipes_exact(&app, &previous_recipes) {
            rollback_errors.push(format!("recipes: {rollback}"));
        }
        if let Err(rollback) = save_local_profile(&app, &previous_profile) {
            rollback_errors.push(format!("local profile: {rollback}"));
        }
        if let Err(rollback) = apply_autostart_setting(&app, &previous_settings) {
            rollback_errors.push(format!("autostart: {rollback}"));
        }
        if let Err(rollback) = persist_app_settings(&app, &state, &previous_settings) {
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
    Ok(document
        .summary(Path::new(&path))
        .with_recovery_backup_path(&recovery_path))
}

fn persisted_window_state_flags() -> StateFlags {
    StateFlags::SIZE | StateFlags::POSITION | StateFlags::MAXIMIZED | StateFlags::FULLSCREEN
}

fn save_main_window_state(app: &AppHandle) {
    if let Err(error) = app.save_window_state(persisted_window_state_flags()) {
        eprintln!("Unable to save Tauridium window state: {error}");
    }
}

fn restore_main_window_state(window: &tauri::Window<Wry>) {
    if let Err(error) = window.restore_state(persisted_window_state_flags()) {
        eprintln!("Unable to restore Tauridium window state: {error}");
    }
}

fn show_main(app: &AppHandle) {
    if let Some(w) = app.get_window("main") {
        if !w.is_visible().unwrap_or(false) {
            restore_main_window_state(&w);
        }
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
            restore_main_window_state(&w);
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
            // Cache app settings in memory for the poller, shutdown handling, and related logic.
            *app.state::<AppState>().settings.lock().unwrap() =
                read_app_settings_value(app.handle());
            {
                let st = app.state::<AppState>();
                let w = st
                    .settings
                    .lock()
                    .unwrap()
                    .get("sidebarWidth")
                    .and_then(Value::as_f64)
                    .unwrap_or(SIDEBAR_W)
                    .clamp(160.0, 420.0); // Prevent corrupted settings from hiding the service.
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
            let mut tray = TrayIconBuilder::new()
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

            // Native application menu: App / Edit / View / Services. The Services submenu
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
                        "toggle-devtools" => toggle_devtools(app),
                        "reload-service" => reload_active_service(app),
                        "reload-app" => reload_app(app),
                        _ => {
                            if let Some(service_id) = id.strip_prefix("goto-service:") {
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
            // Start in background: hide the window at launch.
            if read_app_settings_value(app.handle())
                .get("startMinimized")
                .and_then(Value::as_bool)
                .unwrap_or(false)
            {
                if let Some(w) = app.get_window("main") {
                    let _ = w.hide();
                }
            }

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
            hide_all_services,
            close_service,
            set_sidebar_width,
            close_services,
            logout,
            set_service_flags,
            update_service,
            create_service,
            create_custom_website_service,
            delete_service,
            clear_service_cache,
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
            restore_backup,
            open_external_url
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
            resolve_url(&cfg, None, None).unwrap(),
            "https://web.whatsapp.com"
        );
    }

    #[test]
    fn resolve_url_honours_custom_url_only_when_allowed() {
        let cfg = json!({ "config": { "serviceURL": "https://default", "hasCustomUrl": true } });
        assert_eq!(
            resolve_url(&cfg, Some("chat.example.fr"), None).unwrap(),
            "https://chat.example.fr"
        );
        // Empty custom URL falls back to serviceURL.
        assert_eq!(
            resolve_url(&cfg, Some(""), None).unwrap(),
            "https://default"
        );
        // A recipe without hasCustomUrl ignores the custom URL.
        let cfg2 = json!({ "config": { "serviceURL": "https://default" } });
        assert_eq!(
            resolve_url(&cfg2, Some("chat.example.fr"), None).unwrap(),
            "https://default"
        );
    }

    #[test]
    fn resolve_url_substitutes_team_id() {
        let cfg =
            json!({ "config": { "serviceURL": "https://{teamId}.slack.com", "hasTeamId": true } });
        assert_eq!(
            resolve_url(&cfg, None, Some("acme")).unwrap(),
            "https://acme.slack.com"
        );
    }

    #[test]
    fn resolve_url_errors_without_service_url() {
        assert!(resolve_url(&json!({ "config": {} }), None, None).is_err());
        assert!(resolve_url(&json!({}), None, None).is_err());
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
