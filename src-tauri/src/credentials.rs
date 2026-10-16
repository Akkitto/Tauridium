//! OS-vault credentials, token-free session pointers and explicit session-only use.
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;

const VAULT_SERVICE: &str = "dev.brani.tauridium.account-session";

pub(crate) trait Vault {
    fn set(&self, account: &str, secret: &str) -> Result<(), String>;
    fn get(&self, account: &str) -> Result<String, String>;
    fn delete(&self, account: &str) -> Result<(), String>;
}

pub(crate) struct NativeVault;

fn vault_error() -> String {
    "OS credential store unavailable or locked. Unlock Windows Credential Manager, macOS Keychain or a Linux Secret Service, then retry. For a new session you can uncheck ‘Remember using OS credential store’; Tauridium never silently saves a plaintext token.".into()
}

impl Vault for NativeVault {
    fn set(&self, account: &str, secret: &str) -> Result<(), String> {
        native_entry(account)
            .and_then(|entry| entry.set_password(secret))
            .map_err(|_| vault_error())
    }
    fn get(&self, account: &str) -> Result<String, String> {
        native_entry(account)
            .and_then(|entry| entry.get_password())
            .map_err(|_| vault_error())
    }
    fn delete(&self, account: &str) -> Result<(), String> {
        match native_entry(account).and_then(|entry| entry.delete_credential()) {
            Ok(()) | Err(keyring_core::Error::NoEntry) => Ok(()),
            Err(_) => Err(vault_error()),
        }
    }
}

fn native_entry(account: &str) -> keyring_core::Result<keyring_core::Entry> {
    use keyring_core::api::CredentialStoreApi;
    // Construct a fresh store on each attempt. An unavailable Linux Secret Service
    // must not become a permanently cached initialization failure until restart.
    #[cfg(target_os = "linux")]
    let store = zbus_secret_service_keyring_store::Store::new()?;
    #[cfg(windows)]
    let store = windows_native_keyring_store::Store::new()?;
    #[cfg(target_os = "macos")]
    let store = apple_native_keyring_store::keychain::Store::new()?;
    store.build(VAULT_SERVICE, account, None)
}

#[derive(Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Record {
    #[serde(default)]
    mode: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    server: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    credential_account: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    retired_credential_accounts: Vec<String>,
    #[serde(default)]
    allow_insecure_server: bool,
    // Read-only legacy field: every successful save constructs a new token-free record.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    token: Option<String>,
}

#[derive(Serialize, Deserialize)]
struct Secret {
    server: String,
    token: String,
}

pub(crate) enum SavedSession {
    Local {
        warning: Option<String>,
    },
    Server {
        server: String,
        token: String,
        warning: Option<String>,
    },
}

pub(crate) fn validate_server(server: &str, allow_insecure: bool) -> Result<String, String> {
    let url = tauri::Url::parse(server.trim()).map_err(|_| "Invalid server URL")?;
    if url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
        || url.query().is_some()
        || url.fragment().is_some()
    {
        return Err("Server URL must have a host and no credentials, query or fragment".into());
    }
    let loopback = url.host_str().is_some_and(|host| {
        host.eq_ignore_ascii_case("localhost")
            || host
                .trim_matches(['[', ']'])
                .parse::<std::net::IpAddr>()
                .is_ok_and(|address| address.is_loopback())
    });
    if url.scheme() != "https" && !(url.scheme() == "http" && (loopback || allow_insecure)) {
        return Err("HTTPS is required for account authentication. Non-loopback HTTP exposes credentials; explicitly allow it only on a trusted development network.".into());
    }
    Ok(url.as_str().trim_end_matches('/').to_owned())
}

