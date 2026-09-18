#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.7.13 portable service exports."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")
EXPORT = (ROOT / "src-tauri" / "src" / "service_export.rs").read_text(encoding="utf-8")
ICONS = (ROOT / "src-tauri" / "src" / "icons.rs").read_text(encoding="utf-8")


class Patch0713Tests(unittest.TestCase):
  def test_services_settings_support_subset_and_all_selection(self) -> None:
    for marker in (
      'class="service-export-checkbox"',
      'onclick={selectAllServiceExports}',
      'onclick={clearServiceExportSelection}',
      'onclick={() => doServiceExport(selectedServiceExports)}',
      'bind:checked={serviceExportIncludeAllPersonalRecipes}',
      'let serviceExportStatus = $state("");',
      'Export personal recipes…',
      'Include all personal recipes & custom websites',
    ):
      self.assertIn(marker, APP)

  def test_service_export_uses_a_single_verified_zip_bundle(self) -> None:
    for marker in (
      'defaultPath: `tauridium-services-${backupTimestamp()}.zip`',
      'extensions: ["zip"]',
      'const EXPORT_FORMAT: &str = "tauridium-service-export";',
      'const MAX_UNCOMPRESSED_BYTES: usize = 256 * 1024 * 1024;',
      'ZipWriter::new(cursor)',
      'CompressionMethod::Deflated',
      'verify_zip(&archive, &entries)?;',
      'file.sync_all()',
      'replace_file(&staging, path)',
      'archive_sha256',
    ):
      self.assertIn(marker, APP + EXPORT)

  def test_service_export_embeds_local_icons_and_ferdium_recipe_files(self) -> None:
    for marker in (
      'pub(crate) fn cached_data_uri',
      'icons/services/{id}',
      '("package.json", "application/json", package)',
      '("index.js", "text/javascript", index)',
      '("icon.svg", "image/svg+xml", icon)',
      'webview.js',
      'module.exports = Ferdium => Ferdium;',
      'object.remove("tauridium")',
    ):
      self.assertIn(marker, ICONS + EXPORT)

  def test_export_redacts_secrets_and_never_fetches_icons(self) -> None:
    for marker in (
      '"password"',
      '"token"',
      '"secret"',
      '"cookie"',
      '"authorization"',
      '"secretsRedacted": true',
      '"browserSessionDataIncluded": false',
      '"remoteIconsFetchedDuringExport": false',
    ):
      self.assertIn(marker, EXPORT)
    self.assertNotIn('reqwest', EXPORT)

  def test_export_command_is_typed_registered_and_audited(self) -> None:
    for marker in (
      'export function exportServiceBundle(',
      'return invoke("export_service_bundle", { path, request });',
      'fn export_service_bundle(',
      '"services",\n                "success"',
      'export_service_bundle,',
    ):
      self.assertIn(marker, API + MAIN)

  def test_export_has_focused_rust_regressions(self) -> None:
    for marker in (
      'zip_writer_round_trips_entries_and_crc',
      'zip_writer_rejects_unsafe_and_duplicate_paths',
      'recipe_selection_defaults_to_referenced_and_can_include_all',
      'service_sanitization_redacts_secret_like_fields',
      'ferdium_recipe_package_drops_tauridium_metadata_and_adds_license',
      'custom_website_becomes_standalone_ferdium_recipe',
      'custom_website_selection_always_keeps_selected_and_optionally_adds_all_local',
      'custom_website_recipe_rejects_non_http_urls',
      'manifest_service_references_embedded_icon_asset_without_duplicate_base64',
      'data_uri_icons_are_bounded_and_decoded',
    ):
      self.assertIn(marker, EXPORT)


if __name__ == "__main__":
  unittest.main()
