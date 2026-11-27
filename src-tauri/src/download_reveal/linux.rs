//! Desktop integration over a private GIO D-Bus connection, never shell commands.
use super::{Failure, Outcome};
use gio::prelude::*;
use glib::{translate::ToGlibPtr, variant::ToVariant};
use gtk::{gio, glib};
use std::{
    cell::RefCell,
    collections::HashMap,
    future::poll_fn,
    os::unix::fs::OpenOptionsExt,
    path::Path,
    rc::Rc,
    sync::atomic::{AtomicU64, Ordering},
    task::{Poll, Waker},
    time::Duration,
};

const FILE_MANAGER: &str = "org.freedesktop.FileManager1";
const FILE_MANAGER_PATH: &str = "/org/freedesktop/FileManager1";
const PORTAL: &str = "org.freedesktop.portal.Desktop";
const PORTAL_PATH: &str = "/org/freedesktop/portal/desktop";
const OPEN_URI: &str = "org.freedesktop.portal.OpenURI";
const REQUEST: &str = "org.freedesktop.portal.Request";
static NEXT_REQUEST: AtomicU64 = AtomicU64::new(1);

fn unsupported(error: &glib::Error) -> bool {
    // SAFETY: GIO borrows the live GError and returns an owned nullable string.
    let remote: Option<glib::GString> = unsafe {
        glib::translate::from_glib_full(gio::ffi::g_dbus_error_get_remote_error(
            error.to_glib_none().0,
        ))
    };
    matches!(
        remote.as_deref(),
        Some(
            "org.freedesktop.DBus.Error.ServiceUnknown"
                | "org.freedesktop.DBus.Error.NameHasNoOwner"
                | "org.freedesktop.DBus.Error.UnknownMethod"
        )
    )
}

fn file_uri(path: &Path) -> Result<String, Failure> {
    tauri::Url::from_file_path(path)
        .map(|uri| uri.into())
        .map_err(|_| Failure::Unavailable)
}

pub(super) fn show(path: &Path) -> Result<Outcome, Failure> {
    let address = gio::dbus_address_get_for_bus_sync(gio::BusType::Session, gio::Cancellable::NONE)
        .map_err(|_| Failure::Unavailable)?;
    show_at_address(
        path,
        address.as_str(),
        crate::distribution::is_flatpak(),
        Duration::from_secs(30),
    )
}

fn show_at_address(
    path: &Path,
    address: &str,
    portal_only: bool,
    timeout: Duration,
) -> Result<Outcome, Failure> {
    let context = glib::MainContext::new();
    context
        .with_thread_default(|| {
            context.block_on(async {
                let connection = glib::future_with_timeout(
                    Duration::from_secs(5),
                    gio::DBusConnection::for_address_future(
                        address,
                        gio::DBusConnectionFlags::AUTHENTICATION_CLIENT
                            | gio::DBusConnectionFlags::MESSAGE_BUS_CONNECTION,
                        None,
                    ),
                )
                .await
                .map_err(|_| Failure::Unavailable)?
                .map_err(|_| Failure::Unavailable)?;
                let outcome = glib::future_with_timeout(
                    timeout,
                    request(&connection, path, portal_only, timeout),
                )
                .await
                .unwrap_or(Err(Failure::Unavailable));
                // This is our own connection, never GIO's shared desktop connection.
                // Closing it also withdraws any unfinished portal request after timeout.
                let _ =
                    glib::future_with_timeout(Duration::from_secs(1), connection.close_future())
                        .await;
                outcome
            })
        })
        .map_err(|_| Failure::Unavailable)?
}

async fn request(
    connection: &gio::DBusConnection,
    path: &Path,
    portal_only: bool,
    timeout: Duration,
) -> Result<Outcome, Failure> {
    if !portal_only {
        let parameters = (vec![file_uri(path)?], "").to_variant();
        match connection
            .call_future(
                Some(FILE_MANAGER),
                FILE_MANAGER_PATH,
                FILE_MANAGER,
                "ShowItems",
                Some(&parameters),
                Some(glib::VariantTy::UNIT),
                gio::DBusCallFlags::NONE,
                5_000,
            )
            .await
        {
            Ok(_) => return Ok(Outcome::Shown),
            Err(error) if unsupported(&error) => {}
            Err(_) => return Err(Failure::Unavailable),
        }
    }
    portal_request(connection, path, timeout).await
}

#[derive(Default)]
struct Response {
    result: Option<Result<Outcome, Failure>>,
    waker: Option<Waker>,
}

struct Subscription<'a> {
    connection: &'a gio::DBusConnection,
    id: Option<gio::SignalSubscriptionId>,
}
impl Drop for Subscription<'_> {
    fn drop(&mut self) {
        if let Some(id) = self.id.take() {
            self.connection.signal_unsubscribe(id);
        }
    }
}

fn location_descriptor(path: &Path) -> Result<std::fs::File, Failure> {
    // O_PATH obtains only a location descriptor: no contents are read, FIFOs
    // cannot block, and a swapped symlink cannot redirect the operation.
    let file = std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_PATH | libc::O_NOFOLLOW)
        .open(path)
        .map_err(|error| {
            if error.kind() == std::io::ErrorKind::NotFound {
                Failure::Missing
            } else {
                Failure::Unavailable
            }
        })?;
    if !file.metadata().map_err(|_| Failure::Unavailable)?.is_file() {
        return Err(Failure::Missing);
    }
    Ok(file)
}

