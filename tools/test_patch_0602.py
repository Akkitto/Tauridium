#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.6.2 sidebar spacing and save feedback."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")


class Patch0602Tests(unittest.TestCase):
  def test_sidebar_spacing_preferences_are_persisted_and_bounded(self) -> None:
    for marker in [
      "collapsedServiceSpacing: number;",
      "expandedServiceSpacing: number;",
      "collapsedServiceSpacing: 2,",
      "expandedServiceSpacing: 2,",
    ]:
      self.assertIn(marker, API if marker.endswith("number;") else APP)
    self.assertIn('settings.insert("collapsedServiceSpacing".into(), 2.into());', MAIN)
    self.assertIn('settings.insert("expandedServiceSpacing".into(), 2.into());', MAIN)
    self.assertIn('(\"collapsedServiceSpacing\", 2.0, 24.0)', MAIN)
    self.assertIn('(\"expandedServiceSpacing\", 2.0, 24.0)', MAIN)

  def test_appearance_has_independent_spacing_sliders_with_current_spacing_as_minimum(self) -> None:
    appearance = APP.split('settingsTab === "appearance"', 1)[1].split('settingsTab === "keybindings"', 1)[0]
    self.assertIn("Collapsed icon spacing", appearance)
    self.assertIn("Expanded service spacing", appearance)
    self.assertIn('aria-label="Collapsed service icon spacing"', appearance)
    self.assertIn('aria-label="Expanded service item spacing"', appearance)
    self.assertGreaterEqual(appearance.count('type="range" min="2" max="24" step="1"'), 2)
    self.assertIn('saveAppSetting("collapsedServiceSpacing", appSettings.collapsedServiceSpacing)', appearance)
    self.assertIn('saveAppSetting("expandedServiceSpacing", appSettings.expandedServiceSpacing)', appearance)

  def test_spacing_is_live_previewed_without_changing_minimum_geometry(self) -> None:
    self.assertIn('b.style.setProperty("--collapsed-service-gap", `${appSettings.collapsedServiceSpacing}px`);', APP)
    self.assertIn('b.style.setProperty("--expanded-service-gap", `${appSettings.expandedServiceSpacing}px`);', APP)
    self.assertIn('gap: var(--collapsed-service-gap, 2px)', APP)
    self.assertIn('gap: var(--expanded-service-gap, 2px)', APP)
    self.assertIn('width: 42px; height: 42px; min-height: 42px', APP)

  def test_central_immediate_app_setting_path_shows_saved_toast(self) -> None:
    helper = APP.split("async function saveAppSetting", 1)[1].split("function toggleSidebarCollapsed", 1)[0]
    self.assertIn('showToast("Saved", "success")', helper)
    self.assertIn("appSettings = await setAppSettings", helper)

  def test_direct_immediate_settings_paths_also_show_saved_feedback(self) -> None:
    functions = [
      ("saveWorkspaceDownloadOverride", "chooseGlobalDownloadDirectory"),
      ("saveManagedWorkspaceName", "toggleManagedWorkspaceService"),
      ("toggleManagedWorkspaceService", "persistManagedWorkspaceIcon"),
      ("persistManagedWorkspaceIcon", "saveManagedWorkspaceIcon"),
      ("applyCustomColor", "removeCustomAccent"),
      ("persistServiceIds", "moveService"),
      ("persistWorkspaceIds", "moveManagedWorkspace"),
      ("assignServiceSandbox", "clearSandboxGroup"),
    ]
    for start, end in functions:
      with self.subTest(function=start):
        block = APP.split(f"function {start}", 1)[1].split(f"function {end}", 1)[0]
        self.assertIn('showToast("Saved", "success")', block)


if __name__ == "__main__":
  unittest.main()
