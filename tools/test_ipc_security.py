"""Fail closed when adding native commands or renderer capabilities."""
from rust_sources import read_orchestration_sources
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class IpcSecurityTests(unittest.TestCase):
  def test_all_commands_have_exact_renderer_permissions_with_only_shared_chrome_snapshot(self):
    source = read_orchestration_sources(ROOT)
    # cfg contains brackets too: use the terminating macro invocation instead.
    handler = source.split("tauri::generate_handler![", 1)[1].split("];", 1)[0]
    # Rust module qualification changes ownership, not the IPC command name.
    registered = re.findall(r"^\s*(?:[a-z_][a-z0-9_]*::)*([a-z_][a-z0-9_]*),?\s*$", handler, re.M)
    names = set(registered)
    self.assertEqual(len(names), len(registered), "Duplicate IPC command registration")
    permissions = (ROOT / "src-tauri/permissions/application.toml").read_text(encoding="utf-8")
    arrays = re.findall(r"commands\.allow\s*=\s*(\[[^\]]*\])", permissions)
    main, toast, titlebar, menu = (set(json.loads(value)) for value in arrays)
    self.assertEqual(main | toast | titlebar | menu, names)
    self.assertEqual(main & titlebar, {"get_window_chrome"})
    self.assertFalse(toast & titlebar)
    self.assertEqual(titlebar, {"get_window_chrome", "open_window_menu", "focus_window_content"})
    self.assertEqual(menu, {"get_service_menu", "measure_service_menu", "dismiss_service_menu", "choose_service_menu"})
    self.assertFalse(menu & (main | toast | titlebar))
    self.assertFalse(main & toast)
    self.assertEqual(toast, {"get_download_toast", "dismiss_download_toast", "resize_download_toast", "show_download_in_folder"})
    self.assertIn("ipc_security::command_allowed(", source)
    self.assertIn("invoke.message.webview_ref().label()", source)

  def test_no_capability_grants_a_service_or_whole_parent_window(self):
    for path in (ROOT / "src-tauri/capabilities").glob("*.json"):
      capability = json.loads(path.read_text(encoding="utf-8"))
      self.assertNotIn("windows", capability, str(path))
      self.assertIn(capability["webviews"], [["main"], ["download-toast"], ["window-titlebar"], ["service-menu"]])
      self.assertNotIn("remote", capability)

  def test_popup_scheme_checks_precede_allow(self):
    source = read_orchestration_sources(ROOT)
    popup = source.split("move |url: Url, features: NewWindowFeatures|", 1)[1].split("// TEMPORARY Proton", 1)[0]
    self.assertLess(popup.index("service_navigation_allowed"), popup.index("NewWindowResponse::Allow"))


if __name__ == "__main__":
  unittest.main()
