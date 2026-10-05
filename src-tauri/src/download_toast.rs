//! A local, non-focus-stealing child webview above native service webviews.
//!
//! Never inject download locations into hosted pages or broadcast them as events.
use crate::{
    audit,
    download_notifications::{Completion, Pending},
    AppState,
};
use serde::Serialize;
use std::path::Path;
use std::sync::Mutex;
use tauri::webview::{NewWindowResponse, WebviewBuilder};
use tauri::{
    AppHandle, Emitter, EventTarget, LogicalPosition, LogicalSize, Manager, Webview, WebviewUrl,
};

const LABEL: &str = "download-toast";

#[cfg(target_os = "linux")]
fn gtk_position_handler(parent: &gtk::Overlay, view: &gtk::Widget) -> gtk::glib::SignalHandlerId {
    use gtk::{glib, prelude::*};
    unsafe extern "C" fn position(
        parent: *mut gtk::ffi::GtkOverlay,
        child: *mut gtk::ffi::GtkWidget,
        allocation: *mut gtk::gdk::ffi::GdkRectangle,
        data: glib::ffi::gpointer,
    ) -> glib::ffi::gboolean {
        // SAFETY: GTK's get-child-position signal supplies live widgets and a
        // writable rectangle on its UI thread. connect_raw owns this WeakRef
        // until disconnect; it does not retain the notification widget.
        let weak = unsafe { &*(data as *const glib::WeakRef<gtk::Widget>) };
        let Some(view) = weak.upgrade() else { return 0 };
        if view.as_ptr() != child {
            return 0;
        }
        let parent: glib::translate::Borrowed<gtk::Overlay> =
            unsafe { glib::translate::from_glib_borrow(parent) };
        let width = view
            .width_request()
            .clamp(1, (parent.allocated_width() - 32).max(1));
        let height = view
            .height_request()
            .clamp(1, (parent.allocated_height() - 32).max(1));
        unsafe {
            *allocation = gtk::gdk::ffi::GdkRectangle {
                x: ((parent.allocated_width() - width) / 2).max(0),
                y: (parent.allocated_height() - height - 20).max(0),
                width,
                height,
            };
        }
        1
    }
    // gtk-rs 0.18 omits this signal because its rectangle is an out parameter.
    // Follow its standard connect_raw trampoline/owned-closure convention.
    // SAFETY: the callback signature matches GtkOverlay::get-child-position;
    // GTK owns the boxed weak reference through connect_raw's destroy notifier.
    unsafe {
        glib::signal::connect_raw(
            parent.as_ptr() as *mut _,
            c"get-child-position".as_ptr(),
            Some(std::mem::transmute::<*const (), unsafe extern "C" fn()>(
                position as *const (),
            )),
            Box::into_raw(Box::new(view.downgrade())),
        )
    }
}

pub(crate) fn install_layout_hook(app: &AppHandle) -> Result<(), String> {
    #[cfg(target_os = "linux")]
    {
        let handle = app.clone();
        app.get_webview("main")
            .ok_or("Main webview is unavailable")?
            .with_webview(move |platform| {
                use gtk::prelude::WidgetExt;
                platform.inner().connect_size_allocate(move |_, _| {
                    // GTK updates the content allocation after the native window
                    // resize event. Query bounds only after that allocation, and
                    // off the UI callback to avoid runtime reentrant borrows.
                    let handle = handle.clone();
                    tauri::async_runtime::spawn_blocking(move || crate::reposition_active(&handle));
                });
            })
            .map_err(|error| error.to_string())?;
    }
    #[cfg(not(target_os = "linux"))]
    let _ = app;
    Ok(())
}

fn logical_height(height: f64, pixel_ratio: f64, scale: f64) -> f64 {
    (height * pixel_ratio).ceil() / scale
}

