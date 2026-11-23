//! Native service webview construction and compatibility scripts.

#[cfg(target_os = "macos")]
use super::storage::storage_identifier;
#[cfg(windows)]
use crate::browser_privacy;
use crate::local_profile::validate_recipe_id;

use super::downloads::{
    ask_download_destination, download_filename, effective_download_directory,
    effective_download_preferences, sanitize_download_filename, suggested_download_filename,
    unique_download_path,
};
use super::navigation::{recipe_config, resolve_url, service_custom_url_template_values};
use super::shortcuts::{
    next_service_shortcut_nonce, service_shortcut_action_from_url, service_shortcut_bridge_js,
};
#[cfg(not(target_os = "macos"))]
use super::storage::storage_directory;
use crate::app_settings::validation::{
    effective_service_zoom_percent, SERVICE_ZOOM_DEFAULT_PERCENT,
};
use crate::{
    distribution, download_toast, http_security, ipc_security, open_external, proton_compat,
    recipe_cache_directory, recipe_source, recipes, service_badges, service_menu,
    show_system_notification, startup_diagnostics, storage_security, write_atomic, AppState,
    API_UA, HTTP,
};
use serde_json::Value;
use std::path::Path;
use tauri::webview::DownloadEvent;
use tauri::webview::NewWindowFeatures;
use tauri::webview::NewWindowResponse;
use tauri::webview::PageLoadEvent;
use tauri::webview::WebviewBuilder;
use tauri::{
    AppHandle, Emitter, LogicalPosition, LogicalSize, Manager, State, Url, WebviewUrl, Wry,
};

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

// Minimal `Ferdium` API shim exposed to recipe webview.js files. It executes the
// recipe DOM-scraping code after document parsing. `setBadge` preserves direct and
// indirect counts for the native poller; unsupported optional helpers remain no-ops.
// Recipe errors are isolated so an incompatible recipe cannot break the page.
// Dark Reader (vendored standalone UMD build), injected per service when dark mode
// is enabled so the page is actually darkened (previously the option had no local effect).
const DARK_READER_JS: &str = include_str!("../../assets/darkreader.js");

// Per-service Dark Reader options (defaults aligned with the UI: 100/90/10).
#[derive(Clone, Copy)]
pub(super) struct DarkOpts {
    brightness: i64,
    contrast: i64,
    sepia: i64,
}

// Dark-mode settings received from the frontend (via showService/preloadService).
#[derive(serde::Deserialize)]
pub(super) struct DarkSettings {
    enabled: bool,
    brightness: Option<i64>,
    contrast: Option<i64>,
    sepia: Option<i64>,
}

