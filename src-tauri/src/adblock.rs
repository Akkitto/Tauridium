//! Ad and tracker blocking for service webviews.
//!
//! This module owns the durable and privileged parts of the feature: settings
//! validation, filter list download/validation/cache and the platform adapters
//! that enforce the rules. The Svelte shell only orchestrates through typed
//! commands. See `specs/002-ad-blocking/` for the design.
//!
//! Linux (WebKitGTK content filters) is the only supported platform in this
//! release; other platforms report themselves as unsupported and never
//! download lists or touch a webview.

use serde_json::{Map, Value};
use std::collections::HashSet;

pub(crate) mod compile;
#[cfg(target_os = "linux")]
pub(crate) mod linux_filter;
pub(crate) mod lists;
pub(crate) mod runtime;

pub(crate) const MAX_CUSTOM_LISTS: usize = 20;
pub(crate) const MAX_ALLOWLIST: usize = 500;
const MAX_SERVICE_OVERRIDES: usize = 10_000;
const MAX_HOST_LEN: usize = 253;
const MAX_URL_LEN: usize = 2048;

/// True where this build can actually enforce blocking rules.
pub(crate) const fn engine_supported() -> bool {
    cfg!(target_os = "linux")
}

pub(crate) fn default_enabled() -> Value {
    Value::Bool(false)
}

pub(crate) fn default_lists() -> Value {
    Value::Array(
        lists::CATALOG
            .iter()
            .filter(|entry| entry.default_on)
            .map(|entry| Value::from(entry.id))
            .collect(),
    )
}

pub(crate) fn default_custom_lists() -> Value {
    Value::Array(Vec::new())
}

pub(crate) fn default_allowlist() -> Value {
    Value::Array(Vec::new())
}

pub(crate) fn default_service_overrides() -> Value {
    Value::Object(Map::new())
}

/// The keys this feature adds to the app settings.
pub(crate) const SETTING_KEYS: [&str; 5] = [
    "adblockEnabled",
    "adblockLists",
    "adblockCustomLists",
    "adblockAllowlist",
    "serviceAdblock",
];

/// Normalises a site entry to a lowercase ASCII hostname.
///
/// Accepts a bare host, `*.host`, or a pasted address (`https://host/path`).
/// An entry covers the host and all of its subdomains. Internationalised names
/// must be given in their `xn--` form.
pub(crate) fn normalize_host(input: &str) -> Result<String, String> {
    let mut text = input.trim().to_ascii_lowercase();
    if text.is_empty() {
        return Err("Enter a site name such as example.com".into());
    }
    if let Some(rest) = text.split_once("://").map(|(_, rest)| rest.to_string()) {
        text = rest;
    }
    let end = text.find(['/', '?', '#']).unwrap_or(text.len());
    text.truncate(end);
    if let Some((_, host)) = text.rsplit_once('@') {
        text = host.to_string();
    }
    if let Some(rest) = text.strip_prefix("*.") {
        text = rest.to_string();
    }
    if let Some((host, port)) = text.rsplit_once(':') {
        if !port.is_empty() && port.bytes().all(|b| b.is_ascii_digit()) {
            text = host.to_string();
        }
    }
    let host = text.trim_end_matches('.');
    if host.is_empty() || host.len() > MAX_HOST_LEN {
        return Err(format!("\"{}\" is not a valid site name", input.trim()));
    }
    if !host.is_ascii() {
        return Err(format!(
            "\"{}\" must use ASCII letters; write internationalised names in their xn-- form",
            input.trim()
        ));
    }
    if !host.contains('.') {
        return Err(format!(
            "\"{}\" must include a domain suffix such as example.com",
            input.trim()
        ));
    }
    for label in host.split('.') {
        let ok = (1..=63).contains(&label.len())
            && !label.starts_with('-')
            && !label.ends_with('-')
            && label
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'-');
        if !ok {
            return Err(format!("\"{}\" is not a valid site name", input.trim()));
        }
    }
    Ok(host.to_string())
}

