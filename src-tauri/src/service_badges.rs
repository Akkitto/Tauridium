//! Keep explicit browser badge signals and recipe components bounded and distinct.
use serde_json::Value;

const MAX_COUNT: i64 = 1_000_000;

fn bounded(value: Option<&Value>) -> i64 {
    value
        .and_then(Value::as_i64)
        .unwrap_or(0)
        .clamp(0, MAX_COUNT)
}

pub(crate) fn unread(snapshot: &Value, include_indirect: bool) -> i64 {
    // A website's standard API is authoritative, even when it explicitly clears.
    // That API supplies one total, not a direct/indirect classification.
    if let Some(count) = snapshot.get("a").and_then(Value::as_u64) {
        return count.min(MAX_COUNT as u64) as i64;
    }
    let legacy = bounded(snapshot.get("u"));
    if let Some(components) = snapshot.get("b").filter(|value| value.is_object()) {
        let direct = bounded(components.get("direct"));
        let indirect = bounded(components.get("indirect"));
        // An old custom recipe may still write __pakeUnread directly. Honor its
        // newer total rather than retaining unrelated last bridge components.
        if (direct + indirect).min(MAX_COUNT) == legacy {
            return (direct + if include_indirect { indirect } else { 0 }).min(MAX_COUNT);
        }
    }
    legacy
}

pub(crate) fn requires_browser_identity(host: &str) -> bool {
    // Telegram Web A otherwise mistakes Tauridium for its own Tauri desktop app
    // and invokes an unrelated set_notifications_count native command. Its normal
    // browser branch uses navigator.setAppBadge, captured by our generic bridge.
    host == "web.telegram.org"
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn discord_read_mentions_do_not_retain_an_unrequested_channel_badge() {
        let unread_mentions = json!({"u": 4, "b": {"direct": 3, "indirect": 1}});
        let read_mentions = json!({"u": 1, "b": {"direct": 0, "indirect": 1}});
        assert_eq!(unread(&unread_mentions, false), 3);
        assert_eq!(unread(&read_mentions, false), 0);
        assert_eq!(unread(&read_mentions, true), 1);
        assert_eq!(
            unread(&json!({"u": 0, "b": {"direct": 0, "indirect": 0}}), true),
            0
        );
    }

    #[test]
    fn explicit_browser_clears_override_old_recipe_and_legacy_counts() {
        for include_indirect in [false, true] {
            for count in [17, 2, 0] {
                assert_eq!(
                    unread(
                        &json!({"a": count, "u": 99,
                    "b": {"direct": 90, "indirect": 9}}),
                        include_indirect
                    ),
                    count
                );
            }
        }
    }

    #[test]
    fn legacy_custom_recipe_counts_and_explicit_zero_remain_supported() {
        for count in [8, 2, 0] {
            assert_eq!(unread(&json!({"u": count}), false), count);
        }
        assert_eq!(
            unread(&json!({"u": 0, "b": {"direct": 9, "indirect": 1}}), true),
            0
        );
        assert_eq!(
            unread(&json!({"u": 7, "b": {"direct": 9, "indirect": 1}}), false),
            7
        );
    }

    #[test]
    fn hostile_or_malformed_snapshot_values_cannot_escape_native_limits() {
        for snapshot in [
            json!(null),
            json!({}),
            json!({"u": -9}),
            json!({"u": "99", "a": "999"}),
            json!({"a": -1}),
            json!({"u": 2.5, "b": {"direct": 9.5}}),
        ] {
            assert_eq!(unread(&snapshot, true), 0);
        }
        assert_eq!(unread(&json!({"a": u64::MAX}), false), MAX_COUNT);
        assert_eq!(unread(&json!({"u": i64::MAX}), false), MAX_COUNT);
        let huge = json!({"u": MAX_COUNT, "b": {"direct": i64::MAX, "indirect": i64::MAX}});
        assert_eq!(unread(&huge, true), MAX_COUNT);
        assert_eq!(unread(&huge, false), MAX_COUNT);
    }

    #[test]
    fn browser_identity_exception_is_limited_to_the_actual_hosted_telegram() {
        assert!(requires_browser_identity("web.telegram.org"));
        for host in [
            "telegram.org",
            "t.me",
            "web.telegram.org.example.com",
            "example.com",
            "github.com",
            "discord.com",
            "mail.proton.me",
            "",
        ] {
            assert!(!requires_browser_identity(host), "{host}");
        }
    }
}
