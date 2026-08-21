#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.4.24 workspace icons and settings UI polish."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
BACKUP = (ROOT / "src-tauri/src/backup.rs").read_text(encoding="utf-8")


class Patch0424Tests(unittest.TestCase):
  def test_service_sandbox_search_matches_compact_workspace_search_scale(self) -> None:
    sandbox = APP.split('<div class="set-title">Sandbox</div>', 1)[1].split('<div class="set-title">Appearance</div>', 1)[0]
    self.assertIn('class="service-workspace-search service-sandbox-search"', sandbox)
    self.assertIn('placeholder="Search sandboxes…"', sandbox)
    self.assertIn('.service-sandbox-search { width: min(100%, 420px); flex: 0 1 420px; }', APP)

  def test_sidebar_drop_region_is_accessibility_annotated(self) -> None:
    self.assertIn('class="svcarea" role="region" aria-label="Service list drop area"', APP)

  def test_workspace_icons_are_backend_validated_and_migrate_with_defaults(self) -> None:
    self.assertIn('workspaceIcons: Record<string, string>', API)
    self.assertIn('settings.insert(\n        "workspaceIcons".into()', MAIN)
    self.assertIn('.get("workspaceIcons")', MAIN)
    self.assertIn('icon.starts_with("data:image/")', MAIN)
    self.assertIn('workspace_icon_bytes > 16 * 1024 * 1024', MAIN)

  def test_workspace_settings_can_assign_existing_resolved_service_icons(self) -> None:
    detail = APP.split('{:else if settingsTab === "workspaces"}', 1)[1].split('{:else if settingsTab === "appearance"}', 1)[0]
    self.assertIn('class="setting-card setting-card-stack workspace-icon-card"', detail)
    self.assertIn('assignManagedWorkspaceIconFromService(service)', detail)
    self.assertIn('displayedServiceIcon(service)', APP)
    self.assertIn('saveManagedWorkspaceIcon(null)', detail)
    self.assertIn('Tauridium could not verify the saved workspace icon', APP)

  def test_workspace_icons_are_visible_in_workspace_surfaces_with_fallback(self) -> None:
    self.assertGreaterEqual(APP.count('workspaceIcon(workspace)'), 3)
    self.assertIn('markWorkspaceIconFailed(workspace.id)', APP)
    self.assertIn('workspace-avatar-image', APP)

  def test_workspace_icons_are_cleaned_up_with_deleted_or_stale_workspaces(self) -> None:
    self.assertIn('Object.entries(appSettings.workspaceIcons).filter(([workspaceId]) => workspaceIds.has(workspaceId))', APP)
    self.assertIn('delete workspaceIcons[ws.id];', APP)
    self.assertIn('setAppSettings({ workspaceLastUsed, workspaceIcons })', APP)

  def test_portable_workspace_exports_embed_the_selected_icon(self) -> None:
    self.assertIn('function portableWorkspace(workspace: Workspace): Workspace', APP)
    self.assertIn('return iconUrl ? { ...workspace, iconUrl } : { ...workspace, iconUrl: null };', APP)
    self.assertIn(']).map(portableWorkspace)', APP)
    self.assertIn('.map((workspace) => portableWorkspace({', APP)

  def test_full_backups_already_include_app_settings(self) -> None:
    self.assertIn('app_settings: Value', BACKUP)
    self.assertIn('pub(crate) fn app_settings(&self) -> Value', BACKUP)


if __name__ == "__main__":
  unittest.main()
