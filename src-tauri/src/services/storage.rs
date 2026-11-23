//! Isolated/shared service storage identity and cleanup.

use crate::storage_security;
use serde_json::Value;
use sha2::{Digest, Sha256};
#[cfg(any(not(target_os = "macos"), test))]
use std::path::Path;
#[cfg(any(not(target_os = "macos"), test))]
use std::path::PathBuf;
use tauri::AppHandle;
#[cfg(not(target_os = "macos"))]
use tauri::Manager;

// The service UUID's 16 bytes become the WKWebView data-store identifier.
#[cfg(any(target_os = "macos", test))]
fn uuid_to_bytes(s: &str) -> Option<[u8; 16]> {
    let hex: String = s.chars().filter(|c| *c != '-').collect();
    if hex.len() != 32 {
        return None;
    }
    let mut out = [0u8; 16];
    for i in 0..16 {
        out[i] = u8::from_str_radix(&hex[i * 2..i * 2 + 2], 16).ok()?;
    }
    Some(out)
}

pub(super) fn sandbox_for_service(settings: &Value, service_id: &str) -> Option<String> {
    settings
        .get("serviceSandboxes")
        .and_then(Value::as_object)
        .and_then(|assignments| assignments.get(service_id))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|sandbox_id| !sandbox_id.is_empty())
        .map(str::to_string)
}

#[cfg(any(not(target_os = "macos"), test))]
fn sandbox_storage_name(sandbox_id: &str) -> String {
    let digest = Sha256::digest(format!("tauridium-sandbox:{sandbox_id}").as_bytes());
    let suffix = digest[..12]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    format!("sandbox-{suffix}")
}

#[cfg(any(target_os = "macos", test))]
pub(super) fn storage_identifier(service_id: &str, sandbox_id: Option<&str>) -> Option<[u8; 16]> {
    if let Some(sandbox_id) = sandbox_id {
        let digest = Sha256::digest(format!("tauridium-sandbox:{sandbox_id}").as_bytes());
        let mut identifier = [0u8; 16];
        identifier.copy_from_slice(&digest[..16]);
        Some(identifier)
    } else {
        uuid_to_bytes(service_id)
    }
}

#[cfg(any(not(target_os = "macos"), test))]
pub(super) fn storage_directory(
    app_data: &Path,
    service_id: &str,
    sandbox_id: Option<&str>,
) -> Result<PathBuf, String> {
    storage_security::validate_service_id(service_id)?;
    let name = sandbox_id
        .map(sandbox_storage_name)
        .unwrap_or_else(|| service_id.to_string());
    storage_security::session_path(app_data, &name)
}

// Purge a service's persistent storage (cookies, localStorage, session). Call this
// AFTER closing its webview. macOS: delete the WKWebsiteDataStore by identifier
// (wry API, main thread required); elsewhere delete the data_directory folder.
#[cfg(target_os = "macos")]
pub(super) fn purge_service_storage(
    app: &AppHandle,
    service_id: &str,
    sandbox_id: Option<&str>,
) -> Result<(), String> {
    storage_security::validate_service_id(service_id)?;
    use wry::WebViewExtDarwin;
    if let Some(uuid) = storage_identifier(service_id, sandbox_id) {
        app.run_on_main_thread(move || {
            <wry::WebView as WebViewExtDarwin>::remove_data_store(&uuid, |_| {});
        })
        .map_err(|error| format!("Unable to clear service data store: {error}"))?;
    }
    Ok(())
}

#[cfg(not(target_os = "macos"))]
pub(super) fn purge_service_storage(
    app: &AppHandle,
    service_id: &str,
    sandbox_id: Option<&str>,
) -> Result<(), String> {
    let dir = app
        .path()
        .app_data_dir()
        .map_err(|error| error.to_string())?;
    let path = storage_directory(&dir, service_id, sandbox_id)?;
    let name = path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or("Invalid session storage name")?;
    storage_security::purge(&dir, name)
}

#[cfg(test)]
mod tests;
