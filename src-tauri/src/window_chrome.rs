//! Windows unified chrome with OS-owned caption controls and native popup menus.
//! The titlebar WebView never covers Windows' caption-button hit targets.
use serde::Serialize;
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use tauri::{AppHandle, Emitter, EventTarget, Manager};

pub(crate) const LABEL: &str = "window-titlebar";
#[cfg(windows)]
pub(crate) const HEIGHT: f64 = 32.0;
pub(crate) const MENUS: [&str; 6] = ["Tauridium", "Edit", "View", "Navigate", "Services", "About"];

#[derive(Default)]
pub(crate) struct WindowChromeState {
    enabled: AtomicBool,
    ready: AtomicBool,
    top: AtomicU32,
    left: AtomicU32,
    fallback: AtomicBool,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct Snapshot {
    enabled: bool,
    supported: bool,
    requested: bool,
    fallback: bool,
    title: String,
    theme: String,
    active: bool,
}

pub(crate) fn requested(settings: &serde_json::Value) -> bool {
    settings
        .get("unifiedTitleBar")
        .and_then(serde_json::Value::as_bool)
        .unwrap_or(true)
}

pub(crate) fn snapshot(app: &AppHandle) -> Snapshot {
    let state = app.state::<WindowChromeState>();
    let settings = app
        .state::<crate::AppState>()
        .settings
        .lock()
        .unwrap()
        .clone();
    let window = app.get_window("main");
    let system_dark = window.as_ref().and_then(|w| w.theme().ok()) == Some(tauri::Theme::Dark);
    let theme = match settings.get("theme").and_then(serde_json::Value::as_str) {
        Some("light") => "light",
        Some("oled") => "oled",
        Some("dark") => "dark",
        _ if system_dark => "dark",
        _ => "light",
    };
    #[cfg(windows)]
    let active = window
        .as_ref()
        .and_then(|w| w.hwnd().ok())
        .is_some_and(|hwnd| {
            // SAFETY: foreground ownership is queried without changing window state.
            unsafe {
                windows_sys::Win32::UI::WindowsAndMessaging::GetForegroundWindow() == hwnd.0.cast()
            }
        });
    #[cfg(not(windows))]
    let active = window
        .as_ref()
        .and_then(|w| w.is_focused().ok())
        .unwrap_or(false);
    Snapshot {
        enabled: state.enabled.load(Ordering::Acquire),
        supported: cfg!(windows),
        requested: requested(&settings),
        fallback: state.fallback.load(Ordering::Acquire),
        title: window
            .as_ref()
            .and_then(|w| w.title().ok())
            .unwrap_or_else(|| "Tauridium".into()),
        theme: theme.into(),
        active,
    }
}

pub(crate) fn content_top(app: &AppHandle) -> f64 {
    let state = app.state::<WindowChromeState>();
    let scale = app
        .get_window("main")
        .and_then(|w| w.scale_factor().ok())
        .unwrap_or(1.0);
    f64::from(state.top.load(Ordering::Acquire)) / scale
}

pub(crate) fn refresh(app: &AppHandle) {
    if !app
        .state::<WindowChromeState>()
        .enabled
        .load(Ordering::Acquire)
    {
        return;
    }
    let handle = app.clone();
    // Native calls stay on the window thread; no settings lock crosses them.
    if let Err(error) = app.run_on_main_thread(move || {
        #[cfg(windows)]
        if let Err(error) = platform::colors(&handle) {
            crate::startup_diagnostics::log("primary", "titlebar.colors.error", &error);
        }
        if let Err(error) = handle.emit_to(
            EventTarget::webview(LABEL),
            "window-chrome-changed",
            snapshot(&handle),
        ) {
            crate::startup_diagnostics::log(
                "primary",
                "titlebar.snapshot.error",
                &error.to_string(),
            );
        }
    }) {
        crate::startup_diagnostics::log("primary", "titlebar.refresh.error", &error.to_string());
    }
}

pub(crate) fn install(app: &AppHandle) -> Result<(), String> {
    #[cfg(windows)]
    {
        let settings = app
            .state::<crate::AppState>()
            .settings
            .lock()
            .unwrap()
            .clone();
        if !requested(&settings) {
            return Ok(());
        }
        if let Err(error) = install_windows(app) {
            classic_fallback(app, &error)?;
        } else {
            let handle = app.clone();
            tauri::async_runtime::spawn(async move {
                tokio::time::sleep(std::time::Duration::from_secs(15)).await;
                let state = handle.state::<WindowChromeState>();
                if state.enabled.load(Ordering::Acquire) && !state.ready.load(Ordering::Acquire) {
                    let restore = handle.clone();
                    if let Err(error) = handle.run_on_main_thread(move || {
                        if restore
                            .state::<WindowChromeState>()
                            .ready
                            .load(Ordering::Acquire)
                        {
                            return;
                        }
                        if let Err(error) = classic_fallback(
                            &restore,
                            "Unified title-bar renderer did not become ready",
                        ) {
                            crate::startup_diagnostics::log(
                                "primary",
                                "titlebar.fallback.error",
                                &error,
                            );
                        }
                    }) {
                        crate::startup_diagnostics::log(
                            "primary",
                            "titlebar.fallback.error",
                            &error.to_string(),
                        );
                    }
                }
            });
        }
    }
    #[cfg(not(windows))]
    let _ = app;
    Ok(())
}

#[cfg(windows)]
fn classic_fallback(app: &AppHandle, reason: &str) -> Result<(), String> {
    let state = app.state::<WindowChromeState>();
    state.enabled.store(false, Ordering::Release);
    state.top.store(0, Ordering::Release);
    state.left.store(0, Ordering::Release);
    state.fallback.store(true, Ordering::Release);
    if let Some(view) = app.get_webview(LABEL) {
        view.close().map_err(|e| e.to_string())?;
    }
    platform::remove(app)?;
    app.get_window("main")
        .ok_or("Main window is unavailable")?
        .show_menu()
        .map_err(|e| e.to_string())?;
    restore_main(app)?;
    crate::startup_diagnostics::log("primary", "titlebar.classic_fallback", reason);
    app.emit_to(
        EventTarget::webview("main"),
        "window-chrome-changed",
        snapshot(app),
    )
    .map_err(|e| e.to_string())?;
    crate::reposition_active(app);
    Ok(())
}

#[cfg(windows)]
fn install_windows(app: &AppHandle) -> Result<(), String> {
    use tauri::webview::{NewWindowResponse, WebviewBuilder};
    use tauri::{LogicalPosition, LogicalSize, WebviewUrl};
    let window = app.get_window("main").ok_or("Main window is unavailable")?;
    let main = app
        .get_webview("main")
        .ok_or("Main webview is unavailable")?;
    let main_url = if env!("TAURIDIUM_BUILD_MODE") == "production" {
        tauri::Url::parse("http://tauri.localhost").map_err(|e| e.to_string())?
    } else {
        app.config()
            .build
            .dev_url
            .clone()
            .ok_or("Development app URL is unavailable")?
    };
    let directory = app
        .path()
        .app_cache_dir()
        .map_err(|e| e.to_string())?
        .join(LABEL);
    std::fs::create_dir_all(&directory).map_err(|e| e.to_string())?;
    let builder = WebviewBuilder::new(LABEL, WebviewUrl::App("index.html".into()))
        .focused(false)
        .disable_drag_drop_handler()
        .data_directory(directory)
        .initialization_script(
            "Object.defineProperty(window, '__TAURIDIUM_TITLEBAR__', { value: true });",
        )
        .on_navigation(move |url| {
            url.scheme() == main_url.scheme()
                && url.host_str() == main_url.host_str()
                && url.port() == main_url.port()
                && matches!(url.path(), "" | "/" | "/index.html")
        })
        .on_new_window(|_, _| NewWindowResponse::Deny);
    // Construct while the startup window is hidden. No hosted page or service
    // profile is ever loaded into this app-owned renderer.
    crate::startup_diagnostics::log(
        "primary",
        "titlebar.create.begin",
        "Creating local title-bar renderer",
    );
    window
        .add_child(
            builder,
            LogicalPosition::new(-30000.0, 0.0),
            LogicalSize::new(1.0, HEIGHT),
        )
        .map_err(|e| format!("Unable to create unified title bar: {e}"))?;
    crate::startup_diagnostics::log(
        "primary",
        "titlebar.create.ready",
        "Local title-bar renderer created",
    );
    platform::install(app)?;
    crate::startup_diagnostics::log(
        "primary",
        "titlebar.frame.ready",
        "Native title-bar frame installed",
    );
    app.state::<WindowChromeState>()
        .enabled
        .store(true, Ordering::Release);
    main.set_auto_resize(false).map_err(|e| e.to_string())?;
    window.hide_menu().map_err(|e| e.to_string())?;
    layout(app)?;
    platform::colors(app)?;
    crate::startup_diagnostics::log(
        "primary",
        "titlebar.layout.ready",
        "Unified title-bar layout installed",
    );
    Ok(())
}

pub(crate) fn layout(app: &AppHandle) -> Result<(), String> {
    #[cfg(windows)]
    {
        use tauri::{PhysicalPosition, PhysicalSize};
        let state = app.state::<WindowChromeState>();
        if !state.enabled.load(Ordering::Acquire) {
            return Ok(());
        }
        let window = app.get_window("main").ok_or("Main window is unavailable")?;
        if window.is_minimized().map_err(|e| e.to_string())? {
            return Ok(());
        }
        let main = app
            .get_webview("main")
            .ok_or("Main webview is unavailable")?;
        let titlebar = app
            .get_webview(LABEL)
            .ok_or("Unified title bar is unavailable")?;
        let size = window.inner_size().map_err(|e| e.to_string())?;
        if window.is_fullscreen().map_err(|e| e.to_string())? {
            state.top.store(0, Ordering::Release);
            titlebar.hide().map_err(|e| e.to_string())?;
            main.set_bounds(tauri::Rect {
                position: PhysicalPosition::new(0, 0).into(),
                size: size.into(),
            })
            .map_err(|e| e.to_string())?;
            return Ok(());
        }
        let geometry = platform::geometry(&window)?;
        state.top.store(geometry.height, Ordering::Release);
        state.left.store(geometry.left, Ordering::Release);
        main.set_bounds(tauri::Rect {
            position: PhysicalPosition::new(0, geometry.height as i32).into(),
            size: PhysicalSize::new(
                size.width,
                size.height.saturating_sub(geometry.height).max(1),
            )
            .into(),
        })
        .map_err(|e| e.to_string())?;
        titlebar
            .set_bounds(tauri::Rect {
                position: PhysicalPosition::new(geometry.left as i32, geometry.border as i32)
                    .into(),
                size: PhysicalSize::new(
                    geometry.width.max(1),
                    geometry.height.saturating_sub(geometry.border).max(1),
                )
                .into(),
            })
            .map_err(|e| e.to_string())?;
        titlebar.show().map_err(|e| e.to_string())?;
    }
    #[cfg(not(windows))]
    let _ = app;
    Ok(())
}

#[cfg(windows)]
fn restore_main(app: &AppHandle) -> Result<(), String> {
    use tauri::PhysicalPosition;
    let window = app.get_window("main").ok_or("Main window is unavailable")?;
    let view = app
        .get_webview("main")
        .ok_or("Main webview is unavailable")?;
    view.set_bounds(tauri::Rect {
        position: PhysicalPosition::new(0, 0).into(),
        size: window.inner_size().map_err(|e| e.to_string())?.into(),
    })
    .map_err(|e| e.to_string())?;
    view.set_auto_resize(true).map_err(|e| e.to_string())
}

pub(crate) fn keep_menu_unified(app: &AppHandle) -> Result<(), String> {
    if app
        .state::<WindowChromeState>()
        .enabled
        .load(Ordering::Acquire)
    {
        app.get_window("main")
            .ok_or("Main window is unavailable")?
            .hide_menu()
            .map_err(|e| e.to_string())?;
        layout(app)?;
    }
    Ok(())
}

#[tauri::command]
pub(crate) fn get_window_chrome(app: AppHandle, webview: tauri::Webview) -> Snapshot {
    if webview.label() == LABEL {
        app.state::<WindowChromeState>()
            .ready
            .store(true, Ordering::Release);
    }
    snapshot(&app)
}

#[tauri::command]
pub(crate) async fn open_window_menu(app: AppHandle, index: usize, x: f64) -> Result<(), String> {
    if index > MENUS.len() || !x.is_finite() || !(0.0..=65536.0).contains(&x) {
        return Err("Invalid application menu position".into());
    }
    if !app
        .state::<WindowChromeState>()
        .enabled
        .load(Ordering::Acquire)
    {
        return Err("The unified title bar is not active".into());
    }
    tauri::async_runtime::spawn_blocking(move || {
        use tauri::menu::ContextMenu;
        let window = app.get_window("main").ok_or("Main window is unavailable")?;
        let menu = app.menu().ok_or("Application menu is unavailable")?;
        let items = menu.items().map_err(|e| e.to_string())?;
        // Restore the active content target before native Edit actions execute.
        let active = app
            .state::<crate::AppState>()
            .active
            .lock()
            .unwrap()
            .clone();
        let target = active
            .as_ref()
            .and_then(|id| app.get_webview(&format!("svc-{id}")))
            .or_else(|| app.get_webview("main"));
        if let Some(view) = target {
            view.set_focus().map_err(|e| e.to_string())?;
        }
        let offset = f64::from(
            app.state::<WindowChromeState>()
                .left
                .load(Ordering::Acquire),
        ) / window.scale_factor().map_err(|e| e.to_string())?;
        let position = tauri::LogicalPosition::new(x + offset, content_top(&app));
        if index == MENUS.len() {
            menu.popup_at(window, position)
        } else {
            items
                .get(index)
                .and_then(|item| item.as_submenu())
                .ok_or("Application menu is unavailable")?
                .popup_at(window, position)
        }
        .map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
pub(crate) fn focus_window_content(app: AppHandle) -> Result<(), String> {
    let active = app
        .state::<crate::AppState>()
        .active
        .lock()
        .unwrap()
        .clone();
    let view = active
        .as_ref()
        .and_then(|id| app.get_webview(&format!("svc-{id}")))
        .or_else(|| app.get_webview("main"))
        .ok_or("Application content is unavailable")?;
    view.set_focus().map_err(|e| e.to_string())
}

#[cfg(windows)]
#[path = "window_chrome_windows.rs"]
mod platform;

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn older_settings_default_to_unified_and_explicit_classic_is_preserved() {
        assert!(requested(&serde_json::json!({})));
        assert!(requested(&serde_json::json!({"unifiedTitleBar": true})));
        assert!(!requested(&serde_json::json!({"unifiedTitleBar": false})));
    }
}
