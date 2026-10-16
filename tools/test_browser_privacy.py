"""Preserve sign-in compatibility without blanket tracking/reputation exceptions."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BrowserPrivacyTests(unittest.TestCase):
  def test_remote_services_keep_smartscreen_and_tracking_is_opt_in(self):
    source = (ROOT / "vendor/wry/src/webview2/mod.rs").read_text(encoding="utf-8")
    self.assertIn("options.set_enable_tracking_prevention(!(is_remote_http && relax_tracking));", source)
    defaults = source.split("let default_args = if is_remote_http", 1)[1].split("let mut arguments", 1)[0]
    self.assertNotIn("msSmartScreenProtection", defaults.split("} else {", 1)[0])
    self.assertIn('provided_args = pl_attrs.additional_browser_args.filter(|_| !relax_tracking)', source)
    self.assertIn('attributes.proxy_config', source)
    self.assertIn('attributes.autoplay', source)

  def test_native_environment_policy_is_a_startup_snapshot_and_ui_requires_explicit_consent(self):
    main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    self.assertEqual(main.count('*state.tracking_prevention_startup.lock().unwrap() ='), 1)
    self.assertIn('&state.tracking_prevention_startup.lock().unwrap()', main)
    app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
    setter = app.split("async function saveTrackingException", 1)[1].split("function workspaceIcon", 1)[0]
    self.assertIn('enabled && !(await confirmAsk', setter)
    self.assertIn('ownValue(persisted.trackingPreventionExceptions, namespace)', setter)
    self.assertIn('showToast("Saved — restart', setter)
    self.assertIn('event.preventDefault(); void saveTrackingException', app)
    self.assertIn('every service in this shared sandbox', app)
