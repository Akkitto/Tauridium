#!/usr/bin/env python3
"""Regression coverage for portable local Tauridium backups."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BackupWorkflowTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    cls.backup = (ROOT / "src-tauri/src/backup.rs").read_text(encoding="utf-8")
    cls.recipes = (ROOT / "src-tauri/src/recipes.rs").read_text(encoding="utf-8")
    cls.profile = (ROOT / "src-tauri/src/local_profile.rs").read_text(encoding="utf-8")
    cls.api = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
    cls.app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")

  def test_backup_commands_are_registered_and_exposed(self) -> None:
    handler = self.main.split("tauri::generate_handler![", 1)[1].split("]", 1)[0]
    self.assertIn("export_backup", handler)
    self.assertIn("restore_backup", handler)
    self.assertIn('invoke("export_backup", { path })', self.api)
    self.assertIn('invoke("restore_backup", { path })', self.api)

  def test_backup_contains_local_owned_data_but_excludes_sessions(self) -> None:
    for marker in (
      "app_settings",
      "local_profile",
      "custom_recipes",
      '"ferdiumSessionCredentials"',
      '"websiteCookiesAndStorage"',
      '"remoteRecipeCache"',
      "contains_sensitive_data: true",
    ):
      self.assertIn(marker, self.backup)
    self.assertNotIn('include_bytes!("session.json")', self.backup)
    self.assertNotIn('join("session.json")', self.backup)

  def test_restore_validates_all_components_before_writing(self) -> None:
    body = self.main.split("fn restore_backup", 1)[1].split("fn show_main", 1)[0]
    validate_settings = body.index("merge_app_settings_value")
    validate_profile = body.index("LocalProfile::from_value")
    validate_recipes = body.index("validate_custom_recipe_backups")
    persist_settings = body.index("persist_app_settings")
    persist_profile = body.index("save_local_profile")
    restore_recipes = body.index("restore_custom_recipes")
    self.assertLess(validate_settings, persist_settings)
    self.assertLess(validate_profile, persist_profile)
    self.assertLess(validate_recipes, restore_recipes)
    self.assertIn("fn prepared_backup_recipes", self.recipes)
    self.assertIn("pub(crate) fn from_value", self.profile)

  def test_backup_writes_atomically_and_is_size_limited(self) -> None:
    self.assertIn("write_atomic(path", self.backup)
    self.assertIn("MAX_BACKUP_BYTES", self.backup)
    self.assertIn("Permissions::from_mode(0o600)", self.backup)

  def test_gui_exports_and_restores_one_portable_file(self) -> None:
    self.assertIn("Export backup…", self.app)
    self.assertIn("Restore backup…", self.app)
    self.assertIn("tauridium-backup-", self.app)
    self.assertIn("saveDialog", self.app)
    self.assertIn("Ferdium login tokens, website cookies/storage, and remote caches are excluded", self.app)
    self.assertIn("Backups can contain sensitive local service configuration", self.app)
    self.assertIn("await closeServices();", self.app)
    self.assertIn("window.location.reload()", self.app)


if __name__ == "__main__":
  unittest.main()