#[derive(Default)]
pub(crate) struct DownloadToastState {
    pending: Mutex<Pending>,
    rendering: Mutex<()>,
    height: Mutex<f64>,
    ready: Mutex<bool>,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct Snapshot {
    completion: Option<Completion>,
    waiting: u64,
    duration: u64,
    theme: String,
    active: bool,
}

fn snapshot(app: &AppHandle) -> Snapshot {
    let settings = app.state::<AppState>().settings.lock().unwrap().clone();
    let state = app.state::<DownloadToastState>();
    let (completion, waiting) = {
        let pending = state.pending.lock().unwrap();
        (pending.current(), pending.waiting())
    };
    Snapshot {
        completion,
        waiting,
        duration: settings
            .get("downloadToastDuration")
            .and_then(serde_json::Value::as_u64)
            .unwrap_or(8),
        theme: settings
            .get("theme")
            .and_then(serde_json::Value::as_str)
            .unwrap_or("system")
            .to_string(),
        active: app
            .get_window("main")
            .is_some_and(|window| window.is_focused().unwrap_or(false)),
    }
}

pub(crate) fn report_error(app: &AppHandle, error: String) {
    eprintln!("Tauridium download notification: {error}");
    audit::best_effort(
        app,
        "warning",
        "download",
        "toast",
        "failure",
        error,
        serde_json::Value::Null,
    );
}

fn resize(app: &AppHandle) -> Result<(), String> {
    if !*app.state::<DownloadToastState>().ready.lock().unwrap() {
        return Ok(());
    }
    let Some(overlay) = app.get_webview(LABEL) else {
        return Ok(());
    };
    let window = app.get_window("main").ok_or("Main window is unavailable")?;
    let scale = window.scale_factor().map_err(|error| error.to_string())?;
    // GTK's content area excludes the native menu bar. Window inner_size does
    // not, and would clip the toast at the bottom of the child-view container.
    let size = app
        .get_webview("main")
        .ok_or("Main webview is unavailable")?
        .size()
        .map_err(|error| error.to_string())?;
    let width = (f64::from(size.width) / scale - 32.0).clamp(1.0, 520.0);
    let height = (*app.state::<DownloadToastState>().height.lock().unwrap())
        .clamp(1.0, (f64::from(size.height) / scale - 32.0).max(1.0));
    let x = ((f64::from(size.width) / scale - width) / 2.0).max(0.0);
    let y = (f64::from(size.height) / scale - height - 20.0).max(0.0);
    #[cfg(not(target_os = "linux"))]
    overlay
        .set_size(LogicalSize::new(width, height))
        .map_err(|error| error.to_string())?;
    #[cfg(not(target_os = "linux"))]
    overlay
        .set_position(LogicalPosition::new(x, y))
        .map_err(|error| error.to_string())?;
    #[cfg(target_os = "linux")]
    let _ = (x, y);
    #[cfg(target_os = "linux")]
    overlay
        .with_webview(move |platform| {
            use gtk::prelude::*;
            let view = platform.inner();
            let changed = view.width_request() != width.ceil() as i32
                || view.height_request() != height.ceil() as i32;
            view.set_size_request(width.ceil() as i32, height.ceil() as i32);
            if let Some(parent) = view
                .parent()
                .and_then(|parent| parent.downcast::<gtk::Overlay>().ok())
            {
                parent.reorder_overlay(&view, -1);
                if changed {
                    // Overlay children do not affect preferred container size;
                    // invalidate allocation explicitly when the card changes.
                    parent.queue_allocate();
                    parent.size_allocate(&parent.allocation());
                }
            }
            if let Some(window) = view.parent_window() {
                window.ensure_native();
                window.raise();
            }
            if let Some(window) = platform.inner().window() {
                window.raise();
            }
            platform.inner().queue_draw();
            let view = platform.inner();
            let allocation = view.allocation();
            crate::startup_diagnostics::log(
                "primary",
                "download.toast.layout",
                &format!(
                    "x={} y={} width={} height={} requested_height={} visible={} mapped={}",
                    allocation.x(),
                    allocation.y(),
                    allocation.width(),
                    allocation.height(),
                    view.height_request(),
                    view.is_visible(),
                    view.is_mapped()
                ),
            );
        })
        .map_err(|error| format!("Unable to raise download notification: {error}"))?;
    announce_geometry(app, height)
}

pub(crate) fn visible_height(app: &AppHandle) -> f64 {
    let state = app.state::<DownloadToastState>();
    if *state.ready.lock().unwrap() && app.get_webview(LABEL).is_some() {
        *state.height.lock().unwrap()
    } else {
        0.0
    }
}

fn announce_geometry(app: &AppHandle, height: f64) -> Result<(), String> {
    // Only non-sensitive geometry goes to the shell so existing Saved/zoom
    // feedback can sit above the completion toast instead of being covered.
    app.emit_to(
        EventTarget::webview("main"),
        "download-toast-geometry",
        height,
    )
    .map_err(|error| format!("Unable to update notification layout: {error}"))?;
    crate::reposition_generic_toast(app, height)
}

fn render(app: &AppHandle) -> Result<(), String> {
    let state = app.state::<DownloadToastState>();
    // Creation and closure are serialized off the UI thread; no queue/settings
    // mutex is held across native WebView calls or a renderer initialization.
    let _render = state.rendering.lock().unwrap();
    let value = snapshot(app);
    if value.completion.is_none() {
        if let Some(overlay) = app.get_webview(LABEL) {
            overlay.close().map_err(|error| error.to_string())?;
            crate::startup_diagnostics::log(
                "primary",
                "download.toast.closed",
                "no pending completions remain",
            );
        }
        *state.ready.lock().unwrap() = false;
        announce_geometry(app, 0.0)?;
        return Ok(());
    }
    if app.get_webview(LABEL).is_none() {
        crate::startup_diagnostics::log(
            "primary",
            "download.toast.create",
            "creating local notification renderer",
        );
        let window = app.get_window("main").ok_or("Main window is unavailable")?;
        let main_url = app
            .get_webview("main")
            .ok_or("Main webview is unavailable")?
            .url()
            .map_err(|error| error.to_string())?;
        *state.ready.lock().unwrap() = false;
        let mut builder = WebviewBuilder::new(LABEL, WebviewUrl::App("index.html".into()))
            .focused(false)
            .disable_drag_drop_handler()
            .initialization_script(
                "Object.defineProperty(window, '__TAURIDIUM_DOWNLOAD_TOAST__', { value: true });",
            )
            .on_page_load(|_, payload| {
                crate::startup_diagnostics::log(
                    "primary",
                    "download.toast.load",
                    &format!("renderer phase={:?}", payload.event()),
                );
            })
            .on_navigation(move |url| {
                // The notification is an app-owned document, never a browser tab.
                let allowed = url.host_str() == main_url.host_str()
                    && matches!(url.path(), "" | "/" | "/index.html")
                    && url.scheme() == main_url.scheme()
                    && url.port() == main_url.port();
                if !allowed {
                    crate::startup_diagnostics::log(
                        "primary",
                        "download.toast.navigation.denied",
                        &format!(
                            "scheme_match={} host_match={} port_match={} document_match={}",
                            url.scheme() == main_url.scheme(),
                            url.host_str() == main_url.host_str(),
                            url.port() == main_url.port(),
                            matches!(url.path(), "/" | "/index.html")
                        ),
                    );
                }
                allowed
            })
            .on_new_window(|_, _| NewWindowResponse::Deny);
        #[cfg(not(target_os = "macos"))]
        {
            builder = builder.transparent(true);
        }
        #[cfg(not(target_os = "macos"))]
        {
            // Separate browser storage from both the shell and remote services.
            let directory = app
                .path()
                .app_cache_dir()
                .map_err(|error| error.to_string())?
                .join("download-toast");
            std::fs::create_dir_all(&directory).map_err(|error| error.to_string())?;
            builder = builder.data_directory(directory);
        }
        #[cfg(target_os = "linux")]
        let initial_position = {
            let scale = window.scale_factor().map_err(|error| error.to_string())?;
            let size = app
                .get_webview("main")
                .ok_or("Main webview is unavailable")?
                .size()
                .map_err(|error| error.to_string())?;
            LogicalPosition::new(
                ((f64::from(size.width) / scale - 520.0) / 2.0).max(0.0),
                (f64::from(size.height) / scale - 140.0).max(0.0),
            )
        };
        #[cfg(not(target_os = "linux"))]
        let initial_position = LogicalPosition::new(-30000.0, 0.0);
        window
            .add_child(builder, initial_position, LogicalSize::new(520.0, 120.0))
            .map_err(|error| format!("Unable to create download toast: {error}"))?;
        #[cfg(target_os = "linux")]
        app.get_webview(LABEL)
            .ok_or("Download notification renderer is unavailable")?
            .with_webview(|platform| {
                use gtk::prelude::*;
                let view = platform.inner();
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
                        // A bounded native overlay preserves service visibility
                        // and input outside the notification's own rectangle.
                        view.set_halign(gtk::Align::Center);
                        view.set_valign(gtk::Align::End);
                        parent.add_overlay(&view);
                        view.show();
                    }
                }
                if let Some(parent) = view
                    .parent()
                    .and_then(|parent| parent.downcast::<gtk::Overlay>().ok())
                {
                    let position_handler = gtk_position_handler(&parent, &view.clone().upcast());
                    let weak_view = view.downgrade();
                    // GTK maps/reallocates sibling native windows after a service
                    // is created. Raise after the container's allocation, not
                    // only before GTK applies that allocation.
                    let handler = parent.connect_size_allocate(move |_, _| {
                        if let Some(view) = weak_view.upgrade() {
                            if let Some(window) = view.parent_window() {
                                window.ensure_native();
                                window.raise();
                            }
                            if let Some(window) = view.window() {
                                window.raise();
                            }
                            view.queue_draw();
                        }
                    });
                    let handlers = std::cell::RefCell::new(vec![handler, position_handler]);
                    let weak_parent = parent.downgrade();
                    view.connect_destroy(move |_| {
                        if let Some(parent) = weak_parent.upgrade() {
                            for handler in handlers.borrow_mut().drain(..) {
                                parent.disconnect(handler);
                            }
                        }
                    });
                }
            })
            .map_err(|error| format!("Unable to track notification stacking: {error}"))?;
        #[cfg(target_os = "linux")]
        app.get_webview(LABEL)
            .ok_or("Download notification renderer is unavailable")?
            .reload()
            .map_err(|error| format!("Unable to initialize notification surface: {error}"))?;
        crate::startup_diagnostics::log(
            "primary",
            "download.toast.created",
            "local notification child created",
        );
        // The renderer keeps its card invisible until measured. On GTK, create
        // within the viewport so WebKit does not cache an off-screen blank frame.
    } else {
        app.emit_to(EventTarget::webview(LABEL), "download-toast", value)
            .map_err(|error| format!("Unable to update download toast: {error}"))?;
    }
    Ok(())
}

