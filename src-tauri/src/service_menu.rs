//! The service context menu, drawn by a local child webview above native service webviews.
//!
//! Service webviews are native siblings of the shell webview, so shell DOM can never be drawn
//! over them. The menu therefore lives in its own app-owned renderer whose bounds are exactly
//! the menu rectangle, stacked above every service. Selecting an item never executes anything
//! here: the choice is validated against the open menu and forwarded to the shell, which runs
//! the same handlers as before.
use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::webview::{NewWindowResponse, WebviewBuilder};
use tauri::{
    AppHandle, Emitter, EventTarget, LogicalPosition, LogicalSize, Manager, Webview, WebviewUrl,
};

const LABEL: &str = "service-menu";
const MENU_WIDTH: f64 = 226.0;
// Mirrors src/ServiceMenu.svelte: 5px padding and a 1px border on every side, seven 34px
// items and three 9px separators. The renderer uses fixed heights so this stays exact.
const MENU_HEIGHT: f64 = 2.0 * 6.0 + 7.0 * 34.0 + 3.0 * 9.0;
const EDGE_MARGIN: f64 = 8.0;
const MAX_LABEL_CHARS: usize = 200;
const ACTION_EVENT: &str = "service-menu-action";
const STATE_EVENT: &str = "service-menu";
// While the pointer gesture that opened the menu is still held, the shell regains focus when the
// button is released and that must not dismiss the menu. If the release is never reported (for
// example it lands elsewhere) the grace period ends on its own.
const GESTURE_GRACE: Duration = Duration::from_secs(3);
// The focus loss caused by the release is delivered on either side of the shell's own report of
// that release, so it keeps being ignored for a moment afterwards.
const RELEASE_TAIL: Duration = Duration::from_millis(400);

#[derive(Default)]
pub(crate) struct ServiceMenuState {
    open: Mutex<Option<OpenMenu>>,
    // Identifies each opening so a late blur or dismissal from a previous menu can never
    // close the one that replaced it.
    sequence: AtomicU64,
    // Creation, placement and closure are serialized off the UI thread. No other mutex is
    // held across a native WebView call.
    lifecycle: Mutex<()>,
}

#[derive(Clone)]
struct OpenMenu {
    id: u64,
    service_id: String,
    label: String,
    zoom_percent: u16,
    enabled: bool,
    // Set only for menus opened by a pointer press, until that press is released.
    gesture_since: Option<Instant>,
    // When the shell reported that press as released.
    released_at: Option<Instant>,
}

impl OpenMenu {
    /// Whether a focus loss may still be the side effect of the opening click.
    fn gesture_active(&self) -> bool {
        self.gesture_since
            .is_some_and(|since| since.elapsed() < GESTURE_GRACE)
            || self
                .released_at
                .is_some_and(|released| released.elapsed() < RELEASE_TAIL)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "kebab-case")]
pub(crate) enum MenuAction {
    Settings,
    Reload,
    ZoomIn,
    ZoomOut,
    ZoomReset,
    Duplicate,
    Toggle,
}

