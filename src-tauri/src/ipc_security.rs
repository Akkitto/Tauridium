//! Native authority belongs to app-owned renderers, never service children.
use tauri::Url;

const TOAST_COMMANDS: &[&str] = &[
    "get_download_toast",
    "dismiss_download_toast",
    "resize_download_toast",
];

const SERVICE_MENU_COMMANDS: &[&str] = &[
    "get_service_menu",
    "dismiss_service_menu",
    "service_menu_action",
];

const TITLEBAR_COMMANDS: &[&str] = &[
    "get_window_chrome",
    "open_window_menu",
    "focus_window_content",
];

pub(crate) fn command_allowed(label: &str, command: &str) -> bool {
    match label {
        "main" => {
            command == "get_window_chrome"
                || (!TOAST_COMMANDS.contains(&command)
                    && !TITLEBAR_COMMANDS.contains(&command)
                    && !SERVICE_MENU_COMMANDS.contains(&command))
        }
        "window-titlebar" => TITLEBAR_COMMANDS.contains(&command),
        "download-toast" => TOAST_COMMANDS.contains(&command),
        "service-menu" => SERVICE_MENU_COMMANDS.contains(&command),
        _ => false,
    }
}

pub(crate) fn service_navigation_allowed(url: &Url) -> bool {
    match url.scheme() {
        "http" | "https" => !matches!(
            url.host_str(),
            Some("tauri.localhost" | "asset.localhost" | "ipc.localhost")
        ),
        // Empty authentication popups remain unprivileged even if they inherit
        // an origin. No filesystem/app/IPC protocols belong in service views.
        "about" => url.as_str() == "about:blank",
        _ => false,
    }
}

pub(crate) fn bind_recipe_script(script: &str, origin: &str) -> String {
    let origin = serde_json::to_string(origin).expect("string serialization is infallible");
    format!(
        "(() => {{ if (!['http:', 'https:'].includes(location.protocol) || location.origin !== {origin}) return;\n{script}\n}})();"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn service_children_never_gain_native_authority() {
        for label in [
            "svc-mail",
            "svc-main",
            "",
            "main-child",
            "download-toast-child",
            "window-titlebar-child",
            "service-menu-child",
        ] {
            for command in [
                "get_app_metadata",
                "clear_service_cache",
                "export_audit_log",
                "get_download_toast",
                "get_window_chrome",
                "open_window_menu",
                "focus_window_content",
                "open_service_menu",
                "service_menu_action",
            ] {
                assert!(!command_allowed(label, command));
            }
        }
        assert!(command_allowed("main", "get_app_metadata"));
        assert!(!command_allowed("main", "get_download_toast"));
        assert!(command_allowed("download-toast", "get_download_toast"));
        assert!(command_allowed("service-menu", "service_menu_action"));
        assert!(!command_allowed("main", "service_menu_action"));
        assert!(!command_allowed("main", "get_service_menu"));
        assert!(command_allowed("main", "open_service_menu"));
        assert!(command_allowed("main", "settle_service_menu"));
        assert!(!command_allowed("service-menu", "settle_service_menu"));
        assert!(!command_allowed("service-menu", "open_service_menu"));
        assert!(!command_allowed("service-menu", "clear_service_cache"));
        assert!(!command_allowed("download-toast", "service_menu_action"));
        assert!(!command_allowed("window-titlebar", "service_menu_action"));
        assert!(!command_allowed("download-toast", "clear_service_cache"));
        for command in TITLEBAR_COMMANDS {
            assert!(command_allowed("window-titlebar", command));
        }
        for command in [
            "get_app_settings",
            "set_app_settings",
            "clear_service_cache",
            "get_download_toast",
            "export_backup",
        ] {
            assert!(!command_allowed("window-titlebar", command));
        }
        assert!(!command_allowed("main", "open_window_menu"));
        assert!(command_allowed("main", "get_window_chrome"));
    }

    #[test]
    fn service_navigation_rejects_native_and_filesystem_origins() {
        for value in [
            "tauri://localhost/index.html",
            "http://tauri.localhost/",
            "https://tauri.localhost/index.html",
            "http://ASSET.localhost/file",
            "http://ipc.localhost/",
            "file:///tmp/file",
            "javascript:alert(1)",
            "data:text/html,test",
            "about:srcdoc",
        ] {
            assert!(
                !service_navigation_allowed(&Url::parse(value).unwrap()),
                "{value}"
            );
        }
        for value in [
            "https://mail.proton.me/",
            "https://accounts.google.com/",
            "http://localhost:8000/",
            "http://192.168.178.1/",
            "about:blank",
        ] {
            assert!(
                service_navigation_allowed(&Url::parse(value).unwrap()),
                "{value}"
            );
        }
    }

    #[test]
    fn recipe_script_is_bound_to_the_configured_http_origin() {
        let wrapped =
            bind_recipe_script("window.recipeLoaded = true;", "https://mail.example.test");
        assert!(wrapped.contains("location.origin !== \"https://mail.example.test\""));
        assert!(wrapped.contains("['http:', 'https:']"));
        assert!(wrapped.find("return;").unwrap() < wrapped.find("window.recipeLoaded").unwrap());
    }
}
