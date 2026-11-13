//! Converts filter list text into WebKit content blocking rules.
//!
//! Only network rules are used; cosmetic filters and scriptlets in a list are
//! ignored (they are a later release). The output is deterministic for a given
//! set of lists and allowlist, so its hash identifies the compiled filter.

#[cfg(any(target_os = "linux", test))]
use adblock::lists::{FilterSet, ParseOptions, RuleTypes};
#[cfg(any(target_os = "linux", test))]
use serde_json::{json, Value};
#[cfg(any(target_os = "linux", test))]
use sha2::{Digest, Sha256};

#[cfg(any(target_os = "linux", test))]
/// WebKit accepts at most this many rules in one filter.
pub(crate) const MAX_RULES_PER_FILTER: usize = 150_000;
#[cfg(any(target_os = "linux", test))]
/// Bump to force recompilation when the conversion output format changes.
const COMPILER_VERSION: u32 = 1;

#[cfg(any(target_os = "linux", test))]
#[derive(Debug)]
pub(crate) struct Compiled {
    pub(crate) json: Vec<u8>,
    /// Rules in the output, including allowlist rules.
    pub(crate) rule_count: usize,
    /// Network filters that were converted.
    pub(crate) converted: usize,
}

#[cfg(any(target_os = "linux", test))]
/// Identifier of the compiled filter for these inputs. Pure, so a filter that
/// is already in the store can be reused without recompiling.
pub(crate) fn filter_id(list_hashes: &[String], allowlist: &[String]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(COMPILER_VERSION.to_le_bytes());
    for hash in list_hashes {
        hasher.update(b"list:");
        hasher.update(hash.as_bytes());
        hasher.update(b"\n");
    }
    for host in allowlist {
        hasher.update(b"allow:");
        hasher.update(host.as_bytes());
        hasher.update(b"\n");
    }
    let hex: String = hasher
        .finalize()
        .iter()
        .take(10)
        .map(|byte| format!("{byte:02x}"))
        .collect();
    format!("tauridium-{hex}")
}

#[cfg(any(target_os = "linux", test))]
/// Regular expression matching a page on `host` or any of its subdomains.
fn top_url_pattern(host: &str) -> String {
    let escaped: String = host
        .chars()
        .flat_map(|c| if c == '.' { vec!['\\', '.'] } else { vec![c] })
        .collect();
    format!("^https?://([^/:?#]*\\.)?{escaped}([:/?#]|$)")
}

#[cfg(any(target_os = "linux", test))]
/// A rule that cancels earlier blocking rules while the top-level page is on
/// the allowed site.
fn allowlist_rule(host: &str) -> Value {
    json!({
        "trigger": {
            "url-filter": ".*",
            "if-top-url": [top_url_pattern(host)]
        },
        "action": {"type": "ignore-previous-rules"}
    })
}

#[cfg(any(target_os = "linux", test))]
/// Compiles list texts plus the allowlist into one filter.
pub(crate) fn compile(lists: &[String], allowlist: &[String]) -> Result<Compiled, String> {
    let mut set = FilterSet::new(true);
    for text in lists {
        set.add_filter_list(
            text.clone(),
            ParseOptions {
                rule_types: RuleTypes::NetworkOnly,
                ..ParseOptions::default()
            },
        );
    }
    let (rules, converted) = set
        .into_content_blocking()
        .map_err(|()| "The filter lists could not be converted".to_string())?;
    let mut value = serde_json::to_value(&rules)
        .map_err(|error| format!("Unable to encode the filter rules: {error}"))?;
    let array = value
        .as_array_mut()
        .ok_or_else(|| "The converted filter rules have an unexpected shape".to_string())?;
    array.extend(allowlist.iter().map(|host| allowlist_rule(host)));
    let rule_count = array.len();
    if rule_count > MAX_RULES_PER_FILTER {
        return Err(format!(
            "The selected lists produce {rule_count} rules, more than the {MAX_RULES_PER_FILTER} the web engine accepts. Turn off a list."
        ));
    }
    let json = serde_json::to_vec(&value)
        .map_err(|error| format!("Unable to encode the filter rules: {error}"))?;
    Ok(Compiled {
        json,
        rule_count,
        converted: converted.len(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    const LIST: &str = "||ads.example.com^\n/adserver.js\n@@/allowed/adserver.js\nexample.com##.banner\n##+js(abort-on-property-read, x)\n";

    #[test]
    fn network_rules_convert_and_cosmetic_rules_are_ignored_without_error() {
        let compiled = compile(&[LIST.to_string()], &[]).unwrap();
        let rules: Vec<Value> = serde_json::from_slice(&compiled.json).unwrap();
        assert_eq!(rules.len(), compiled.rule_count);
        assert!(compiled.converted >= 3);
        let text = String::from_utf8(compiled.json).unwrap();
        assert!(text.contains("adserver"));
        // No css-display-none or script rules from the cosmetic lines.
        assert!(!text.contains("css-display-none"));
        assert!(!text.contains("abort-on-property-read"));
    }

    #[test]
    fn allowlist_becomes_trailing_ignore_rules() {
        let compiled = compile(
            &[LIST.to_string()],
            &["example.org".to_string(), "a-b.co.uk".to_string()],
        )
        .unwrap();
        let rules: Vec<Value> = serde_json::from_slice(&compiled.json).unwrap();
        let tail = &rules[rules.len() - 2..];
        for rule in tail {
            assert_eq!(rule["action"]["type"], "ignore-previous-rules");
        }
        assert_eq!(
            tail[0]["trigger"]["if-top-url"][0],
            "^https?://([^/:?#]*\\.)?example\\.org([:/?#]|$)"
        );
    }

    #[test]
    fn allowlist_pattern_matches_site_and_subdomains_only() {
        let re = regex::Regex::new(&top_url_pattern("example.org")).unwrap();
        for yes in [
            "https://example.org/",
            "http://example.org",
            "https://www.example.org/a?b",
            "https://a.b.example.org:8443/x",
        ] {
            assert!(re.is_match(yes), "{yes}");
        }
        for no in [
            "https://notexample.org/",
            "https://example.org.evil.com/",
            "https://evil.com/example.org/",
            "https://example-org.com/",
        ] {
            assert!(!re.is_match(no), "{no}");
        }
    }

    #[test]
    fn filter_id_depends_on_every_input_and_nothing_else() {
        let a = filter_id(&["h1".into(), "h2".into()], &["a.com".into()]);
        assert_eq!(a, filter_id(&["h1".into(), "h2".into()], &["a.com".into()]));
        assert_ne!(a, filter_id(&["h1".into()], &["a.com".into()]));
        assert_ne!(a, filter_id(&["h1".into(), "h2".into()], &[]));
        assert_ne!(a, filter_id(&["h2".into(), "h1".into()], &["a.com".into()]));
        assert!(a.starts_with("tauridium-") && a.len() == "tauridium-".len() + 20);
    }

    #[test]
    fn oversize_rule_sets_are_refused_with_a_clear_message() {
        let mut text = String::new();
        for i in 0..(MAX_RULES_PER_FILTER + 10) {
            text.push_str(&format!("||h{i}.example.com^\n"));
        }
        let error = compile(&[text], &[]).unwrap_err();
        assert!(error.contains("more than"), "{error}");
    }
}
