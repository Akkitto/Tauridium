#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.5.3 workspace startup preferences."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
UI = (ROOT / "src/lib/ui.ts").read_text(encoding="utf-8")
UI_TEST = (ROOT / "src/lib/ui.test.ts").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")


class WorkspaceStartupPatchTests(unittest.TestCase):
  def test_settings_contract_is_persisted_and_validated(self) -> None:
    for token in [
      "defaultWorkspaceId: string;",
      "restoreLastWorkspaceOnStartup: boolean;",
      "lastWorkspaceId: string;",
      'settings.insert("defaultWorkspaceId".into(), "".into())',
      'settings.insert("restoreLastWorkspaceOnStartup".into(), false.into())',
      'settings.insert("lastWorkspaceId".into(), "".into())',
      'feature_0503_settings_validate_workspace_startup_preferences',
    ]:
      self.assertTrue(token in API or token in MAIN, token)

  def test_workspace_settings_expose_default_and_restore_controls(self) -> None:
    self.assertIn('id="settings-workspaces-startup"', APP)
    self.assertIn('aria-label="Default workspace"', APP)
    self.assertIn('<option value="">All services</option>', APP)
    self.assertIn('Restore last workspace on startup', APP)
    self.assertIn('saveRestoreLastWorkspaceOnStartup', APP)

  def test_startup_precedence_is_explicit_and_unit_tested(self) -> None:
    self.assertIn('export function resolveStartupWorkspaceId(', UI)
    self.assertIn('if (restoreLastWorkspaceOnStartup)', UI)
    self.assertIn('const fallback = resolve(defaultWorkspaceId);', UI)
    self.assertIn('describe("0.5.3 workspace startup selection"', UI_TEST)
    self.assertIn('resolveStartupWorkspaceId(workspaceIds, "work", true, "personal")', UI_TEST)
    self.assertIn('resolveStartupWorkspaceId(workspaceIds, "work", true, "deleted")', UI_TEST)

  def test_last_workspace_is_saved_for_workspace_and_all_services(self) -> None:
    self.assertIn('const lastWorkspaceId = workspaceId ?? "";', APP)
    self.assertIn('setAppSettings({ lastWorkspaceId, workspaceLastUsed })', APP)
    self.assertIn('const lastWorkspaceId = enabled ? (activeWorkspace ?? "")', APP)

  def test_stale_workspace_references_are_reconciled(self) -> None:
    self.assertIn('const defaultWorkspaceId = !appSettings.defaultWorkspaceId || workspaceIds.has(appSettings.defaultWorkspaceId)', APP)
    self.assertIn(': defaultWorkspaceId;', APP)
    self.assertIn('appSettings.defaultWorkspaceId === ws.id ? ""', APP)
    self.assertIn('appSettings.lastWorkspaceId === ws.id ? ""', APP)


if __name__ == "__main__":
  unittest.main()
