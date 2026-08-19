#!/usr/bin/env python3
"""Static release regressions for Tauridium 0.4.0 feature work."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Feature0400Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
    cls.api = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
    cls.main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    cls.backup = (ROOT / "src-tauri/src/backup.rs").read_text(encoding="utf-8")

  def test_oled_and_custom_appearance_are_persisted(self) -> None:
    for marker in (
      'appSettings.theme === "oled"',
      ':global(body.oled)',
      'customAccentColors: []',
      'customSidebarWidths: []',
      'Black OLED',
      'Save current preset',
    ):
      self.assertIn(marker, self.app)
    for marker in ('"customAccentColors": []', '"customSidebarWidths": []', '"system" | "dark" | "oled" | "light"'):
      self.assertIn(marker, self.main)

  def test_service_management_scales_and_preserves_global_slots(self) -> None:
    for marker in (
      'const MANAGED_SERVICE_PAGE_SIZE = 100;',
      'managedWorkspaceFilter',
      'managedServiceQuery',
      'paged(managedServices, managedServicePage, MANAGED_SERVICE_PAGE_SIZE)',
      'reorderVisibleSubset(previousIds, visibleIds',
    ):
      self.assertIn(marker, self.app)

  def test_keybindings_include_requested_defaults_and_chords(self) -> None:
    for marker in (
      'quickWorkspaceSwitch: "Ctrl+D"',
      'quickServiceSwitch: "Ctrl+S"',
      'bindingStrokes(binding)',
      'recordingStrokes',
      'shortcutPending',
      'Quick workspace switcher',
      'Quick service search',
    ):
      self.assertIn(marker, self.app + (ROOT / "src/lib/ui.ts").read_text(encoding="utf-8"))
    self.assertIn('binding.split_whitespace().count() > 2', self.main)
    self.assertIn('app.emit("shortcut-action", action.to_string())', self.main)

  def test_shared_sandboxes_are_backend_authoritative(self) -> None:
    for marker in (
      '"sandboxes": []',
      '"serviceSandboxes": {}',
      'fn sandbox_for_service',
      'fn sandbox_storage_name',
      'fn storage_directory',
      'fn clear_sandbox',
      'sandbox_for_service(&state.settings.lock().unwrap(), &service_id)',
    ):
      self.assertIn(marker, self.main)
    self.assertNotIn('sandbox_id: Option<String>', self.main)
    self.assertIn('invoke("clear_sandbox", { sandboxId })', self.api)

  def test_all_new_settings_flow_through_integrity_protected_backup(self) -> None:
    self.assertIn('app_settings: &self.app_settings', self.backup)
    self.assertIn('app_settings: Value', self.backup)
    self.assertIn('self.validate_integrity()', self.backup)
    self.assertIn('let app_settings = effective_app_settings_value(&app);', self.main)
    self.assertIn('let app_settings = merge_app_settings_value(&document.app_settings())?;', self.main)

  def test_release_identity_sync_covers_every_versioned_surface(self) -> None:
    sync = (ROOT / "tools/sync_version.mjs").read_text(encoding="utf-8")
    for marker in (
      '"src-tauri/tauri.conf.json"',
      '"package.json"',
      '"package-lock.json"',
      '"src-tauri/Cargo.toml"',
      '"src-tauri/Cargo.lock"',
      '"tools/init.py"',
      '"tools/init.ps1"',
      '"README.md"',
    ):
      self.assertIn(marker, sync)


if __name__ == "__main__":
  unittest.main()