pub(crate) fn refresh(app: &AppHandle) {
    let app = app.clone();
    tauri::async_runtime::spawn_blocking(move || {
        if let Err(error) = render(&app) {
            report_error(&app, error);
        }
    });
}

pub(crate) fn completed(app: &AppHandle, path: Option<&Path>, fallback: &str) {
    // Observe the current setting and enqueue under the same settings lock, so a
    // concurrent successful toggle-off cannot be followed by a stale toast.
    {
        let state = app.state::<AppState>();
        let settings = state.settings.lock().unwrap();
        let Some(completion) = crate::download_notifications::completion(&settings, path, fallback)
        else {
            return;
        };
        app.state::<DownloadToastState>()
            .pending
            .lock()
            .unwrap()
            .enqueue(completion);
    }
    crate::startup_diagnostics::log(
        "primary",
        "download.toast.queued",
        "successful download queued without logging filename or location",
    );
    refresh(app);
}

pub(crate) fn clear(app: &AppHandle) {
    app.state::<DownloadToastState>()
        .pending
        .lock()
        .unwrap()
        .clear();
    refresh(app);
}

pub(crate) fn settings_changed(
    app: &AppHandle,
    previous: &serde_json::Value,
    current: &serde_json::Value,
) {
    if current
        .get("downloadToasts")
        .and_then(serde_json::Value::as_bool)
        != Some(true)
    {
        clear(app);
    } else {
        if previous.get("downloadToastLocation") != current.get("downloadToastLocation")
            || previous.get("downloadToastParentLevels") != current.get("downloadToastParentLevels")
        {
            app.state::<DownloadToastState>()
                .pending
                .lock()
                .unwrap()
                .redact_locations();
        }
        if app.get_webview(LABEL).is_some() {
            refresh(app);
        }
    }
}

