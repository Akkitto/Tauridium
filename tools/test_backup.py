#!/usr/bin/env python3
"""Regression coverage for versioned, integrity-checked Tauridium backups."""

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

  def test_backup_schema_is_versioned_and_has_a_migration_floor(self) -> None:
    self.assertIn('const BACKUP_FORMAT: &str = "tauridium-backup"', self.backup)
    self.assertIn("const BACKUP_SCHEMA_CURRENT: u32 = 2", self.backup)
    self.assertIn("const BACKUP_SCHEMA_MIN: u32 = 1", self.backup)
    self.assertIn("source_schema", self.backup)
    self.assertIn("legacy_schema_one_is_migrated_without_claiming_integrity", self.backup)
    self.assertIn("Unsupported Tauridium backup schema", self.backup)

  def test_current_backups_are_sha256_integrity_protected(self) -> None:
    for marker in (
      'const INTEGRITY_ALGORITHM: &str = "sha256"',
      "Sha256::digest(payload)",
      "payload_sha256",
      "refresh_integrity",
      "validate_integrity",
      "Backup integrity check failed; the file is corrupted or was modified",
      "backup_detects_payload_tampering",
    ):
      self.assertIn(marker, self.backup)
    self.assertIn('.collect::<Vec<_>>()\n            .join("")', self.backup)

  def test_backup_contains_owned_progress_and_excludes_runtime_secrets(self) -> None:
    for marker in (
      "app_settings",
      "local_profile",
      "custom_recipes",
      '"ferdiumSessionCredentials"',
      '"websiteCookiesAndStorage"',
      '"remoteRecipeCache"',
      '"windowMonitorGeometry"',
      "contains_sensitive_data: true",
    ):
      self.assertIn(marker, self.backup)
    self.assertIn("serviceOrder", self.main)
    self.assertIn("workspaceOrder", self.main)
    self.assertNotIn('include_bytes!("session.json")', self.backup)
    self.assertNotIn('join("session.json")', self.backup)

  def test_restore_validates_every_component_before_first_commit(self) -> None:
    body = self.main.split("fn restore_backup", 1)[1].split("fn persisted_window_state_flags", 1)[0]
    validate_settings = body.index("merge_app_settings_value")
    validate_profile = body.index("LocalProfile::from_value")
    validate_recipes = body.index("validate_custom_recipe_backups")
    recovery_snapshot = body.index("Unable to create pre-restore safety backup")
    first_commit = body.index("replace_custom_recipes_exact(&app, &restored_recipes)")
    self.assertLess(validate_settings, recovery_snapshot)
    self.assertLess(validate_profile, recovery_snapshot)
    self.assertLess(validate_recipes, recovery_snapshot)
    self.assertLess(recovery_snapshot, first_commit)
    self.assertIn("validate_app_settings_value", self.main)
    self.assertIn("validate_backup_integrity", self.profile)
    self.assertIn("prepared_backup_recipes", self.recipes)

  def test_restore_creates_recovery_snapshot_before_mutation(self) -> None:
    body = self.main.split("fn restore_backup", 1)[1].split("fn persisted_window_state_flags", 1)[0]
    self.assertIn('join("backups")', self.main)
    self.assertIn('format!("pre-restore-{stamp}.json")', self.main)
    self.assertIn("previous_settings.clone()", body)
    self.assertIn("previous_profile_value", body)
    self.assertIn("previous_recipes.clone()", body)
    self.assertIn("backup::save(&recovery_path, &recovery_document)", body)
    self.assertIn("with_recovery_backup_path(&recovery_path)", body)
    self.assertIn("recoveryBackupPath?: string", self.api)
    self.assertIn("Recovery snapshot:", self.app)

  def test_restore_is_transactional_and_rolls_back_every_owned_component(self) -> None:
    body = self.main.split("fn restore_backup", 1)[1].split("fn persisted_window_state_flags", 1)[0]
    for marker in (
      "previous_settings",
      "previous_profile",
      "previous_recipes",
      "replace_custom_recipes_exact(&app, &previous_recipes)",
      "save_local_profile(&app, &previous_profile)",
      "apply_autostart_setting(&app, &previous_settings)",
      "persist_app_settings(&app, &state, &previous_settings)",
      "Backup restore failed and the previous Tauridium state was restored",
      "Rollback also reported",
    ):
      self.assertIn(marker, body)

  def test_recipe_restore_is_staged_and_non_destructive_for_unrelated_recipes(self) -> None:
    for marker in (
      "merge_custom_recipe_backups",
      "replace_custom_recipes_exact",
      ".restore-tmp",
      ".restore-bak",
      "Unable to recover interrupted recipe restore",
      "Unable to commit custom recipe restore",
      "Backup contains duplicate custom recipe id",
    ):
      self.assertIn(marker, self.recipes)
    self.assertIn("current.iter().chain(incoming.iter())", self.recipes)

  def test_local_profile_restore_rejects_structural_corruption(self) -> None:
    for marker in (
      "Backup contains duplicate local service id",
      "Backup contains duplicate local workspace id",
      "references unknown local service id",
      "contains duplicate service id",
      "backup_profile_rejects_duplicate_ids_and_broken_workspace_membership",
    ):
      self.assertIn(marker, self.profile)

  def test_backup_writes_atomically_is_size_limited_and_private_on_unix(self) -> None:
    self.assertIn("replace_file(&staging, path)", self.backup)
    self.assertIn("MAX_BACKUP_BYTES", self.backup)
    self.assertIn("Permissions::from_mode(0o600)", self.backup)
    self.assertIn("Backup destination path is empty", self.backup)

  def test_export_is_fsync_verified_before_replacing_existing_backup(self) -> None:
    save = self.backup.split("pub(crate) fn save", 1)[1].split("pub(crate) fn load", 1)[0]
    self.assertIn(".create_new(true)", save)
    self.assertIn("file.sync_all()", save)
    self.assertIn("let verified = load(&staging)", save)
    self.assertIn("verified.payload_digest() != document.payload_digest()", save)
    self.assertIn("replace_file(&staging, path)", save)
    self.assertLess(save.index("let verified = load(&staging)"), save.index("replace_file(&staging, path)"))
    self.assertIn("let _ = fs::remove_file(&staging);", save)

  def test_interrupted_recipe_transaction_has_startup_recovery(self) -> None:
    self.assertIn("fn recover_interrupted_recipe_restore", self.recipes)
    self.assertIn("if !root.exists() && rollback.exists()", self.recipes)
    self.assertIn("fs::rename(&rollback, root)", self.recipes)
    self.assertIn("if root.exists() && staging.exists()", self.recipes)
    self.assertIn("interrupted_recipe_restore_recovers_or_cleans_transaction_artifacts", self.recipes)

  def test_gui_explains_versioning_integrity_and_restore_safety(self) -> None:
    for marker in (
      "Export backup…",
      "Restore backup…",
      "tauridium-backup-",
      "integrity verified",
      "migrated from legacy schema",
      "validates every component before committing",
      "Ferdium login tokens, website cookies/storage, remote caches",
      "Backups can contain sensitive local service configuration",
      "Recovery snapshot:",
      "await closeServices();",
      "window.location.reload()",
    ):
      self.assertIn(marker, self.app)


if __name__ == "__main__":
  unittest.main()
