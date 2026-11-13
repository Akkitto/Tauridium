//! Filter list catalog, download, validation and on-disk cache.
//!
//! Lists are fetched only from the addresses the user selected, over HTTPS,
//! with every hop resolved and checked so a list address can never reach the
//! local network. A download replaces the cached copy only after it parses as a
//! filter list; a failed update keeps the previous good copy and is reported
//! once per failure episode.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::net::{IpAddr, SocketAddr, ToSocketAddrs};
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::Duration;
use tauri::Url;

/// Largest list body accepted.
pub(crate) const MAX_LIST_BYTES: usize = 32 * 1024 * 1024;
const MAX_REDIRECTS: usize = 5;
const META_FILE: &str = "lists.json";
const META_VERSION: u32 = 1;
const DEFAULT_REFRESH_SECS: u64 = 4 * 24 * 3600;
const MIN_REFRESH_SECS: u64 = 24 * 3600;
const MAX_REFRESH_SECS: u64 = 14 * 24 * 3600;

pub(crate) struct CatalogEntry {
    pub(crate) id: &'static str,
    pub(crate) name: &'static str,
    pub(crate) url: &'static str,
    pub(crate) default_on: bool,
}

/// Curated lists. They are downloaded at runtime and never bundled.
pub(crate) const CATALOG: [CatalogEntry; 2] = [
    CatalogEntry {
        id: "easylist",
        name: "EasyList (ads)",
        url: "https://easylist.to/easylist/easylist.txt",
        default_on: true,
    },
    CatalogEntry {
        id: "easyprivacy",
        name: "EasyPrivacy (trackers)",
        url: "https://easylist.to/easylist/easyprivacy.txt",
        default_on: true,
    },
];

pub(crate) fn catalog_entry(id: &str) -> Option<&'static CatalogEntry> {
    CATALOG.iter().find(|entry| entry.id == id)
}

/// A list that is selected, with the source it is fetched from.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ListSource {
    pub(crate) id: String,
    pub(crate) name: String,
    pub(crate) url: String,
    pub(crate) custom: bool,
}

/// Stable id for a custom list address.
pub(crate) fn custom_list_id(url: &str) -> String {
    let digest = Sha256::digest(url.as_bytes());
    let hex: String = digest.iter().take(6).map(|b| format!("{b:02x}")).collect();
    format!("custom-{hex}")
}

/// The lists selected by the app settings, in catalog-then-custom order.
pub(crate) fn selected_sources(settings: &serde_json::Value) -> Vec<ListSource> {
    let mut out = Vec::new();
    if let Some(ids) = settings.get("adblockLists").and_then(|v| v.as_array()) {
        for id in ids.iter().filter_map(|v| v.as_str()) {
            if let Some(entry) = catalog_entry(id) {
                out.push(ListSource {
                    id: entry.id.to_string(),
                    name: entry.name.to_string(),
                    url: entry.url.to_string(),
                    custom: false,
                });
            }
        }
    }
    if let Some(urls) = settings
        .get("adblockCustomLists")
        .and_then(|v| v.as_array())
    {
        for url in urls.iter().filter_map(|v| v.as_str()) {
            out.push(ListSource {
                id: custom_list_id(url),
                name: url.to_string(),
                url: url.to_string(),
                custom: true,
            });
        }
    }
    out
}

// ---------------------------------------------------------------------------
// Address safety
// ---------------------------------------------------------------------------

/// True for globally routable unicast addresses only.
pub(crate) fn is_public_ip(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(v4) => {
            let n = u32::from(v4);
            let in_net = |base: u32, bits: u32| (n >> (32 - bits)) == (base >> (32 - bits));
            !(v4.is_unspecified()
                || v4.is_loopback()
                || v4.is_private()
                || v4.is_link_local()
                || v4.is_broadcast()
                || v4.is_multicast()
                || v4.is_documentation()
                || in_net(0x0000_0000, 8) // 0.0.0.0/8 "this network"
                || in_net(0x6440_0000, 10) // 100.64.0.0/10 shared address space
                || in_net(0xc000_0000, 24) // 192.0.0.0/24 protocol assignments
                || in_net(0xc612_0000, 15) // 198.18.0.0/15 benchmarking
                || in_net(0xf000_0000, 4)) // 240.0.0.0/4 reserved
        }
        IpAddr::V6(v6) => {
            if let Some(mapped) = v6.to_ipv4_mapped() {
                return is_public_ip(IpAddr::V4(mapped));
            }
            let segments = v6.segments();
            !(v6.is_unspecified()
                || v6.is_loopback()
                || v6.is_multicast()
                || (segments[0] & 0xfe00) == 0xfc00
                || (segments[0] & 0xffc0) == 0xfe80
                || (segments[0] == 0x2001 && segments[1] == 0x0db8))
        }
    }
}

