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
fn stock_gemini_uses_the_explicit_service_override() {
    // Shape of pinned recipes/google-gemini/package.json: no hasCustomUrl flag.
    let cfg = json!({ "config": { "serviceURL": "https://gemini.google.com" } });
    assert_eq!(
        resolve_url(
            &cfg,
            Some(" https://calendar.google.com/calendar/u/0/r "),
            None,
            &CustomUrlTemplateValues::default(),
        )
        .unwrap(),
        "https://calendar.google.com/calendar/u/0/r"
    );
}
#[test]
fn override_precedes_the_recipe_default_regardless_of_custom_deployment_support() {
    for config in [
        json!({ "serviceURL": "https://default.example" }),
        json!({ "serviceURL": "https://default.example", "hasCustomUrl": false }),
        json!({ "serviceURL": "https://default.example", "hasCustomUrl": true }),
    ] {
        let cfg = json!({ "config": config });
        let templates = CustomUrlTemplateValues::default();
        assert_eq!(
            resolve_url(&cfg, Some("chat.example.fr"), None, &templates).unwrap(),
            "https://chat.example.fr"
        );
        for (input, expected) in [
            ("HTTPS://chat.example.fr", "HTTPS://chat.example.fr"),
            (
                "chat.example.fr:8443/go?next=https://example.test/",
                "https://chat.example.fr:8443/go?next=https://example.test/",
            ),
        ] {
            assert_eq!(
                resolve_url(&cfg, Some(input), None, &templates).unwrap(),
                expected
            );
        }
        for empty in [None, Some(""), Some(" \t ")] {
            assert_eq!(
                resolve_url(&cfg, empty, None, &templates).unwrap(),
                "https://default.example"
            );
        }
    }
}

#[test]
fn malformed_and_internal_overrides_never_fall_back_to_a_recipe() {
    let cfg = json!({ "config": { "serviceURL": "https://gemini.google.com" } });
    let templates = CustomUrlTemplateValues::default();
    for invalid in [
        "https://",
        "file:///tmp/example",
        "tauri://localhost/",
        "https://tauri.localhost/",
        "http://asset.localhost/",
        "http://ipc.localhost/",
        "about:blank",
        "javascript:alert(1)",
    ] {
        assert!(
            resolve_url(&cfg, Some(invalid), None, &templates).is_err(),
            "{invalid}"
        );
    }
}

#[test]
fn fixed_origin_recipe_runtime_stays_on_the_recipe_origin() {
    let cfg = json!({ "config": { "serviceURL": "https://gemini.google.com" } });
    assert!(recipe_runtime_allowed(
        &cfg,
        None,
        &Url::parse("https://gemini.google.com/app").unwrap()
    ));
    for other in [
        "https://calendar.google.com/",
        "https://workspace.google.com/products/gemini/",
        "http://gemini.google.com/",
        "https://gemini.google.com:444/",
    ] {
        assert!(
            !recipe_runtime_allowed(&cfg, None, &Url::parse(other).unwrap()),
            "{other}"
        );
    }

    let self_hosted =
        json!({ "config": { "serviceURL": "https://hosted.example", "hasCustomUrl": true } });
    assert!(recipe_runtime_allowed(
        &self_hosted,
        None,
        &Url::parse("https://self-hosted.example").unwrap()
    ));

    let team = json!({ "config": { "serviceURL": "https://example.test", "teamURL": "https://{teamId}.example.test", "hasTeamId": true } });
    assert!(recipe_runtime_allowed(
        &team,
        Some("acme"),
        &Url::parse("https://acme.example.test/inbox").unwrap()
    ));
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
            "hasTeamId": true
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
