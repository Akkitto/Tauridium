//! App-owned styled popup above native service views. Remote pages receive no IPC.
use serde::{Deserialize, Serialize};
#[cfg(target_os = "linux")]
use std::sync::Arc;
use std::sync::Mutex;
use tauri::webview::{NewWindowResponse, WebviewBuilder};
use tauri::{
    AppHandle, Emitter, EventTarget, LogicalPosition, LogicalSize, Manager, PhysicalPosition,
    PhysicalSize, Webview, WebviewUrl,
};

const LABEL: &str = "service-menu";

#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct Request {
    service_id: String,
    label: String,
    enabled: bool,
    zoom_percent: u16,
    x: f64,
    y: f64,
    pixel_ratio: f64,
    theme: String,
}

#[derive(Clone, Copy, Deserialize, Serialize)]
#[serde(rename_all = "kebab-case")]
pub(crate) enum Action {
    Settings,
    Reload,
    ZoomIn,
    ZoomOut,
    ZoomReset,
    Duplicate,
    Toggle,
}

impl Action {
    fn allowed(self, request: &Request) -> bool {
        match self {
            Self::Reload => request.enabled,
            Self::ZoomIn => request.zoom_percent < 200,
            Self::ZoomOut => request.zoom_percent > 50,
            Self::ZoomReset => request.zoom_percent != 100,
            _ => true,
        }
    }
}

#[derive(Clone, Copy, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct Measurement {
    width: f64,
    height: f64,
    pixel_ratio: f64,
    inset_x: f64,
    inset_y: f64,
}

struct Session {
    id: u64,
    request: Request,
    measured: Option<Measurement>,
    visible: bool,
}

struct Core {
    revision: u64,
    session: Option<Session>,
    owner_input: bool,
}

impl Default for Core {
    fn default() -> Self {
        Self {
            revision: 0,
            session: None,
            owner_input: true,
        }
    }
}

impl Core {
    fn prepare(&mut self, request: Request) -> u64 {
        self.revision += 1;
        self.session = self.owner_input.then_some(Session {
            id: self.revision,
            request,
            measured: None,
            visible: false,
        });
        self.revision
    }

    fn take(&mut self, id: u64) -> Option<Session> {
        if self
            .session
            .as_ref()
            .is_some_and(|session| session.id == id)
        {
            self.session.take()
        } else {
            None
        }
    }

    fn claim(&mut self, id: u64, action: Action) -> Option<Session> {
        if self.session.as_ref().is_some_and(|session| {
            session.id == id && session.visible && action.allowed(&session.request)
        }) {
            self.session.take()
        } else {
            None
        }
    }

