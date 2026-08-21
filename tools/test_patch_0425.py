#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.4.25 workspace icon URL and downloads."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
ICONS = (ROOT / "src-tauri/src/icons.rs").read_text(encoding="utf-8")
BACKUP = (ROOT / "src-tauri/src/backup.rs").read_text(encoding="utf-8")
CARGO = (ROOT / "src-tauri/Cargo.toml").read_text(encoding="utf-8")


class Patch0425Tests(unittest.TestCase):
  def test_workspace_icon_can_be_fetched_from_arbitrary_http_url_and_stored_locally(self) -> None:
    self.assertIn('export function fetchWorkspaceIconUrl(url: string): Promise<string>', API)
    self.assertIn('async fn fetch_workspace_icon_url(url: String)', MAIN)
    self.assertIn('icons::fetch_workspace_icon_url(&HTTP, &url).await', MAIN)
    self.assertIn('pub(crate) async fn fetch_workspace_icon_url', ICONS)
    self.assertIn('matches!(parsed.scheme(), "http" | "https")', ICONS)
    self.assertIn('The result is always a self-contained', ICONS)
    self.assertIn('bind:value={managedWorkspaceIconUrlDraft}', APP)
    self.assertIn('onclick={assignManagedWorkspaceIconFromUrl}', APP)
    self.assertIn('const icon = await fetchWorkspaceIconUrl(url);', APP)
    self.assertIn('await persistManagedWorkspaceIcon(icon, true);', APP)

  def test_download_defaults_are_migrated_validated_and_exposed_in_advanced_settings(self) -> None:
    for marker in (
      'downloadDirectory: string;',
      'askEachDownload: boolean;',
      'serviceDownloadSettings: Record<string, DownloadPreferenceOverride>;',
      'workspaceDownloadSettings: Record<string, DownloadPreferenceOverride>;',
    ):
      self.assertIn(marker, API)
    for marker in (
      'settings.insert("downloadDirectory".into(), "".into());',
      'settings.insert("askEachDownload".into(), false.into());',
      '"serviceDownloadSettings".into()',
      '"workspaceDownloadSettings".into()',
      'fn validate_download_settings_map',
      'fn feature_0425_download_settings_validate_and_resolve_precedence()',
    ):
      self.assertIn(marker, MAIN)
    advanced = APP.split('id="settings-advanced-downloads"', 1)[1].split('id="settings-advanced-browser"', 1)[0]
    self.assertIn('Default download directory', advanced)
    self.assertIn('chooseGlobalDownloadDirectory', advanced)
    self.assertIn('Ask where to save each download', advanced)

  def test_server_suggested_filename_wins_over_opaque_download_url(self) -> None:
    requested = MAIN.split('DownloadEvent::Requested { url, destination }', 1)[1].split('DownloadEvent::Finished', 1)[0]
    self.assertIn('suggested_download_filename(destination, &url)', requested)
    self.assertIn('.file_name()', MAIN.split('fn suggested_download_filename', 1)[1].split('fn effective_download_directory', 1)[0])
    self.assertNotIn('unique_download_path(&dir, &download_filename(&url))', MAIN)
    self.assertIn('fn feature_0425_download_uses_server_suggested_filename_and_sanitizes_safely()', MAIN)
    self.assertIn('"quarterly-report.zip"', MAIN)

  def test_download_preferences_have_service_workspace_global_precedence(self) -> None:
    body = MAIN.split('fn effective_download_preferences', 1)[1].split('fn sanitize_download_filename', 1)[0]
    service_pos = body.index('"serviceDownloadSettings"')
    workspace_pos = body.index('"workspaceDownloadSettings"')
    global_pos = body.index('"downloadDirectory"')
    self.assertLess(service_pos, workspace_pos)
    self.assertLess(workspace_pos, global_pos)
    self.assertIn('showService(s, activeWorkspace)', APP)
    self.assertIn('workspaceId,', API)
    self.assertIn('download_workspaces', MAIN)

  def test_per_service_and_workspace_download_overrides_are_immediate_and_verified(self) -> None:
    self.assertIn('Service download settings', APP)
    self.assertIn('saveServiceDownloadOverride', APP)
    self.assertIn('Tauridium could not verify the service download settings', APP)
    self.assertIn('workspace-download-card', APP)
    self.assertIn('saveWorkspaceDownloadOverride', APP)
    self.assertIn('Tauridium could not verify the workspace download settings', APP)
    self.assertIn('delete serviceDownloadSettings[s.id];', APP)
    self.assertIn('delete workspaceDownloadSettings[ws.id];', APP)
    self.assertIn('serviceDownloadSettings[newId] = { ...serviceDownloadSettings[service.id] };', APP)

  def test_ask_each_download_keeps_original_authenticated_webview_download(self) -> None:
    handler = MAIN.split('builder = builder.on_download', 1)[1].split('// Per-service storage isolation', 1)[0]
    self.assertIn('ask_download_destination', handler)
    self.assertIn('*destination = path', handler)
    self.assertNotIn('reqwest', handler)
    self.assertIn('rfd = "0.16"', CARGO)
    self.assertIn('rfd::FileDialog::new()', MAIN)
    self.assertIn('.set_parent(parent)', MAIN)
    self.assertIn('.save_file()', MAIN)
    self.assertIn('would deadlock', MAIN)
    self.assertNotIn('blocking_save_file()', MAIN)
    self.assertNotIn('tauridium-download-dialog', MAIN)

  def test_full_backups_preserve_download_preferences_without_changing_portable_paths(self) -> None:
    self.assertIn('app_settings: Value', BACKUP)
    self.assertIn('pub(crate) fn app_settings(&self) -> Value', BACKUP)
    self.assertIn('Directory overrides are device-specific settings', APP)


if __name__ == "__main__":
  unittest.main()
