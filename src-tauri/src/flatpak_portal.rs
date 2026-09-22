#![cfg(all(target_os = "linux", feature = "flatpak"))]

use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use zbus::blocking::{Connection, Proxy};
use zbus::zvariant::{OwnedObjectPath, OwnedValue, Value};

const PORTAL_SERVICE: &str = "org.freedesktop.portal.Desktop";
const PORTAL_PATH: &str = "/org/freedesktop/portal/desktop";
const REQUEST_INTERFACE: &str = "org.freedesktop.portal.Request";
const BACKGROUND_INTERFACE: &str = "org.freedesktop.portal.Background";
const NOTIFICATION_INTERFACE: &str = "org.freedesktop.portal.Notification";
const OPEN_URI_INTERFACE: &str = "org.freedesktop.portal.OpenURI";
static TOKEN_COUNTER: AtomicU64 = AtomicU64::new(1);
static NOTIFICATION_COUNTER: AtomicU64 = AtomicU64::new(1);

fn portal_error(context: &str, error: impl std::fmt::Display) -> String {
    format!("{context}: {error}")
}

fn token(prefix: &str) -> String {
    format!(
        "{prefix}_{}_{}",
        std::process::id(),
        TOKEN_COUNTER.fetch_add(1, Ordering::Relaxed)
    )
}

fn request_path(connection: &Connection, handle_token: &str) -> Result<String, String> {
    let sender = connection
        .unique_name()
        .ok_or_else(|| "Portal D-Bus connection has no unique sender name".to_string())?
        .as_str()
        .trim_start_matches(':')
        .replace('.', "_");
    Ok(format!(
        "/org/freedesktop/portal/desktop/request/{sender}/{handle_token}"
    ))
}

fn wait_for_request<F>(
    connection: &Connection,
    handle_token: &str,
    call: F,
) -> Result<HashMap<String, OwnedValue>, String>
where
    F: FnOnce() -> Result<OwnedObjectPath, zbus::Error>,
{
    // Subscribe before issuing the portal call. The Request API explicitly recommends
    // this ordering so a fast portal response cannot race past the signal listener.
    let expected_path = request_path(connection, handle_token)?;
    let request_proxy = Proxy::new(
        connection,
        PORTAL_SERVICE,
        expected_path.as_str(),
        REQUEST_INTERFACE,
    )
    .map_err(|error| portal_error("Unable to create XDG portal request proxy", error))?;
    let mut responses = request_proxy
        .receive_signal("Response")
        .map_err(|error| portal_error("Unable to subscribe to XDG portal response", error))?;

    let returned_path = call().map_err(|error| portal_error("XDG portal request failed", error))?;
    if returned_path.as_str() != expected_path {
        return Err(format!(
            "XDG portal returned an unexpected request handle: {}",
            returned_path.as_str()
        ));
    }

    let message = responses
        .next()
        .ok_or_else(|| "XDG portal request ended without a response".to_string())?;
    let (response, results): (u32, HashMap<String, OwnedValue>) = message
        .body()
        .deserialize()
        .map_err(|error| portal_error("Unable to decode XDG portal response", error))?;
    match response {
        0 => Ok(results),
        1 => Err("XDG portal request was cancelled by the user".to_string()),
        2 => Err("XDG portal request was denied or failed".to_string()),
        code => Err(format!("XDG portal returned unknown response code {code}")),
    }
}

pub fn request_autostart(enabled: bool) -> Result<bool, String> {
    let connection = Connection::session()
        .map_err(|error| portal_error("Unable to connect to the session D-Bus", error))?;
    let handle_token = token("tauridium_background");
    let portal = Proxy::new(
        &connection,
        PORTAL_SERVICE,
        PORTAL_PATH,
        BACKGROUND_INTERFACE,
    )
    .map_err(|error| portal_error("Unable to create XDG Background portal proxy", error))?;

    let mut options = HashMap::<&str, Value<'_>>::new();
    options.insert("handle_token", Value::new(handle_token.as_str()));
    options.insert(
        "reason",
        Value::new("Start Tauridium automatically when you sign in"),
    );
    options.insert("autostart", Value::new(enabled));
    // `commandline` is deliberately omitted. The portal specification then uses the
    // installed desktop file's `Exec=tauridium`, avoiding host autostart file access.

    let results = wait_for_request(&connection, &handle_token, || {
        portal.call("RequestBackground", &("", options))
    })?;
    let background = results
        .get("background")
        .and_then(|value| bool::try_from(value).ok())
        .unwrap_or(false);
    let autostart = results
        .get("autostart")
        .and_then(|value| bool::try_from(value).ok())
        .unwrap_or(false);

    if enabled && !background {
        return Ok(false);
    }
    Ok(autostart)
}

pub fn open_uri(uri: &str) -> Result<(), String> {
    let connection = Connection::session()
        .map_err(|error| portal_error("Unable to connect to the session D-Bus", error))?;
    let handle_token = token("tauridium_open_uri");
    let portal = Proxy::new(&connection, PORTAL_SERVICE, PORTAL_PATH, OPEN_URI_INTERFACE)
        .map_err(|error| portal_error("Unable to create XDG OpenURI portal proxy", error))?;
    let mut options = HashMap::<&str, Value<'_>>::new();
    options.insert("handle_token", Value::new(handle_token.as_str()));
    wait_for_request(&connection, &handle_token, || {
        portal.call("OpenURI", &("", uri, options))
    })?;
    Ok(())
}

pub fn add_notification(title: &str, body: Option<&str>) -> Result<(), String> {
    let connection = Connection::session()
        .map_err(|error| portal_error("Unable to connect to the session D-Bus", error))?;
    let portal = Proxy::new(
        &connection,
        PORTAL_SERVICE,
        PORTAL_PATH,
        NOTIFICATION_INTERFACE,
    )
    .map_err(|error| portal_error("Unable to create XDG Notification portal proxy", error))?;

    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    let id = format!(
        "tauridium-{millis}-{}",
        NOTIFICATION_COUNTER.fetch_add(1, Ordering::Relaxed)
    );
    let mut notification = HashMap::<&str, Value<'_>>::new();
    notification.insert("title", Value::new(title));
    if let Some(body) = body.filter(|body| !body.is_empty()) {
        notification.insert("body", Value::new(body));
    }
    let _: () = portal
        .call("AddNotification", &(id.as_str(), notification))
        .map_err(|error| portal_error("Unable to send XDG portal notification", error))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn portal_tokens_are_valid_object_path_elements() {
        for prefix in ["tauridium_background", "tauridium_open_uri"] {
            let value = token(prefix);
            assert!(!value.is_empty());
            assert!(value
                .chars()
                .all(|character| character.is_ascii_alphanumeric() || character == '_'));
        }
    }
}
