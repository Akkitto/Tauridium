//! Confine session creation/deletion without renaming existing safe profiles.
use std::fs;
use std::path::{Path, PathBuf};

fn safe_component(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, b'-' | b'_'))
        && !matches!(
            value.to_ascii_uppercase().as_str(),
            "CON"
                | "PRN"
                | "AUX"
                | "NUL"
                | "COM1"
                | "COM2"
                | "COM3"
                | "COM4"
                | "COM5"
                | "COM6"
                | "COM7"
                | "COM8"
                | "COM9"
                | "LPT1"
                | "LPT2"
                | "LPT3"
                | "LPT4"
                | "LPT5"
                | "LPT6"
                | "LPT7"
                | "LPT8"
                | "LPT9"
        )
}

pub(crate) fn validate_service_id(id: &str) -> Result<(), String> {
    // Shared sandboxes already use this reserved hashed namespace. A server
    // cannot impersonate one by supplying the same string as a service ID.
    if !safe_component(id) || id.to_ascii_lowercase().starts_with("sandbox-") {
        return Err("Service id must be a safe, non-reserved ASCII identifier".into());
    }
    Ok(())
}

pub(crate) fn session_path(app_data: &Path, name: &str) -> Result<PathBuf, String> {
    if !safe_component(name) {
        return Err("Session storage name is not a confined path component".into());
    }
    Ok(app_data.join("sessions").join(name))
}

fn real_directory(path: &Path) -> Result<bool, String> {
    match fs::symlink_metadata(path) {
        Ok(metadata) => {
            #[cfg(windows)]
            let reparse_point = {
                use std::os::windows::fs::MetadataExt;
                metadata.file_attributes() & 0x400 != 0
            };
            #[cfg(not(windows))]
            let reparse_point = false;
            if metadata.file_type().is_symlink() || reparse_point || !metadata.is_dir() {
                return Err(
                    "Session storage must be an owned directory, not a link or reparse point"
                        .into(),
                );
            }
            Ok(true)
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(format!("Unable to inspect session storage: {error}")),
    }
}

fn create_private_directory(path: &Path) -> Result<(), String> {
    let builder = fs::DirBuilder::new();
    #[cfg(unix)]
    let builder = {
        use std::os::unix::fs::DirBuilderExt;
        let mut builder = builder;
        builder.mode(0o700);
        builder
    };
    match builder.create(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
            if real_directory(path)? {
                Ok(())
            } else {
                Err("Session storage disappeared during creation".into())
            }
        }
        Err(error) => Err(format!("Unable to create private session storage: {error}")),
    }
}

pub(crate) fn prepare(app_data: &Path, name: &str) -> Result<PathBuf, String> {
    let target = session_path(app_data, name)?;
    let root = app_data.join("sessions");
    if !real_directory(&root)? {
        create_private_directory(&root)?;
    }
    if !real_directory(&target)? {
        create_private_directory(&target)?;
    }
    Ok(target)
}

pub(crate) fn purge(app_data: &Path, name: &str) -> Result<(), String> {
    let target = session_path(app_data, name)?;
    let root = app_data.join("sessions");
    if !real_directory(&root)? || !real_directory(&target)? {
        return Ok(());
    }
    let canonical_root = root
        .canonicalize()
        .map_err(|error| format!("Unable to resolve session root: {error}"))?;
    let canonical_target = target
        .canonicalize()
        .map_err(|error| format!("Unable to resolve session target: {error}"))?;
    if canonical_target.parent() != Some(canonical_root.as_path()) {
        return Err("Refusing to delete outside owned session storage".into());
    }
    // std::fs::remove_dir_all does not traverse directory symlinks; never
    // replace this with a recursive walker which follows engine-created links.
    fs::remove_dir_all(&target).map_err(|error| format!("Unable to clear session storage: {error}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn fixture() -> PathBuf {
        let path = std::env::temp_dir().join(format!(
            "tauridium-storage-security-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir(&path).unwrap();
        path
    }

    #[test]
    fn unsafe_service_ids_and_shared_namespace_are_rejected() {
        for id in [
            "",
            ".",
            "..",
            "/tmp/canary",
            "../canary",
            "a/b",
            "a\\b",
            "C:\\canary",
            "\\\\server\\share",
            "NUL",
            "con",
            "COM1",
            "LPT9",
            "trailing.",
            "trailing ",
            "a:b",
            "sandbox-existing",
            "SANDBOX-existing",
        ] {
            assert!(validate_service_id(id).is_err(), "{id}");
        }
        for id in [
            "service-a",
            "local-001",
            "00112233-4455-6677-8899-aabbccddeeff",
        ] {
            assert!(validate_service_id(id).is_ok());
        }
    }

    #[test]
    fn existing_safe_storage_is_preserved_and_purge_is_confined() {
        let root = fixture();
        let owned = prepare(&root, "service-a").unwrap();
        let outside = root.join("outside-canary");
        fs::create_dir(&outside).unwrap();
        fs::write(owned.join("session-marker"), "existing session").unwrap();
        assert_eq!(prepare(&root, "service-a").unwrap(), owned);
        assert!(owned.join("session-marker").exists());
        assert!(purge(&root, outside.to_str().unwrap()).is_err());
        assert!(purge(&root, "../outside-canary").is_err());
        assert!(outside.is_dir());
        purge(&root, "service-a").unwrap();
        assert!(!owned.exists());
        assert!(outside.is_dir());
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn linked_session_target_and_root_are_never_followed() {
        use std::os::unix::fs::symlink;
        let root = fixture();
        let outside = root.join("outside-canary");
        fs::create_dir(&outside).unwrap();
        fs::create_dir(root.join("sessions")).unwrap();
        symlink(&outside, root.join("sessions/service-a")).unwrap();
        assert!(purge(&root, "service-a").is_err());
        assert!(prepare(&root, "service-a").is_err());
        fs::remove_file(root.join("sessions/service-a")).unwrap();
        fs::remove_dir(root.join("sessions")).unwrap();
        symlink(&outside, root.join("sessions")).unwrap();
        assert!(purge(&root, "service-a").is_err());
        assert!(prepare(&root, "service-a").is_err());
        assert!(outside.is_dir());
        fs::remove_dir_all(root).unwrap();
    }
}
