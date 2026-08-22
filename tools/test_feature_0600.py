#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.6.0 collapsible sidebar."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
UI = (ROOT / "src/lib/ui.ts").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
JUST = (ROOT / "justfile").read_text(encoding="utf-8")


class Feature0600Tests(unittest.TestCase):
  def test_release_recipe_does_not_duplicate_release_clean_dependency(self) -> None:
    self.assertIn("release: release-clean ci\n  just release-clean\n  just package", JUST)
    self.assertNotIn("release: release-clean ci release-clean package", JUST)

  def test_sidebar_collapsed_state_is_persisted_and_defaults_expanded(self) -> None:
    self.assertIn("sidebarCollapsed: boolean;", API)
    self.assertIn("sidebarCollapsed: false,", APP)
    self.assertIn('settings.insert("sidebarCollapsed".into(), false.into());', MAIN)
    self.assertIn('"sidebarCollapsed",', MAIN)

  def test_collapsed_sidebar_uses_fixed_icon_rail_without_overwriting_expanded_width(self) -> None:
    self.assertIn("export const COLLAPSED_SIDEBAR_WIDTH_PX = 64;", UI)
    self.assertIn("if (appSettings.sidebarCollapsed) return COLLAPSED_SIDEBAR_WIDTH_PX;", APP)
    self.assertIn("const COLLAPSED_SIDEBAR_W: f64 = 64.0;", MAIN)
    self.assertIn("MIN_RUNTIME_SIDEBAR_W", MAIN)
    self.assertIn("class:collapsed={appSettings.sidebarCollapsed}", APP)
    collapsed_css = APP.split(".sidebar.collapsed {", 1)[1].split(".link {", 1)[0]
    self.assertIn("padding-inline: 8px", collapsed_css)
    self.assertIn("justify-content: center", collapsed_css)
    self.assertIn("position: absolute", collapsed_css)

  def test_sidebar_toggle_has_button_menu_shortcut_and_service_bridge_support(self) -> None:
    self.assertIn('toggleSidebar: "Ctrl+Shift+B"', UI)
    self.assertIn('["toggleSidebar", "Toggle sidebar"', APP)
    self.assertIn('case "toggleSidebar": toggleSidebarCollapsed(); break;', APP)
    self.assertIn('aria-label={appSettings.sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}', APP)
    self.assertIn('"toggleSidebar",', MAIN.split("const SHORTCUT_ACTIONS", 1)[1].split("static SERVICE_SHORTCUT", 1)[0])
    self.assertIn('"toggle-sidebar"', MAIN)
    self.assertIn('shortcut("toggleSidebar")', MAIN)
    self.assertIn('app.emit("shortcut-action", "toggleSidebar".to_string())', MAIN)

  def test_collapsed_rows_keep_names_accessible_without_rendering_labels(self) -> None:
    row = APP.split("{#snippet row(s: Service)}", 1)[1].split("{/snippet}", 1)[0]
    self.assertIn("title={`${serviceLabel(s)}", row)
    self.assertIn("aria-label={`${serviceLabel(s)}", row)
    self.assertIn("appSettings.showServiceName && !appSettings.sidebarCollapsed", row)
    self.assertIn("hibernated.has(s.id) && !appSettings.sidebarCollapsed", row)

  def test_appearance_explains_collapsed_mode_and_preserves_icon_size_control(self) -> None:
    appearance = APP.split('settingsTab === "appearance"', 1)[1].split('settingsTab === "keybindings"', 1)[0]
    self.assertIn("Collapse sidebar", appearance)
    self.assertIn("fixed 64 px rail", appearance)
    self.assertIn("Service icon size", appearance)


if __name__ == "__main__":
  unittest.main()
