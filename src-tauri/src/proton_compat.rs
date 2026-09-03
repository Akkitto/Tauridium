/*
 * TEMPORARY Proton web-client compatibility workaround.
 *
 * Proton's shared web client currently treats the generic Tauri runtime marker
 * (`window.isTauri === true`) as proof that it is running inside Proton's own
 * native desktop shell. Tauridium is itself a Tauri application, so ordinary
 * hosted Proton pages with native platform client identities are otherwise
 * misclassified as native Proton clients and can select native client identities
 * during authentication.
 *
 * Keep this module intentionally small and service-specific. Remove it together
 * with the vendor/tauri marker-descriptor patch once Proton fixes its upstream
 * environment detection.
 */

pub(crate) const TAURI_MARKER_WORKAROUND_JS: &str = r#"(function(){
  try {
    // The vendored Tauri 2.11.3 patch makes this marker configurable while
    // preserving its normal value everywhere else. Deleting it makes this
    // hosted page look like the ordinary browser environment Proton expects.
    if (window.isTauri === true) {
      delete window.isTauri;
    }
  } catch (_) {}
})();"#;

pub(crate) fn requires_tauri_marker_workaround(initial_host: &str) -> bool {
    matches!(
        initial_host,
        "account.proton.me"
            | "mail.proton.me"
            | "calendar.proton.me"
            | "pass.proton.me"
            | "authenticator.proton.me"
            | "meet.proton.me"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn workaround_targets_proton_web_clients_with_native_platform_identities() {
        for host in [
            "account.proton.me",
            "mail.proton.me",
            "calendar.proton.me",
            "pass.proton.me",
            "authenticator.proton.me",
            "meet.proton.me",
        ] {
            assert!(requires_tauri_marker_workaround(host), "{host}");
        }

        for host in [
            "drive.proton.me",
            "wallet.proton.me",
            "docs.proton.me",
            "sheets.proton.me",
            "lumo.proton.me",
            "contacts.proton.me",
            "proton.me",
            "example.com",
        ] {
            assert!(!requires_tauri_marker_workaround(host), "{host}");
        }
    }

    #[test]
    fn workaround_deletes_instead_of_spoofing_the_tauri_marker() {
        assert!(TAURI_MARKER_WORKAROUND_JS.contains("delete window.isTauri"));
        assert!(!TAURI_MARKER_WORKAROUND_JS.contains("window.isTauri = false"));
    }
}
