//! A deliberately small, allowlisted support report. Never collect raw diagnostics,
//! account/session data, service identities, URLs, paths or clipboard contents.
#[cfg(target_os = "linux")]
use gtk::prelude::*;
use serde_json::Value;
use tauri::{AppHandle, Manager};

use crate::{distribution, AppState, TAURIDIUM_BUILD_MODE, TAURIDIUM_TARGET};

const COPY_ERROR: &str =
    "Unable to copy support information. Open the preview and copy it manually.";

#[derive(Default)]
struct Presentation {
    theme: &'static str,
    sidebar_collapsed: Option<bool>,
    styled_service_menu: Option<bool>,
    capture_service_shortcuts: Option<bool>,
}

impl Presentation {
    fn from_settings(settings: &Value) -> Self {
        Self {
            theme: match settings.get("theme").and_then(Value::as_str) {
                Some("system") => "System",
                Some("light") => "Light",
                Some("dark") => "Dark",
                Some("oled") => "Black OLED",
                _ => "Unavailable",
            },
            sidebar_collapsed: settings.get("sidebarCollapsed").and_then(Value::as_bool),
            styled_service_menu: settings
                .get("prettyServiceContextMenu")
                .and_then(Value::as_bool),
            capture_service_shortcuts: settings
                .get("captureServiceShortcuts")
                .and_then(Value::as_bool),
        }
    }
}

fn flag(value: Option<bool>) -> &'static str {
    match value {
        Some(true) => "Enabled",
        Some(false) => "Disabled",
        None => "Unavailable",
    }
}

fn safe_runtime_version(value: Option<&str>) -> Option<&str> {
    value.filter(|value| {
        // WebView2 may append one of its documented preview-channel names.
        let (version, channel) = value
            .split_once(' ')
            .map_or((*value, None), |(version, channel)| {
                (version, Some(channel))
            });
        value.len() <= 64
            && channel.is_none_or(|channel| {
                ["beta", "dev", "canary"]
                    .iter()
                    .any(|known| channel.eq_ignore_ascii_case(known))
            })
            && !version.is_empty()
            && version.split('.').all(|part| {
                !part.is_empty()
                    && part.len() <= 10
                    && part.bytes().all(|byte| byte.is_ascii_digit())
            })
    })
}

struct Report {
    runtime_version: Option<String>,
    presentation: Presentation,
    unified_title_bar: Option<bool>,
    service_webviews: usize,
    display_backend: &'static str,
}

impl Report {
    fn render(&self) -> String {
        let engine = if cfg!(windows) {
            "WebView2"
        } else if cfg!(target_os = "linux") {
            "WebKitGTK"
        } else {
            "WebKit"
        };
        let os = if cfg!(windows) {
            "Windows"
        } else if cfg!(target_os = "macos") {
            "macOS"
        } else {
            std::env::consts::OS
        };
        let runtime =
            safe_runtime_version(self.runtime_version.as_deref()).unwrap_or("Unavailable");
        let title_bar = match self.unified_title_bar {
            Some(true) => "Unified",
            Some(false) => "Native",
            None => "Unavailable",
        };
        let theme = if self.presentation.theme.is_empty() {
            "Unavailable"
        } else {
            self.presentation.theme
        };
        format!(
            "```text\nTauridium support information\nFormat: 1\n\
             App version: {}\nBuild mode: {}\nBuild target: {}\n\
             Operating system: {}\nApp architecture: {}\nDisplay backend: {}\n\
             WebView engine: {}\nWebView version: {}\nDistribution: {}\n\
             Service webviews: {}\nTheme setting: {}\nTitle bar: {}\n\
             Collapsed sidebar: {}\nStyled service menu: {}\n\
             Service shortcut capture: {}\n```\n",
            env!("CARGO_PKG_VERSION"),
            TAURIDIUM_BUILD_MODE,
            TAURIDIUM_TARGET,
            os,
            std::env::consts::ARCH,
            self.display_backend,
            engine,
            runtime,
            distribution::mode().as_str(),
            self.service_webviews,
            theme,
            title_bar,
            flag(self.presentation.sidebar_collapsed),
            flag(self.presentation.styled_service_menu),
            flag(self.presentation.capture_service_shortcuts),
        )
    }
}

