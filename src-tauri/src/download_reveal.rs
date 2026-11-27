//! Reveal a completed download, without opening its contents or accepting UI paths.
use serde::Serialize;
use std::path::Path;

#[cfg(target_os = "linux")]
mod linux;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) enum Outcome {
    Shown,
    #[cfg(windows)]
    FolderOpened,
    #[cfg(target_os = "linux")]
    Cancelled,
}

/// Stable, path-free IPC failures. Never serialize OS or desktop-service errors.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub(crate) enum Failure {
    Stale,
    Missing,
    Unavailable,
}

fn validate(path: &Path) -> Result<(), Failure> {
    if !path.is_absolute() || path.file_name().is_none() {
        return Err(Failure::Unavailable);
    }
    #[cfg(windows)]
    {
        use std::path::{Component, Prefix};
        if !matches!(path.components().next(),
            Some(Component::Prefix(prefix)) if matches!(prefix.kind(),
                Prefix::Disk(_) | Prefix::UNC(_, _) | Prefix::VerbatimDisk(_) | Prefix::VerbatimUNC(_, _)))
        {
            return Err(Failure::Unavailable);
        }
    }
    match std::fs::symlink_metadata(path) {
        Ok(metadata) if metadata.file_type().is_file() => Ok(()),
        Ok(_) => Err(Failure::Missing),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Err(Failure::Missing),
        Err(_) => Err(Failure::Unavailable),
    }
}

/// Run on a blocking worker, never on the application's native UI thread.
pub(crate) fn show(path: &Path) -> Result<Outcome, Failure> {
    validate(path)?;
    #[cfg(windows)]
    {
        windows::show(path)
    }
    #[cfg(target_os = "linux")]
    {
        linux::show(path)
    }
    #[cfg(target_os = "macos")]
    {
        // Absolute native paths are separate arguments, never shell text or URIs.
        // -R reveals in Finder instead of opening/executing the downloaded file.
        std::process::Command::new("/usr/bin/open")
            .arg("-R")
            .arg(path)
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .map_err(|_| Failure::Unavailable)?
            .success()
            .then_some(Outcome::Shown)
            .ok_or(Failure::Unavailable)
    }
    #[cfg(not(any(windows, target_os = "linux", target_os = "macos")))]
    {
        Err(Failure::Unavailable)
    }
}

#[cfg(windows)]
mod windows;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reveal_requires_an_absolute_existing_regular_file() {
        assert_eq!(
            validate(Path::new("relative.txt")),
            Err(Failure::Unavailable)
        );
        let root = tempfile::tempdir().unwrap();
        assert_eq!(validate(root.path()), Err(Failure::Missing));
        let file = root.path().join("file, # percent %.txt");
        assert_eq!(validate(&file), Err(Failure::Missing));
        std::fs::write(&file, "synthetic data").unwrap();
        assert_eq!(validate(&file), Ok(()));
        std::fs::remove_file(&file).unwrap();
        assert_eq!(validate(&file), Err(Failure::Missing));
    }

    #[cfg(unix)]
    #[test]
    fn replaced_symlinks_are_not_followed() {
        let root = tempfile::tempdir().unwrap();
        let target = root.path().join("target");
        std::fs::write(&target, "synthetic data").unwrap();
        let link = root.path().join("link");
        std::os::unix::fs::symlink(&target, &link).unwrap();
        assert_eq!(validate(&link), Err(Failure::Missing));
        assert_eq!(std::fs::read(&target).unwrap(), b"synthetic data");
    }

    #[test]
    fn reveal_errors_are_path_free_and_the_command_is_overlay_only() {
        for (value, expected) in [
            (Failure::Stale, "\"stale\""),
            (Failure::Missing, "\"missing\""),
            (Failure::Unavailable, "\"unavailable\""),
        ] {
            assert_eq!(serde_json::to_string(&value).unwrap(), expected);
        }
        assert!(crate::ipc_security::command_allowed(
            "download-toast",
            "show_download_in_folder"
        ));
        for label in [
            "main",
            "service-menu",
            "window-titlebar",
            "svc-mail",
            "download-toast-child",
            "",
        ] {
            assert!(!crate::ipc_security::command_allowed(
                label,
                "show_download_in_folder"
            ));
        }
    }
}