fn read(path: &Path) -> Result<Option<Record>, String> {
    for candidate in [path.to_path_buf(), path.with_extension("bak")] {
        match fs::symlink_metadata(candidate) {
            Ok(metadata)
                if !metadata.is_file()
                    || metadata.file_type().is_symlink()
                    || metadata.len() > 1024 * 1024 =>
            {
                return Err("Saved session must be a bounded regular file".into())
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(_) => return Err("Unable to inspect saved session".into()),
        }
    }
    let text = match crate::read_persistent(path) {
        Ok(text) => text,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(_) => return Err("Unable to read saved session".into()),
    };
    if text.len() > 1024 * 1024 {
        return Err("Saved session is too large".into());
    }
    serde_json::from_str(&text)
        .map(Some)
        .map_err(|_| "Saved session is invalid".into())
}

fn write(path: &Path, record: &Record) -> Result<(), String> {
    let text = serde_json::to_vec(record).map_err(|_| "Unable to encode saved session")?;
    crate::private_file::write(path, &text)
        .map_err(|error| format!("Unable to persist private session: {error}"))
}

fn account_valid(account: &str) -> bool {
    account.len() == 48 && account.bytes().all(|c| c.is_ascii_hexdigit())
}

fn accounts(record: &Record) -> Result<Vec<String>, String> {
    let mut values = record.retired_credential_accounts.clone();
    values.extend(record.credential_account.iter().cloned());
    if values.len() > 32 || values.iter().any(|account| !account_valid(account)) {
        return Err("Saved credential references are invalid".into());
    }
    values.sort();
    values.dedup();
    Ok(values)
}

fn remove_legacy_staging(path: &Path) -> Result<(), String> {
    for candidate in [path.with_extension("bak"), path.with_extension("tmp")] {
        match fs::remove_file(&candidate) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(format!(
                    "Unable to remove obsolete session staging file: {error}"
                ))
            }
        }
    }
    Ok(())
}

// References survive a failed cleanup so logout/startup can retry; there is no
// unreported orphaned credential and no plaintext fallback.
fn cleanup(path: &Path, record: &mut Record, vault: &impl Vault) -> Option<String> {
    record
        .retired_credential_accounts
        .retain(|account| vault.delete(account).is_err());
    let mut warnings = Vec::new();
    if !record.retired_credential_accounts.is_empty() {
        warnings.push("Some obsolete OS credentials could not be removed. Unlock the credential store and sign out to retry.".to_owned());
    }
    if let Err(error) = remove_legacy_staging(path) {
        warnings.push(error);
    }
    if let Err(error) = write(path, record) {
        warnings.push(error);
    }
    (!warnings.is_empty()).then(|| warnings.join(" "))
}

pub(crate) fn save(
    path: &Path,
    server: Option<&str>,
    token: Option<&str>,
    remember: bool,
    allow_insecure_server: bool,
    vault: &impl Vault,
) -> Result<Option<String>, String> {
    let previous = read(path)?.unwrap_or_default();
    if remember && accounts(&previous)?.len() >= 32 {
        return Err("Too many pending credential cleanups; unlock the OS store and sign out before remembering another account".into());
    }
    let mut record = Record {
        mode: if server.is_none() {
            "local"
        } else if remember {
            "server"
        } else {
            "ephemeral"
        }
        .into(),
        server: server.filter(|_| remember).map(str::to_owned),
        retired_credential_accounts: accounts(&previous)?,
        allow_insecure_server,
        ..Record::default()
    };
    if let Some(server) = server.filter(|_| remember) {
        let mut random = [0_u8; 24];
        getrandom::fill(&mut random).map_err(|_| "Unable to generate credential reference")?;
        let account = random
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect::<String>();
        let secret = serde_json::to_string(&Secret {
            server: server.into(),
            token: token.ok_or("Missing authentication token")?.into(),
        })
        .map_err(|_| "Unable to encode credential")?;
        vault.set(&account, &secret)?;
        record.credential_account = Some(account);
    }
    if let Err(error) = write(path, &record) {
        if let Some(account) = &record.credential_account {
            vault.delete(account).map_err(|_| format!("{error}. Also unable to remove newly created OS credential; remove Tauridium's account-session entry in your credential manager."))?;
        }
        return Err(error);
    }
    Ok(cleanup(path, &mut record, vault))
}

