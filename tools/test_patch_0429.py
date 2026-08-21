#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.4.29 service navigation and settings UX fixes."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
API_TEST = (ROOT / "src/lib/api.test.ts").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")


class Patch0429Tests(unittest.TestCase):
  def test_external_link_preference_reaches_new_window_handler_and_windows_has_no_cmd_flash(self) -> None:
    self.assertIn("openLinksExternally: s.trapLinkClicks === true", API)
    self.assertIn("open_links_externally: bool", MAIN)
    self.assertIn("open_links_externally && matches!(url.scheme(), \"http\" | \"https\")", MAIN)
    self.assertIn("webview.navigate(url)", MAIN)
    self.assertIn('"trapLinkClicks",', APP.split("const RELOAD_FIELDS", 1)[1].split("]);", 1)[0])
    self.assertIn("openLinksExternally: true", API_TEST)
    self.assertIn("ShellExecuteW", MAIN)
    self.assertNotIn('.args(["/C", "start", "", url])', MAIN)

  def test_immediate_service_settings_share_green_saved_feedback(self) -> None:
    self.assertIn("function showServiceSettingsSaved(serviceId: string)", APP)
    helper = APP.split("function showServiceSettingsSaved", 1)[1].split("function preferredWebsiteIcon", 1)[0]
    self.assertIn('showToast("Saved", "success")', helper)
    for function_name in (
      "saveServiceIconInversion",
      "saveServiceDownloadOverride",
      "setServiceShortcutCaptureMode",
      "assignServiceSandbox",
    ):
      body = APP.split(f"function {function_name}", 1)[1].split("\n  }", 1)[0]
      self.assertIn("showServiceSettingsSaved(", body, function_name)
    enabled_body = APP.split("async function setServiceEnabled", 1)[1].split("async function toggleServiceEnabled", 1)[0]
    self.assertIn("showServiceSettingsSaved(service.id)", enabled_body)

  def test_original_service_context_menu_is_default_with_native_fallback(self) -> None:
    self.assertIn("prettyServiceContextMenu: boolean", API)
    self.assertIn("prettyServiceContextMenu: true", APP)
    self.assertIn('settings.insert("prettyServiceContextMenu".into(), true.into());', MAIN)
    self.assertIn('"prettyServiceContextMenu",', MAIN)
    self.assertIn("Use original service context menu", APP)
    self.assertIn('class="service-context-menu"', APP)
    self.assertIn("service-context-backdrop", APP)
    self.assertIn("if (!appSettings.prettyServiceContextMenu)", APP)
    self.assertIn("popupNativeServiceContextMenu", APP)
    self.assertIn("await menu.popup(new LogicalPosition(x, y));", APP)

  def test_native_about_menu_has_project_source_and_author_quick_links(self) -> None:
    builder = MAIN.split("fn build_native_application_menu", 1)[1].split("#[derive(Clone, Copy)]", 1)[0]
    events = MAIN.split("// Native application menu", 1)[1].split("// Request notification", 1)[0]
    for marker in (
      '"About"',
      '"Project Homepage"',
      '"Project Source Code"',
      '"Author Homepage"',
    ):
      self.assertIn(marker, builder)
    self.assertLess(builder.index('"Services"'), builder.index('"About"'))
    self.assertIn("PROJECT_HOMEPAGE", MAIN)
    self.assertIn("PROJECT_SOURCE_CODE", MAIN)
    self.assertIn("AUTHOR_HOMEPAGE", MAIN)
    self.assertIn("open_external(PROJECT_HOMEPAGE)", events)
    self.assertIn("open_external(PROJECT_SOURCE_CODE)", events)
    self.assertIn("open_external(AUTHOR_HOMEPAGE)", events)

  def test_services_settings_page_exposes_create_service_action(self) -> None:
    services_panel = APP.split('{:else if settingsTab === "services"}', 1)[1].split('{:else if settingsTab === "workspaces"}', 1)[0]
    self.assertIn("Configured services", services_panel)
    self.assertIn('onclick={openAdd}>Create service</button>', services_panel)
    self.assertIn("Create a service above", services_panel)


if __name__ == "__main__":
  unittest.main()
