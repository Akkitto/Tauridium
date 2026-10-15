//! Redact known credential categories without claiming arbitrary text is safe.
use regex::Regex;
use serde_json::Value;
use std::sync::LazyLock;
use tauri::Url;

const REDACTED: &str = "[redacted]";
static HEADERS: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
        r"(?im)(\b(?:authorization|proxy-authorization|set-cookie|cookie)\b[ \t]*:[ \t]*)[^\r\n]+",
    )
    .expect("constant sensitive header pattern")
});
static URLS: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r#"(?i)\bhttps?://[^\s<>\"']+"#).expect("constant URL pattern"));
static AUTH: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)\b(bearer|basic)\s+[a-z0-9+/_.=-]{4,}")
        .expect("constant authorization pattern")
});
static ASSIGNMENTS: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r#"(?i)(\b(?:api[ _-]?key|access[ _-]?key|access[ _-]?token|refresh[ _-]?token|client[ _-]?secret|password|passwd|authorization|cookie|secret|token)\b[\"']?[ \t]*[:=][ \t]*)(?:\"[^\"]*\"|'[^']*'|[^\s,;&#]+)"#).expect("constant credential pattern")
});

pub(crate) fn sensitive_key(key: &str) -> bool {
    let normalized: String = key
        .chars()
        .filter(|c| c.is_ascii_alphanumeric())
        .map(|c| c.to_ascii_lowercase())
        .collect();
    [
        "password",
        "passwd",
        "token",
        "secret",
        "credential",
        "authorization",
        "cookie",
        "apikey",
        "accesskey",
        "privatekey",
        "sessionid",
        "sessionkey",
    ]
    .iter()
    .any(|needle| normalized.contains(needle))
}

fn parameters(query: &str, depth: usize) -> String {
    let mut temporary = Url::parse("https://redaction.invalid/").expect("constant URL");
    temporary.set_query(Some(query));
    let mut changed = false;
    let pairs: Vec<(String, String)> = temporary
        .query_pairs()
        .map(|(key, value)| {
            let sensitive = sensitive_key(&key)
                || matches!(
                    key.to_ascii_lowercase().as_str(),
                    "code" | "state" | "samlresponse" | "samlrequest" | "assertion"
                );
            let replacement = if sensitive {
                REDACTED.to_string()
            } else {
                text_at_depth(&value, depth + 1)
            };
            changed |= replacement != value;
            (key.into_owned(), replacement)
        })
        .collect();
    if !changed {
        return query.to_string();
    }
    temporary.query_pairs_mut().clear().extend_pairs(pairs);
    temporary.query().unwrap_or_default().to_string()
}

fn url_text(input: &str, depth: usize) -> String {
    if depth > 4 {
        return REDACTED.into();
    }
    let Ok(mut url) = Url::parse(input) else {
        return "[redacted URL]".into();
    };
    let original = url.clone();
    if url.set_password(None).is_err() || url.set_username("").is_err() {
        return "[redacted URL]".into();
    }
    if let Some(query) = url.query().map(str::to_string) {
        url.set_query(Some(&parameters(&query, depth)));
    }
    if let Some(fragment) = url.fragment().map(str::to_string) {
        let fragment = if let Some((route, query)) = fragment.split_once('?') {
            format!("{route}?{}", parameters(query, depth))
        } else if fragment.contains('=') {
            parameters(&fragment, depth)
        } else {
            text_at_depth(&fragment, depth + 1)
        };
        url.set_fragment(Some(&fragment));
    }
    if url == original {
        input.to_string()
    } else {
        url.into()
    }
}

fn text_at_depth(input: &str, depth: usize) -> String {
    if depth > 4 {
        return REDACTED.into();
    }
    let urls = URLS.replace_all(input, |captures: &regex::Captures<'_>| {
        url_text(&captures[0], depth)
    });
    let headers = HEADERS.replace_all(&urls, "${1}[redacted]");
    let auth = AUTH.replace_all(&headers, "$1 [redacted]");
    ASSIGNMENTS
        .replace_all(&auth, "${1}[redacted]")
        .into_owned()
}

pub(crate) fn text(input: &str) -> String {
    text_at_depth(input, 0)
}

pub(crate) fn redact(value: &Value) -> Value {
    match value {
        Value::Object(map) => Value::Object(
            map.iter()
                .map(|(key, value)| {
                    (
                        key.clone(),
                        if sensitive_key(key) {
                            Value::String(REDACTED.into())
                        } else {
                            redact(value)
                        },
                    )
                })
                .collect(),
        ),
        Value::Array(values) => Value::Array(values.iter().map(redact).collect()),
        Value::String(value) => Value::String(text(value)),
        _ => value.clone(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn redacts_url_userinfo_query_fragment_and_nested_redirect_credentials() {
        for input in [
            "https://fixture-user:SYNTHETIC_USERINFO@example.test/path?api_key=SYNTHETIC_QUERY&team=visible",
            "request failed: https://example.test/#access_token=SYNTHETIC_FRAGMENT",
            "https://example.test/#/callback?code=SYNTHETIC_CODE",
            "https://example.test/?redirect=https%3A%2F%2Fuser%3ASYNTHETIC_NESTED%40other.test%2F%3Ftoken%3DSYNTHETIC_TOKEN",
        ] {
            let output = text(input);
            assert!(!output.contains("SYNTHETIC_"), "{output}");
            assert!(!output.contains("fixture-user"));
        }
        assert!(text("https://example.test/?team=visible").contains("team=visible"));
    }

    #[test]
    fn redacts_structured_and_free_text_credentials() {
        let value = json!({"apiKey":"SYNTHETIC_KEY", "nested":[{"client-secret":"SYNTHETIC_SECRET"}], "ordinary":"preserved", "enabled":true});
        let output = redact(&value);
        assert!(!output.to_string().contains("SYNTHETIC_"));
        assert_eq!(output["ordinary"], "preserved");
        assert_eq!(output["enabled"], true);
        for input in [
            "Authorization: Bearer SYNTHETIC_BEARER",
            "HTTP Basic SYNTHETIC_BASIC",
            "password='SYNTHETIC_PASSWORD'",
            "api_key=SYNTHETIC_API_KEY",
            "Cookie: first=SYNTHETIC_COOKIE; second=SYNTHETIC_COOKIE2",
        ] {
            assert!(!text(input).contains("SYNTHETIC_"));
        }
    }
}