/// Normalises, deduplicates and bounds a user-supplied allowlist. Returns the
/// accepted entries and the rejected inputs with their reasons.
pub(crate) fn normalize_allowlist(inputs: &[String]) -> (Vec<String>, Vec<(String, String)>) {
    let mut accepted = Vec::new();
    let mut rejected = Vec::new();
    let mut seen = HashSet::new();
    for input in inputs {
        match normalize_host(input) {
            Ok(host) => {
                if seen.insert(host.clone()) {
                    if accepted.len() >= MAX_ALLOWLIST {
                        rejected.push((
                            input.clone(),
                            format!("The allowlist is limited to {MAX_ALLOWLIST} sites"),
                        ));
                    } else {
                        accepted.push(host);
                    }
                }
            }
            Err(reason) => rejected.push((input.clone(), reason)),
        }
    }
    (accepted, rejected)
}

fn validate_hosts(value: &Value, name: &str) -> Result<(), String> {
    let hosts = value
        .as_array()
        .ok_or_else(|| format!("{name} must be an array"))?;
    if hosts.len() > MAX_ALLOWLIST {
        return Err(format!("{name} may list at most {MAX_ALLOWLIST} sites"));
    }
    let mut seen = HashSet::new();
    for host in hosts {
        let host = host
            .as_str()
            .ok_or_else(|| format!("{name} must contain only strings"))?;
        match normalize_host(host) {
            Ok(normal) if normal == host => {}
            _ => return Err(format!("{name} contains an invalid or unnormalised site")),
        }
        if !seen.insert(host) {
            return Err(format!("{name} contains a duplicate site"));
        }
    }
    Ok(())
}

fn validate_service_overrides(value: &Value) -> Result<(), String> {
    let overrides = value
        .as_object()
        .ok_or_else(|| "App setting serviceAdblock must be an object".to_string())?;
    if overrides.len() > MAX_SERVICE_OVERRIDES {
        return Err("App setting serviceAdblock has too many entries".into());
    }
    for (service_id, entry) in overrides {
        if !crate::valid_service_setting_id(service_id) {
            return Err("App setting serviceAdblock contains an invalid service id".into());
        }
        let entry = entry
            .as_object()
            .ok_or_else(|| "App setting serviceAdblock entries must be objects".to_string())?;
        if entry.is_empty() {
            return Err("App setting serviceAdblock contains an empty override".into());
        }
        for (key, field) in entry {
            match key.as_str() {
                "enabled" if field.is_boolean() => {}
                "allowlist" => validate_hosts(field, "App setting serviceAdblock allowlist")?,
                _ => return Err("App setting serviceAdblock contains an unknown field".into()),
            }
        }
    }
    Ok(())
}

/// Validates the ad blocking keys of an app settings object.
pub(crate) fn validate_settings(settings: &Map<String, Value>) -> Result<(), String> {
    if !settings
        .get("adblockEnabled")
        .is_some_and(Value::is_boolean)
    {
        return Err("App setting adblockEnabled must be boolean".into());
    }
    let selected = settings
        .get("adblockLists")
        .and_then(Value::as_array)
        .ok_or_else(|| "App setting adblockLists must be an array".to_string())?;
    let mut seen = HashSet::new();
    for id in selected {
        let id = id
            .as_str()
            .filter(|id| lists::catalog_entry(id).is_some())
            .ok_or_else(|| "App setting adblockLists contains an unknown list".to_string())?;
        if !seen.insert(id) {
            return Err("App setting adblockLists contains a duplicate list".into());
        }
    }
    let custom = settings
        .get("adblockCustomLists")
        .and_then(Value::as_array)
        .ok_or_else(|| "App setting adblockCustomLists must be an array".to_string())?;
    if custom.len() > MAX_CUSTOM_LISTS {
        return Err(format!(
            "App setting adblockCustomLists may list at most {MAX_CUSTOM_LISTS} lists"
        ));
    }
    let mut seen = HashSet::new();
    for url in custom {
        let url = url
            .as_str()
            .filter(|url| url.len() <= MAX_URL_LEN)
            .ok_or_else(|| {
                "App setting adblockCustomLists contains an invalid address".to_string()
            })?;
        lists::validate_list_url(url)
            .map_err(|error| format!("App setting adblockCustomLists is invalid: {error}"))?;
        if !seen.insert(url) {
            return Err("App setting adblockCustomLists contains a duplicate list".into());
        }
    }
    validate_hosts(
        settings
            .get("adblockAllowlist")
            .ok_or_else(|| "App setting adblockAllowlist is missing".to_string())?,
        "App setting adblockAllowlist",
    )?;
    validate_service_overrides(
        settings
            .get("serviceAdblock")
            .ok_or_else(|| "App setting serviceAdblock is missing".to_string())?,
    )
}

