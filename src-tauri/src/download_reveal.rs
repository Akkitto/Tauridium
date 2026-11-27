//! Reveal a completed download, without opening its contents or accepting UI paths.
use serde::Serialize;
use std::path::Path;

#[cfg(target_os = "linux")]
mod linux;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub(crate) enum Outcome {
    Shown,
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
mod windows {
    use super::{Failure, Outcome};
    use std::{os::windows::ffi::OsStrExt, path::Path, ptr};
    use windows_sys::Win32::{
        Foundation::RPC_E_CHANGED_MODE,
        System::Com::{
            CoInitializeEx, CoTaskMemFree, CoUninitialize, COINIT_APARTMENTTHREADED,
            COINIT_DISABLE_OLE1DDE,
        },
        UI::Shell::{
            Common::ITEMIDLIST, ILFindLastID, SHOpenFolderAndSelectItems, SHParseDisplayName,
        },
    };

    struct Apartment(bool);
    impl Apartment {
        fn new() -> Result<Self, Failure> {
            // SAFETY: this worker's COM initialization is balanced by Drop.
            let result = unsafe {
                CoInitializeEx(
                    ptr::null(),
                    (COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE) as u32,
                )
            };
            // A pre-existing MTA is usable, but belongs to its original initializer.
            if result < 0 && result != RPC_E_CHANGED_MODE {
                return Err(Failure::Unavailable);
            }
            Ok(Self(result >= 0))
        }
    }
    impl Drop for Apartment {
        fn drop(&mut self) {
            if self.0 {
                // SAFETY: balances this worker's successful COM initialization.
                unsafe { CoUninitialize() };
            }
        }
    }

    struct Item(*mut ITEMIDLIST);
    impl Item {
        fn parse(path: &Path) -> Result<Self, Failure> {
            let mut wide: Vec<u16> = path.as_os_str().encode_wide().collect();
            if wide.contains(&0) {
                return Err(Failure::Unavailable);
            }
            wide.push(0);
            let mut item = Self(ptr::null_mut());
            // SAFETY: NUL-terminated native path and writable PIDL out-parameter.
            let result = unsafe {
                SHParseDisplayName(
                    wide.as_ptr(),
                    ptr::null_mut(),
                    &mut item.0,
                    0,
                    ptr::null_mut(),
                )
            };
            if result != 0 || item.0.is_null() {
                Err(Failure::Unavailable)
            } else {
                Ok(item)
            }
        }
    }
    impl Drop for Item {
        fn drop(&mut self) {
            // SAFETY: SHParseDisplayName allocated this PIDL with the COM allocator.
            unsafe { CoTaskMemFree(self.0.cast()) };
        }
    }

    pub(super) fn show(path: &Path) -> Result<Outcome, Failure> {
        let _apartment = Apartment::new()?;
        let folder = Item::parse(path.parent().ok_or(Failure::Unavailable)?)?;
        let item = Item::parse(path)?;
        // SAFETY: the absolute file PIDL stays alive through the selection call.
        // Its last ID is a relative child ID, borrowed rather than separately freed.
        let child = unsafe { ILFindLastID(item.0) };
        if child.is_null() {
            return Err(Failure::Unavailable);
        }
        let children = [child.cast_const()];
        // Use an explicit parent and one child, rather than cidl=0's convenience
        // path: Windows x64 can open that folder without retaining the selection.
        // SAFETY: live absolute parent PIDL and a live one-element child array.
        // Flags=0 avoids editing/renaming or activating the downloaded file.
        let result = unsafe { SHOpenFolderAndSelectItems(folder.0, 1, children.as_ptr(), 0) };
        if result == 0 {
            Ok(Outcome::Shown)
        } else {
            Err(Failure::Unavailable)
        }
    }

    #[cfg(test)]
    mod tests {
        use super::*;
        use windows_sys::Win32::UI::Shell::{ILGetSize, ILIsParent};

        #[test]
        fn selection_uses_the_actual_parent_and_a_relative_child_id() {
            let _apartment = Apartment::new().unwrap();
            let directory = tempfile::tempdir().unwrap();
            let parent = Item::parse(directory.path()).unwrap();
            for name in [
                "file with spaces, % #.txt",
                "-literal;[name].txt",
                "Gr\u{fc}\u{df}e.txt",
            ] {
                let path = directory.path().join(name);
                std::fs::write(&path, "synthetic metadata fixture").unwrap();
                let item = Item::parse(&path).unwrap();
                // SAFETY: all arguments are live Shell-allocated PIDLs; queries only.
                unsafe {
                    assert_ne!(ILIsParent(parent.0, item.0, 1), 0);
                    let child = ILFindLastID(item.0);
                    assert!(!child.is_null());
                    assert!(ILGetSize(child) > 2);
                    assert!(ILGetSize(child) < ILGetSize(item.0));
                }
            }
        }
    }
}

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
