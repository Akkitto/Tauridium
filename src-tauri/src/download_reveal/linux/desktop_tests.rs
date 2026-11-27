//! Actual private-bus exchanges: no logged-in desktop or personal files involved.
use super::*;
use std::{
    io::{BufRead, Read},
    os::{fd::AsRawFd, unix::fs::MetadataExt},
    process::{Child, Command, Stdio},
    sync::{atomic::AtomicU32, Arc, Mutex},
};
use zbus::{Connection, OwnedFd, OwnedObjectPath, OwnedVariant};

#[derive(Default)]
struct Observed {
    items: Vec<(Vec<String>, String)>,
    files: Vec<(u64, u64)>,
}
struct Desktop {
    observed: Arc<Mutex<Observed>>,
    mode: Arc<AtomicU32>,
}
#[zbus::interface(name = "org.freedesktop.FileManager1")]
impl Desktop {
    fn show_items(&self, uris: Vec<String>, startup_id: String) -> zbus::fdo::Result<()> {
        self.observed.lock().unwrap().items.push((uris, startup_id));
        match self.mode.load(Ordering::Relaxed) {
            10 => Err(zbus::fdo::Error::UnknownMethod("unsupported".into())),
            11 => Err(zbus::fdo::Error::AccessDenied(
                "PRIVATE_ERROR_CANARY".into(),
            )),
            _ => Ok(()),
        }
    }
}
struct Portal {
    observed: Arc<Mutex<Observed>>,
    mode: Arc<AtomicU32>,
}
#[zbus::interface(name = "org.freedesktop.portal.OpenURI")]
impl Portal {
    async fn open_directory(
        &self,
        parent_window: String,
        descriptor: OwnedFd,
        options: HashMap<String, OwnedVariant>,
        #[zbus(header)] header: zbus::message::Header<'_>,
        #[zbus(connection)] connection: &Connection,
    ) -> zbus::fdo::Result<OwnedObjectPath> {
        assert!(parent_window.is_empty());
        assert_eq!(options.len(), 1); // No renderer path/URI or unnecessary options.
        let descriptor: std::os::fd::OwnedFd = descriptor.into();
        let mut file = std::fs::File::from(descriptor);
        // SAFETY: queries the live fixture-owned FD, never follows a pathname.
        let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
        assert!(flags >= 0 && flags & libc::O_PATH != 0);
        assert_eq!(
            file.read(&mut [0]).unwrap_err().raw_os_error(),
            Some(libc::EBADF)
        );
        let metadata = file.metadata().unwrap();
        assert!(metadata.is_file());
        self.observed
            .lock()
            .unwrap()
            .files
            .push((metadata.dev(), metadata.ino()));
        let token = <&str>::try_from(options.get("handle_token").unwrap()).unwrap();
        let sender = header
            .sender()
            .unwrap()
            .as_str()
            .trim_start_matches(':')
            .replace('.', "_");
        let path = format!("/org/freedesktop/portal/desktop/request/{sender}/{token}");
        let mode = self.mode.load(Ordering::Relaxed);
        if mode != 5 {
            // Deliberately emit before returning to catch response-subscription races.
            if mode == 4 {
                connection
                    .emit_signal(
                        None::<&str>,
                        path.as_str(),
                        REQUEST,
                        "Response",
                        &"malformed",
                    )
                    .await
                    .unwrap();
            } else {
                connection
                    .emit_signal(
                        None::<&str>,
                        path.as_str(),
                        REQUEST,
                        "Response",
                        &(
                            if mode <= 2 {
                                mode
                            } else if mode == 9 {
                                9
                            } else {
                                0
                            },
                            HashMap::<String, OwnedVariant>::new(),
                        ),
                    )
                    .await
                    .unwrap();
            }
        }
        Ok(OwnedObjectPath::try_from(if mode == 3 {
            "/unexpected"
        } else {
            path.as_str()
        })
        .unwrap())
    }
}

