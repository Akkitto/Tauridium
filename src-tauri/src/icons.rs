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
    } else {
        None
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
) -> Result<Option<String>, String> {
    let path = cache_path(app, service_id)?;
    if !force && !should_fetch {
        return Ok(None);
    }
    let previous = read_cache(&path);
    if !force {
        if let Some(cached) = previous {
            return Ok(cached);
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
            Ok(Some(icon))
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
}