fn blocked_host_name(host: &str) -> bool {
    let host = host.trim_end_matches('.').to_ascii_lowercase();
    host == "localhost"
        || host.ends_with(".localhost")
        || host.ends_with(".local")
        || host.ends_with(".internal")
        || host.ends_with(".lan")
        || host.ends_with(".home.arpa")
        || !host.contains('.') && host.parse::<IpAddr>().is_err()
}

/// Static checks on a list address: HTTPS, no credentials, and no host that
/// names the local network. DNS results are checked again at download time.
pub(crate) fn validate_list_url(input: &str) -> Result<Url, String> {
    if input != input.trim() {
        return Err("The list address must not have leading or trailing spaces".into());
    }
    let url = Url::parse(input).map_err(|_| "The list address is not a valid URL".to_string())?;
    if url.scheme() != "https" {
        return Err("List addresses must start with https://".into());
    }
    if !url.username().is_empty() || url.password().is_some() {
        return Err("List addresses must not contain a user name or password".into());
    }
    if url.fragment().is_some() {
        return Err("List addresses must not contain a fragment".into());
    }
    let host = url
        .host_str()
        .ok_or_else(|| "The list address has no host".to_string())?;
    let literal = host.trim_start_matches('[').trim_end_matches(']');
    let local = match literal.parse::<IpAddr>() {
        Ok(ip) => !is_public_ip(ip),
        Err(_) => blocked_host_name(host),
    };
    if local {
        return Err("List addresses must not point at a private or local network".into());
    }
    Ok(url)
}

// ---------------------------------------------------------------------------
// Download
// ---------------------------------------------------------------------------

pub(crate) enum Fetched {
    NotModified,
    Body { text: String, etag: Option<String> },
}

fn resolve_public(host: &str, port: u16) -> Result<Vec<SocketAddr>, String> {
    let addresses: Vec<SocketAddr> = (host, port)
        .to_socket_addrs()
        .map_err(|error| format!("Unable to resolve {host}: {error}"))?
        .collect();
    if addresses.is_empty() {
        return Err(format!("{host} did not resolve to any address"));
    }
    if addresses.iter().any(|addr| !is_public_ip(addr.ip())) {
        return Err(format!(
            "{host} resolves to a private or local network address and was refused"
        ));
    }
    Ok(addresses)
}

