"""Fail closed when adding native commands or renderer capabilities."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class IpcSecurityTests(unittest.TestCase):
  def test_all_commands_have_one_exact_renderer_permission(self):
    source = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    # cfg contains brackets too: use the terminating macro invocation instead.
    handler = source.split("tauri::generate_handler![", 1)[1].split("];", 1)[0]
    names = set(re.findall(r"^\s*(?:download_toast::)?([a-z_]+),?\s*$", handler, re.M))
    permissions = (ROOT / "src-tauri/permissions/application.toml").read_text(encoding="utf-8")
    arrays = re.findall(r"commands\.allow\s*=\s*(\[[^\]]*\])", permissions)
    main, toast = (set(json.loads(value)) for value in arrays)
    self.assertEqual(main | toast, names)
    self.assertFalse(main & toast)
    self.assertEqual(toast, {"get_download_toast", "dismiss_download_toast", "resize_download_toast"})
    self.assertIn("ipc_security::command_allowed(", source)
    self.assertIn("invoke.message.webview_ref().label()", source)

  def test_no_capability_grants_a_service_or_whole_parent_window(self):
    for path in (ROOT / "src-tauri/capabilities").glob("*.json"):
      capability = json.loads(path.read_text(encoding="utf-8"))
      self.assertNotIn("windows", capability, str(path))
      self.assertIn(capability["webviews"], [["main"], ["download-toast"]])
      self.assertNotIn("remote", capability)

  def test_popup_scheme_checks_precede_allow(self):
    source = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    popup = source.split("move |url: Url, features: NewWindowFeatures|", 1)[1].split("// TEMPORARY Proton", 1)[0]
    self.assertLess(popup.index("service_navigation_allowed"), popup.index("NewWindowResponse::Allow"))


if __name__ == "__main__":
  unittest.main()
