use serde::Serialize;

#[cfg(not(any(feature = "native-distribution", feature = "flatpak")))]
compile_error!(
    "Tauridium requires exactly one distribution feature: native-distribution or flatpak"
);

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum DistributionMode {
    Native,
    Flatpak,
}

impl DistributionMode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Native => "native",
            Self::Flatpak => "flatpak",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DistributionInfo {
    pub mode: DistributionMode,
    pub updater_managed_externally: bool,
    pub portal_file_access: bool,
    pub portal_notifications: bool,
    pub portal_autostart: bool,
    pub downloads_require_destination: bool,
    pub automatic_backups_use_private_storage: bool,
}

/// Compile-time packaging selection is authoritative. Flatpak takes precedence when
/// diagnostic `--all-features` builds enable both feature sets; release Flatpak builds
/// use `--no-default-features --features flatpak`. Runtime sandbox detection is not
/// allowed to change capabilities compiled into the executable.
pub const fn mode() -> DistributionMode {
    if cfg!(feature = "flatpak") {
        DistributionMode::Flatpak
    } else {
        DistributionMode::Native
    }
}

pub fn is_flatpak() -> bool {
    mode() == DistributionMode::Flatpak
}

pub fn info() -> DistributionInfo {
    let flatpak = is_flatpak();
    DistributionInfo {
        mode: if flatpak {
            DistributionMode::Flatpak
        } else {
            DistributionMode::Native
        },
        updater_managed_externally: flatpak,
        // Flatpak packaging enables the Linux XDG portal dialog backend. These flags
        // describe distribution policy, not portal availability on native packages.
        portal_file_access: flatpak,
        portal_notifications: flatpak,
        portal_autostart: flatpak,
        downloads_require_destination: flatpak,
        automatic_backups_use_private_storage: flatpak,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn distribution_info_is_internally_consistent() {
        let info = info();
        let flatpak = info.mode == DistributionMode::Flatpak;
        assert_eq!(info.updater_managed_externally, flatpak);
        assert_eq!(info.portal_notifications, flatpak);
        assert_eq!(info.portal_autostart, flatpak);
        assert_eq!(info.downloads_require_destination, flatpak);
        assert_eq!(info.automatic_backups_use_private_storage, flatpak);
    }
}