impl DarkSettings {
    pub(super) fn into_opts(self) -> Option<DarkOpts> {
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
  function startRecipe(){
  try {
    var module = { exports: {} };
    var exports = module.exports;
    var __dirname = '';
    function require(m){ if(m==='path') return { join: function(){ return Array.prototype.slice.call(arguments).join('/'); } }; return {}; }
    var Ferdium = {
      setBadge: function(direct, indirect){ window.__pakeSetBadge(direct, indirect); },
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
  }
  // Initialization scripts run at document start; recipe metadata/DOM do not yet exist.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startRecipe, { once: true });
  } else {
    startRecipe();
  }
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
    let dir = recipe_cache_directory(app).ok()?;
    let _ = std::fs::create_dir_all(&dir);
    let cache = dir.join(format!("{recipe_id}.webview.js"));
    if let Some(s) = recipe_source::read_cache_with_legacy(
        &cache,
        &recipe_source::legacy_cache_directory(app_data).join(format!("{recipe_id}.webview.js")),
        http_security::MAX_RECIPE_BYTES,
    ) {
        return Some(service_badges::pinned_recipe_script(recipe_id, s));
    }
    let url = recipe_source::asset_url(recipe_id, "webview.js");
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
    let text = http_security::text(res, http_security::MAX_RECIPE_BYTES)
        .await
        .ok()?;
    let _ = write_atomic(&cache, &text);
    Some(service_badges::pinned_recipe_script(recipe_id, text))
}

// --- Service webviews ----------------------------------------------------
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

const IPC_SHIM_JS: &str = r#"(function(){
  window.__PAKE_SHIM__ = (window.__PAKE_SHIM__ || 0) + 1;
  window.__pakeUnread = window.__pakeUnread || 0;
  // Intercept the web Notification API (WKWebView does not fully support it): queue
  // service notifications for the Rust poller to drain into native system notifications.
  (function(){
    window.__pakeNotifQueue = window.__pakeNotifQueue || [];
    function N(title, options){
      options = options || {};
      try {
        if (window.__pakeNotifQueue.length >= 8) window.__pakeNotifQueue.shift();
        window.__pakeNotifQueue.push({
          title: String(title == null ? '' : title).slice(0, 160),
          body: String(options.body == null ? '' : options.body).slice(0, 1024)
        });
      } catch(e){}
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
        if (v && typeof v === 'object' && ('direct' in v || 'indirect' in v)) {
          window.__pakeSetBadge(v.direct, v.indirect);
        } else {
          var n = (v && typeof v.count === 'number') ? v.count : parseInt(v, 10);
          if (Number.isFinite(n)) window.__pakeSetBadge(n, 0);
        }
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

// Create a service webview if absent at the requested position/size. Recipe fetches for
// config + webview.js happen ONLY HERE during creation, not on every switch.
#[allow(clippy::too_many_arguments)]
pub(super) async fn create_service_webview(
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
    if !matches!(url.scheme(), "http" | "https") || !ipc_security::service_navigation_allowed(&url)
    {
        return Err(
            "Service URLs must use an HTTP(S) origin outside the application protocols".into(),
        );
    }
    let recipe_origin = url.origin().ascii_serialization();
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
        // Service pages must receive native HTML5 file drops (including File objects).
        // Tauri's default handler intercepts them and disables WebView2 external drops;
        // the main shell's dragDropEnabled setting does not apply to these child views.
        .disable_drag_drop_handler()
        // Creation never takes focus. The active service is focused only after the latest
        // requested switch wins the desired-active race.
        .focused(false)
        .on_navigation(move |url| {
            if url.scheme() != "tauridium-shortcut" {
                return ipc_security::service_navigation_allowed(url);
            }
            if let Some(action) =
                service_shortcut_action_from_url(url, &shortcut_nonce_for_navigation)
            {
                let _ = shortcut_app.emit("shortcut-action", action);
            }
            false
        })
        .initialization_script(include_str!("../service_badges.js"))
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
                if url.scheme() != "mailto" && !ipc_security::service_navigation_allowed(&url) {
                    return NewWindowResponse::Deny;
                }
                if features.size().is_some() && url.scheme() != "mailto" {
                    return NewWindowResponse::Allow;
                }
                if url.scheme() == "mailto"
                    || (open_links_externally && matches!(url.scheme(), "http" | "https"))
                {
                    if let Err(error) = open_external(url.as_str()) {
                        eprintln!("Unable to open external link: {error}");
                    }
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
    #[cfg(target_os = "linux")]
    {
        builder = builder.initialization_script(include_str!("../linux_file_drop.js"));
    }
    // TEMPORARY Proton web-client workaround. Keep this conditional at the
    // service boundary rather than changing generic remote-webview behavior.
    // The initialization script stays attached across authentication navigation.
    // Hosted Telegram also needs its browser branch for standard badge updates.
    if proton_compat::requires_tauri_marker_workaround(&host)
        || service_badges::requires_browser_identity(&host)
    {
        builder = builder.initialization_script(proton_compat::TAURI_MARKER_WORKAROUND_JS);
    }
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

            if distribution::is_flatpak() || preferences.ask_each_download {
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
            let message = format!("Downloaded \"{filename}\"");
            startup_diagnostics::log(
                "primary",
                "download.finished",
                "native download engine reported successful completion",
            );
            let _ = show_system_notification(webview.app_handle(), "Tauridium", Some(&message));
            download_toast::completed(webview.app_handle(), path.as_deref(), &filename);
            true
        }
        _ => true,
    });
    // Per-service storage isolation: macOS -> data_store_identifier (data_directory
    // ignored); Windows/Linux use a dedicated data_directory to avoid shared sessions.
    #[cfg(windows)]
    if browser_privacy::exception_enabled(
        &state.tracking_prevention_startup.lock().unwrap(),
        service_id,
        sandbox_id,
    ) {
        // Internal marker consumed by patched Wry, never a Chromium command-line flag.
        builder = builder.additional_browser_args("--tauridium-relax-tracking-prevention");
    }
    #[cfg(target_os = "macos")]
    {
        let store = storage_identifier(service_id, sandbox_id)
            .ok_or("serviceId is not a UUID and no sandbox is assigned")?;
        builder = builder.data_store_identifier(store);
    }
    #[cfg(not(target_os = "macos"))]
    {
        let target = storage_directory(app_data, service_id, sandbox_id)?;
        let name = target
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or("Invalid session storage name")?;
        let dir = storage_security::prepare(app_data, name)?;
        builder = builder.data_directory(dir);
    }
    // Google compatibility (userAgentData / window.chrome, etc.) for generic Google services.
    if is_google_host(&host) && !is_google_auth_host(&host) {
        builder = builder.initialization_script(GOOGLE_AUTH_COMPAT_JS);
    }
    if let Some(rt) = runtime {
        builder =
            builder.initialization_script(ipc_security::bind_recipe_script(&rt, &recipe_origin));
    }
    // Per-service dark mode: inject and enable Dark Reader (best effort).
    if let Some(o) = dark {
        builder = builder.initialization_script(dark_reader_init(o));
    }
    let webview = win
        .add_child(builder, pos, size)
        .map_err(|e| format!("Failed to create service webview: {e}"))?;
    #[cfg(target_os = "linux")]
    service_menu::watch_input(&webview)?;
    let zoom_percent = effective_service_zoom_percent(&state.settings.lock().unwrap(), service_id);
    if zoom_percent != SERVICE_ZOOM_DEFAULT_PERCENT {
        if let Err(error) = webview.set_zoom(f64::from(zoom_percent) / 100.0) {
            let _ = webview.close();
            return Err(format!(
                "Unable to apply the saved {zoom_percent}% zoom to service {service_id}: {error}"
            ));
        }
    }
    state.created.lock().unwrap().insert(service_id.to_string());
    download_toast::restack(win.app_handle());
    service_menu::restack(win.app_handle());
    Ok(())
}