#[cfg(any(target_os = "linux", test))]
/// Blocking behaviour that applies to one service.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct EffectiveAdblock {
    pub(crate) enabled: bool,
    /// Global allowlist plus the service's own entries, sorted and unique.
    pub(crate) allowlist: Vec<String>,
}

#[cfg(any(target_os = "linux", test))]
fn string_list(value: Option<&Value>) -> Vec<String> {
    value
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default()
}

#[cfg(any(target_os = "linux", test))]
/// Resolves global defaults and the per-service override for one service.
/// Always `enabled = false` where the engine is unsupported.
pub(crate) fn effective_for_service(settings: &Value, service_id: &str) -> EffectiveAdblock {
    let global_enabled = settings
        .get("adblockEnabled")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let override_entry = settings
        .get("serviceAdblock")
        .and_then(Value::as_object)
        .and_then(|map| map.get(service_id))
        .and_then(Value::as_object);
    let enabled = override_entry
        .and_then(|entry| entry.get("enabled"))
        .and_then(Value::as_bool)
        .unwrap_or(global_enabled);
    let mut allowlist = string_list(settings.get("adblockAllowlist"));
    allowlist.extend(string_list(
        override_entry.and_then(|entry| entry.get("allowlist")),
    ));
    allowlist.sort();
    allowlist.dedup();
    EffectiveAdblock {
        enabled: enabled && engine_supported(),
        allowlist,
    }
}

/// When a restored backup predates ad blocking it lacks these keys; keep the
/// profile's current values instead of resetting them to defaults.
pub(crate) fn carry_forward_missing(
    restored: Value,
    backup_settings: &Value,
    previous: &Value,
) -> Value {
    let mut restored = restored;
    if let (Some(target), Some(backup), Some(previous)) = (
        restored.as_object_mut(),
        backup_settings.as_object(),
        previous.as_object(),
    ) {
        for key in SETTING_KEYS {
            if !backup.contains_key(key) {
                if let Some(value) = previous.get(key) {
                    target.insert(key.to_string(), value.clone());
                }
            }
        }
    }
    restored
}

