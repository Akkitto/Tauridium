#!/usr/bin/env python3
"""Regression coverage for captured service identity after menu dismissal."""

from frontend_source import read_frontend_source
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
APP = read_frontend_source(ROOT)

class Patch0614Tests(unittest.TestCase):
  def test_pretty_context_actions_capture_service_before_dispatch(self):
    helper = APP.split("function dispatchServiceMenuAction", 1)[1].split("async function popupNativeServiceContextMenu", 1)[0]
    self.assertIn("serviceMenu.takeAction(id, serviceId)", helper)
    self.assertIn("const service = services.find((item) => item.id === serviceId)", helper)
    self.assertIn("if (!service) return", helper)
    for action in ("duplicateServiceFromUi", "reloadServiceFromUi", "toggleServiceEnabled"):
      self.assertIn(f"void {action}(service)", helper)
      self.assertLess(helper.index("const service ="), helper.index(f"void {action}(service)"))

  def test_pretty_context_actions_do_not_read_cleared_reactive_menu_state(self):
    self.assertNotIn("serviceContextMenu", APP)
    native = (ROOT / "src-tauri/src/service_menu.rs").read_text(encoding="utf-8")
    choice = native.split("async fn choose_service_menu", 1)[1].split("#[cfg(test)]", 1)[0]
    self.assertIn("claim(id, action)", choice)
    self.assertIn("session.request.service_id", choice)
    self.assertLess(choice.index("claim(id, action)"), choice.index("hide_idle(&app)"))

if __name__ == "__main__":
  unittest.main()