async fn portal_request(
    connection: &gio::DBusConnection,
    path: &Path,
    timeout: Duration,
) -> Result<Outcome, Failure> {
    let file = location_descriptor(path)?;
    let descriptors = gio::UnixFDList::new();
    let descriptor = descriptors.append(file).map_err(|_| Failure::Unavailable)?;
    let token = format!(
        "tauridium_reveal_{}_{}",
        std::process::id(),
        NEXT_REQUEST.fetch_add(1, Ordering::Relaxed)
    );
    let sender = connection.unique_name().ok_or(Failure::Unavailable)?;
    let expected = format!(
        "/org/freedesktop/portal/desktop/request/{}/{}",
        sender.trim_start_matches(':').replace('.', "_"),
        token
    );
    let response = Rc::new(RefCell::new(Response::default()));
    let state = response.clone();
    // Subscribe before the method call: even an immediate Response is retained.
    let id = connection.signal_subscribe(
        Some(PORTAL),
        Some(REQUEST),
        Some("Response"),
        Some(&expected),
        None,
        gio::DBusSignalFlags::NONE,
        move |_, _, _, _, _, parameters| {
            let result = parameters
                .get::<(u32, HashMap<String, glib::Variant>)>()
                .ok_or(Failure::Unavailable)
                .and_then(|(code, _)| match code {
                    0 => Ok(Outcome::Shown),
                    1 => Ok(Outcome::Cancelled),
                    _ => Err(Failure::Unavailable),
                });
            let waker = {
                let mut state = state.borrow_mut();
                state.result = Some(result);
                state.waker.take()
            };
            if let Some(waker) = waker {
                waker.wake();
            }
        },
    );
    let _subscription = Subscription {
        connection,
        id: Some(id),
    };
    let options = HashMap::from([("handle_token", token.to_variant())]);
    let parameters = ("", glib::variant::Handle(descriptor), options).to_variant();
    // GIO 0.18's call-with-FDs binding treats a nullable *reply* FD list as
    // mandatory. OpenDirectory legitimately returns no FDs; use the message
    // API so a successful normal portal reply cannot panic in that binding.
    let message = gio::DBusMessage::new_method_call(
        Some(PORTAL),
        PORTAL_PATH,
        Some(OPEN_URI),
        "OpenDirectory",
    );
    message.set_body(&parameters);
    message.set_unix_fd_list(Some(&descriptors));
    let reply = connection
        .send_message_with_reply_future(
            &message,
            gio::DBusSendMessageFlags::NONE,
            timeout.as_millis().min(i32::MAX as u128) as i32,
        )
        .await
        .map_err(|_| Failure::Unavailable)?;
    if reply.message_type() != gio::DBusMessageType::MethodReturn {
        return Err(Failure::Unavailable);
    }
    let body = reply.body().ok_or(Failure::Unavailable)?;
    if body.type_().as_str() != "(o)" || body.child_value(0).str() != Some(expected.as_str()) {
        return Err(Failure::Unavailable);
    }
    poll_fn(|context| {
        let mut state = response.borrow_mut();
        match state.result.take() {
            Some(result) => Poll::Ready(result),
            None => {
                state.waker = Some(context.waker().clone());
                Poll::Pending
            }
        }
    })
    .await
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{io::Read, os::fd::AsRawFd};

    #[test]
    fn file_manager_uris_round_trip_without_shell_or_option_interpretation() {
        for name in [
            "file with spaces, % #.txt",
            "-option;$(literal).desktop",
            "Gr\u{fc}\u{df}e.txt",
        ] {
            let path = Path::new("/tmp").join(name);
            let uri = file_uri(&path).unwrap();
            assert!(uri.starts_with("file:///"));
            assert_eq!(
                tauri::Url::parse(&uri).unwrap().to_file_path().unwrap(),
                path
            );
        }
    }

    #[test]
    fn portal_descriptors_cannot_read_contents_or_follow_replaced_links() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("file.txt");
        std::fs::write(&path, "synthetic contents").unwrap();
        let mut descriptor = location_descriptor(&path).unwrap();
        // SAFETY: this is the live descriptor owned by our File; fcntl only queries flags.
        let flags = unsafe { libc::fcntl(descriptor.as_raw_fd(), libc::F_GETFL) };
        assert!(flags >= 0 && flags & libc::O_PATH != 0);
        let mut buffer = [0u8; 1];
        assert_eq!(
            descriptor.read(&mut buffer).unwrap_err().raw_os_error(),
            Some(libc::EBADF)
        );
        let link = root.path().join("link");
        std::os::unix::fs::symlink(&path, &link).unwrap();
        assert!(matches!(location_descriptor(&link), Err(Failure::Missing)));
        assert!(matches!(
            location_descriptor(root.path()),
            Err(Failure::Missing)
        ));
    }
}

#[cfg(test)]
mod desktop_tests;