/// True when a settings patch touches anything this feature reacts to.
pub(crate) fn patch_affects(patch: &Map<String, Value>) -> bool {
    patch.keys().any(|key| SETTING_KEYS.contains(&key.as_str()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn defaults() -> Map<String, Value> {
        let mut map = Map::new();
        map.insert("adblockEnabled".into(), default_enabled());
        map.insert("adblockLists".into(), default_lists());
        map.insert("adblockCustomLists".into(), default_custom_lists());
        map.insert("adblockAllowlist".into(), default_allowlist());
        map.insert("serviceAdblock".into(), default_service_overrides());
        map
    }

    #[test]
    fn defaults_validate_and_are_off() {
        let settings = defaults();
        assert!(validate_settings(&settings).is_ok());
        assert_eq!(settings["adblockEnabled"], json!(false));
        assert_eq!(settings["adblockLists"], json!(["easylist", "easyprivacy"]));
    }

    #[test]
    fn hosts_are_normalised() {
        assert_eq!(normalize_host("Example.COM").unwrap(), "example.com");
        assert_eq!(
            normalize_host("https://www.Example.com/path?q=1").unwrap(),
            "www.example.com"
        );
        assert_eq!(normalize_host("*.example.com").unwrap(), "example.com");
        assert_eq!(normalize_host("example.com:8080").unwrap(), "example.com");
        assert_eq!(normalize_host("user@example.com").unwrap(), "example.com");
        assert_eq!(normalize_host("example.com.").unwrap(), "example.com");
        for bad in [
            "",
            "  ",
            "localhost",
            "exa mple.com",
            "-a.com",
            "a..com",
            "ex\u{e4}mple.com",
            "http://",
        ] {
            assert!(normalize_host(bad).is_err(), "{bad:?} should be rejected");
        }
    }

    #[test]
    fn allowlist_input_is_deduplicated_and_rejects_are_reported() {
        let inputs = vec![
            "A.com".to_string(),
            "https://a.com/x".to_string(),
            "nonsense".to_string(),
            "b.org".to_string(),
        ];
        let (accepted, rejected) = normalize_allowlist(&inputs);
        assert_eq!(accepted, ["a.com", "b.org"]);
        assert_eq!(rejected.len(), 1);
        assert_eq!(rejected[0].0, "nonsense");
    }

    #[test]
    fn allowlist_is_bounded() {
        let inputs: Vec<String> = (0..MAX_ALLOWLIST + 3)
            .map(|i| format!("site{i}.com"))
            .collect();
        let (accepted, rejected) = normalize_allowlist(&inputs);
        assert_eq!(accepted.len(), MAX_ALLOWLIST);
        assert_eq!(rejected.len(), 3);
    }

    #[test]
    fn validation_rejects_bad_shapes() {
        let cases: Vec<(&str, Value)> = vec![
            ("adblockEnabled", json!("yes")),
            ("adblockLists", json!(["nope"])),
            ("adblockLists", json!(["easylist", "easylist"])),
            ("adblockCustomLists", json!(["http://example.com/list.txt"])),
            ("adblockCustomLists", json!(["https://localhost/list.txt"])),
            ("adblockCustomLists", json!(["https://127.0.0.1/list.txt"])),
            ("adblockAllowlist", json!(["Example.com"])),
            ("adblockAllowlist", json!(["a.com", "a.com"])),
            ("serviceAdblock", json!({"": {"enabled": true}})),
            ("serviceAdblock", json!({"bad\u{1}id": {"enabled": true}})),
            ("serviceAdblock", json!({"svc-1": {}})),
            ("serviceAdblock", json!({"svc-1": {"enabled": "x"}})),
            ("serviceAdblock", json!({"svc-1": {"other": true}})),
            (
                "serviceAdblock",
                json!({"svc-1": {"allowlist": ["Bad.com"]}}),
            ),
        ];
        for (key, value) in cases {
            let mut settings = defaults();
            settings.insert(key.into(), value.clone());
            assert!(
                validate_settings(&settings).is_err(),
                "{key}={value} should be rejected"
            );
        }
        let mut ok = defaults();
        ok.insert(
            "adblockCustomLists".into(),
            json!(["https://example.com/list.txt"]),
        );
        ok.insert("adblockAllowlist".into(), json!(["a.com", "b.org"]));
        ok.insert(
            "serviceAdblock".into(),
            json!({"svc-1": {"enabled": false, "allowlist": ["c.com"]}}),
        );
        assert!(validate_settings(&ok).is_ok());
    }

    #[test]
    fn effective_settings_follow_global_then_override() {
        let settings = json!({
            "adblockEnabled": true,
            "adblockAllowlist": ["b.org", "a.com"],
            "serviceAdblock": {
                "svc-off": {"enabled": false},
                "svc-list": {"allowlist": ["a.com", "c.net"]}
            }
        });
        let inherit = effective_for_service(&settings, "svc-other");
        let off = effective_for_service(&settings, "svc-off");
        let listed = effective_for_service(&settings, "svc-list");
        assert_eq!(inherit.enabled, engine_supported());
        assert!(!off.enabled);
        assert_eq!(listed.allowlist, ["a.com", "b.org", "c.net"]);
        assert_eq!(inherit.allowlist, ["a.com", "b.org"]);
        let global_off =
            json!({"adblockEnabled": false, "serviceAdblock": {"s": {"enabled": true}}});
        assert_eq!(
            effective_for_service(&global_off, "s").enabled,
            engine_supported()
        );
        assert!(!effective_for_service(&global_off, "t").enabled);
    }

    #[test]
    fn restoring_an_old_backup_keeps_current_blocking_settings() {
        let current = json!({"adblockEnabled": true, "adblockAllowlist": ["a.com"], "other": 1});
        let old_backup = json!({"other": 2});
        let restored = json!({"adblockEnabled": false, "adblockAllowlist": [], "other": 2});
        let restored = carry_forward_missing(restored, &old_backup, &current);
        assert_eq!(restored["adblockEnabled"], json!(true));
        assert_eq!(restored["adblockAllowlist"], json!(["a.com"]));
        assert_eq!(restored["other"], json!(2));
        let new_backup = json!({"adblockEnabled": false, "adblockAllowlist": []});
        let restored = json!({"adblockEnabled": false, "adblockAllowlist": []});
        let restored = carry_forward_missing(restored, &new_backup, &current);
        assert_eq!(restored["adblockEnabled"], json!(false));
    }

    #[test]
    fn patches_that_touch_blocking_are_detected() {
        let mut patch = Map::new();
        patch.insert("theme".into(), json!("dark"));
        assert!(!patch_affects(&patch));
        patch.insert("adblockAllowlist".into(), json!([]));
        assert!(patch_affects(&patch));
    }
}