/// Services created after the toast must not cover it. Never focus the toast.
pub(crate) fn restack(app: &AppHandle) {
    let app = app.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<DownloadToastState>();
        let _render = state.rendering.lock().unwrap();
        #[cfg(not(target_os = "linux"))]
        let Some(overlay) = app.get_webview(LABEL) else {
            return;
        };
        #[cfg(not(any(windows, target_os = "linux")))]
        if let Some(window) = app.get_window("main") {
            // GTK's fixed container reinserts the native child last; macOS also
            // reattaches the child. Bounds are restored immediately afterwards.
            if let Err(error) = overlay.reparent(&window) {
                report_error(&app, format!("Unable to restack download toast: {error}"));
                return;
            }
        }
        #[cfg(windows)]
        {
            let report_app = app.clone();
            if let Err(error) = overlay.with_webview(move |platform| {
                use windows_sys::Win32::UI::WindowsAndMessaging::{
                    SetWindowPos, HWND_TOP, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE,
                };
                let mut hwnd = Default::default();
                // SAFETY: with_webview runs on the native UI thread. ParentWindow
                // is the live Wry child container, not the top-level app window.
                unsafe {
                    if let Err(error) = platform.controller().ParentWindow(&mut hwnd) {
                        report_error(
                            &report_app,
                            format!("Unable to obtain download toast container: {error}"),
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
                            format!(
                                "Unable to restack download toast: {}",
                                std::io::Error::last_os_error()
                            ),
                        );
                    }
                }
            }) {
                report_error(
                    &app,
                    format!("Unable to dispatch download toast stacking: {error}"),
                );
            }
        }
        if let Err(error) = resize(&app) {
            report_error(&app, error);
        }
    });
}