// Called on the native UI thread, including for GTK's actual display type.
fn collect(app: &AppHandle) -> String {
    let state = app.state::<AppState>();
    let presentation = state
        .settings
        .lock()
        .ok()
        .map(|settings| Presentation::from_settings(&settings))
        .unwrap_or_default();
    #[cfg(target_os = "linux")]
    let display_backend = {
        match gtk::gdk::Display::default().map(|display| display.type_()) {
            Some(kind) if kind.name() == "GdkWaylandDisplay" => "Wayland",
            Some(kind) if kind.name() == "GdkX11Display" => "X11",
            Some(_) => "Other",
            None => "Unavailable",
        }
    };
    #[cfg(windows)]
    let display_backend = "Win32";
    #[cfg(target_os = "macos")]
    let display_backend = "AppKit";
    #[cfg(not(any(target_os = "linux", target_os = "macos", windows)))]
    let display_backend = "Unavailable";

    Report {
        runtime_version: wry::webview_version().ok(),
        presentation,
        unified_title_bar: crate::window_chrome::unified_title_bar_enabled(app),
        service_webviews: app
            .webviews()
            .keys()
            .filter(|label| label.starts_with("svc-"))
            .count(),
        display_backend,
    }
    .render()
}

async fn gather(app: &AppHandle) -> Result<String, String> {
    let (send, receive) = tokio::sync::oneshot::channel();
    let handle = app.clone();
    app.run_on_main_thread(move || {
        let _ = send.send(collect(&handle));
    })
    .map_err(|_| "Support information is temporarily unavailable".to_string())?;
    receive
        .await
        .map_err(|_| "Support information is temporarily unavailable".to_string())
}

fn require_main(webview: &tauri::Webview) -> Result<(), String> {
    if webview.label() == "main" {
        Ok(())
    } else {
        Err("Support information is available only in the main application".into())
    }
}

#[tauri::command]
pub(crate) async fn get_support_information(
    app: AppHandle,
    webview: tauri::Webview,
) -> Result<String, String> {
    require_main(&webview)?;
    gather(&app).await
}

#[cfg(any(windows, target_os = "macos"))]
static COPY_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

async fn write_report(app: &AppHandle, report: String) -> Result<(), String> {
    #[cfg(target_os = "linux")]
    {
        let (send, receive) = tokio::sync::oneshot::channel();
        app.run_on_main_thread(move || {
            // GTK uses the focused application's normal selection protocol on
            // both X11 and Wayland; no compositor-specific data-control access.
            let result = if gtk::gdk::Display::default().is_some() {
                let clipboard = gtk::Clipboard::get(&gtk::gdk::SELECTION_CLIPBOARD);
                clipboard.set_text(&report);
                Ok(())
            } else {
                Err(COPY_ERROR.to_string())
            };
            let _ = send.send(result);
        })
        .map_err(|_| COPY_ERROR.to_string())?;
        receive.await.map_err(|_| COPY_ERROR.to_string())?
    }
    #[cfg(any(windows, target_os = "macos"))]
    {
        let _ = app;
        tauri::async_runtime::spawn_blocking(move || {
            // Clipboard operations must not race or stall the application's UI.
            let _guard = COPY_LOCK.lock().map_err(|_| COPY_ERROR.to_string())?;
            let mut clipboard = arboard::Clipboard::new().map_err(|_| COPY_ERROR.to_string())?;
            clipboard
                .set_text(report)
                .map_err(|_| COPY_ERROR.to_string())
        })
        .await
        .map_err(|_| COPY_ERROR.to_string())?
    }
    #[cfg(not(any(target_os = "linux", target_os = "macos", windows)))]
    {
        let _ = (app, report);
        Err(COPY_ERROR.to_string())
    }
}

