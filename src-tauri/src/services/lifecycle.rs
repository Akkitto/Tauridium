//! Service creation, activation, geometry, suspension and closure.

use super::storage::sandbox_for_service;
use super::webview::{create_service_webview, DarkSettings};
use crate::{
    download_toast, reposition_active, service_menu, window_chrome, AppState, MAX_SIDEBAR_W,
    MIN_RUNTIME_SIDEBAR_W,
};
use std::collections::HashSet;
use tauri::{AppHandle, LogicalPosition, LogicalSize, Manager, State, Wry};

#[derive(serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ServiceViewRequest {
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

// Logical rectangle for the service area: everything to the right of the sidebar.
pub(crate) fn service_rect(
    win: &tauri::window::Window<Wry>,
    sidebar_w: f64,
) -> Result<(LogicalPosition<f64>, LogicalSize<f64>), String> {
    #[cfg(target_os = "linux")]
    let phys = win
        .app_handle()
        .get_webview("main")
        .ok_or("Main webview is unavailable")?
        .size()
        .map_err(|e| e.to_string())?;
    #[cfg(not(target_os = "linux"))]
    let phys = win.inner_size().map_err(|e| e.to_string())?;
    let scale = win.scale_factor().map_err(|e| e.to_string())?;
    let w = phys.width as f64 / scale;
    let h = phys.height as f64 / scale;
    let top = window_chrome::content_top(win.app_handle());
    Ok((
        LogicalPosition::new(sidebar_w, top),
        LogicalSize::new((w - sidebar_w).max(0.0), (h - top).max(0.0)),
    ))
}

pub(crate) fn service_toast_overlay_script(
    message: &str,
    duration_ms: u64,
) -> Result<String, String> {
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

pub(super) fn activate_service_webview(
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
        download_toast::restack(app);
        service_menu::restack(app);
    }
    activated
}

#[tauri::command]
pub(crate) async fn show_service(
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

#[tauri::command]
pub(crate) async fn preload_service(
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

pub(crate) fn hide_service_webviews(app: &AppHandle, state: &AppState) {
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
    // A hidden child webview can retain keyboard focus on Windows. Explicitly focus the
    // shell webview so Esc and shortcut toggles immediately work in quick switchers and
    // every other full-screen Tauridium panel opened from a focused service.
    if let Some(shell) = app.get_webview("main") {
        let _ = shell.set_focus();
    }
}

#[tauri::command]
pub(crate) fn hide_all_services(app: AppHandle, state: State<'_, AppState>) {
    hide_service_webviews(&app, &state);
}

#[tauri::command]
pub(crate) fn close_service(app: AppHandle, state: State<'_, AppState>, service_id: String) {
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

#[tauri::command]
pub(crate) fn set_sidebar_width(app: AppHandle, state: State<'_, AppState>, width: f64) {
    *state.sidebar_w.lock().unwrap() = width.clamp(MIN_RUNTIME_SIDEBAR_W, MAX_SIDEBAR_W);
    reposition_active(&app);
}

#[tauri::command]
pub(crate) fn close_services(app: AppHandle, state: State<'_, AppState>) {
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

pub(super) fn close_service_ids(app: &AppHandle, state: &AppState, service_ids: &[String]) {
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
