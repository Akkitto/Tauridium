//! Tracking exceptions are opt-in and scoped to the actual shared browser profile.
use serde_json::Value;

pub(crate) fn validate(settings: Option<&Value>) -> Result<(), String> {
    let map = settings
        .and_then(Value::as_object)
        .ok_or("App setting trackingPreventionExceptions must be an object")?;
    if map.len() > 10_256 {
        return Err("Too many browser-profile tracking exceptions".into());
    }
    for (key, value) in map {
        if let Some(id) = key.strip_prefix("service:") {
            crate::storage_security::validate_service_id(id)?;
        } else if let Some(id) = key.strip_prefix("sandbox:") {
            if id.is_empty()
                || id.len() > 80
                || !id
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
            {
                return Err("Invalid sandbox profile tracking exception".into());
            }
        } else {
            return Err(
                "Tracking exception requires a service: or sandbox: profile namespace".into(),
            );
        }
        if !value.is_boolean() {
            return Err("Browser tracking exception must be boolean".into());
        }
    }
    Ok(())
}

#[cfg(any(windows, test))]
pub(crate) fn exception_enabled(
    snapshot: &Value,
    service_id: &str,
    sandbox_id: Option<&str>,
) -> bool {
    let namespace = match sandbox_id {
        Some(id) => format!("sandbox:{id}"),
        None => format!("service:{service_id}"),
    };
    snapshot.get(&namespace).and_then(Value::as_bool) == Some(true)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn default_and_unrelated_profiles_keep_tracking_protection() {
        assert!(!exception_enabled(&json!({}), "one", None));
        let snapshot = json!({"service:one": true, "sandbox:shared": true});
        assert!(exception_enabled(&snapshot, "one", None));
        assert!(!exception_enabled(&snapshot, "two", None));
        assert!(!exception_enabled(&snapshot, "one", Some("unrelated")));
        assert!(exception_enabled(&snapshot, "two", Some("shared")));
        assert!(exception_enabled(&snapshot, "three", Some("shared")));
    }

    #[test]
    fn exceptions_are_bounded_typed_and_namespaced() {
        assert!(validate(Some(&json!({"service:one": true, "sandbox:shared": false}))).is_ok());
        for invalid in [
            json!(null),
            json!({"one": true}),
            json!({"service:../one": true}),
            json!({"service:one": "true"}),
        ] {
            assert!(validate(Some(&invalid)).is_err());
        }
    }
}