struct Bus {
    child: Child,
    _directory: tempfile::TempDir,
}
impl Drop for Bus {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

#[test]
fn native_selection_portal_fallback_fast_response_and_consent_are_preserved() {
    let directory = tempfile::tempdir().unwrap();
    let config = directory.path().join("bus.conf");
    std::fs::write(&config, format!(
        "<busconfig><type>session</type><listen>unix:path={}/bus.sock</listen><policy context=\"default\"><allow send_destination=\"*\"/><allow receive_sender=\"*\"/><allow own=\"*\"/></policy></busconfig>",
        directory.path().display())).unwrap();
    let child = Command::new("dbus-daemon")
        .args(["--nofork", "--print-address=1"])
        .arg(format!("--config-file={}", config.display()))
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .expect("dbus-daemon is required for reveal regression tests");
    let mut bus = Bus {
        child,
        _directory: directory,
    };
    let mut address = String::new();
    std::io::BufReader::new(bus.child.stdout.take().unwrap())
        .read_line(&mut address)
        .unwrap();
    let address = address.trim();
    let root = tempfile::tempdir().unwrap();
    let path = root.path().join("file with spaces, % # \u{fc}.txt");
    std::fs::write(&path, "synthetic contents, never opened").unwrap();
    let metadata = path.metadata().unwrap();
    let identity = (metadata.dev(), metadata.ino());
    let observed = Arc::new(Mutex::new(Observed::default()));
    let mode = Arc::new(AtomicU32::new(0));
    let server = zbus::block_on(async {
        zbus::connection::Builder::address(address)
            .name(FILE_MANAGER)
            .name(PORTAL)
            .serve_at(
                FILE_MANAGER_PATH,
                Desktop {
                    observed: observed.clone(),
                    mode: mode.clone(),
                },
            )
            .serve_at(
                PORTAL_PATH,
                Portal {
                    observed: observed.clone(),
                    mode: mode.clone(),
                },
            )
            .build()
            .await
    })
    .unwrap();
    let timeout = Duration::from_secs(3);
    assert_eq!(
        show_at_address(&path, address, false, timeout),
        Ok(Outcome::Shown)
    );
    {
        let seen = observed.lock().unwrap();
        assert_eq!(
            seen.items,
            vec![(vec![file_uri(&path).unwrap()], String::new())]
        );
        assert!(seen.files.is_empty());
    }
    for (code, expected) in [
        (0, Ok(Outcome::Shown)),
        (1, Ok(Outcome::Cancelled)),
        (2, Err(Failure::Unavailable)),
        (3, Err(Failure::Unavailable)),
        (4, Err(Failure::Unavailable)),
        (5, Err(Failure::Unavailable)),
        (9, Err(Failure::Unavailable)),
    ] {
        mode.store(code, Ordering::Relaxed);
        assert_eq!(
            show_at_address(&path, address, true, Duration::from_millis(500)),
            expected,
            "portal response {code}"
        );
    }
    {
        let seen = observed.lock().unwrap();
        assert_eq!(
            seen.items.len(),
            1,
            "sandboxed mode must never call FileManager1"
        );
        assert_eq!(seen.files, vec![identity; 7]);
    }
    mode.store(11, Ordering::Relaxed);
    assert_eq!(
        show_at_address(&path, address, false, timeout),
        Err(Failure::Unavailable)
    );
    assert_eq!(
        observed.lock().unwrap().files.len(),
        7,
        "access denial must not fall back"
    );
    mode.store(10, Ordering::Relaxed);
    assert_eq!(
        show_at_address(&path, address, false, timeout),
        Ok(Outcome::Shown)
    );
    assert_eq!(
        observed.lock().unwrap().files.len(),
        8,
        "unsupported interface must use portal"
    );
    // A desktop with no FileManager1 also falls back to the portal.
    zbus::block_on(server.release_name(FILE_MANAGER)).unwrap();
    assert_eq!(
        show_at_address(&path, address, false, timeout),
        Ok(Outcome::Shown)
    );
    assert_eq!(observed.lock().unwrap().files.len(), 9);
    drop(server);
    drop(bus);
}