impl OpenMenu {
    fn permits(&self, action: MenuAction) -> bool {
        match action {
            MenuAction::Reload => self.enabled,
            MenuAction::ZoomIn => self.zoom_percent < crate::SERVICE_ZOOM_MAX_PERCENT,
            MenuAction::ZoomOut => self.zoom_percent > crate::SERVICE_ZOOM_MIN_PERCENT,
            MenuAction::ZoomReset => self.zoom_percent != crate::SERVICE_ZOOM_DEFAULT_PERCENT,
            MenuAction::Settings | MenuAction::Duplicate | MenuAction::Toggle => true,
        }
    }
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct Snapshot {
    id: u64,
    label: String,
    enabled: bool,
    zoom_percent: u16,
    theme: String,
    // macOS child webviews are opaque, so the renderer must paint its own square backdrop.
    transparent: bool,
    width: f64,
    height: f64,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct ActionEvent {
    service_id: String,
    action: MenuAction,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct OpenRequest {
    service_id: String,
    label: String,
    x: f64,
    y: f64,
    zoom_percent: u16,
    enabled: bool,
    #[serde(default)]
    pointer: bool,
}

fn validate(request: &OpenRequest) -> Result<(), String> {
    if request.service_id.is_empty() || request.service_id.len() > 128 {
        return Err("Service menu service id is invalid".into());
    }
    if request.label.chars().count() > MAX_LABEL_CHARS {
        return Err("Service menu label is too long".into());
    }
    if !request.x.is_finite() || !request.y.is_finite() {
        return Err("Service menu position is invalid".into());
    }
    if !(crate::SERVICE_ZOOM_MIN_PERCENT..=crate::SERVICE_ZOOM_MAX_PERCENT)
        .contains(&request.zoom_percent)
    {
        return Err("Service menu zoom is outside its supported range".into());
    }
    Ok(())
}

/// Places the menu at `anchor` (relative to `origin`) while keeping it inside `bounds`.
/// All values are logical pixels; the result is relative to the window's content area.
fn place(anchor: (f64, f64), origin: (f64, f64), bounds: (f64, f64)) -> (f64, f64) {
    let axis = |anchor: f64, origin: f64, bound: f64, extent: f64| {
        let min = origin + EDGE_MARGIN;
        // A tiny window must pin the menu to the leading edge rather than panic in clamp.
        let max = (origin + bound - extent - EDGE_MARGIN).max(min);
        (origin + anchor).clamp(min, max)
    };
    (
        axis(anchor.0, origin.0, bounds.0, MENU_WIDTH),
        axis(anchor.1, origin.1, bounds.1, MENU_HEIGHT),
    )
}

fn snapshot(app: &AppHandle, menu: &OpenMenu) -> Snapshot {
    let theme = app
        .state::<crate::AppState>()
        .settings
        .lock()
        .unwrap()
        .get("theme")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("system")
        .to_string();
    Snapshot {
        id: menu.id,
        label: menu.label.clone(),
        enabled: menu.enabled,
        zoom_percent: menu.zoom_percent,
        theme,
        transparent: cfg!(not(target_os = "macos")),
        width: MENU_WIDTH,
        height: MENU_HEIGHT,
    }
}

fn report_error(app: &AppHandle, error: &str) {
    eprintln!("Tauridium service menu: {error}");
    crate::audit::best_effort(
        app,
        "warning",
        "service-menu",
        "overlay",
        "failure",
        error.to_string(),
        serde_json::Value::Null,
    );
}

fn position(app: &AppHandle, overlay: &Webview, x: f64, y: f64) -> Result<(), String> {
    #[cfg(not(target_os = "linux"))]
    {
        let _ = app;
        overlay
            .set_bounds(tauri::Rect {
                position: LogicalPosition::new(x, y).into(),
                size: LogicalSize::new(MENU_WIDTH, MENU_HEIGHT).into(),
            })
            .map_err(|error| error.to_string())
    }
    #[cfg(target_os = "linux")]
    {
        let _ = app;
        overlay
            .with_webview(move |platform| {
                use gtk::prelude::*;
                place_gtk(platform.inner().upcast_ref(), x, y);
            })
            .map_err(|error| format!("Unable to place service menu: {error}"))
    }
}

/// A GtkOverlay child is placed by alignment and margins, so a Start/Start child with margins
/// and a size request is an exact rectangle in the content area.
#[cfg(target_os = "linux")]
fn place_gtk(view: &gtk::Widget, x: f64, y: f64) {
    use gtk::prelude::*;
    view.set_margin_start(x.round() as i32);
    view.set_margin_top(y.round() as i32);
    view.set_size_request(MENU_WIDTH as i32, MENU_HEIGHT as i32);
    if let Some(parent) = view
        .parent()
        .and_then(|parent| parent.downcast::<gtk::Overlay>().ok())
    {
        parent.queue_resize();
    }
}

#[cfg(target_os = "linux")]
fn is_wayland() -> bool {
    use gtk::glib::prelude::*;
    gtk::gdk::Display::default().is_some_and(|display| display.type_().name().contains("Wayland"))
}

fn menu_is_open(app: &AppHandle) -> bool {
    app.state::<ServiceMenuState>()
        .open
        .lock()
        .unwrap()
        .is_some()
}

/// Shows or hides the renderer to match the menu state. On GTK this runs as a queued step and
/// reads the state when it executes, so a stale "show" queued by creation can never reveal a
/// menu that has since closed: a visible but empty surface would swallow every click over it.
fn sync_visibility(app: &AppHandle, overlay: &Webview) -> Result<(), String> {
    #[cfg(target_os = "linux")]
    {
        let handle = app.clone();
        overlay
            .with_webview(move |platform| {
                use gtk::prelude::*;
                let view = platform.inner();
                if menu_is_open(&handle) {
                    view.show();
                } else {
                    view.hide();
                }
            })
            .map_err(|error| format!("Unable to update service menu visibility: {error}"))?;
    }
    if menu_is_open(app) {
        overlay.show().map_err(|error| error.to_string())
    } else {
        overlay.hide().map_err(|error| error.to_string())
    }
}

/// Moves keyboard focus into the menu. On GTK this is queued after creation and placement:
/// focusing the view first would be undone when it is moved into its overlay, and the lost
/// focus would immediately dismiss the menu.
fn focus(app: &AppHandle, overlay: &Webview) -> Result<(), String> {
    #[cfg(target_os = "linux")]
    {
        let handle = app.clone();
        overlay
            .with_webview(move |platform| {
                use gtk::prelude::*;
                if menu_is_open(&handle) {
                    platform.inner().grab_focus();
                }
            })
            .map_err(|error| format!("Unable to focus service menu: {error}"))
    }
    #[cfg(not(target_os = "linux"))]
    {
        let _ = app;
        overlay.set_focus().map_err(|error| error.to_string())
    }
}

/// Stacks the menu above every service. A service created or reshown afterwards can otherwise
/// cover it, so this is repeated by [`restack`].
fn raise(app: &AppHandle, overlay: &Webview) -> Result<(), String> {
    #[cfg(target_os = "linux")]
    {
        let _ = app;
        overlay
            .with_webview(|platform| {
                use gtk::prelude::*;
                let view = platform.inner();
                if let Some(parent) = view
                    .parent()
                    .and_then(|parent| parent.downcast::<gtk::Overlay>().ok())
                {
                    parent.reorder_overlay(&view, -1);
                }
                // Only X11 stacks child views as native windows. Wayland has no such windows
                // and is stacked purely by the overlay order above.
                if !is_wayland() {
                    if let Some(window) = view.parent_window() {
                        window.ensure_native();
                        window.raise();
                    }
                    if let Some(window) = view.window() {
                        window.raise();
                    }
                }
                view.queue_draw();
            })
            .map_err(|error| format!("Unable to raise service menu: {error}"))
    }
    #[cfg(windows)]
    {
        let report_app = app.clone();
        overlay
            .with_webview(move |platform| {
                use windows_sys::Win32::UI::WindowsAndMessaging::{
                    SetWindowPos, HWND_TOP, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE,
                };
                let mut hwnd = Default::default();
                // SAFETY: with_webview runs on the native UI thread. ParentWindow is the
                // live Wry child container, not the top-level application window.
                unsafe {
                    if let Err(error) = platform.controller().ParentWindow(&mut hwnd) {
                        report_error(
                            &report_app,
                            &format!("Unable to obtain service menu container: {error}"),
                        );
                    } else if SetWindowPos(
                        hwnd.0,
                        HWND_TOP,
                        0,
                        0,
                        0,
                        0,
                        SWP_NOACTIVATE | SWP_NOMOVE | SWP_NOSIZE,
                    ) == 0
                    {
                        report_error(
                            &report_app,
                            &format!(
                                "Unable to restack service menu: {}",
                                std::io::Error::last_os_error()
                            ),
                        );
                    }
                }
            })
            .map_err(|error| format!("Unable to dispatch service menu stacking: {error}"))
    }
    #[cfg(not(any(windows, target_os = "linux")))]
    {
        // macOS reattaches the child last when it is reparented. Bounds are restored by the
        // caller afterwards.
        let window = app.get_window("main").ok_or("Main window is unavailable")?;
        overlay
            .reparent(&window)
            .map_err(|error| format!("Unable to restack service menu: {error}"))
    }
}

fn create(app: &AppHandle, x: f64, y: f64) -> Result<(), String> {
    let window = app.get_window("main").ok_or("Main window is unavailable")?;
    let main_url = app
        .get_webview("main")
        .ok_or("Main webview is unavailable")?
        .url()
        .map_err(|error| error.to_string())?;
    let mut builder = WebviewBuilder::new(LABEL, WebviewUrl::App("index.html".into()))
        .focused(false)
        .disable_drag_drop_handler()
        .initialization_script(
            "Object.defineProperty(window, '__TAURIDIUM_SERVICE_MENU__', { value: true });",
        )
        .on_navigation(move |url| {
            // The menu is an app-owned document, never a browser tab.
            url.host_str() == main_url.host_str()
                && matches!(url.path(), "" | "/" | "/index.html")
                && url.scheme() == main_url.scheme()
                && url.port() == main_url.port()
        })
        .on_new_window(|_, _| NewWindowResponse::Deny);
    #[cfg(not(target_os = "macos"))]
    {
        builder = builder.transparent(true);
        // Separate browser storage from both the shell and remote services.
        let directory = app
            .path()
            .app_cache_dir()
            .map_err(|error| error.to_string())?
            .join("service-menu");
        std::fs::create_dir_all(&directory).map_err(|error| error.to_string())?;
        builder = builder.data_directory(directory);
    }
    window
        .add_child(
            builder,
            LogicalPosition::new(x, y),
            LogicalSize::new(MENU_WIDTH, MENU_HEIGHT),
        )
        .map_err(|error| format!("Unable to create service menu: {error}"))?;
    #[cfg(target_os = "linux")]
    {
        let overlay = app
            .get_webview(LABEL)
            .ok_or("Service menu renderer is unavailable")?;
        overlay
            .with_webview(move |platform| {
                use gtk::prelude::*;
                let view = platform.inner();
                // Wry gives every child its own fixed layer. Move the view into a GtkOverlay
                // so it floats above services and still lets everything outside its own
                // rectangle receive input.
                if let Some(layer) = view
                    .parent()
                    .and_then(|layer| layer.downcast::<gtk::Fixed>().ok())
                {
                    if let Some(parent) = layer
                        .parent()
                        .and_then(|parent| parent.downcast::<gtk::Overlay>().ok())
                    {
                        layer.remove(&view);
                        parent.remove(&layer);
                        view.set_halign(gtk::Align::Start);
                        view.set_valign(gtk::Align::Start);
                        parent.add_overlay(&view);
                        place_gtk(view.upcast_ref(), x, y);
                    }
                }
            })
            .map_err(|error| format!("Unable to track service menu stacking: {error}"))?;
        // Matches the download notification: initialize the surface after it is in place so
        // WebKit does not cache a blank frame from its original container.
        overlay
            .reload()
            .map_err(|error| format!("Unable to initialize service menu surface: {error}"))?;
    }
    Ok(())
}

fn open(app: &AppHandle, request: OpenRequest) -> Result<u64, String> {
    validate(&request)?;
    let state = app.state::<ServiceMenuState>();
    let _lifecycle = state.lifecycle.lock().unwrap();
    let scale = app
        .get_window("main")
        .ok_or("Main window is unavailable")?
        .scale_factor()
        .map_err(|error| error.to_string())?;
    let main = app
        .get_webview("main")
        .ok_or("Main webview is unavailable")?;
    let origin = main.position().map_err(|error| error.to_string())?;
    let size = main.size().map_err(|error| error.to_string())?;
    let (x, y) = place(
        (request.x, request.y),
        (f64::from(origin.x) / scale, f64::from(origin.y) / scale),
        (
            f64::from(size.width) / scale,
            f64::from(size.height) / scale,
        ),
    );
    let id = state.sequence.fetch_add(1, Ordering::Relaxed) + 1;
    let menu = OpenMenu {
        id,
        service_id: request.service_id,
        label: request.label,
        zoom_percent: request.zoom_percent,
        enabled: request.enabled,
        gesture_since: request.pointer.then(Instant::now),
        released_at: None,
    };
    let value = snapshot(app, &menu);
    *state.open.lock().unwrap() = Some(menu);
    let result = (|| {
        match app.get_webview(LABEL) {
            Some(overlay) => {
                // Reuse the live renderer: tell it what to show, then place and reveal it.
                app.emit_to(EventTarget::webview(LABEL), STATE_EVENT, Some(value))
                    .map_err(|error| format!("Unable to update service menu: {error}"))?;
                position(app, &overlay, x, y)?;
            }
            None => create(app, x, y)?,
        }
        let overlay = app
            .get_webview(LABEL)
            .ok_or("Service menu renderer is unavailable")?;
        sync_visibility(app, &overlay)?;
        raise(app, &overlay)?;
        #[cfg(not(any(windows, target_os = "linux")))]
        position(app, &overlay, x, y)?;
        focus(app, &overlay)
    })();
    if result.is_err() {
        // Never leave an invisible renderer holding state or intercepting input.
        *state.open.lock().unwrap() = None;
        if let Some(overlay) = app.get_webview(LABEL) {
            let _ = sync_visibility(app, &overlay);
        }
    }
    result.map(|()| id)
}

/// Hides the menu. The renderer stays alive so the next right-click does not pay for a new
/// WebView. `restore_focus` returns keyboard focus to the shell, as a native menu would.
pub(crate) fn close(app: &AppHandle, restore_focus: bool, reason: &str) {
    close_menu(app, restore_focus, None, reason);
}

fn close_menu(app: &AppHandle, restore_focus: bool, only_id: Option<u64>, reason: &str) {
    let state = app.state::<ServiceMenuState>();
    let was_open = {
        let mut open = state.open.lock().unwrap();
        match open.as_ref() {
            Some(menu) if only_id.is_none_or(|id| id == menu.id) => open.take().is_some(),
            _ => false,
        }
    };
    if !was_open {
        return;
    }
    // Why a menu closed is the first question when one disappears unexpectedly.
    crate::startup_diagnostics::log("primary", "service-menu.closed", reason);
    if let Some(overlay) = app.get_webview(LABEL) {
        let _ = app.emit_to(
            EventTarget::webview(LABEL),
            STATE_EVENT,
            Option::<Snapshot>::None,
        );
        if let Err(error) = sync_visibility(app, &overlay) {
            report_error(app, &format!("Unable to hide service menu: {error}"));
        }
    }
    if restore_focus {
        if let Some(main) = app.get_webview("main") {
            let _ = main.set_focus();
        }
    }
}

/// Services created or reshown after the menu opened must not cover it.
pub(crate) fn restack(app: &AppHandle) {
    if app
        .state::<ServiceMenuState>()
        .open
        .lock()
        .unwrap()
        .is_none()
    {
        return;
    }
    let app = app.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<ServiceMenuState>();
        let _lifecycle = state.lifecycle.lock().unwrap();
        if state.open.lock().unwrap().is_none() {
            return;
        }
        if let Some(overlay) = app.get_webview(LABEL) {
            if let Err(error) = raise(&app, &overlay) {
                report_error(&app, &error);
            }
        }
    });
}

fn require_overlay(webview: &Webview) -> Result<(), String> {
    if webview.label() == LABEL {
        Ok(())
    } else {
        Err("This command is restricted to the service menu renderer".into())
    }
}

#[tauri::command]
pub(crate) async fn open_service_menu(app: AppHandle, request: OpenRequest) -> Result<u64, String> {
    let report = app.clone();
    tauri::async_runtime::spawn_blocking(move || open(&app, request))
        .await
        .map_err(|error| format!("Unable to finish opening the service menu: {error}"))?
        .inspect_err(|error| report_error(&report, error))
}

#[tauri::command]
pub(crate) fn close_service_menu(app: AppHandle, id: u64) {
    // Only the menu the shell opened: a late close can never dismiss a newer one.
    close_menu(&app, false, Some(id), "shell-pointer");
}

#[tauri::command]
pub(crate) fn get_service_menu(
    app: AppHandle,
    webview: Webview,
) -> Result<Option<Snapshot>, String> {
    require_overlay(&webview)?;
    let menu = app.state::<ServiceMenuState>().open.lock().unwrap().clone();
    Ok(menu.map(|menu| snapshot(&app, &menu)))
}

#[tauri::command]
pub(crate) fn dismiss_service_menu(
    app: AppHandle,
    webview: Webview,
    id: u64,
    restore_focus: bool,
    reason: String,
) -> Result<bool, String> {
    require_overlay(&webview)?;
    // The renderer names its trigger; only known values are recorded.
    let reason = match reason.as_str() {
        "escape" => "renderer-escape",
        "blur" => "renderer-blur",
        _ => "renderer-dismiss",
    };
    if reason == "renderer-blur" {
        let held = app
            .state::<ServiceMenuState>()
            .open
            .lock()
            .unwrap()
            .as_ref()
            .is_some_and(|menu| menu.id == id && menu.gesture_active());
        if held {
            // The opening click's release moved focus back to the shell; keep the menu.
            if let Some(overlay) = app.get_webview(LABEL) {
                if let Err(error) = focus(&app, &overlay) {
                    report_error(&app, &error);
                }
            }
            return Ok(false);
        }
    }
    close_menu(&app, restore_focus, Some(id), reason);
    Ok(true)
}

/// The shell reports that the button which opened the menu was released: from now on losing
/// focus is a real dismissal, and the menu takes focus back for keyboard navigation.
#[tauri::command]
pub(crate) fn settle_service_menu(app: AppHandle, id: u64) {
    let state = app.state::<ServiceMenuState>();
    {
        let mut open = state.open.lock().unwrap();
        match open.as_mut() {
            Some(menu) if menu.id == id => {
                menu.gesture_since = None;
                menu.released_at = Some(Instant::now());
            }
            _ => {
                return;
            }
        }
    }
    if let Some(overlay) = app.get_webview(LABEL) {
        if let Err(error) = focus(&app, &overlay) {
            report_error(&app, &error);
        }
    }
}

#[tauri::command]
pub(crate) fn service_menu_action(
    app: AppHandle,
    webview: Webview,
    id: u64,
    action: MenuAction,
) -> Result<(), String> {
    require_overlay(&webview)?;
    // The target service comes from the menu Rust opened, never from the renderer.
    let menu = app
        .state::<ServiceMenuState>()
        .open
        .lock()
        .unwrap()
        .clone()
        .filter(|menu| menu.id == id)
        .ok_or("This service menu is no longer open")?;
    if !menu.permits(action) {
        return Err("That action is not available for this service".into());
    }
    close_menu(&app, true, Some(id), "action");
    app.emit_to(
        EventTarget::webview("main"),
        ACTION_EVENT,
        ActionEvent {
            service_id: menu.service_id,
            action,
        },
    )
    .map_err(|error| format!("Unable to deliver service menu action: {error}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn menu(zoom_percent: u16, enabled: bool) -> OpenMenu {
        OpenMenu {
            id: 1,
            service_id: "svc".into(),
            label: "Service".into(),
            zoom_percent,
            enabled,
            gesture_since: None,
            released_at: None,
        }
    }

    #[test]
    fn menu_height_matches_the_renderer_layout() {
        assert_eq!(MENU_HEIGHT, 277.0);
    }

    #[test]
    fn placement_stays_inside_the_content_area() {
        // Plenty of room: follow the pointer, offset by the webview origin.
        assert_eq!(
            place((20.0, 30.0), (0.0, 0.0), (900.0, 700.0)),
            (20.0, 30.0)
        );
        assert_eq!(
            place((20.0, 30.0), (0.0, 40.0), (900.0, 660.0)),
            (20.0, 70.0)
        );
        // Near the right and bottom edges the menu is pulled back inside.
        assert_eq!(
            place((890.0, 690.0), (0.0, 0.0), (900.0, 700.0)),
            (
                900.0 - MENU_WIDTH - EDGE_MARGIN,
                700.0 - MENU_HEIGHT - EDGE_MARGIN
            )
        );
        // Negative anchors cannot leave the leading edge.
        assert_eq!(
            place((-50.0, -50.0), (0.0, 0.0), (900.0, 700.0)),
            (8.0, 8.0)
        );
    }

    #[test]
    fn placement_survives_windows_smaller_than_the_menu() {
        assert_eq!(
            place((100.0, 100.0), (0.0, 0.0), (100.0, 100.0)),
            (8.0, 8.0)
        );
        assert_eq!(
            place((100.0, 100.0), (10.0, 20.0), (0.0, 0.0)),
            (18.0, 28.0)
        );
    }

    #[test]
    fn actions_respect_the_state_the_menu_was_opened_with() {
        let default = menu(crate::SERVICE_ZOOM_DEFAULT_PERCENT, true);
        assert!(default.permits(MenuAction::ZoomIn));
        assert!(default.permits(MenuAction::ZoomOut));
        assert!(!default.permits(MenuAction::ZoomReset));
        assert!(default.permits(MenuAction::Reload));
        assert!(!menu(100, false).permits(MenuAction::Reload));
        assert!(menu(100, false).permits(MenuAction::Toggle));
        assert!(!menu(crate::SERVICE_ZOOM_MAX_PERCENT, true).permits(MenuAction::ZoomIn));
        assert!(!menu(crate::SERVICE_ZOOM_MIN_PERCENT, true).permits(MenuAction::ZoomOut));
    }

    #[test]
    fn open_requests_reject_unsafe_values() {
        let valid = || OpenRequest {
            service_id: "svc".into(),
            label: "Service".into(),
            x: 1.0,
            y: 2.0,
            zoom_percent: 100,
            enabled: true,
            pointer: false,
        };
        assert!(validate(&valid()).is_ok());
        for request in [
            OpenRequest {
                service_id: String::new(),
                ..valid()
            },
            OpenRequest {
                service_id: "x".repeat(129),
                ..valid()
            },
            OpenRequest {
                label: "x".repeat(MAX_LABEL_CHARS + 1),
                ..valid()
            },
            OpenRequest {
                x: f64::NAN,
                ..valid()
            },
            OpenRequest {
                y: f64::INFINITY,
                ..valid()
            },
            OpenRequest {
                zoom_percent: crate::SERVICE_ZOOM_MAX_PERCENT + 1,
                ..valid()
            },
            OpenRequest {
                zoom_percent: crate::SERVICE_ZOOM_MIN_PERCENT - 1,
                ..valid()
            },
        ] {
            assert!(validate(&request).is_err());
        }
    }

    #[test]
    fn opening_gesture_only_shields_the_menu_for_a_bounded_time() {
        let mut menu = menu(100, true);
        assert!(
            !menu.gesture_active(),
            "keyboard-opened menus are never shielded"
        );
        menu.gesture_since = Some(Instant::now());
        assert!(menu.gesture_active());
        menu.gesture_since = Instant::now().checked_sub(GESTURE_GRACE + Duration::from_millis(1));
        assert!(
            !menu.gesture_active(),
            "an unreported release must not shield it forever"
        );
    }

    #[test]
    fn the_release_tail_covers_a_focus_loss_that_lands_after_the_report() {
        let mut menu = menu(100, true);
        menu.released_at = Some(Instant::now());
        assert!(menu.gesture_active());
        menu.released_at = Instant::now().checked_sub(RELEASE_TAIL + Duration::from_millis(1));
        assert!(
            !menu.gesture_active(),
            "a later click away must dismiss the menu"
        );
    }

    #[test]
    fn actions_use_stable_wire_names() {
        assert_eq!(
            serde_json::to_string(&MenuAction::ZoomReset).unwrap(),
            "\"zoom-reset\""
        );
        assert!(serde_json::from_str::<MenuAction>("\"rm-rf\"").is_err());
    }
}