#[tauri::command]
pub(crate) async fn copy_support_information(
    app: AppHandle,
    webview: tauri::Webview,
) -> Result<String, String> {
    require_main(&webview)?;
    let report = gather(&app).await?;
    write_report(&app, report.clone()).await?;
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn report(settings: &Value, version: Option<&str>) -> Report {
        Report {
            runtime_version: version.map(str::to_owned),
            presentation: Presentation::from_settings(settings),
            unified_title_bar: Some(false),
            service_webviews: 3,
            display_backend: "X11",
        }
    }

    #[test]
    fn report_contains_only_the_reviewed_fields() {
        let text = report(
            &json!({
                "theme": "dark", "sidebarCollapsed": false,
                "prettyServiceContextMenu": true, "captureServiceShortcuts": true
            }),
            Some("2.50.4"),
        )
        .render();
        let keys: Vec<_> = text
            .lines()
            .filter_map(|line| line.split_once(':').map(|(key, _)| key))
            .collect();
        assert_eq!(
            keys,
            [
                "Format",
                "App version",
                "Build mode",
                "Build target",
                "Operating system",
                "App architecture",
                "Display backend",
                "WebView engine",
                "WebView version",
                "Distribution",
                "Service webviews",
                "Theme setting",
                "Title bar",
                "Collapsed sidebar",
                "Styled service menu",
                "Service shortcut capture",
            ]
        );
        assert!(text.starts_with("```text\nTauridium support information\n"));
        assert!(text.ends_with("\n```\n"));
        assert!(text.contains("WebView version: 2.50.4\n"));
        assert!(text.contains("Styled service menu: Enabled\n"));
        assert!(text.contains("Collapsed sidebar: Disabled\n"));
        assert!(text.len() < 2048);
    }

    #[test]
    fn private_and_invalid_preference_values_never_reach_the_report() {
        let settings = json!({
            "theme": "PRIVATE_THEME_CANARY",
            "sidebarCollapsed": "PRIVATE_BOOLEAN_CANARY",
            "prettyServiceContextMenu": {"private": "PRIVATE_OBJECT_CANARY"},
            "userAgentPref": "PRIVATE_AGENT_CANARY",
            "windowTitleTemplate": "PRIVATE_TITLE_CANARY",
            "automaticBackupDirectory": "/private/PATH_CANARY",
            "serviceCustomUrlTemplates": {"name": "PRIVATE_SERVICE_CANARY"},
            "server": "https://private.invalid/URL_CANARY",
            "password": "CANARY",
            "token": "CANARY",
            "sandboxes": [{"name": "PRIVATE_SANDBOX_CANARY"}]
        });
        let original = settings.clone();
        let text = report(&settings, Some("2.50.4\nPRIVATE_VERSION_CANARY")).render();
        assert!(!text.contains("PRIVATE_"));
        assert!(!text.contains("CANARY"));
        assert!(!text.contains("private.invalid"));
        assert!(!text.contains("/private/"));
        assert!(text.contains("WebView version: Unavailable"));
        assert!(text.contains("Theme setting: Unavailable"));
        assert_eq!(settings, original);
    }

    #[test]
    fn runtime_versions_reject_paths_control_characters_and_arbitrary_text() {
        for value in [
            "",
            "2..50",
            ".2",
            "2.",
            "2.50 secret",
            "/private/version",
            "user@example.invalid",
            "2.50.4\r\nCANARY",
            "2.50.4\u{202e}",
        ] {
            assert_eq!(safe_runtime_version(Some(value)), None, "{value:?}");
        }
        let long = "1".repeat(65);
        assert_eq!(safe_runtime_version(Some(&long)), None);
        for value in [
            "2.50.4",
            "141.0.3537.85",
            "620.1.15",
            "2",
            "141.0.3537.85 Beta",
            "142.0.0.0 dev",
            "143.0.0.0 Canary",
        ] {
            assert_eq!(safe_runtime_version(Some(value)), Some(value));
        }
    }

    #[test]
    fn missing_presentation_values_are_explicitly_unavailable() {
        let mut report = report(&Value::Null, None);
        report.unified_title_bar = None;
        let text = report.render();
        for key in [
            "WebView version",
            "Theme setting",
            "Title bar",
            "Collapsed sidebar",
            "Styled service menu",
            "Service shortcut capture",
        ] {
            assert!(text.contains(&format!("{key}: Unavailable")));
        }
    }

    #[test]
    fn support_commands_never_belong_to_service_or_overlay_renderers() {
        for command in ["get_support_information", "copy_support_information"] {
            assert!(crate::ipc_security::command_allowed("main", command));
            for label in [
                "svc-private",
                "service-menu",
                "download-toast",
                "window-titlebar",
                "main-child",
                "",
            ] {
                assert!(
                    !crate::ipc_security::command_allowed(label, command),
                    "{label}: {command}"
                );
            }
        }
    }
}
