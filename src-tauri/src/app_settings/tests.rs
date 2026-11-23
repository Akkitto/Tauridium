use super::*;

#[test]
fn autostart_application_is_idempotent_when_os_state_already_matches() {
    assert!(!autostart_needs_update(false, false));
    assert!(!autostart_needs_update(true, true));
    assert!(autostart_needs_update(false, true));
    assert!(autostart_needs_update(true, false));
}