    fn snapshot(&self) -> Snapshot {
        Snapshot {
            revision: self.revision,
            menu: self.session.as_ref().map(|session| session.request.clone()),
        }
    }
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct Snapshot {
    revision: u64,
    menu: Option<Request>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct Layout {
    x: i32,
    y: i32,
    width: u32,
    height: u32,
}

#[derive(Default)]
pub(crate) struct ServiceMenuState {
    core: Mutex<Core>,
    // Native work is serialized on blocking workers, never while holding core.
    lifecycle: Mutex<()>,
    #[cfg(target_os = "linux")]
    gtk_layout: Arc<Mutex<Option<Layout>>>,
}

fn ratio(value: f64) -> bool {
    value.is_finite() && (0.25..=8.0).contains(&value)
}

fn layout(
    request: &Request,
    measured: Measurement,
    origin: PhysicalPosition<i32>,
    bounds: PhysicalSize<u32>,
) -> Layout {
    let margin = 8.0;
    let width = (measured.width * measured.pixel_ratio)
        .ceil()
        .min(f64::from(bounds.width))
        .max(1.0);
    let height = (measured.height * measured.pixel_ratio)
        .ceil()
        .min(f64::from(bounds.height))
        .max(1.0);
    let x = (request.x * request.pixel_ratio - measured.inset_x * measured.pixel_ratio)
        .clamp(0.0, (f64::from(bounds.width) - width - margin).max(0.0));
    let y = (request.y * request.pixel_ratio - measured.inset_y * measured.pixel_ratio)
        .clamp(0.0, (f64::from(bounds.height) - height - margin).max(0.0));
    Layout {
        x: origin.x + x.round() as i32,
        y: origin.y + y.round() as i32,
        width: width as u32,
        height: height as u32,
    }
}

fn require(webview: &Webview, label: &str) -> Result<(), String> {
    if webview.label() == label {
        Ok(())
    } else {
        Err("Service menu command is restricted to its owning renderer".into())
    }
}

fn announce(app: &AppHandle) -> Result<(), String> {
    let value = app
        .state::<ServiceMenuState>()
        .core
        .lock()
        .unwrap()
        .snapshot();
    app.emit_to(EventTarget::webview(LABEL), "service-menu-state", value)
        .map_err(|error| error.to_string())
}

fn report(error: impl std::fmt::Display) {
    eprintln!("Tauridium service menu: {error}");
}

fn hide_idle(app: &AppHandle) -> Result<(), String> {
    if app
        .state::<ServiceMenuState>()
        .core
        .lock()
        .unwrap()
        .session
        .is_some()
    {
        return Ok(());
    }
    if let Some(view) = app.get_webview(LABEL) {
        if let Err(error) = view.hide() {
            // A failed hide must not leave an invisible input surface behind.
            view.close().map_err(|close_error| {
                format!("Unable to hide service menu: {error}; cleanup: {close_error}")
            })?;
        }
    }
    announce(app)
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct Closed {
    id: u64,
    restore_focus: bool,
}

fn notify_closed(app: &AppHandle, id: u64, restore_focus: bool) -> Result<(), String> {
    app.emit_to(
        EventTarget::webview("main"),
        "service-menu-closed",
        Closed { id, restore_focus },
    )
    .map_err(|error| error.to_string())
}

fn close_id(app: &AppHandle, id: u64, restore_focus: bool) -> Result<(), String> {
    let removed = app
        .state::<ServiceMenuState>()
        .core
        .lock()
        .unwrap()
        .take(id);
    let Some(session) = removed else {
        return Ok(());
    };
    finish_close(app, session, restore_focus)
}

fn finish_close(app: &AppHandle, session: Session, restore_focus: bool) -> Result<(), String> {
    let state = app.state::<ServiceMenuState>();
    let _lifecycle = state.lifecycle.lock().unwrap();
    hide_idle(app)?;
    let restore = restore_focus && session.visible && state.core.lock().unwrap().session.is_none();
    if restore {
        app.get_webview("main")
            .ok_or("Main webview is unavailable")?
            .set_focus()
            .map_err(|error| error.to_string())?;
    }
    notify_closed(app, session.id, restore)
}

fn finish_close_async(app: &AppHandle, session: Option<Session>) {
    if let Some(session) = session {
        let app = app.clone();
        tauri::async_runtime::spawn_blocking(move || {
            if let Err(error) = finish_close(&app, session, false) {
                report(error);
            }
        });
    }
}

pub(crate) fn close(app: &AppHandle) {
    // Invalidate synchronously, including when called by a native input event.
    // Native cleanup can wait for the worker without allowing a late reveal.
    let session = app
        .state::<ServiceMenuState>()
        .core
        .lock()
        .unwrap()
        .session
        .take();
    finish_close_async(app, session);
}

#[cfg(target_os = "linux")]
pub(crate) fn watch_input(view: &Webview) -> Result<(), String> {
    let owner = view.label() == "main";
    let app = view.app_handle().clone();
    view.with_webview(move |platform| {
        use gtk::prelude::*;
        let view = platform.inner();
        let pointer_app = app.clone();
        view.connect_button_press_event(move |_, _| {
            native_input(&pointer_app, owner);
            gtk::glib::Propagation::Proceed
        });
        let key_app = app.clone();
        view.connect_key_press_event(move |_, _| {
            native_input(&key_app, owner);
            gtk::glib::Propagation::Proceed
        });
        view.connect_focus_in_event(move |_, _| {
            if owner {
                app.state::<ServiceMenuState>()
                    .core
                    .lock()
                    .unwrap()
                    .owner_input = true;
            } else {
                native_input(&app, false);
            }
            gtk::glib::Propagation::Proceed
        });
    })
    .map_err(|error| error.to_string())
}

#[cfg(target_os = "linux")]
fn native_input(app: &AppHandle, owner: bool) {
    let session = {
        let state = app.state::<ServiceMenuState>();
        let mut core = state.core.lock().unwrap();
        // A service click can precede delivery of an already queued owner IPC.
        // Keep preparation disarmed until fresh owner input or focus arrives.
        core.owner_input = owner;
        core.session.take()
    };
    finish_close_async(app, session);
}

fn window_active(app: &AppHandle) -> bool {
    let Some(window) = app.get_window("main") else {
        return false;
    };
    #[cfg(windows)]
    {
        use windows_sys::Win32::UI::WindowsAndMessaging::{
            GetAncestor, GetForegroundWindow, GA_ROOT,
        };
        window.hwnd().ok().is_some_and(|hwnd| {
            // SAFETY: queries only. Children of this exact top-level window count
            // as active; another dialog/window in the same process does not.
            unsafe { GetAncestor(GetForegroundWindow(), GA_ROOT) == hwnd.0.cast() }
        })
    }
    #[cfg(not(windows))]
    window.is_focused().unwrap_or(false)
}

pub(crate) fn focus_lost(app: &AppHandle) {
    let app = app.clone();
    tauri::async_runtime::spawn_blocking(move || {
        if !window_active(&app) {
            close(&app);
        }
    });
}

#[cfg(target_os = "linux")]
fn install_gtk(view: &Webview, layout: Arc<Mutex<Option<Layout>>>) -> Result<(), String> {
    let (send, receive) = std::sync::mpsc::sync_channel(1);
    view.with_webview(move |platform| {
        use gtk::{glib, prelude::*};
        let view = platform.inner();
        view.hide();
        let result = (|| -> Result<(), String> {
            let layer = view
                .parent()
                .and_then(|parent| parent.downcast::<gtk::Fixed>().ok())
                .ok_or("Service menu container is unavailable")?;
            let parent = layer
                .parent()
                .and_then(|parent| parent.downcast::<gtk::Overlay>().ok())
                .ok_or("Service menu overlay parent is unavailable")?;
            layer.remove(&view);
            parent.remove(&layer);
            view.set_halign(gtk::Align::Start);
            view.set_valign(gtk::Align::Start);
            parent.add_overlay(&view);
            parent.set_overlay_pass_through(&view, false);
            struct Position {
                view: glib::WeakRef<gtk::Widget>,
                layout: Arc<Mutex<Option<Layout>>>,
            }
            unsafe extern "C" fn position(
                _: *mut gtk::ffi::GtkOverlay,
                child: *mut gtk::ffi::GtkWidget,
                allocation: *mut gtk::gdk::ffi::GdkRectangle,
                data: glib::ffi::gpointer,
            ) -> glib::ffi::gboolean {
                // SAFETY: GTK owns Position through connect_raw and supplies a
                // live child and writable allocation on its UI thread.
                let position = unsafe { &*(data as *const Position) };
                let Some(view) = position.view.upgrade() else {
                    return 0;
                };
                if view.as_ptr() != child {
                    return 0;
                }
                let Some(layout) = *position.layout.lock().unwrap() else {
                    return 0;
                };
                unsafe {
                    *allocation = gtk::gdk::ffi::GdkRectangle {
                        x: layout.x,
                        y: layout.y,
                        width: layout.width as i32,
                        height: layout.height as i32,
                    };
                }
                1
            }
            // gtk-rs omits this signal because allocation is an out parameter.
            // SAFETY: the callback matches get-child-position; GTK releases its
            // boxed weak state on disconnect, without retaining the webview.
            let handler = unsafe {
                glib::signal::connect_raw(
                    parent.as_ptr().cast(),
                    c"get-child-position".as_ptr(),
                    Some(std::mem::transmute::<*const (), unsafe extern "C" fn()>(
                        position as *const (),
                    )),
                    Box::into_raw(Box::new(Position {
                        view: view.clone().upcast::<gtk::Widget>().downgrade(),
                        layout,
                    })),
                )
            };
            let weak_view = view.downgrade();
            let allocation = parent.connect_size_allocate(move |_, _| {
                if let Some(view) = weak_view.upgrade().filter(|view| view.is_visible()) {
                    if let Some(window) = view.window() {
                        window.raise();
                    }
                }
            });
            let handlers = std::cell::RefCell::new(vec![handler, allocation]);
            let parent = parent.downgrade();
            view.connect_destroy(move |_| {
                if let Some(parent) = parent.upgrade() {
                    for handler in handlers.borrow_mut().drain(..) {
                        parent.disconnect(handler);
                    }
                }
            });
            Ok(())
        })();
        let _ = send.send(result);
    })
    .map_err(|error| error.to_string())?;
    receive.recv().map_err(|error| error.to_string())?
}

fn ensure_view(app: &AppHandle) -> Result<(), String> {
    if app.get_webview(LABEL).is_some() {
        return Ok(());
    }
    let window = app.get_window("main").ok_or("Main window is unavailable")?;
    let owner = app
        .get_webview("main")
        .ok_or("Main webview is unavailable")?
        .url()
        .map_err(|error| error.to_string())?;
    let builder = WebviewBuilder::new(LABEL, WebviewUrl::App("index.html".into()))
        .focused(false)
        .disable_drag_drop_handler()
        .initialization_script(if cfg!(target_os = "macos") {
            "Object.defineProperty(window, '__TAURIDIUM_SERVICE_MENU__', { value: true }); Object.defineProperty(window, '__TAURIDIUM_SERVICE_MENU_OPAQUE__', { value: true });"
        } else {
            "Object.defineProperty(window, '__TAURIDIUM_SERVICE_MENU__', { value: true });"
        })
        .on_navigation(move |url| {
            url.scheme() == owner.scheme()
                && url.host_str() == owner.host_str()
                && url.port() == owner.port()
                && matches!(url.path(), "/" | "/index.html" | "")
        })
        .on_new_window(|_, _| NewWindowResponse::Deny);
    #[cfg(not(target_os = "macos"))]
    let builder = {
        let root = app
            .path()
            .app_cache_dir()
            .map_err(|error| error.to_string())?;
        std::fs::create_dir_all(&root).map_err(|error| error.to_string())?;
        let directory = crate::storage_security::prepare(&root, LABEL)?;
        builder.transparent(true).data_directory(directory)
    };
    window
        .add_child(
            builder,
            LogicalPosition::new(-30000.0, 0.0),
            LogicalSize::new(300.0, 480.0),
        )
        .map_err(|error| format!("Unable to create service menu: {error}"))?;
    let view = app
        .get_webview(LABEL)
        .ok_or("Service menu renderer is unavailable")?;
    view.hide().map_err(|error| error.to_string())?;
    #[cfg(target_os = "linux")]
    {
        install_gtk(&view, app.state::<ServiceMenuState>().gtk_layout.clone())?;
        view.reload().map_err(|error| error.to_string())?;
    }
    Ok(())
}

fn reveal(app: &AppHandle, id: u64, focus: bool) -> Result<bool, String> {
    let state = app.state::<ServiceMenuState>();
    let _lifecycle = state.lifecycle.lock().unwrap();
    let value = {
        let core = state.core.lock().unwrap();
        core.session
            .as_ref()
            .filter(|session| session.id == id)
            .and_then(|session| {
                session
                    .measured
                    .map(|measured| (session.request.clone(), measured))
            })
    };
    let Some((request, measured)) = value else {
        return Ok(false);
    };
    if focus && !window_active(app) {
        return Ok(false);
    }
    let view = app
        .get_webview(LABEL)
        .ok_or("Service menu renderer is unavailable")?;
    let owner = app
        .get_webview("main")
        .ok_or("Main webview is unavailable")?;
    let geometry = layout(
        &request,
        measured,
        owner.position().map_err(|error| error.to_string())?,
        owner.size().map_err(|error| error.to_string())?,
    );
    #[cfg(not(target_os = "linux"))]
    {
        view.set_position(PhysicalPosition::new(geometry.x, geometry.y))
            .map_err(|error| error.to_string())?;
        view.set_size(PhysicalSize::new(geometry.width, geometry.height))
            .map_err(|error| error.to_string())?;
    }
    #[cfg(target_os = "linux")]
    {
        let scale = app
            .get_window("main")
            .ok_or("Main window is unavailable")?
            .scale_factor()
            .map_err(|error| error.to_string())?;
        *state.gtk_layout.lock().unwrap() = Some(Layout {
            x: (f64::from(geometry.x) / scale).round() as i32,
            y: (f64::from(geometry.y) / scale).round() as i32,
            width: (f64::from(geometry.width) / scale).ceil() as u32,
            height: (f64::from(geometry.height) / scale).ceil() as u32,
        });
    }
    // Cancellation can arrive during native sizing. It invalidates core before
    // waiting for lifecycle, so no cancelled session may become visible here.
    #[cfg(not(target_os = "linux"))]
    {
        let mut core = state.core.lock().unwrap();
        let Some(session) = core.session.as_mut().filter(|session| session.id == id) else {
            return Ok(false);
        };
        session.visible = true;
    }
    #[cfg(target_os = "linux")]
    {
        // Resolve only a weak owner reference on GTK's thread. The final focus
        // check, display and focus transfer must share one UI callback: a click
        // queued while native geometry is being prepared must win over a popup.
        let (send, receive) = std::sync::mpsc::sync_channel(1);
        owner
            .with_webview(move |platform| {
                use gtk::prelude::*;
                let owner: gtk::glib::SendWeakRef<gtk::Widget> =
                    platform.inner().upcast::<gtk::Widget>().downgrade().into();
                let _ = send.send(owner);
            })
            .map_err(|error| error.to_string())?;
        let owner = receive.recv().map_err(|error| error.to_string())?;
        let native_layout = *state.gtk_layout.lock().unwrap();
        let handle = app.clone();
        let (send, receive) = std::sync::mpsc::sync_channel(1);
        view.with_webview(move |platform| {
            use gtk::prelude::*;
            let view = platform.inner();
            if focus
                && !owner.upgrade().is_some_and(|owner| {
                    owner.has_focus()
                        && owner
                            .toplevel()
                            .and_then(|widget| widget.downcast::<gtk::Window>().ok())
                            .is_some_and(|window| window.is_active())
                })
            {
                let _ = send.send(false);
                return;
            }
            {
                let state = handle.state::<ServiceMenuState>();
                let mut core = state.core.lock().unwrap();
                let Some(session) = core.session.as_mut().filter(|session| session.id == id) else {
                    let _ = send.send(false);
                    return;
                };
                session.visible = true;
            }
            if let Some(layout) = native_layout {
                view.set_size_request(layout.width as i32, layout.height as i32);
            }
            if let Some(parent) = view
                .parent()
                .and_then(|parent| parent.downcast::<gtk::Overlay>().ok())
            {
                parent.reorder_overlay(&view, -1);
                view.show();
                parent.queue_allocate();
                parent.size_allocate(&parent.allocation());
            }
            if let Some(window) = view.parent_window() {
                window.ensure_native();
                window.raise();
            }
            if let Some(window) = view.window() {
                window.raise();
            }
            view.queue_draw();
            if focus {
                view.grab_focus();
            }
            let _ = send.send(true);
        })
        .map_err(|error| error.to_string())?;
        if !receive.recv().map_err(|error| error.to_string())? {
            return Ok(false);
        }
    }
    #[cfg(windows)]
    {
        let (send, receive) = std::sync::mpsc::sync_channel(1);
        view.with_webview(move |platform| {
            use windows_sys::Win32::UI::WindowsAndMessaging::{
                SetWindowPos, HWND_TOP, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE,
            };
            let result = (|| -> Result<(), String> {
                let mut hwnd = Default::default();
                // SAFETY: live native child container on its owning UI thread.
                unsafe {
                    platform
                        .controller()
                        .ParentWindow(&mut hwnd)
                        .map_err(|error| error.to_string())?;
                    if SetWindowPos(
                        hwnd.0,
                        HWND_TOP,
                        0,
                        0,
                        0,
                        0,
                        SWP_NOACTIVATE | SWP_NOMOVE | SWP_NOSIZE,
                    ) == 0
                    {
                        return Err(std::io::Error::last_os_error().to_string());
                    }
                }
                Ok(())
            })();
            let _ = send.send(result);
        })
        .map_err(|error| error.to_string())?;
        receive.recv().map_err(|error| error.to_string())??;
    }
    #[cfg(target_os = "macos")]
    if let Some(window) = app.get_window("main") {
        view.reparent(&window).map_err(|error| error.to_string())?;
        view.set_position(PhysicalPosition::new(geometry.x, geometry.y))
            .map_err(|error| error.to_string())?;
    }
    if !state
        .core
        .lock()
        .unwrap()
        .session
        .as_ref()
        .is_some_and(|session| session.id == id)
    {
        return Ok(false);
    }
    #[cfg(not(target_os = "linux"))]
    {
        view.show().map_err(|error| error.to_string())?;
        if focus && window_active(app) {
            view.set_focus().map_err(|error| error.to_string())?;
        }
    }
    // A cancellation that raced reveal is completed under the same lifecycle
    // before its close command returns; it cannot affect a newer session.
    if !state
        .core
        .lock()
        .unwrap()
        .session
        .as_ref()
        .is_some_and(|session| session.id == id)
    {
        hide_idle(app)?;
        return Ok(false);
    }
    Ok(true)
}

pub(crate) fn restack(app: &AppHandle) {
    let id = app
        .state::<ServiceMenuState>()
        .core
        .lock()
        .unwrap()
        .session
        .as_ref()
        .filter(|session| session.visible)
        .map(|session| session.id);
    if let Some(id) = id {
        let app = app.clone();
        tauri::async_runtime::spawn_blocking(move || {
            if let Err(error) = reveal(&app, id, false) {
                report(error);
                close(&app);
            }
        });
    }
}

#[tauri::command]
pub(crate) async fn prepare_service_menu(
    app: AppHandle,
    webview: Webview,
    request: Request,
) -> Result<u64, String> {
    require(&webview, "main")?;
    crate::require_known_service(&app.state::<crate::AppState>(), &request.service_id)?;
    if !request.x.is_finite()
        || !request.y.is_finite()
        || !(0.0..=100000.0).contains(&request.x)
        || !(0.0..=100000.0).contains(&request.y)
        || !ratio(request.pixel_ratio)
        || request.label.len() > 1024
        || !(50..=200).contains(&request.zoom_percent)
        || !matches!(request.theme.as_str(), "light" | "dark" | "oled")
    {
        return Err("Service menu presentation is invalid".into());
    }
    let handle = app.clone();
    let id = tauri::async_runtime::spawn_blocking(move || {
        let app = handle;
        let state = app.state::<ServiceMenuState>();
        let _lifecycle = state.lifecycle.lock().unwrap();
        let previous = state.core.lock().unwrap().session.take();
        hide_idle(&app)?;
        if let Some(previous) = previous {
            notify_closed(&app, previous.id, false)?;
        }
        let id = state.core.lock().unwrap().prepare(request);
        if state.core.lock().unwrap().session.is_none() {
            return Ok(id);
        }
        if let Err(error) = ensure_view(&app).and_then(|()| announce(&app)) {
            state.core.lock().unwrap().take(id);
            hide_idle(&app)?;
            return Err(error);
        }
        Ok(id)
    })
    .await
    .map_err(|error| error.to_string())??;

    // Keep the owner intent cancellable until the renderer is actually ready.
    // Presenting never waits on page loading or measurement after this returns.
    for _ in 0..160 {
        let ready = {
            let state = app.state::<ServiceMenuState>();
            let core = state.core.lock().unwrap();
            let Some(session) = core.session.as_ref().filter(|session| session.id == id) else {
                return Ok(id);
            };
            session.measured.is_some()
        };
        if ready {
            return Ok(id);
        }
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;
    }
    tauri::async_runtime::spawn_blocking(move || {
        close_id(&app, id, false)?;
        let state = app.state::<ServiceMenuState>();
        let _lifecycle = state.lifecycle.lock().unwrap();
        let idle = {
            let core = state.core.lock().unwrap();
            core.session.is_none() && core.revision == id
        };
        if idle {
            if let Some(view) = app.get_webview(LABEL) {
                view.close().map_err(|error| error.to_string())?;
            }
        }
        Ok::<(), String>(())
    })
    .await
    .map_err(|error| error.to_string())??;
    Err("Service menu renderer did not become ready".into())
}

#[tauri::command]
pub(crate) async fn present_service_menu(
    app: AppHandle,
    webview: Webview,
    id: u64,
) -> Result<bool, String> {
    require(&webview, "main")?;
    tauri::async_runtime::spawn_blocking(move || reveal(&app, id, true))
        .await
        .map_err(|error| error.to_string())?
}

#[tauri::command]
pub(crate) async fn close_service_menu(
    app: AppHandle,
    webview: Webview,
    id: u64,
    restore_focus: bool,
) -> Result<(), String> {
    require(&webview, "main")?;
    tauri::async_runtime::spawn_blocking(move || close_id(&app, id, restore_focus))
        .await
        .map_err(|error| error.to_string())?
}

#[tauri::command]
pub(crate) fn get_service_menu(app: AppHandle, webview: Webview) -> Result<Snapshot, String> {
    require(&webview, LABEL)?;
    Ok(app
        .state::<ServiceMenuState>()
        .core
        .lock()
        .unwrap()
        .snapshot())
}

#[tauri::command]
pub(crate) fn measure_service_menu(
    app: AppHandle,
    webview: Webview,
    id: u64,
    measurement: Measurement,
) -> Result<(), String> {
    require(&webview, LABEL)?;
    if !measurement.width.is_finite()
        || !measurement.height.is_finite()
        || !(100.0..=600.0).contains(&measurement.width)
        || !(80.0..=800.0).contains(&measurement.height)
        || !ratio(measurement.pixel_ratio)
        || !measurement.inset_x.is_finite()
        || !measurement.inset_y.is_finite()
        || !(0.0..=64.0).contains(&measurement.inset_x)
        || !(0.0..=64.0).contains(&measurement.inset_y)
    {
        return Err("Service menu measurement is invalid".into());
    }
    let state = app.state::<ServiceMenuState>();
    let mut core = state.core.lock().unwrap();
    if let Some(session) = core
        .session
        .as_mut()
        .filter(|session| session.id == id && !session.visible)
    {
        session.measured = Some(measurement);
    }
    Ok(())
}

#[tauri::command]
pub(crate) async fn dismiss_service_menu(
    app: AppHandle,
    webview: Webview,
    id: u64,
    restore_focus: bool,
) -> Result<(), String> {
    require(&webview, LABEL)?;
    let visible = app
        .state::<ServiceMenuState>()
        .core
        .lock()
        .unwrap()
        .session
        .as_ref()
        .is_some_and(|session| session.id == id && session.visible);
    if !visible {
        return Ok(());
    }
    tauri::async_runtime::spawn_blocking(move || close_id(&app, id, restore_focus))
        .await
        .map_err(|error| error.to_string())?
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct Choice {
    id: u64,
    service_id: String,
    action: Action,
}

#[tauri::command]
pub(crate) async fn choose_service_menu(
    app: AppHandle,
    webview: Webview,
    id: u64,
    action: Action,
) -> Result<(), String> {
    require(&webview, LABEL)?;
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<ServiceMenuState>();
        let _lifecycle = state.lifecycle.lock().unwrap();
        let session = state.core.lock().unwrap().claim(id, action);
        let Some(session) = session else {
            return Ok(());
        };
        hide_idle(&app)?;
        crate::require_known_service(&app.state::<crate::AppState>(), &session.request.service_id)?;
        app.get_webview("main")
            .ok_or("Main webview is unavailable")?
            .set_focus()
            .map_err(|error| error.to_string())?;
        app.emit_to(
            EventTarget::webview("main"),
            "service-menu-action",
            Choice {
                id,
                service_id: session.request.service_id,
                action,
            },
        )
        .map_err(|error| error.to_string())
    })
    .await
    .map_err(|error| error.to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;
    fn request() -> Request {
        Request {
            service_id: "test".into(),
            label: "Test".into(),
            enabled: true,
            zoom_percent: 100,
            x: 220.0,
            y: 200.0,
            pixel_ratio: 1.0,
            theme: "dark".into(),
        }
    }
    #[test]
    fn stale_close_and_action_cannot_affect_new_opening() {
        let mut core = Core::default();
        let first = core.prepare(request());
        let next = core.prepare(request());
        core.session.as_mut().unwrap().visible = true;
        assert!(core.take(first).is_none());
        assert!(core.claim(first, Action::Toggle).is_none());
        assert_eq!(core.claim(next, Action::Settings).unwrap().id, next);
        assert!(core.claim(next, Action::Settings).is_none());
        assert!(core.snapshot().menu.is_none());
    }
    #[test]
    fn native_service_input_disarms_queued_preparation_until_fresh_owner_input() {
        let mut core = Core::default();
        let previous = core.prepare(request());
        core.owner_input = false;
        assert_eq!(core.session.take().unwrap().id, previous);
        let cancelled = core.prepare(request());
        assert!(core.snapshot().menu.is_none());
        assert!(core.claim(cancelled, Action::Settings).is_none());
        core.owner_input = true;
        let next = core.prepare(request());
        assert!(next > cancelled);
        assert!(core.take(previous).is_none());
        assert!(core.take(cancelled).is_none());
        assert_eq!(core.take(next).unwrap().id, next);
    }

    #[test]
    fn only_visible_enabled_actions_can_be_claimed() {
        let mut core = Core::default();
        let mut value = request();
        value.enabled = false;
        value.zoom_percent = 200;
        let id = core.prepare(value);
        assert!(core.claim(id, Action::Settings).is_none());
        core.session.as_mut().unwrap().visible = true;
        assert!(core.claim(id, Action::Reload).is_none());
        assert!(core.claim(id, Action::ZoomIn).is_none());
        assert!(core.claim(id, Action::Toggle).is_some());
    }
    #[test]
    fn independent_css_scales_and_titlebar_origin_are_converted() {
        let mut value = request();
        value.pixel_ratio = 1.5;
        let result = layout(
            &value,
            Measurement {
                width: 270.0,
                height: 309.0,
                pixel_ratio: 100.0 / 96.0,
                inset_x: 16.0,
                inset_y: 16.0,
            },
            PhysicalPosition::new(4, 48),
            PhysicalSize::new(1200, 900),
        );
        assert_eq!(
            result,
            Layout {
                x: 317,
                y: 331,
                width: 282,
                height: 322
            }
        );
    }
    #[test]
    fn opaque_surface_uses_its_measured_zero_insets() {
        let result = layout(
            &request(),
            Measurement {
                width: 238.0,
                height: 277.0,
                pixel_ratio: 1.0,
                inset_x: 0.0,
                inset_y: 0.0,
            },
            PhysicalPosition::new(0, 32),
            PhysicalSize::new(1100, 688),
        );
        assert_eq!(
            result,
            Layout {
                x: 220,
                y: 232,
                width: 238,
                height: 277
            }
        );
    }

    #[test]
    fn edge_and_tiny_bounds_never_clip_the_native_rectangle() {
        let mut value = request();
        value.x = 100000.0;
        value.y = 100000.0;
        for bounds in [PhysicalSize::new(1000, 600), PhysicalSize::new(100, 80)] {
            let result = layout(
                &value,
                Measurement {
                    width: 270.0,
                    height: 309.0,
                    pixel_ratio: 2.0,
                    inset_x: 16.0,
                    inset_y: 16.0,
                },
                PhysicalPosition::new(0, 32),
                bounds,
            );
            assert!(result.x >= 0 && result.y >= 32);
            assert!(result.x as u32 + result.width <= bounds.width);
            assert!((result.y - 32) as u32 + result.height <= bounds.height);
        }
        for invalid in [f64::NAN, f64::INFINITY, 0.0, -1.0, 100.0] {
            assert!(!ratio(invalid));
        }
    }
}
