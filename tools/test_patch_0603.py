#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.6.3 window restore and spacing-preview fixes."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")


class Patch0603Tests(unittest.TestCase):
  def test_startup_relies_on_single_window_state_plugin_restore(self) -> None:
    plugin = MAIN.split("tauri_plugin_window_state::Builder::new()", 1)[1].split(".build(),", 1)[0]
    reveal = MAIN.split("fn reveal_main_window_after_startup_restore", 1)[1].split("fn show_main", 1)[0]
    self.assertNotIn('skip_initial_state("main")', plugin)
    self.assertNotIn("restore_state(", reveal)
    self.assertNotIn("fn restore_main_window_state", MAIN)
    self.assertIn("window.show();", reveal)

  def test_hidden_window_reveal_does_not_replay_maximized_or_fullscreen_state(self) -> None:
    show = MAIN.split("fn show_main(app: &AppHandle)", 1)[1].split("fn toggle_main", 1)[0]
    toggle = MAIN.split("fn toggle_main(app: &AppHandle)", 1)[1].split("// Open/close devtools", 1)[0]
    for block in (show, toggle):
      self.assertNotIn("restore_state(", block)
      self.assertNotIn("restore_main_window_state", block)
      self.assertIn(".show();", block)
    self.assertIn("save_main_window_state(app);", toggle)

  def test_spacing_preview_switches_sidebar_to_the_mode_being_tuned(self) -> None:
    appearance = APP.split('settingsTab === "appearance"', 1)[1].split('settingsTab === "keybindings"', 1)[0]
    self.assertIn('previewServiceSpacing("collapsedServiceSpacing", Number(event.currentTarget.value), true)', appearance)
    self.assertIn('previewServiceSpacing("expandedServiceSpacing", Number(event.currentTarget.value), false)', appearance)
    helper = APP.split("function previewServiceSpacing", 1)[1].split("async function saveServiceSpacing", 1)[0]
    self.assertIn("appSettings.sidebarCollapsed = collapsed;", helper)
    self.assertIn("syncSidebarWidth();", helper)

  def test_spacing_commit_persists_spacing_and_matching_sidebar_state_together(self) -> None:
    helper = APP.split("async function saveServiceSpacing", 1)[1].split("async function moveManagedService", 1)[0]
    self.assertIn("[key]: value,", helper)
    self.assertIn("sidebarCollapsed: collapsed,", helper)
    self.assertIn('showToast("Saved", "success")', helper)
    self.assertIn("appSettings = await getAppSettings();", helper)


if __name__ == "__main__":
  unittest.main()
