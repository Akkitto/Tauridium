#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.6.7 quick-switcher focus and Windows instance reuse."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
CARGO = (ROOT / "src-tauri/Cargo.toml").read_text(encoding="utf-8")


class Patch0607Tests(unittest.TestCase):
  def test_hiding_focused_service_explicitly_returns_focus_to_shell(self) -> None:
    function = MAIN.split("fn hide_service_webviews", 1)[1].split("// Hide all service webviews", 1)[0]
    self.assertIn('app.get_webview("main")', function)
    self.assertIn("shell.set_focus()", function)
    self.assertIn("*state.active.lock().unwrap() = None;", function)

  def test_quick_switchers_keep_escape_and_same_shortcut_close_paths(self) -> None:
    keydown = APP.split("function handleGlobalKeydown(event: KeyboardEvent)", 1)[1].split("async function createSandboxGroup", 1)[0]
    self.assertIn('if (event.key === "Escape")', keydown)
    self.assertIn("closeQuickSwitcher();", keydown)
    self.assertIn("handleQuickSwitcherToggleShortcut(event)", keydown)
    self.assertIn('case "quickWorkspaceSwitch": openQuickSwitcher("workspace"); break;', APP)
    self.assertIn('case "quickServiceSwitch": openQuickSwitcher("service"); break;', APP)

  def test_advanced_instance_reuse_setting_defaults_on(self) -> None:
    combined = APP + API + MAIN
    for marker in (
      "reuseExistingSessionOnLaunch: boolean;",
      "reuseExistingSessionOnLaunch: true,",
      'settings.insert("reuseExistingSessionOnLaunch".into(), true.into());',
      '"reuseExistingSessionOnLaunch",',
      "Reuse existing session on launch",
      "Starting Tauridium.exe again reopens and focuses the existing session",
    ):
      self.assertIn(marker, combined)

  def test_windows_instance_coordination_exits_before_tauri_when_reuse_is_enabled(self) -> None:
    self.assertIn("windows_instance_preflight()", MAIN)
    self.assertIn("WindowsInstancePreflight::ReuseExisting) => return", MAIN)
    self.assertIn("CreateMutexW", MAIN)
    self.assertIn("CreateEventW", MAIN)
    self.assertIn("SetEvent(event)", MAIN)
    self.assertIn("start_windows_instance_activation_listener", MAIN)
    self.assertIn('get_webview_window("main")', MAIN)
    self.assertIn("window.unminimize()", MAIN)
    self.assertIn("window.set_focus()", MAIN)
    self.assertIn('windows-sys = { version = ">=0.59, <=0.61"', CARGO)

  def test_disabled_setting_preserves_multi_instance_behavior(self) -> None:
    function = MAIN.split("fn windows_instance_preflight()", 1)[1].split("fn start_windows_instance_activation_listener", 1)[0]
    self.assertIn("if already_running && reuse_existing", function)
    self.assertIn("WindowsInstancePreflight::Continue", function)
    self.assertIn("unwrap_or(true)", MAIN.split("fn reuse_existing_session_setting", 1)[1].split("#[cfg(windows)]", 1)[0])


if __name__ == "__main__":
  unittest.main()
