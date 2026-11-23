use super::*;
use serde_json::json;
use tauri::Url;

#[test]
fn ensure_scheme_prepends_https_when_missing() {
    assert_eq!(ensure_scheme("example.com"), "https://example.com");
    assert_eq!(ensure_scheme("https://example.com"), "https://example.com");
    assert_eq!(ensure_scheme("http://example.com"), "http://example.com");
}
#[test]
fn nested_blob_url_origins_are_opaque_without_recursive_stack_growth() {
    for prefixes in [1, 2, 10_000] {
        let value = format!("{}https://example.invalid/", "blob:".repeat(prefixes));
        let parsed = Url::parse(&value).unwrap();
        assert_eq!(parsed.origin().is_tuple(), prefixes == 1);
    }
}
#[test]
fn resolve_url_uses_plain_service_url() {
    let cfg = json!({ "config": { "serviceURL": "https://web.whatsapp.com" } });
    assert_eq!(
        resolve_url(&cfg, None, None, &CustomUrlTemplateValues::default()).unwrap(),
        "https://web.whatsapp.com"
    );
}
#[test]
fn resolve_url_honours_custom_url_only_when_allowed() {
    let cfg = json!({ "config": { "serviceURL": "https://default", "hasCustomUrl": true } });
    assert_eq!(
        resolve_url(
            &cfg,
            Some("chat.example.fr"),
            None,
            &CustomUrlTemplateValues::default()
        )
        .unwrap(),
        "https://chat.example.fr"
    );
    // Empty custom URL falls back to serviceURL.
    assert_eq!(
        resolve_url(&cfg, Some(""), None, &CustomUrlTemplateValues::default()).unwrap(),
        "https://default"
    );
    // A recipe without hasCustomUrl ignores the custom URL.
    let cfg2 = json!({ "config": { "serviceURL": "https://default" } });
    assert_eq!(
        resolve_url(
            &cfg2,
            Some("chat.example.fr"),
            None,
            &CustomUrlTemplateValues::default()
        )
        .unwrap(),
        "https://default"
    );
}
#[test]
fn resolve_url_substitutes_team_id() {
    let cfg =
        json!({ "config": { "serviceURL": "https://{teamId}.slack.com", "hasTeamId": true } });
    assert_eq!(
        resolve_url(
            &cfg,
            None,
            Some("acme"),
            &CustomUrlTemplateValues::default()
        )
        .unwrap(),
        "https://acme.slack.com"
    );
}
#[test]
fn resolve_url_uses_recipe_team_url_and_custom_placeholders() {
    let cfg = json!({
        "config": {
            "serviceURL": "https://opencode.ai/go",
            "teamURL": "https://opencode.ai/workspace/{teamId}/go",
            "hasTeamId": true,
            "hasCustomUrl": true
        }
    });
    assert_eq!(
        resolve_url(
            &cfg,
            None,
            Some("wrk_01ABC123EXAMPLE"),
            &CustomUrlTemplateValues::default(),
        )
        .unwrap(),
        "https://opencode.ai/workspace/wrk_01ABC123EXAMPLE/go"
    );

    let templates = CustomUrlTemplateValues {
        enabled: true,
        custom_id_1: "alpha".into(),
        custom_id_2: "beta".into(),
    };
    assert_eq!(
        resolve_url(
            &cfg,
            Some("https://example.com/{{custom_id_1}}/go?slot={{custom_id_2}}"),
            None,
            &templates,
        )
        .unwrap(),
        "https://example.com/alpha/go?slot=beta"
    );
}
#[test]
fn custom_url_placeholders_require_values_when_enabled() {
    let cfg = json!({ "config": { "serviceURL": "https://default", "hasCustomUrl": true } });
    let templates = CustomUrlTemplateValues {
        enabled: true,
        custom_id_1: String::new(),
        custom_id_2: String::new(),
    };
    assert!(resolve_url(
        &cfg,
        Some("https://example.com/{{custom_id_1}}"),
        None,
        &templates,
    )
    .is_err());
}
#[test]
fn resolve_url_errors_without_service_url() {
    assert!(resolve_url(
        &json!({ "config": {} }),
        None,
        None,
        &CustomUrlTemplateValues::default()
    )
    .is_err());
    assert!(resolve_url(&json!({}), None, None, &CustomUrlTemplateValues::default()).is_err());
}
