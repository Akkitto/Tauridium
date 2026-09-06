#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.7.8 robust Windows single-instance activation."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
SINGLE = (ROOT / "src-tauri/src/single_instance.rs").read_text(encoding="utf-8")
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")


class Patch0708Tests(unittest.TestCase):
  def test_named_mutex_is_owned_atomically_and_crash_takeover_is_supported(self) -> None:
    self.assertIn("CreateMutexW(std::ptr::null(), 1", SINGLE)
    self.assertIn("WAIT_ABANDONED", SINGLE)
    self.assertIn("WAIT_OBJECT_0 | WAIT_ABANDONED", SINGLE)
    self.assertIn("ReleaseMutex(self.mutex)", SINGLE)

  def test_activation_pipe_starts_before_tauri_setup_and_acknowledges_requests(self) -> None:
    pre_setup = MAIN.split("tauri::Builder::default()", 1)[0]
    self.assertIn("windows_instance_coordinator.start_activation_listener();", pre_setup)
    self.assertIn("CreateNamedPipeW", SINGLE)
    self.assertIn("GetNamedPipeServerProcessId", SINGLE)
    self.assertIn("AllowSetForegroundWindow(primary_pid)", SINGLE)
    self.assertIn("write_all(pipe, &[ACTIVATION_ACK])", SINGLE)
    self.assertIn("PeekNamedPipe", SINGLE)

  def test_activation_carries_launch_context_and_is_queued_until_ui_is_ready(self) -> None:
    self.assertIn('activation_type: "launch".into()', SINGLE)
    self.assertIn("std::env::args_os()", SINGLE)
    self.assertIn("std::env::current_dir()", SINGLE)
    self.assertIn("state.pending.push(PendingActivation", SINGLE)
    self.assertIn('emit("single-instance-activation", event_request)', SINGLE)

  def test_reactivation_restores_existing_window_without_recreating_it(self) -> None:
    activation = SINGLE.split("fn restore_main_window", 1)[1].split("fn current_activation_request", 1)[0]
    self.assertIn('get_window("main")', activation)
    self.assertIn("window.show()", activation)
    self.assertIn("window.is_minimized()", activation)
    self.assertIn("window.unminimize()", activation)
    self.assertIn("SetForegroundWindow(hwnd.0)", activation)
    self.assertNotIn("window.set_focus()", activation)
    self.assertNotIn("WebviewWindowBuilder", activation)

  def test_startup_race_is_bounded_and_never_fails_open(self) -> None:
    self.assertIn("Duration::from_secs(5)", SINGLE)
    self.assertIn("WaitNamedPipeW", SINGLE)
    self.assertIn("refusing to start a parallel application session", SINGLE)
    preflight = MAIN.split("let windows_instance_coordinator", 1)[1].split("tauri::Builder::default()", 1)[0]
    self.assertIn("std::process::exit(2);", preflight)
    self.assertNotIn("Fail open", preflight)

  def test_legacy_multi_instance_opt_out_is_retired(self) -> None:
    self.assertNotIn("reuseExistingSessionOnLaunch: boolean", API)
    self.assertNotIn("Reuse existing session on launch", APP)
    self.assertNotIn("reuseExistingSessionOnLaunch: true", APP)
    self.assertIn('key != "reuseExistingSessionOnLaunch"', MAIN)


if __name__ == "__main__":
  unittest.main()
