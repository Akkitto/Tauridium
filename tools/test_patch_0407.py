#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.4.7 service controls and URL/icon behavior."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0407Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
    cls.api = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
    cls.main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    cls.recipes = (ROOT / "src-tauri/src/recipes.rs").read_text(encoding="utf-8")
    cls.icons = (ROOT / "src-tauri/src/icons.rs").read_text(encoding="utf-8")
    cls.build = (ROOT / "src-tauri/build.rs").read_text(encoding="utf-8")
    cls.cargo = (ROOT / "src-tauri/Cargo.toml").read_text(encoding="utf-8")

  def test_sidebar_uses_full_row_without_cogwheel_and_has_context_menu(self) -> None:
    row = self.app.split("{#snippet row(s: Service)}", 1)[1].split("{/snippet}", 1)[0]
    self.assertNotIn('class="cog"', row)
    self.assertIn('oncontextmenu={(e) => openServiceContextMenu(e, s)}', row)
    self.assertIn('onkeydown={(e) => openServiceContextMenuFromKeyboard(e, s)}', row)
    self.assertIn('aria-disabled={s.isEnabled === false}', row)
    self.assertIn('class:disabled={s.isEnabled === false}', row)
    self.assertIn('.srow-wrap { display: flex; align-items: center; position: relative; width: 100%; }', self.app)
    self.assertIn('.srow { width: 100%;', self.app)
    self.assertIn('>Settings</button>', self.app)
    self.assertIn('>Reload</button>', self.app)
    self.assertIn('onkeydown={handleServiceContextMenuKeydown}', self.app)
    self.assertIn('event.key === \"ArrowDown\"', self.app)
    self.assertIn('"Enable" : "Disable"', self.app)

  def test_disabled_services_are_closed_and_never_selected_or_preloaded(self) -> None:
    self.assertIn('if (s.isEnabled === false) return;', self.app)
    self.assertIn('const first = sorted.find((s) => s.isEnabled !== false) ?? null;', self.app)
    self.assertIn('s.isEnabled !== false &&', self.app)
    body = self.app.split('async function setServiceEnabled', 1)[1].split('async function toggleServiceEnabled', 1)[0]
    self.assertIn('await closeService(service.id)', body)
    self.assertIn('activeId = null;', body)
    self.assertIn('candidate.isEnabled !== false', body)
    self.assertIn('keepServiceSettingsOpen', body)
    self.assertNotIn('sorted[0]', self.app.split('function backToService()', 1)[1].split('async function handleLogout', 1)[0])

  def test_service_settings_has_immediate_enable_disable_control_in_danger_zone(self) -> None:
    service_settings = self.app.split('{:else if view === "svcSettings"', 1)[1].split('{:else if view === "add"}', 1)[0]
    self.assertNotIn('@render toggle("Enabled"', service_settings)
    clear_pos = service_settings.index('Clear cache & session')
    enable_pos = service_settings.index('settingsSvc.isEnabled === false ? "Enable service" : "Disable service"')
    delete_pos = service_settings.index('Delete service')
    self.assertLess(clear_pos, enable_pos)
    self.assertLess(enable_pos, delete_pos)

  def test_opencode_has_browser_default_title_and_workspace_route(self) -> None:
    self.assertIn('"OpenCode",', self.recipes)
    self.assertNotIn('"OpenCode Web"', self.recipes)
    self.assertIn('"https://opencode.ai/go"', self.recipes)
    self.assertIn('"https://opencode.ai/workspace/{teamId}/go"', self.recipes)
    self.assertIn('"hasTeamId": id == "opencode"', self.recipes)
    self.assertIn('wrk_01ABC123EXAMPLE', self.app)
    self.assertIn('https://opencode.ai/workspace/wrk_01ABC123EXAMPLE/go', self.app)
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    self.assertNotIn('OpenCode Web', readme)
    self.assertNotIn('127.0.0.1:4096', readme)

  def test_custom_url_placeholder_feature_is_opt_in_and_backed_up_as_app_settings(self) -> None:
    for marker in (
      '"customUrlTemplatesEnabled": false',
      '"serviceCustomUrlTemplates": {}',
      'service_custom_url_template_values',
      '"{{custom_id_1}}"',
      '"{{custom_id_2}}"',
      'Custom URL contains an unsupported custom ID placeholder',
    ):
      self.assertIn(marker, self.main)
    self.assertIn('customUrlTemplatesEnabled: false', self.app)
    self.assertIn('serviceCustomUrlTemplates: {}', self.app)
    self.assertIn('Enable custom URL placeholders for all services', self.app)
    self.assertIn('Enable for this service', self.app)
    self.assertIn('serviceCustomUrlTemplates: {', self.app)

  def test_custom_url_template_values_are_removed_when_service_is_deleted(self) -> None:
    body = self.app.split('async function handleDelete', 1)[1].split('async function handleClearCache', 1)[0]
    self.assertIn('const serviceCustomUrlTemplates = { ...appSettings.serviceCustomUrlTemplates };', body)
    self.assertIn('delete serviceCustomUrlTemplates[s.id];', body)
    self.assertIn('setAppSettings({ serviceSandboxes, serviceCustomUrlTemplates })', body)

  def test_website_icons_are_persistently_positive_and_negative_cached(self) -> None:
    for marker in (
      'const ICON_CACHE_DIR: &str = "service-icons";',
      'const MISSING_SENTINEL: &str = "missing";',
      'if !force && !should_fetch',
      'if let Some(cached) = previous',
      'write_atomic(&path, &format!("{MISSING_SENTINEL}\\n"))',
      'pub(crate) fn remove_cached',
      'fs::create_dir_all(&root)',
    ):
      self.assertIn(marker, self.icons)
    self.assertIn('"fetchMissingServiceIcons": true', self.main)
    self.assertIn('Fetch missing website icons', self.app)
    self.assertIn('Refetch all service icons', self.app)
    self.assertIn('Refetch icon', self.app)
    self.assertIn('confirmAsk("Refetch and replace cached website icons for all services?', self.app)

  def test_broken_recipe_icon_uses_cached_fallback_without_forcing_network(self) -> None:
    body = self.app.split('function markIconFailed', 1)[1].split('function closeServiceContextMenu', 1)[0]
    self.assertIn('loadServiceIcon(service, false, false, true)', body)
    self.assertIn('`${service.id}:${preferWebsiteIcon ? \"website\" : \"default\"}`', self.app)
    self.assertNotIn('loadServiceIcon(service, true', body)

  def test_reload_shortcut_and_context_menu_share_optional_toast_path(self) -> None:
    self.assertIn('case "reloadService": if (activeService) void reloadServiceFromUi(activeService); break;', self.app)
    self.assertIn('onclick={() => reloadServiceFromUi(contextService)}', self.app)
    body = self.app.split('async function reloadServiceFromUi', 1)[1].split('async function refetchAllServiceIcons', 1)[0]
    self.assertIn('if (appSettings.reloadToasts)', body)
    self.assertIn('reloaded.`', body)
    self.assertIn('"reloadToasts": true', self.main)
    self.assertIn('Show reload notifications', self.app)

  def test_about_uses_build_and_cargo_metadata_instead_of_ui_literals(self) -> None:
    self.assertIn('env!("CARGO_PKG_DESCRIPTION")', self.main)
    self.assertIn('env!("CARGO_PKG_REPOSITORY")', self.main)
    self.assertIn('env!("CARGO_PKG_LICENSE")', self.main)
    self.assertIn('env!("TAURIDIUM_MAINTAINER")', self.main)
    self.assertIn('cargo:rerun-if-env-changed=TAURIDIUM_MAINTAINER', self.build)
    self.assertIn('repository = "https://github.com/Gizmo091/Tauridium"', self.cargo)
    about = self.app.split('{:else if settingsTab === "about"}', 1)[1].split('{/if}', 1)[0]
    self.assertIn('appMetadata?.maintainer', about)
    self.assertIn('appMetadata?.license', about)
    self.assertIn('projectRepository', about)
    self.assertNotIn('Mathieu Vedie', about)

  def test_backend_has_unit_coverage_for_opencode_and_custom_templates(self) -> None:
    self.assertIn('fn resolve_url_uses_recipe_team_url_and_custom_placeholders()', self.main)
    self.assertIn('fn custom_url_placeholders_require_values_when_enabled()', self.main)
    self.assertIn('fn opencode_uses_workspace_route_and_plain_title()', self.recipes)


if __name__ == "__main__":
  unittest.main()
