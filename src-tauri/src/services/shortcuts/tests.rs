use super::*;
use serde_json::json;

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
