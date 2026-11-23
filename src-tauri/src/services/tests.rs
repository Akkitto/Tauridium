use super::*;

#[test]
fn service_toast_overlay_script_encodes_untrusted_text_without_page_global() {
    let message = "quote \" and newline\n);alert(1)//";
    let encoded = serde_json::to_string(message).unwrap();
    let script = service_toast_overlay_script(message, 2600).unwrap();

    assert!(script.contains(&format!(")({encoded},2600);")));
    assert!(!script.contains(message));
    assert!(!script.contains("window.__tauridiumShowToast"));
    assert!(script.contains("attachShadow"));
}
