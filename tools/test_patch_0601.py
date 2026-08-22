#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.6.1 sidebar startup and collapsed geometry."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
UI = (ROOT / "src/lib/ui.ts").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")


class Patch0601Tests(unittest.TestCase):
  def test_sidebar_startup_preferences_mirror_workspace_precedence(self) -> None:
    self.assertIn("defaultSidebarCollapsed: boolean;", API)
    self.assertIn("restoreLastSidebarStateOnStartup: boolean;", API)
    self.assertIn("defaultSidebarCollapsed: false,", APP)
    self.assertIn("restoreLastSidebarStateOnStartup: true,", APP)
    self.assertIn('settings.insert("defaultSidebarCollapsed".into(), false.into());', MAIN)
    self.assertIn('settings.insert("restoreLastSidebarStateOnStartup".into(), true.into());', MAIN)
    self.assertIn("resolveStartupSidebarCollapsed(", APP)
    self.assertIn("resolve_startup_sidebar_collapsed(&settings)", MAIN)

  def test_appearance_exposes_default_and_restore_last_sidebar_startup_controls(self) -> None:
    appearance = APP.split('settingsTab === "appearance"', 1)[1].split('settingsTab === "keybindings"', 1)[0]
    self.assertIn("Default sidebar state", appearance)
    self.assertIn('<option value="expanded">Expanded</option>', appearance)
    self.assertIn('<option value="collapsed">Collapsed</option>', appearance)
    self.assertIn("Restore last sidebar state on startup", appearance)
    self.assertIn("saveRestoreLastSidebarStateOnStartup", appearance)

  def test_collapsed_selection_target_is_square_and_larger_than_every_supported_icon(self) -> None:
    collapsed_css = APP.split(".sidebar.collapsed {", 1)[1].split(".link {", 1)[0]
    self.assertIn("width: 42px; height: 42px", collapsed_css)
    self.assertIn("box-sizing: border-box", collapsed_css)
    icon_control = APP.split('aria-label="Service icon size"', 1)[1].split('</select>', 1)[0]
    icon_sizes = [int(value) for value in re.findall(r'<option value=\{(\d+)\}>[^<]+</option>', icon_control)]
    self.assertEqual(icon_sizes, [18, 21, 24, 28, 34])
    self.assertGreater(42, max(icon_sizes))

  def test_collapsed_rail_is_centered_without_shifting_the_existing_icon_anchor_right(self) -> None:
    self.assertIn("export const COLLAPSED_SIDEBAR_WIDTH_PX = 52;", UI)
    self.assertIn("const COLLAPSED_SIDEBAR_W: f64 = 52.0;", MAIN)
    collapsed_css = APP.split(".sidebar.collapsed {", 1)[1].split(".link {", 1)[0]
    self.assertIn("padding-inline: 5px", collapsed_css)
    self.assertIn("width: 42px", collapsed_css)
    self.assertIn("scrollbar-width: none", collapsed_css)
    self.assertIn("::-webkit-scrollbar", collapsed_css)
    self.assertIn("width: 0; height: 0", collapsed_css)
    self.assertEqual((52 - 42) // 2, 5)


if __name__ == "__main__":
  unittest.main()