pub(crate) fn load(path: &Path, vault: &impl Vault) -> Result<SavedSession, String> {
    let mut record = read(path)?.ok_or("No saved session")?;
    if record.mode == "local" {
        let warning = cleanup(path, &mut record, vault);
        return Ok(SavedSession::Local { warning });
    }
    if record.mode == "ephemeral" {
        return Err("No saved session".into());
    }
    if record.token.is_some() {
        write(path, &record)?;
        for legacy in [path.with_extension("bak"), path.with_extension("tmp")] {
            match fs::symlink_metadata(&legacy) {
                Ok(metadata)
                    if metadata.is_file()
                        && !metadata.file_type().is_symlink()
                        && metadata.len() <= 1024 * 1024 =>
                {
                    let bytes = fs::read(&legacy)
                        .map_err(|_| "Unable to read legacy private session staging")?;
                    crate::private_file::write(&legacy, &bytes)
                        .map_err(|_| "Unable to protect legacy session staging")?;
                }
                Ok(_) => return Err("Legacy session staging is not a bounded regular file".into()),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(_) => return Err("Unable to inspect legacy session staging".into()),
            }
        }
    }
    let server = validate_server(
        record.server.as_deref().ok_or("Invalid saved server")?,
        record.allow_insecure_server,
    )?;
    if let Some(token) = record.token.take() {
        // Protect old bytes before attempting migration. A locked/unavailable vault
        // leaves the old session recoverable, owner-private and visibly blocked.
        record.token = Some(token.clone());
        write(path, &record)?;
        let warning = save(path, Some(&server), Some(&token), true, record.allow_insecure_server, vault)
            .map_err(|error| format!("Saved plaintext session migration could not finish. The original session remains private; unlock the credential store, or sign in again without remembering. {error}"))?;
        return Ok(SavedSession::Server {
            server,
            token,
            warning,
        });
    }
    let account = record
        .credential_account
        .as_deref()
        .filter(|account| account_valid(account))
        .ok_or("Invalid saved credential reference")?;
    let secret = vault.get(account)?;
    let credential: Secret =
        serde_json::from_str(&secret).map_err(|_| "Saved OS credential is invalid")?;
    if credential.server != server || credential.token.is_empty() {
        return Err("Saved OS credential does not match the configured server".into());
    }
    let warning = cleanup(path, &mut record, vault);
    Ok(SavedSession::Server {
        server,
        token: credential.token,
        warning,
    })
}