pub(crate) fn reposition(app: &AppHandle) {
    if let Err(error) = resize(app) {
        report_error(app, error);
    }
}

fn require_overlay(webview: &Webview) -> Result<(), String> {
    if webview.label() == LABEL {
        Ok(())
    } else {
        Err("This command is restricted to the download notification renderer".into())
    }
}

#[tauri::command]
pub(crate) fn get_download_toast(app: AppHandle, webview: Webview) -> Result<Snapshot, String> {
    require_overlay(&webview)?;
    crate::startup_diagnostics::log(
        "primary",
        "download.toast.snapshot",
        "local renderer requested completion state",
    );
    let value = snapshot(&app);
    crate::startup_diagnostics::log(
        "primary",
        "download.toast.state",
        &format!(
            "duration={} active={} completion={}",
            value.duration,
            value.active,
            value.completion.is_some()
        ),
    );
    Ok(value)
}

#[tauri::command]
pub(crate) async fn dismiss_download_toast(
    app: AppHandle,
    webview: Webview,
    id: u64,
) -> Result<(), String> {
    require_overlay(&webview)?;
    app.state::<DownloadToastState>()
        .pending
        .lock()
        .unwrap()
        .dismiss(id);
    tauri::async_runtime::spawn_blocking(move || render(&app))
        .await
        .map_err(|error| format!("Unable to finish download notification dismissal: {error}"))?
}

#[tauri::command]
pub(crate) async fn resize_download_toast(
    app: AppHandle,
    webview: Webview,
    id: u64,
    height: f64,
    pixel_ratio: f64,
) -> Result<(), String> {
    require_overlay(&webview)?;
    if !height.is_finite() || !(80.0..=240.0).contains(&height) {
        return Err("Download notification height is outside its supported range".into());
    }
    if !pixel_ratio.is_finite() || !(0.25..=8.0).contains(&pixel_ratio) {
        return Err("Download notification pixel ratio is outside its supported range".into());
    }
    let state = app.state::<DownloadToastState>();
    if !state
        .pending
        .lock()
        .unwrap()
        .current()
        .is_some_and(|completion| completion.id == id)
    {
        return Ok(());
    }
    let scale = app
        .get_window("main")
        .ok_or("Main window is unavailable")?
        .scale_factor()
        .map_err(|error| error.to_string())?;
    // CSS pixels need not equal toolkit logical pixels (GTK's 100-DPI default
    // is a common example). Round physical pixels upward to prevent clipping.
    *state.height.lock().unwrap() = logical_height(height, pixel_ratio, scale);
    *state.ready.lock().unwrap() = true;
    crate::startup_diagnostics::log(
        "primary",
        "download.toast.ready",
        "local renderer measured content",
    );
    resize(&app)
}

#[cfg(test)]
mod tests {
    #[test]
    fn css_measurements_preserve_content_at_gtk_and_windows_dpi() {
        assert_eq!(super::logical_height(92.0, 1.0, 1.0), 92.0);
        assert_eq!(super::logical_height(92.0, 2.0, 2.0), 92.0);
        assert_eq!(super::logical_height(92.0, 100.0 / 96.0, 1.0), 96.0);
        assert_eq!(super::logical_height(92.0, 1.5, 1.0), 138.0);
    }
}