/// Downloads a list. Every hop is validated, its addresses are resolved once
/// and pinned for the connection (so DNS cannot change between check and use),
/// and redirects are followed manually up to a small limit.
pub(crate) async fn fetch(url: &str, etag: Option<&str>) -> Result<Fetched, String> {
    let mut current = validate_list_url(url)?;
    for _ in 0..=MAX_REDIRECTS {
        let host = current
            .host_str()
            .ok_or_else(|| "The list address has no host".to_string())?
            .to_string();
        let port = current.port_or_known_default().unwrap_or(443);
        let addresses = {
            let host = host.clone();
            tauri::async_runtime::spawn_blocking(move || resolve_public(&host, port))
                .await
                .map_err(|error| format!("Address lookup failed: {error}"))??
        };
        let client = reqwest::Client::builder()
            .connect_timeout(Duration::from_secs(10))
            .timeout(Duration::from_secs(90))
            .redirect(reqwest::redirect::Policy::none())
            .resolve_to_addrs(&host, &addresses)
            .build()
            .map_err(|error| format!("Unable to prepare the download: {error}"))?;
        let mut request = client.get(current.clone()).header(
            reqwest::header::USER_AGENT,
            concat!("Tauridium/", env!("CARGO_PKG_VERSION")),
        );
        if let Some(etag) = etag {
            request = request.header(reqwest::header::IF_NONE_MATCH, etag);
        }
        let response = request
            .send()
            .await
            .map_err(|error| format!("Download failed: {error}"))?;
        let status = response.status();
        if status == reqwest::StatusCode::NOT_MODIFIED {
            return Ok(Fetched::NotModified);
        }
        if status.is_redirection() {
            let location = response
                .headers()
                .get(reqwest::header::LOCATION)
                .and_then(|value| value.to_str().ok())
                .ok_or_else(|| "The list server sent a redirect without a location".to_string())?;
            let next = current
                .join(location)
                .map_err(|_| "The list server sent an invalid redirect".to_string())?;
            current = validate_list_url(next.as_str())
                .map_err(|error| format!("Refused redirect: {error}"))?;
            continue;
        }
        if !status.is_success() {
            return Err(format!("The list server returned HTTP {status}"));
        }
        let etag = response
            .headers()
            .get(reqwest::header::ETAG)
            .and_then(|value| value.to_str().ok())
            .map(str::to_string);
        let bytes = crate::http_security::bytes(response, MAX_LIST_BYTES).await?;
        let text = String::from_utf8(bytes)
            .map_err(|_| "The downloaded list is not valid UTF-8 text".to_string())?;
        return Ok(Fetched::Body { text, etag });
    }
    Err("The list address redirected too many times".into())
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct ListStats {
    pub(crate) network: u32,
    pub(crate) cosmetic: u32,
}

/// Parses a list and rejects text that is not a usable filter list.
pub(crate) fn validate_list_text(text: &str) -> Result<ListStats, String> {
    let head = text.trim_start();
    if head.is_empty() {
        return Err("The list is empty".into());
    }
    if head.starts_with('<') {
        return Err("The address returned a web page, not a filter list".into());
    }
    let (network, cosmetic) =
        adblock::lists::parse_filters(text.lines(), false, adblock::lists::ParseOptions::default());
    if network.is_empty() {
        return Err("The list contains no network blocking rules".into());
    }
    Ok(ListStats {
        network: u32::try_from(network.len()).unwrap_or(u32::MAX),
        cosmetic: u32::try_from(cosmetic.len()).unwrap_or(u32::MAX),
    })
}

/// How long a downloaded list stays fresh, from its `Expires` header.
pub(crate) fn refresh_interval_secs(text: &str) -> u64 {
    let interval = text
        .lines()
        .take(40)
        .filter_map(|line| line.trim().strip_prefix("! Expires:"))
        .find_map(|value| {
            let mut parts = value.split_whitespace();
            let amount: u64 = parts.next()?.parse().ok()?;
            match parts
                .next()?
                .trim_end_matches(|c: char| !c.is_ascii_alphabetic())
            {
                "hour" | "hours" | "h" => Some(amount * 3600),
                "day" | "days" | "d" => Some(amount * 24 * 3600),
                _ => None,
            }
        })
        .unwrap_or(DEFAULT_REFRESH_SECS);
    interval.clamp(MIN_REFRESH_SECS, MAX_REFRESH_SECS)
}

// ---------------------------------------------------------------------------
// Cache and metadata
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", default)]
pub(crate) struct ListMeta {
    pub(crate) url: String,
    pub(crate) last_updated: Option<u64>,
    pub(crate) next_check: Option<u64>,
    pub(crate) etag: Option<String>,
    pub(crate) network_rules: u32,
    pub(crate) cosmetic_rules: u32,
    pub(crate) content_hash: String,
    pub(crate) last_error: Option<String>,
    /// True once the current failure episode has been shown to the user.
    pub(crate) error_reported: bool,
}

#[derive(Debug, Default, Serialize, Deserialize)]
struct MetaFile {
    version: u32,
    lists: BTreeMap<String, ListMeta>,
}

static CACHE_LOCK: Mutex<()> = Mutex::new(());

fn meta_path(dir: &Path) -> PathBuf {
    dir.join(META_FILE)
}

fn list_path(dir: &Path, id: &str) -> PathBuf {
    dir.join("lists").join(format!("{id}.txt"))
}

fn read_meta_file(dir: &Path) -> Result<MetaFile, String> {
    match std::fs::read(meta_path(dir)) {
        Ok(bytes) => {
            let file: MetaFile = serde_json::from_slice(&bytes)
                .map_err(|error| format!("Filter list cache index is unreadable: {error}"))?;
            if file.version != META_VERSION {
                return Err("Filter list cache index has an unsupported version".into());
            }
            Ok(file)
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(MetaFile {
            version: META_VERSION,
            lists: BTreeMap::new(),
        }),
        Err(error) => Err(format!(
            "Unable to read the filter list cache index: {error}"
        )),
    }
}

fn write_meta_file(dir: &Path, file: &MetaFile) -> Result<(), String> {
    std::fs::create_dir_all(dir.join("lists"))
        .map_err(|error| format!("Unable to create the filter list cache: {error}"))?;
    let bytes = serde_json::to_vec_pretty(file)
        .map_err(|error| format!("Unable to encode the filter list cache index: {error}"))?;
    crate::private_file::write(&meta_path(dir), &bytes)
        .map_err(|error| format!("Unable to save the filter list cache index: {error}"))
}

/// Metadata for every cached list.
pub(crate) fn load_meta(dir: &Path) -> BTreeMap<String, ListMeta> {
    let _guard = CACHE_LOCK.lock().unwrap();
    read_meta_file(dir)
        .map(|file| file.lists)
        .unwrap_or_default()
}

/// The cached list text, if the file and its recorded hash agree.
pub(crate) fn read_cached(dir: &Path, id: &str) -> Option<String> {
    let _guard = CACHE_LOCK.lock().unwrap();
    let text = std::fs::read_to_string(list_path(dir, id)).ok()?;
    let meta = read_meta_file(dir).ok()?.lists.get(id).cloned()?;
    (meta.content_hash == content_hash(&text)).then_some(text)
}

pub(crate) fn content_hash(text: &str) -> String {
    Sha256::digest(text.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

/// Atomically stores a validated list and updates its metadata.
pub(crate) fn store_list(
    dir: &Path,
    id: &str,
    url: &str,
    text: &str,
    stats: ListStats,
    etag: Option<String>,
    now: u64,
) -> Result<bool, String> {
    let _guard = CACHE_LOCK.lock().unwrap();
    let mut file = read_meta_file(dir)?;
    let hash = content_hash(text);
    let changed = file
        .lists
        .get(id)
        .is_none_or(|meta| meta.content_hash != hash);
    std::fs::create_dir_all(dir.join("lists"))
        .map_err(|error| format!("Unable to create the filter list cache: {error}"))?;
    if changed {
        crate::private_file::write(&list_path(dir, id), text.as_bytes())
            .map_err(|error| format!("Unable to save the filter list: {error}"))?;
    }
    file.lists.insert(
        id.to_string(),
        ListMeta {
            url: url.to_string(),
            last_updated: Some(now),
            next_check: Some(now + refresh_interval_secs(text)),
            etag,
            network_rules: stats.network,
            cosmetic_rules: stats.cosmetic,
            content_hash: hash,
            last_error: None,
            error_reported: false,
        },
    );
    write_meta_file(dir, &file)?;
    Ok(changed)
}

/// Records that the list was checked and is unchanged.
pub(crate) fn mark_unchanged(dir: &Path, id: &str, text: &str, now: u64) -> Result<(), String> {
    let _guard = CACHE_LOCK.lock().unwrap();
    let mut file = read_meta_file(dir)?;
    if let Some(meta) = file.lists.get_mut(id) {
        meta.next_check = Some(now + refresh_interval_secs(text));
        meta.last_error = None;
        meta.error_reported = false;
        write_meta_file(dir, &file)?;
    }
    Ok(())
}

/// Records a failed update, keeping the last good copy. Returns true when the
/// error is new to the user (first failure of an episode) and should be shown.
pub(crate) fn record_failure(
    dir: &Path,
    id: &str,
    url: &str,
    error: &str,
    now: u64,
) -> Result<bool, String> {
    let _guard = CACHE_LOCK.lock().unwrap();
    let mut file = read_meta_file(dir)?;
    let meta = file
        .lists
        .entry(id.to_string())
        .or_insert_with(|| ListMeta {
            url: url.to_string(),
            ..ListMeta::default()
        });
    let announce = !meta.error_reported;
    meta.last_error = Some(error.to_string());
    meta.error_reported = true;
    // Retry sooner than a healthy refresh, but not on every start.
    meta.next_check = Some(now + 6 * 3600);
    write_meta_file(dir, &file)?;
    Ok(announce)
}

/// Removes cached lists that are no longer selected.
pub(crate) fn prune(dir: &Path, keep: &[String]) -> Result<(), String> {
    let _guard = CACHE_LOCK.lock().unwrap();
    let mut file = read_meta_file(dir)?;
    let stale: Vec<String> = file
        .lists
        .keys()
        .filter(|id| !keep.contains(id))
        .cloned()
        .collect();
    if stale.is_empty() {
        return Ok(());
    }
    for id in &stale {
        file.lists.remove(id);
        let _ = std::fs::remove_file(list_path(dir, id));
    }
    write_meta_file(dir, &file)
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = "[Adblock Plus 2.0]\n! Title: Test\n! Expires: 2 days\n||ads.example.com^\n/adserver.js\n@@||ok.example.com^\nexample.com##.banner\n";

    #[test]
    fn urls_must_be_canonical_public_https() {
        for ok in [
            "https://easylist.to/easylist/easylist.txt",
            "https://example.com/list.txt?x=1",
            "https://8.8.8.8/list.txt",
        ] {
            assert!(validate_list_url(ok).is_ok(), "{ok}");
        }
        for bad in [
            "http://example.com/list.txt",
            "https://localhost/list.txt",
            "https://foo.localhost/list.txt",
            "https://printer.local/list.txt",
            "https://intranet/list.txt",
            "https://127.0.0.1/list.txt",
            "https://10.0.0.1/list.txt",
            "https://192.168.1.5/list.txt",
            "https://169.254.169.254/latest",
            "https://[::1]/list.txt",
            "https://[fd00::1]/list.txt",
            "https://[::ffff:127.0.0.1]/list.txt",
            "https://user:pw@example.com/list.txt",
            "https://example.com/list.txt#frag",
            "ftp://example.com/list.txt",
            "not a url",
            "",
        ] {
            assert!(validate_list_url(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn ip_classification() {
        for ip in ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"] {
            assert!(is_public_ip(ip.parse().unwrap()), "{ip}");
        }
        for ip in [
            "0.0.0.0",
            "127.0.0.1",
            "10.1.2.3",
            "172.16.0.1",
            "192.168.0.1",
            "169.254.1.1",
            "100.64.0.1",
            "198.18.0.1",
            "224.0.0.1",
            "255.255.255.255",
            "::",
            "::1",
            "fe80::1",
            "fc00::1",
            "ff02::1",
            "::ffff:10.0.0.1",
            "2001:db8::1",
        ] {
            assert!(!is_public_ip(ip.parse().unwrap()), "{ip}");
        }
    }

    #[test]
    fn resolution_refuses_private_addresses() {
        assert!(resolve_public("localhost", 443).is_err());
        assert!(resolve_public("127.0.0.1", 443).is_err());
    }

    #[test]
    fn list_validation() {
        let stats = validate_list_text(SAMPLE).unwrap();
        assert_eq!(stats.network, 3);
        assert_eq!(stats.cosmetic, 1);
        assert!(validate_list_text("").is_err());
        assert!(validate_list_text("<!doctype html><html></html>").is_err());
        assert!(validate_list_text("! only comments\n! more\n").is_err());
        assert!(validate_list_text("example.com##.banner\n").is_err());
    }

    #[test]
    fn refresh_interval_follows_expires_with_bounds() {
        assert_eq!(refresh_interval_secs(SAMPLE), 2 * 24 * 3600);
        assert_eq!(
            refresh_interval_secs("! Expires: 6 hours\n||a.com^"),
            MIN_REFRESH_SECS
        );
        assert_eq!(
            refresh_interval_secs("! Expires: 90 days\n||a.com^"),
            MAX_REFRESH_SECS
        );
        assert_eq!(refresh_interval_secs("||a.com^"), DEFAULT_REFRESH_SECS);
    }

    #[test]
    fn custom_list_ids_are_stable_and_distinct() {
        let a = custom_list_id("https://example.com/a.txt");
        assert_eq!(a, custom_list_id("https://example.com/a.txt"));
        assert_ne!(a, custom_list_id("https://example.com/b.txt"));
        assert!(a.starts_with("custom-") && a.len() == "custom-".len() + 12);
    }

    #[test]
    fn selected_sources_follow_settings() {
        let settings = serde_json::json!({
            "adblockLists": ["easyprivacy"],
            "adblockCustomLists": ["https://example.com/a.txt"]
        });
        let sources = selected_sources(&settings);
        assert_eq!(sources.len(), 2);
        assert_eq!(sources[0].id, "easyprivacy");
        assert!(sources[1].custom);
    }

    #[test]
    fn cache_keeps_last_good_copy_and_reports_each_failure_episode_once() {
        let dir = tempfile::tempdir().unwrap();
        let stats = validate_list_text(SAMPLE).unwrap();
        let url = "https://example.com/a.txt";
        assert!(store_list(
            dir.path(),
            "x",
            url,
            SAMPLE,
            stats,
            Some("\"e1\"".into()),
            100
        )
        .unwrap());
        assert_eq!(read_cached(dir.path(), "x").as_deref(), Some(SAMPLE));
        // Same content again is not a change.
        assert!(!store_list(dir.path(), "x", url, SAMPLE, stats, None, 200).unwrap());

        assert!(record_failure(dir.path(), "x", url, "boom", 300).unwrap());
        assert!(!record_failure(dir.path(), "x", url, "boom again", 400).unwrap());
        let meta = load_meta(dir.path());
        assert_eq!(meta["x"].last_error.as_deref(), Some("boom again"));
        // The previous good copy is still served.
        assert_eq!(read_cached(dir.path(), "x").as_deref(), Some(SAMPLE));

        // Recovery clears the episode, so a later failure is announced again.
        store_list(dir.path(), "x", url, SAMPLE, stats, None, 500).unwrap();
        assert!(load_meta(dir.path())["x"].last_error.is_none());
        assert!(record_failure(dir.path(), "x", url, "later", 600).unwrap());
    }

    #[test]
    fn tampered_cache_is_not_trusted() {
        let dir = tempfile::tempdir().unwrap();
        let stats = validate_list_text(SAMPLE).unwrap();
        store_list(
            dir.path(),
            "x",
            "https://example.com/a.txt",
            SAMPLE,
            stats,
            None,
            1,
        )
        .unwrap();
        std::fs::write(list_path(dir.path(), "x"), "||evil.example^\n").unwrap();
        assert!(read_cached(dir.path(), "x").is_none());
    }

    #[test]
    fn unknown_index_version_is_rejected_without_overwriting() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(meta_path(dir.path()), br#"{"version":99,"lists":{}}"#).unwrap();
        let stats = validate_list_text(SAMPLE).unwrap();
        assert!(store_list(
            dir.path(),
            "x",
            "https://example.com/a.txt",
            SAMPLE,
            stats,
            None,
            1
        )
        .is_err());
        assert_eq!(
            std::fs::read_to_string(meta_path(dir.path())).unwrap(),
            r#"{"version":99,"lists":{}}"#
        );
    }

    #[test]
    fn prune_removes_unselected_lists() {
        let dir = tempfile::tempdir().unwrap();
        let stats = validate_list_text(SAMPLE).unwrap();
        for id in ["a", "b"] {
            store_list(
                dir.path(),
                id,
                "https://example.com/x.txt",
                SAMPLE,
                stats,
                None,
                1,
            )
            .unwrap();
        }
        prune(dir.path(), &["a".to_string()]).unwrap();
        assert!(read_cached(dir.path(), "a").is_some());
        assert!(read_cached(dir.path(), "b").is_none());
        assert!(!list_path(dir.path(), "b").exists());
    }
}