pub(crate) fn clear(path: &Path, vault: &impl Vault) -> Result<(), String> {
    let previous = read(path)?.unwrap_or_default();
    let mut record = Record {
        mode: "ephemeral".into(),
        retired_credential_accounts: accounts(&previous)?,
        ..Record::default()
    };
    // Disable automatic restore even if the OS vault cannot currently delete entries.
    write(path, &record)?;
    if let Some(warning) = cleanup(path, &mut record, vault) {
        return Err(warning);
    }
    fs::remove_file(path).map_err(|error| format!("Unable to remove saved session: {error}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::{Cell, RefCell};
    use std::collections::HashMap;

    #[derive(Default)]
    struct MemoryVault {
        data: RefCell<HashMap<String, String>>,
        fail: bool,
        fail_delete: Cell<bool>,
    }
    impl Vault for MemoryVault {
        fn set(&self, account: &str, secret: &str) -> Result<(), String> {
            if self.fail {
                return Err("synthetic locked vault".into());
            }
            self.data.borrow_mut().insert(account.into(), secret.into());
            Ok(())
        }
        fn get(&self, account: &str) -> Result<String, String> {
            self.data
                .borrow()
                .get(account)
                .cloned()
                .ok_or("missing synthetic credential".into())
        }
        fn delete(&self, account: &str) -> Result<(), String> {
            if self.fail || self.fail_delete.get() {
                return Err("synthetic locked vault".into());
            }
            self.data.borrow_mut().remove(account);
            Ok(())
        }
    }
    fn path(label: &str) -> std::path::PathBuf {
        let root =
            std::env::temp_dir().join(format!("tauridium-vault-{label}-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        root.join("session.json")
    }
    #[test]
    fn server_transport_requires_https_or_explicit_non_loopback_consent() {
        for server in [
            "http://localhost:8123",
            "http://127.0.0.2",
            "http://[::1]",
            "https://example.test",
        ] {
            assert!(validate_server(server, false).is_ok());
        }
        for server in [
            "http://example.test",
            "https://user:pass@example.test",
            "https://example.test/?token=bad",
            "file:///tmp/test",
            "https://example.test/#fragment",
        ] {
            assert!(validate_server(server, false).is_err());
        }
        assert!(validate_server("http://example.test", true).is_ok());
        assert!(validate_server("ftp://example.test", true).is_err());
    }
    #[test]
    fn remembered_session_has_no_plaintext_token_and_legacy_migrates() {
        let path = path("migration");
        let vault = MemoryVault::default();
        fs::write(&path, r#"{"mode":"server","server":"https://example.test","token":"SYNTHETIC_PRIVATE_TOKEN"}"#).unwrap();
        assert!(matches!(
            load(&path, &vault).unwrap(),
            SavedSession::Server { .. }
        ));
        assert!(!fs::read_to_string(&path)
            .unwrap()
            .contains("SYNTHETIC_PRIVATE_TOKEN"));
        assert_eq!(vault.data.borrow().len(), 1);
        save(
            &path,
            Some("https://example.test"),
            Some("new-token"),
            true,
            false,
            &vault,
        )
        .unwrap();
        assert_eq!(vault.data.borrow().len(), 1);
        clear(&path, &vault).unwrap();
        assert!(vault.data.borrow().is_empty());
        fs::remove_dir_all(path.parent().unwrap()).unwrap();
    }
    #[cfg(windows)]
    #[test]
    fn native_windows_vault_migrates_and_removes_only_its_synthetic_session() {
        let mut nonce = [0_u8; 16];
        getrandom::fill(&mut nonce).unwrap();
        let label: String = nonce.iter().map(|byte| format!("{byte:02x}")).collect();
        let token = format!("synthetic-native-control-{label}");
        let path = path(&label);
        struct Cleanup(std::path::PathBuf);
        impl Drop for Cleanup {
            fn drop(&mut self) {
                // Only this newly generated test session is eligible for cleanup.
                if clear(&self.0, &NativeVault).is_err() {
                    eprintln!("Synthetic Windows credential cleanup needs review");
                }
                let _ = fs::remove_dir(self.0.parent().unwrap());
            }
        }
        let _cleanup = Cleanup(path.clone());
        crate::private_file::write(
            &path,
            &serde_json::to_vec(&serde_json::json!({
                "mode": "server", "server": "https://example.test", "token": token
            }))
            .unwrap(),
        )
        .unwrap();
        let saved = load(&path, &NativeVault).unwrap();
        assert!(matches!(saved, SavedSession::Server { token: restored, .. } if restored == token));
        assert!(!fs::read_to_string(&path).unwrap().contains(&token));
        let account = read(&path).unwrap().unwrap().credential_account.unwrap();
        assert!(native_entry(&account).unwrap().get_password().is_ok());
        clear(&path, &NativeVault).unwrap();
        assert!(matches!(
            native_entry(&account).unwrap().get_password(),
            Err(keyring_core::Error::NoEntry)
        ));
        assert!(!path.exists());
    }

    #[test]
    fn unavailable_vault_never_silently_falls_back_to_plaintext() {
        let path = path("locked");
        let vault = MemoryVault {
            fail: true,
            ..MemoryVault::default()
        };
        assert!(save(
            &path,
            Some("https://example.test"),
            Some("SYNTHETIC_TOKEN"),
            true,
            false,
            &vault
        )
        .is_err());
        assert!(!path.exists());
        save(
            &path,
            Some("https://example.test"),
            Some("SYNTHETIC_TOKEN"),
            false,
            false,
            &vault,
        )
        .unwrap();
        assert!(!fs::read_to_string(&path)
            .unwrap()
            .contains("SYNTHETIC_TOKEN"));
        assert!(load(&path, &vault).is_err());
        fs::remove_dir_all(path.parent().unwrap()).unwrap();
    }

    #[test]
    fn failed_vault_cleanup_disables_restore_and_preserves_retry_references() {
        let path = path("cleanup");
        let vault = MemoryVault::default();
        save(
            &path,
            Some("https://example.test"),
            Some("SYNTHETIC_TOKEN"),
            true,
            false,
            &vault,
        )
        .unwrap();
        vault.fail_delete.set(true);
        assert!(clear(&path, &vault).is_err());
        assert_eq!(read(&path).unwrap().unwrap().mode, "ephemeral");
        assert!(load(&path, &vault).is_err());
        assert_eq!(accounts(&read(&path).unwrap().unwrap()).unwrap().len(), 1);
        vault.fail_delete.set(false);
        clear(&path, &vault).unwrap();
        assert!(!path.exists());
        assert!(vault.data.borrow().is_empty());
        fs::remove_dir_all(path.parent().unwrap()).unwrap();
    }

    #[test]
    fn failed_session_write_removes_new_vault_credential() {
        struct BlockingDestination {
            path: std::path::PathBuf,
            inner: MemoryVault,
        }
        impl Vault for BlockingDestination {
            fn set(&self, account: &str, secret: &str) -> Result<(), String> {
                self.inner.set(account, secret)?;
                fs::create_dir(&self.path).unwrap();
                Ok(())
            }
            fn get(&self, account: &str) -> Result<String, String> {
                self.inner.get(account)
            }
            fn delete(&self, account: &str) -> Result<(), String> {
                self.inner.delete(account)
            }
        }
        let path = path("rollback");
        let vault = BlockingDestination {
            path: path.clone(),
            inner: MemoryVault::default(),
        };
        assert!(save(
            &path,
            Some("https://example.test"),
            Some("SYNTHETIC_TOKEN"),
            true,
            false,
            &vault
        )
        .is_err());
        assert!(vault.inner.data.borrow().is_empty());
        assert_eq!(fs::read_dir(path.parent().unwrap()).unwrap().count(), 1);
        fs::remove_dir_all(path.parent().unwrap()).unwrap();
    }
}
