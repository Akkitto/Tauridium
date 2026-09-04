use base64::Engine;
use reqwest::header::CONTENT_TYPE;
use std::fs;
use std::path::{Path, PathBuf};
use tauri::{AppHandle, Manager, Url};

use crate::write_atomic;

const ICON_CACHE_DIR: &str = "service-icons";
const MAX_ICON_BYTES: usize = 512 * 1024;
const MAX_HTML_BYTES: usize = 1024 * 1024;
const MISSING_SENTINEL: &str = "missing";

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum ServiceIconLoad {
    Disabled,
    Cached(Option<String>),
    Fetched(String),
}

impl ServiceIconLoad {
    pub(crate) fn icon(self) -> Option<String> {
        match self {
            Self::Disabled | Self::Cached(None) => None,
            Self::Cached(Some(icon)) | Self::Fetched(icon) => Some(icon),
        }
    }
}

fn cache_key(service_id: &str) -> String {
    use sha2::{Digest, Sha256};
    let digest = Sha256::digest(service_id.as_bytes());
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn cache_path(app: &AppHandle, service_id: &str) -> Result<PathBuf, String> {
    let root = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Service icon cache directory unavailable: {error}"))?
        .join(ICON_CACHE_DIR);
    fs::create_dir_all(&root)
        .map_err(|error| format!("Unable to create service icon cache directory: {error}"))?;
    Ok(root.join(format!("{}.txt", cache_key(service_id))))
}

fn read_cache(path: &Path) -> Option<Option<String>> {
    let value = fs::read_to_string(path).ok()?;
    let value = value.trim();
    if value == MISSING_SENTINEL {
        return Some(None);
    }
    value
        .starts_with("data:image/")
        .then_some(Some(value.to_string()))
}

fn content_type_mime(response: &reqwest::Response, url: &Url) -> Option<String> {
    if let Some(value) = response
        .headers()
        .get(CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.split(';').next())
        .map(str::trim)
        .filter(|value| value.starts_with("image/"))
    {
        return Some(value.to_string());
    }
    let path = url.path().to_ascii_lowercase();
    if path.ends_with(".svg") {
        Some("image/svg+xml".into())
    } else if path.ends_with(".png") {
        Some("image/png".into())
    } else if path.ends_with(".jpg") || path.ends_with(".jpeg") {
        Some("image/jpeg".into())
    } else if path.ends_with(".gif") {
        Some("image/gif".into())
    } else if path.ends_with(".webp") {
        Some("image/webp".into())
    } else if path.ends_with(".ico") {
        Some("image/x-icon".into())
    } else if path.ends_with(".avif") {
        Some("image/avif".into())
    } else if path.ends_with(".bmp") {
        Some("image/bmp".into())
    } else {
        None
    }
}

fn image_bytes_look_compatible(mime: &str, bytes: &[u8]) -> bool {
    match mime {
        "image/png" => bytes.starts_with(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg" => bytes.starts_with(&[0xff, 0xd8, 0xff]),
        "image/gif" => bytes.starts_with(b"GIF87a") || bytes.starts_with(b"GIF89a"),
        "image/webp" => bytes.len() >= 12 && bytes.starts_with(b"RIFF") && &bytes[8..12] == b"WEBP",
        "image/x-icon" | "image/vnd.microsoft.icon" => {
            bytes.starts_with(&[0x00, 0x00, 0x01, 0x00]) || bytes.starts_with(b"\x89PNG\r\n\x1a\n")
        }
        "image/svg+xml" => bytes.windows(4).take(4096).any(|window| window == b"<svg"),
        "image/avif" => {
            bytes.len() >= 12
                && &bytes[4..8] == b"ftyp"
                && bytes[8..]
                    .windows(4)
                    .any(|brand| brand == b"avif" || brand == b"avis")
        }
        "image/bmp" => bytes.starts_with(b"BM"),
        _ => false,
    }
}

async fn fetch_image(client: &reqwest::Client, url: &Url) -> Result<String, String> {
    let response = client
        .get(url.clone())
        .header(
            reqwest::header::USER_AGENT,
            concat!("Tauridium/", env!("CARGO_PKG_VERSION")),
        )
        .send()
        .await
        .map_err(|error| format!("Unable to fetch website icon: {error}"))?;
    if !response.status().is_success() {
        return Err(format!("Website icon returned HTTP {}", response.status()));
    }
    if response
        .content_length()
        .is_some_and(|size| size > MAX_ICON_BYTES as u64)
    {
        return Err("Website icon is too large".into());
    }
    let mime = content_type_mime(&response, url)
        .ok_or_else(|| "Website icon response is not an image".to_string())?;
    let bytes = response
        .bytes()
        .await
        .map_err(|error| format!("Unable to read website icon: {error}"))?;
    if bytes.is_empty() || bytes.len() > MAX_ICON_BYTES {
        return Err("Website icon has an invalid size".into());
    }
    if !image_bytes_look_compatible(&mime, &bytes) {
        return Err(format!(
            "Website icon uses incompatible or invalid image data ({mime})"
        ));
    }
    Ok(format!(
        "data:{mime};base64,{}",
        base64::engine::general_purpose::STANDARD.encode(bytes)
    ))
}

fn attribute_value(tag: &str, attribute: &str) -> Option<String> {
    let lower = tag.to_ascii_lowercase();
    let mut offset = 0;
    while let Some(index) = lower[offset..].find(attribute) {
        let index = offset + index;
        let before_ok = index == 0 || !lower.as_bytes()[index - 1].is_ascii_alphanumeric();
        let after_index = index + attribute.len();
        let after_ok = lower
            .as_bytes()
            .get(after_index)
            .is_none_or(|byte| !byte.is_ascii_alphanumeric() && *byte != b'-');
        if !before_ok || !after_ok {
            offset = after_index;
            continue;
        }
        let mut rest = &tag[after_index..];
        rest = rest.trim_start();
        let Some(rest) = rest.strip_prefix('=') else {
            offset = after_index;
            continue;
        };
        let rest = rest.trim_start();
        let first = rest.chars().next()?;
        if first == '"' || first == '\'' {
            let value = &rest[first.len_utf8()..];
            let end = value.find(first)?;
            return Some(value[..end].to_string());
        }
        let end = rest
            .find(|character: char| character.is_ascii_whitespace() || character == '>')
            .unwrap_or(rest.len());
        return Some(rest[..end].to_string());
    }
    None
}

fn icon_href_from_html(html: &str) -> Option<String> {
    let lower = html.to_ascii_lowercase();
    let mut offset = 0;
    while let Some(start) = lower[offset..].find("<link") {
        let start = offset + start;
        let Some(end_relative) = lower[start..].find('>') else {
            break;
        };
        let end = start + end_relative + 1;
        let tag = &html[start..end];
        let rel = attribute_value(tag, "rel")
            .unwrap_or_default()
            .to_ascii_lowercase();
        if rel.split_ascii_whitespace().any(|token| token == "icon") {
            if let Some(href) =
                attribute_value(tag, "href").filter(|value| !value.trim().is_empty())
            {
                return Some(href);
            }
        }
        offset = end;
    }
    None
}

fn looks_like_direct_image_url(url: &Url) -> bool {
    let path = url.path().to_ascii_lowercase();
    [
        ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".avif", ".bmp",
    ]
    .iter()
    .any(|extension| path.ends_with(extension))
}

async fn fetch_icon_url(
    client: &reqwest::Client,
    raw_url: &str,
    kind: &str,
) -> Result<String, String> {
    let parsed =
        Url::parse(raw_url.trim()).map_err(|error| format!("Invalid {kind} URL: {error}"))?;
    if !matches!(parsed.scheme(), "http" | "https") {
        return Err(format!("{kind} URLs must use HTTP or HTTPS"));
    }

    // Accept either a direct image URL or an ordinary website URL. A URL ending in a supported
    // image extension is treated as an explicit image and must itself be valid; silently replacing
    // a broken direct image with the website favicon would hide an incompatible custom source.
    // Ordinary page URLs fall back to favicon discovery. The result is always a self-contained
    // data URL so persistent icon storage never depends on the remote source remaining available.
    match fetch_image(client, &parsed).await {
        Ok(icon) => Ok(icon),
        Err(error) if looks_like_direct_image_url(&parsed) => Err(error),
        Err(_) => discover_icon(client, &parsed).await,
    }
}

pub(crate) async fn fetch_workspace_icon_url(
    client: &reqwest::Client,
    raw_url: &str,
) -> Result<String, String> {
    fetch_icon_url(client, raw_url, "workspace icon").await
}

pub(crate) async fn fetch_service_icon_url(
    app: &AppHandle,
    client: &reqwest::Client,
    service_id: &str,
    raw_url: &str,
) -> Result<String, String> {
    let path = cache_path(app, service_id)?;
    match fetch_icon_url(client, raw_url, "service icon source").await {
        Ok(icon) => {
            if let Err(error) = write_atomic(&path, &format!("{icon}\n")) {
                let _ = fs::remove_file(&path);
                return Err(format!("Unable to cache custom service icon: {error}"));
            }
            Ok(icon)
        }
        Err(error) => {
            // A custom source is an explicit replacement request. Do not retain a stale cached
            // website/custom icon when the replacement fails; the UI must fall back to the
            // service's recipe/default icon.
            let _ = fs::remove_file(&path);
            Err(error)
        }
    }
}

async fn discover_icon(client: &reqwest::Client, page_url: &Url) -> Result<String, String> {
    let response = client
        .get(page_url.clone())
        .header(
            reqwest::header::USER_AGENT,
            concat!("Tauridium/", env!("CARGO_PKG_VERSION")),
        )
        .send()
        .await
        .map_err(|error| format!("Unable to inspect service page for its icon: {error}"))?;
    if response.status().is_success()
        && !response
            .content_length()
            .is_some_and(|size| size > MAX_HTML_BYTES as u64)
    {
        if let Ok(bytes) = response.bytes().await {
            if bytes.len() <= MAX_HTML_BYTES {
                if let Ok(html) = std::str::from_utf8(&bytes) {
                    if let Some(href) = icon_href_from_html(html) {
                        if href.starts_with("data:image/") {
                            if href.len() <= MAX_ICON_BYTES * 2 {
                                return Ok(href.to_string());
                            }
                        } else if let Ok(icon_url) = page_url.join(&href) {
                            if let Ok(icon) = fetch_image(client, &icon_url).await {
                                return Ok(icon);
                            }
                        }
                    }
                }
            }
        }
    }

    let mut root = page_url.clone();
    root.set_path("/favicon.ico");
    root.set_query(None);
    root.set_fragment(None);
    fetch_image(client, &root).await
}

pub(crate) async fn cached_or_fetch(
    app: &AppHandle,
    client: &reqwest::Client,
    service_id: &str,
    page_url: &str,
    force: bool,
    should_fetch: bool,
) -> Result<ServiceIconLoad, String> {
    let path = cache_path(app, service_id)?;
    if !should_fetch {
        return Ok(ServiceIconLoad::Disabled);
    }
    let previous = read_cache(&path);
    if !force {
        if let Some(cached) = previous.clone() {
            return Ok(ServiceIconLoad::Cached(cached));
        }
    }

    let parsed = Url::parse(page_url)
        .map_err(|error| format!("Invalid service URL for icon discovery: {error}"))?;
    if !matches!(parsed.scheme(), "http" | "https") {
        return Err("Website icons can only be fetched from HTTP(S) services".into());
    }
    match discover_icon(client, &parsed).await {
        Ok(icon) => {
            write_atomic(&path, &format!("{icon}\n"))
                .map_err(|error| format!("Unable to cache website icon: {error}"))?;
            Ok(ServiceIconLoad::Fetched(icon))
        }
        Err(error) => {
            // A failed automatic discovery is negatively cached so startup does not repeatedly hit
            // the website. Explicit Refetch always bypasses this sentinel and preserves any good
            // existing icon if the retry itself fails.
            if !force && previous.is_none() {
                let _ = write_atomic(&path, &format!("{MISSING_SENTINEL}\n"));
            }
            Err(error)
        }
    }
}

pub(crate) fn copy_cached(
    app: &AppHandle,
    source_service_id: &str,
    target_service_id: &str,
) -> Result<(), String> {
    let source = cache_path(app, source_service_id)?;
    if !source.is_file() {
        return Ok(());
    }
    let value = fs::read_to_string(&source)
        .map_err(|error| format!("Unable to read source service icon cache: {error}"))?;
    if read_cache(&source).is_none() {
        return Err("Source service icon cache is invalid".into());
    }
    let target = cache_path(app, target_service_id)?;
    write_atomic(&target, &value)
        .map_err(|error| format!("Unable to copy service icon cache: {error}"))
}

pub(crate) fn remove_cached(app: &AppHandle, service_id: &str) {
    if let Ok(path) = cache_path(app, service_id) {
        let _ = fs::remove_file(path);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn html_icon_discovery_accepts_standard_rel_forms_and_quotes() {
        assert_eq!(
            icon_href_from_html(
                r#"<html><head><link rel="shortcut icon" href="/brand.ico"></head></html>"#
            ),
            Some("/brand.ico".into())
        );
        assert_eq!(
            icon_href_from_html("<link href='/icon.svg' rel='icon'>"),
            Some("/icon.svg".into())
        );
    }

    #[test]
    fn html_icon_discovery_ignores_unrelated_links() {
        assert_eq!(
            icon_href_from_html(
                r#"<link rel="stylesheet" href="/app.css"><link rel="preload" href="/x">"#
            ),
            None
        );
    }

    #[test]
    fn cache_keys_are_stable_and_filename_safe() {
        let key = cache_key("service/with unsafe chars");
        assert_eq!(key.len(), 64);
        assert!(key.bytes().all(|byte| byte.is_ascii_hexdigit()));
        assert_eq!(key, cache_key("service/with unsafe chars"));
    }

    #[test]
    fn service_icon_load_preserves_cache_vs_network_origin() {
        assert_eq!(ServiceIconLoad::Disabled.icon(), None);
        assert_eq!(ServiceIconLoad::Cached(None).icon(), None);
        assert_eq!(
            ServiceIconLoad::Cached(Some("data:image/png;base64,cached".into())).icon(),
            Some("data:image/png;base64,cached".into())
        );
        assert_eq!(
            ServiceIconLoad::Fetched("data:image/png;base64,fetched".into()).icon(),
            Some("data:image/png;base64,fetched".into())
        );
    }

    #[test]
    fn direct_image_urls_are_classified_without_query_string_confusion() {
        assert!(looks_like_direct_image_url(
            &Url::parse("https://example.com/icon.svg?cache=1").unwrap()
        ));
        assert!(looks_like_direct_image_url(
            &Url::parse("https://example.com/assets/icon.AVIF").unwrap()
        ));
        assert!(!looks_like_direct_image_url(
            &Url::parse("https://example.com/products/icon").unwrap()
        ));
    }

    #[test]
    fn icon_payload_validation_rejects_declared_images_with_incompatible_bytes() {
        assert!(image_bytes_look_compatible(
            "image/png",
            b"\x89PNG\r\n\x1a\nrest"
        ));
        assert!(image_bytes_look_compatible(
            "image/x-icon",
            b"\x00\x00\x01\x00rest"
        ));
        assert!(image_bytes_look_compatible(
            "image/svg+xml",
            br#"<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"></svg>"#
        ));
        assert!(!image_bytes_look_compatible(
            "image/png",
            b"<html>not an icon</html>"
        ));
        assert!(!image_bytes_look_compatible(
            "image/tiff",
            b"II*\x00unsupported"
        ));
    }
}
