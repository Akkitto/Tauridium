#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0318Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
    cls.api = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
    cls.ui = (ROOT / "src/lib/ui.ts").read_text(encoding="utf-8")
    cls.main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")

  def test_manual_backup_name_contains_local_date_time_seconds_and_milliseconds(self) -> None:
    self.assertIn('return `tauridium-backup-${backupTimestamp()}.json`;', self.app)
    self.assertIn('date.getHours()', self.ui)
    self.assertIn('date.getMinutes()', self.ui)
    self.assertIn('date.getSeconds()', self.ui)
    self.assertIn('date.getMilliseconds()', self.ui)

  def test_automatic_backup_has_all_requested_schedules_and_retention(self) -> None:
    for marker in (
      '"off" | "startup" | "daily" | "weekly" | "monthly"',
      'On program startup',
      '<option value="daily">Daily</option>',
      '<option value="weekly">Weekly</option>',
      '<option value="monthly">Monthly</option>',
      'automaticBackupRetention',
      'min="1" max="365"',
      'create_automatic_backup',
      'prune_automatic_backups',
      'backups/automatic',
    ):
      self.assertTrue(marker in self.app or marker in self.api or marker in self.ui or marker in self.main, marker)

  def test_automatic_backup_serializes_and_prunes_only_after_verified_save(self) -> None:
    body = self.main.split('fn create_automatic_backup', 1)[1].split('fn restore_recovery_backup_path', 1)[0]
    self.assertIn('backup::save(&path, &document)?', body)
    self.assertIn('prune_automatic_backups(&root, retention_mode, retention, max_age_days)', body)
    self.assertLess(body.index('backup::save(&path, &document)?'), body.index('prune_automatic_backups(&root, retention_mode, retention, max_age_days)'))
    prune = self.main.split('fn prune_automatic_backups', 1)[1].split('#[tauri::command]', 1)[0]
    self.assertIn('validate_automatic_backup_filename(name).is_ok()', prune)
    self.assertIn('retention_paths_to_delete', prune)

  def test_automatic_backup_scheduler_avoids_concurrent_runs(self) -> None:
    body = self.app.split('async function maybeRunAutomaticBackup', 1)[1].split('function backupSummaryText', 1)[0]
    self.assertIn('if (automaticBackupRunning) return;', body)
    self.assertIn('automaticBackupRunning = true;', body)
    self.assertIn('finally', body)
    self.assertIn('automaticBackupRunning = false;', body)
    self.assertIn('60 * 60 * 1000', self.app)

  def test_appearance_updates_do_not_touch_autostart(self) -> None:
    body = self.main.split('fn set_app_settings', 1)[1].split('#[tauri::command]\nfn export_backup', 1)[0]
    self.assertIn('let autostart_changed = patch.contains_key("autostart");', body)
    self.assertIn('if autostart_changed {', body)
    self.assertIn('apply_autostart_setting(&app, &value)?;', body)
    self.assertLess(body.index('if autostart_changed {'), body.index('apply_autostart_setting(&app, &value)?;'))

  def test_automatic_backup_filename_is_path_traversal_safe(self) -> None:
    body = self.main.split('fn validate_automatic_backup_filename', 1)[1].split('fn prune_automatic_backups', 1)[0]
    self.assertIn('character.is_ascii_alphanumeric()', body)
    self.assertIn("matches!(character, '-' | '.')", body)
    self.assertIn('filename.starts_with("tauridium-auto-backup-")', body)
    self.assertIn('filename.ends_with(".json")', body)

  def test_local_only_wording_is_absent_from_current_tracked_text(self) -> None:
    for path in ROOT.rglob('*'):
      if not path.is_file() or '.git' in path.parts:
        continue
      if path.suffix.lower() not in {'.rs', '.ts', '.svelte', '.py', '.md', '.json', '.toml', '.ps1', ''}:
        continue
      try:
        text = path.read_text(encoding='utf-8').lower()
      except UnicodeDecodeError:
        continue
      self.assertNotIn('local' + '-only', text, str(path))
      self.assertNotIn('local' + ' only', text, str(path))


if __name__ == '__main__':
  unittest.main()
