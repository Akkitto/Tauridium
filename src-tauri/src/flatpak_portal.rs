#![cfg(all(target_os = "linux", feature = "flatpak"))]

use futures_lite::StreamExt;
use std::collections::HashMap;
use std::future::Future;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use zbus::{Connection, OwnedObjectPath, OwnedVariant, Proxy, Variant};

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

async fn wait_for_request<F, Fut>(
    connection: &Connection,
    handle_token: &str,
    call: F,
) -> Result<HashMap<String, OwnedVariant>, String>
where
    F: FnOnce() -> Fut,
    Fut: Future<Output = Result<OwnedObjectPath, zbus::Error>>,
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
    .await
    .map_err(|error| portal_error("Unable to create XDG portal request proxy", error))?;
    let mut responses = request_proxy
        .receive_signal("Response")
        .await
        .map_err(|error| portal_error("Unable to subscribe to XDG portal response", error))?;

    let returned_path = call()
        .await
        .map_err(|error| portal_error("XDG portal request failed", error))?;
    if returned_path.as_str() != expected_path {
        return Err(format!(
            "XDG portal returned an unexpected request handle: {}",
            returned_path.as_str()
        ));
    }

    let message = responses
        .next()
        .await
        .ok_or_else(|| "XDG portal request ended without a response".to_string())?;
    let (response, results): (u32, HashMap<String, OwnedVariant>) = message
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
    zbus::block_on(request_autostart_async(enabled))
}

async fn request_autostart_async(enabled: bool) -> Result<bool, String> {
    let connection = Connection::session()
        .await
        .map_err(|error| portal_error("Unable to connect to the session D-Bus", error))?;
    let handle_token = token("tauridium_background");
    let portal = Proxy::new(
        &connection,
        PORTAL_SERVICE,
        PORTAL_PATH,
        BACKGROUND_INTERFACE,
    )
    .await
    .map_err(|error| portal_error("Unable to create XDG Background portal proxy", error))?;

    let mut options = HashMap::<&str, Variant<'_>>::new();
    options.insert("handle_token", Variant::new(handle_token.as_str()));
    options.insert(
        "reason",
        Variant::new("Start Tauridium automatically when you sign in"),
    );
    options.insert("autostart", Variant::new(enabled));
    // `commandline` is deliberately omitted. The portal specification then uses the
    // installed desktop file's `Exec=tauridium`, avoiding host autostart file access.

    let results = wait_for_request(&connection, &handle_token, || async move {
        portal.call("RequestBackground", &("", options)).await
    })
    .await?;
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
    zbus::block_on(open_uri_async(uri))
}

async fn open_uri_async(uri: &str) -> Result<(), String> {
    let connection = Connection::session()
        .await
        .map_err(|error| portal_error("Unable to connect to the session D-Bus", error))?;
    let handle_token = token("tauridium_open_uri");
    let portal = Proxy::new(&connection, PORTAL_SERVICE, PORTAL_PATH, OPEN_URI_INTERFACE)
        .await
        .map_err(|error| portal_error("Unable to create XDG OpenURI portal proxy", error))?;
    let mut options = HashMap::<&str, Variant<'_>>::new();
    options.insert("handle_token", Variant::new(handle_token.as_str()));
    wait_for_request(&connection, &handle_token, || async move {
        portal.call("OpenURI", &("", uri, options)).await
    })
    .await?;
    Ok(())
}

pub fn add_notification(title: &str, body: Option<&str>) -> Result<(), String> {
    zbus::block_on(add_notification_async(title, body))
}

