/*
 * TEMPORARY Proton Mail/Calendar compatibility workaround.
 *
 * Proton's shared web client currently treats the generic Tauri runtime marker
 * (`window.isTauri === true`) as proof that it is running inside Proton's own
 * native desktop shell. Tauridium is itself a Tauri application, so ordinary
 * hosted Mail/Calendar pages are otherwise misclassified as native Proton
 * clients and can select native client identities during authentication.
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
    matches!(initial_host, "mail.proton.me" | "calendar.proton.me")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn workaround_targets_only_proton_mail_and_calendar_entry_hosts() {
        assert!(requires_tauri_marker_workaround("mail.proton.me"));
        assert!(requires_tauri_marker_workaround("calendar.proton.me"));

        // Proton Pass currently uses a separate native identity/authentication
        // path and must retain Tauridium's ordinary Tauri environment marker.
        assert!(!requires_tauri_marker_workaround("pass.proton.me"));

        // Account is reached as a navigation within an already-classified
        // Mail/Calendar service webview. The initialization script remains
        // attached across navigations, so it does not need a global host rule.
        assert!(!requires_tauri_marker_workaround("account.proton.me"));
        assert!(!requires_tauri_marker_workaround("proton.me"));
        assert!(!requires_tauri_marker_workaround("example.com"));
    }

    #[test]
    fn workaround_deletes_instead_of_spoofing_the_tauri_marker() {
        assert!(TAURI_MARKER_WORKAROUND_JS.contains("delete window.isTauri"));
        assert!(!TAURI_MARKER_WORKAROUND_JS.contains("window.isTauri = false"));
    }
}
