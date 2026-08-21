#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.4.8 frontend type and accessibility fixes."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0408Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")

  def test_native_menu_selection_narrows_optional_service_before_use(self) -> None:
    body = self.app.split('listen<string>("select-service-id"', 1)[1].split('listen("open-settings"', 1)[0]
    self.assertIn('if (service && service.isEnabled !== false) selectService(service);', body)
    self.assertNotIn('service?.isEnabled !== false', body)

  def test_custom_url_template_setter_preserves_field_types_without_unsafe_record_cast(self) -> None:
    body = self.app.split('function saveServiceTemplateField', 1)[1].split('function saveNum', 1)[0]
    self.assertIn('<K extends keyof ServiceCustomUrlTemplate>', body)
    self.assertIn('value: ServiceCustomUrlTemplate[K]', body)
    self.assertIn('serviceTemplateDraft = { ...serviceTemplateDraft, [key]: value };', body)
    self.assertNotIn('as Record<string, unknown>', body)
    self.assertNotIn('as unknown', body)

  def test_managed_service_icon_failure_passes_service_not_service_id(self) -> None:
    managed = self.app.split('aria-label="Configured services"', 1)[1].split('managed-empty', 1)[0]
    self.assertIn('onerror={() => markIconFailed(service)}', managed)
    self.assertNotIn('markIconFailed(service.id)', managed)

  def test_context_menu_is_native_and_keyboard_accessible(self) -> None:
    self.assertIn('import { Menu } from "@tauri-apps/api/menu";', self.app)
    self.assertIn('import { LogicalPosition } from "@tauri-apps/api/dpi";', self.app)
    self.assertIn('event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")', self.app)
    self.assertIn('await menu.popup(new LogicalPosition(x, y));', self.app)


if __name__ == "__main__":
  unittest.main()