async fn add_notification_async(title: &str, body: Option<&str>) -> Result<(), String> {
    let connection = Connection::session()
        .await
        .map_err(|error| portal_error("Unable to connect to the session D-Bus", error))?;
    let portal = Proxy::new(
        &connection,
        PORTAL_SERVICE,
        PORTAL_PATH,
        NOTIFICATION_INTERFACE,
    )
    .await
    .map_err(|error| portal_error("Unable to create XDG Notification portal proxy", error))?;

    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    let id = format!(
        "tauridium-{millis}-{}",
        NOTIFICATION_COUNTER.fetch_add(1, Ordering::Relaxed)
    );
    let mut notification = HashMap::<&str, Variant<'_>>::new();
    notification.insert("title", Variant::new(title));
    if let Some(body) = body.filter(|body| !body.is_empty()) {
        notification.insert("body", Variant::new(body));
    }
    let _: () = portal
        .call("AddNotification", &(id.as_str(), notification))
        .await
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
    struct SyntheticPortal;

    #[zbus::interface(name = "org.freedesktop.portal.Background")]
    impl SyntheticPortal {
        async fn exercise(
            &self,
            path: &str,
            code: u32,
            mismatch: bool,
            malformed: bool,
            #[zbus(connection)] connection: &Connection,
        ) -> zbus::fdo::Result<OwnedObjectPath> {
            // Emit before returning the handle, exercising the fast-response race.
            if malformed {
                connection
                    .emit_signal(
                        None::<&str>,
                        path,
                        REQUEST_INTERFACE,
                        "Response",
                        &"invalid",
                    )
                    .await
                    .map_err(|error| zbus::fdo::Error::Failed(error.to_string()))?;
            } else {
                let mut results = HashMap::<String, OwnedVariant>::new();
                results.insert("background".into(), OwnedVariant::from(true));
                connection
                    .emit_signal(
                        None::<&str>,
                        path,
                        REQUEST_INTERFACE,
                        "Response",
                        &(code, results),
                    )
                    .await
                    .map_err(|error| zbus::fdo::Error::Failed(error.to_string()))?;
            }
            OwnedObjectPath::try_from(if mismatch { "/unexpected" } else { path })
                .map_err(|error| zbus::fdo::Error::Failed(error.to_string()))
        }
    }

    struct PrivateBus {
        child: std::process::Child,
        _directory: tempfile::TempDir,
    }

    impl Drop for PrivateBus {
        fn drop(&mut self) {
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
    }

    #[test]
    fn private_bus_preserves_fast_responses_consent_and_validation() {
        use std::io::BufRead;
        let directory = tempfile::tempdir().expect("private test directory");
        let config = directory.path().join("bus.conf");
        std::fs::write(&config, format!(
            "<busconfig><type>session</type><listen>unix:path={}/bus.sock</listen><policy context=\"default\"><allow send_destination=\"*\"/><allow receive_sender=\"*\"/><allow own=\"*\"/></policy></busconfig>",
            directory.path().display()
        )).expect("private bus config");
        let child = std::process::Command::new("dbus-daemon")
            .arg("--nofork")
            .arg("--print-address=1")
            .arg(format!("--config-file={}", config.display()))
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::null())
            .spawn()
            .expect("dbus-daemon is required for portal regression tests");
        let mut bus = PrivateBus {
            child,
            _directory: directory,
        };
        let mut address = String::new();
        std::io::BufReader::new(bus.child.stdout.take().unwrap())
            .read_line(&mut address)
            .expect("private bus address");
        let address = address.trim().to_owned();
        assert!(address.starts_with("unix:path="));
        let (send, receive) = std::sync::mpsc::channel();
        let worker = std::thread::spawn(move || {
            // A caller may already be inside Tauri's Tokio runtime. zbus 6 must
            // drive its independent runtime without a nested Tokio block_on.
            let runtime = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .unwrap();
            runtime.block_on(async {
                let result = zbus::block_on(async {
                    let server = zbus::connection::Builder::address(address.as_str())
                        .name(PORTAL_SERVICE)
                        .serve_at(PORTAL_PATH, SyntheticPortal)
                        .build()
                        .await?;
                    let client = zbus::connection::Builder::address(address.as_str())
                        .build()
                        .await?;
                    let portal =
                        Proxy::new(&client, PORTAL_SERVICE, PORTAL_PATH, BACKGROUND_INTERFACE)
                            .await?;
                    let mut outcomes = Vec::new();
                    for (code, mismatch, malformed) in [
                        (0u32, false, false),
                        (1, false, false),
                        (2, false, false),
                        (9, false, false),
                        (0, true, false),
                        (0, false, true),
                    ] {
                        let handle = token("synthetic");
                        let path = request_path(&client, &handle).unwrap();
                        outcomes.push(
                            wait_for_request(&client, &handle, || async {
                                portal
                                    .call("Exercise", &(path.as_str(), code, mismatch, malformed))
                                    .await
                            })
                            .await,
                        );
                    }
                    drop(server);
                    Ok::<_, zbus::Error>(outcomes)
                });
                send.send(result).unwrap();
            });
        });
        let outcomes = receive.recv_timeout(std::time::Duration::from_secs(30));
        drop(bus); // A timeout closes only our own bus and unblocks its clients.
        let outcomes = outcomes
            .expect("private portal requests must finish within 30 seconds")
            .unwrap();
        worker.join().unwrap();
        assert_eq!(outcomes.len(), 6);
        assert!(bool::try_from(outcomes[0].as_ref().unwrap().get("background").unwrap()).unwrap());
        for (index, message) in [
            (1, "cancelled by the user"),
            (2, "denied or failed"),
            (3, "unknown response code 9"),
            (4, "unexpected request handle"),
            (5, "Unable to decode"),
        ] {
            assert!(outcomes[index].as_ref().unwrap_err().contains(message));
        }
    }
}
