#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.6.7 quick-switcher focus and its superseded instance reuse path."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
SINGLE_INSTANCE = (ROOT / "src-tauri/src/single_instance.rs").read_text(encoding="utf-8")
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

  def test_instance_reuse_is_now_mandatory_instead_of_user_optional(self) -> None:
    self.assertNotIn("reuseExistingSessionOnLaunch: boolean;", API)
    self.assertNotIn("reuseExistingSessionOnLaunch: true,", APP)
    self.assertNotIn("Reuse existing session on launch", APP)
    self.assertIn('key != "reuseExistingSessionOnLaunch"', MAIN)

  def test_windows_instance_coordination_exits_before_tauri_after_ack(self) -> None:
    self.assertIn("windows_instance_preflight()", MAIN)
    self.assertIn("WindowsInstancePreflight::ActivatedExisting) => return", MAIN)
    self.assertIn("CreateMutexW", SINGLE_INSTANCE)
    self.assertIn("CreateNamedPipeW", SINGLE_INSTANCE)
    self.assertIn("ACTIVATION_ACK", SINGLE_INSTANCE)
    self.assertIn("AllowSetForegroundWindow", SINGLE_INSTANCE)
    self.assertIn('get_webview_window("main")', SINGLE_INSTANCE)
    self.assertIn("window.unminimize()", SINGLE_INSTANCE)
    self.assertIn("SetForegroundWindow(hwnd.0)", SINGLE_INSTANCE)
    self.assertNotIn("window.set_focus()", SINGLE_INSTANCE)
    self.assertIn('windows-sys = { version = ">=0.59, <=0.61"', CARGO)

  def test_parallel_instance_opt_out_is_removed(self) -> None:
    self.assertNotIn("if already_running && reuse_existing", SINGLE_INSTANCE)
    self.assertIn("refusing to start a parallel application session", SINGLE_INSTANCE)
    self.assertIn("std::process::exit(2);", MAIN)


if __name__ == "__main__":
  unittest.main()
