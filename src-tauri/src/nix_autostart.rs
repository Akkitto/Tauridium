//! Nix profiles provide the stable launcher; never persist the unwrapped store ELF.
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::unix::fs::OpenOptionsExt;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

const ENTRY: &str = "[Desktop Entry]\nType=Application\nName=Tauridium\nExec=tauridium\nTryExec=tauridium\nIcon=dev.brani.tauridium\nTerminal=false\nX-Tauridium-Nix-Autostart=true\n";
static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);

fn config_dir() -> Result<PathBuf, String> {
    dirs::config_dir().ok_or_else(|| "Unable to resolve the XDG config directory".to_string())
}

pub fn is_enabled() -> Result<bool, String> {
    enabled_at(&config_dir()?)
}

pub fn set_enabled(enabled: bool) -> Result<bool, String> {
    set_enabled_at(&config_dir()?, enabled)
}

fn entry_path(config: &Path) -> PathBuf {
    config.join("autostart/dev.brani.tauridium.desktop")
}

fn enabled_at(config: &Path) -> Result<bool, String> {
    let path = entry_path(config);
    let metadata = match fs::symlink_metadata(&path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
        Err(error) => return Err(format!("Unable to inspect Nix autostart: {error}")),
    };
    if !metadata.is_file() || metadata.file_type().is_symlink() {
        return Err(
            "Nix autostart is managed externally; change its declarative configuration instead"
                .into(),
        );
    }
    let content = fs::read_to_string(&path)
        .map_err(|error| format!("Unable to read Nix autostart: {error}"))?;
    if content != ENTRY {
        return Err(
            "Refusing to overwrite a custom Tauridium autostart entry; manage it manually".into(),
        );
    }
    Ok(true)
}

fn set_enabled_at(config: &Path, enabled: bool) -> Result<bool, String> {
    let current = enabled_at(config)?;
    if current == enabled {
        return Ok(current);
    }
    let path = entry_path(config);
    let directory = config.join("autostart");
    if let Ok(metadata) = fs::symlink_metadata(&directory) {
        if !metadata.is_dir() || metadata.file_type().is_symlink() {
            return Err(
                "Refusing to change a symlinked or externally managed autostart directory".into(),
            );
        }
    }
    if !enabled {
        fs::remove_file(&path)
            .map_err(|error| format!("Unable to disable Nix autostart: {error}"))?;
        return Ok(false);
    }
    if fs::symlink_metadata(directory.join("tauridium.desktop")).is_ok() {
        return Err("Disable or remove the previous native Tauridium autostart entry before enabling Nix autostart".into());
    }
    fs::create_dir_all(&directory)
        .map_err(|error| format!("Unable to create the autostart directory: {error}"))?;
    let temporary = directory.join(format!(
        ".tauridium-{}-{}.tmp",
        std::process::id(),
        NEXT_TEMP.fetch_add(1, Ordering::Relaxed)
    ));
    // create_new rejects symlinks. A hard link publishes the complete synced file
    // atomically and cannot replace an entry installed concurrently by another tool.
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&temporary)
        .map_err(|error| format!("Unable to prepare Nix autostart: {error}"))?;
    let result = file
        .write_all(ENTRY.as_bytes())
        .and_then(|()| file.sync_all())
        .and_then(|()| fs::hard_link(&temporary, &path));
    drop(file);
    let cleanup = fs::remove_file(&temporary);
    result.map_err(|error| format!("Unable to enable Nix autostart: {error}"))?;
    cleanup
        .map_err(|error| format!("Autostart enabled but temporary file cleanup failed: {error}"))?;
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;

    struct Config(PathBuf);
    impl Config {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "tauridium-nix-test-{}-{}",
                std::process::id(),
                NEXT_TEMP.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for Config {
        fn drop(&mut self) {
            fs::remove_dir_all(&self.0).unwrap();
        }
    }

    #[test]
    fn profile_launcher_is_stable_and_idempotent() {
        let config = Config::new();
        assert!(!enabled_at(&config.0).unwrap());
        assert!(set_enabled_at(&config.0, true).unwrap());
        assert!(set_enabled_at(&config.0, true).unwrap());
        assert_eq!(fs::read_to_string(entry_path(&config.0)).unwrap(), ENTRY);
        assert!(!ENTRY.contains("/nix/store"));
        assert_eq!(fs::read_dir(config.0.join("autostart")).unwrap().count(), 1);
        assert!(!set_enabled_at(&config.0, false).unwrap());
        assert!(!set_enabled_at(&config.0, false).unwrap());
    }

    #[test]
    fn custom_entry_is_preserved_on_enable_and_disable() {
        let config = Config::new();
        fs::create_dir(config.0.join("autostart")).unwrap();
        fs::write(entry_path(&config.0), "custom entry").unwrap();
        assert!(set_enabled_at(&config.0, true).is_err());
        assert!(set_enabled_at(&config.0, false).is_err());
        assert_eq!(
            fs::read_to_string(entry_path(&config.0)).unwrap(),
            "custom entry"
        );
    }

    #[test]
    fn declarative_symlink_is_preserved_including_dangling_links() {
        let config = Config::new();
        fs::create_dir(config.0.join("autostart")).unwrap();
        let target = config.0.join("managed.desktop");
        symlink(&target, entry_path(&config.0)).unwrap();
        assert!(set_enabled_at(&config.0, true).is_err());
        assert!(set_enabled_at(&config.0, false).is_err());
        assert!(fs::symlink_metadata(entry_path(&config.0))
            .unwrap()
            .file_type()
            .is_symlink());
        assert!(!target.exists());
    }

    #[test]
    fn legacy_native_entry_is_not_removed_or_duplicated() {
        let config = Config::new();
        fs::create_dir(config.0.join("autostart")).unwrap();
        let legacy = config.0.join("autostart/tauridium.desktop");
        fs::write(&legacy, "legacy entry").unwrap();
        assert!(set_enabled_at(&config.0, true).is_err());
        assert!(!set_enabled_at(&config.0, false).unwrap());
        assert_eq!(fs::read_to_string(legacy).unwrap(), "legacy entry");
    }

    #[test]
    fn symlinked_directory_is_not_mutated() {
        let config = Config::new();
        let target = config.0.join("managed");
        fs::create_dir(&target).unwrap();
        symlink(&target, config.0.join("autostart")).unwrap();
        assert!(set_enabled_at(&config.0, true).is_err());
        assert_eq!(fs::read_dir(target).unwrap().count(), 0);
    }
}
