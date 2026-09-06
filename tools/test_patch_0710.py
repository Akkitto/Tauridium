#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.7.10 tray activation and startup diagnostics."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
SINGLE = (ROOT / "src-tauri/src/single_instance.rs").read_text(encoding="utf-8")
DIAGNOSTICS = (ROOT / "src-tauri/src/startup_diagnostics.rs").read_text(encoding="utf-8")
CARGO = (ROOT / "src-tauri/Cargo.toml").read_text(encoding="utf-8")
INSTALLATION = (ROOT / "docs/installation.md").read_text(encoding="utf-8")


class Patch0710Tests(unittest.TestCase):
  def test_secondary_ack_waits_for_completed_ui_activation(self) -> None:
    self.assertIn("mpsc::sync_channel(1)", SINGLE)
    self.assertIn("completion_rx.recv_timeout(ACTIVATION_UI_TIMEOUT)", SINGLE)
    self.assertIn("let result = activate_existing_window(&main_thread_app, request);", SINGLE)
    self.assertIn("let _ = completion.send(result);", SINGLE)
    accept_pos = SINGLE.index("if let Err(error) = target.accept(request)")
    ack_pos = SINGLE.index("write_all(pipe, &[ACTIVATION_ACK])?;")
    self.assertLess(accept_pos, ack_pos)
    self.assertIn("ACK only after accept() returns", SINGLE)

  def test_startup_queued_activation_is_bound_after_visibility_restore(self) -> None:
    self.assertIn("pending: Vec<PendingActivation>", SINGLE)
    self.assertIn("state.pending.push(PendingActivation", SINGLE)
    reveal_pos = MAIN.index("reveal_main_window_after_startup_restore(app.handle(), start_minimized);")
    bind_pos = MAIN.index("windows_activation_target.bind(app.handle().clone())")
    self.assertLess(reveal_pos, bind_pos)
    self.assertIn("Pending requests are completed here", MAIN)

  def test_tray_hidden_window_uses_native_restore_and_verification(self) -> None:
    restore = SINGLE.split("fn restore_main_window", 1)[1].split("fn activate_existing_window", 1)[0]
    self.assertIn('get_window("main")', restore)
    self.assertIn("window.unminimize()", restore)
    self.assertIn("window.show()", restore)
    self.assertIn("ShowWindow(hwnd.0, SW_RESTORE)", restore)
    self.assertIn("ShowWindow(hwnd.0, SW_SHOW)", restore)
    self.assertIn("IsWindowVisible(hwnd.0)", restore)
    self.assertIn("IsIconic(hwnd.0)", restore)
    self.assertIn("SetForegroundWindow(hwnd.0)", restore)
    self.assertIn("Windows declined SetForegroundWindow", restore)
    self.assertNotIn("set_focus", restore)
    self.assertIn("show_existing_main_window(app)", MAIN)

  def test_diagnostics_flag_attaches_console_and_writes_file(self) -> None:
    self.assertIn('STARTUP_DIAGNOSTICS_FLAG: &str = "--startup-diagnostics"', DIAGNOSTICS)
    self.assertIn("AttachConsole(ATTACH_PARENT_PROCESS)", DIAGNOSTICS)
    self.assertIn('open("CONOUT$")', DIAGNOSTICS)
    self.assertIn('.join("Tauridium")\n        .join("diagnostics")', DIAGNOSTICS)
    self.assertIn('"startup-{}-{}.log"', DIAGNOSTICS)
    self.assertIn('"Win32_System_Console"', CARGO)
    self.assertIn("%LOCALAPPDATA%\\Tauridium\\diagnostics", INSTALLATION)

  def test_existing_primary_can_append_to_secondary_diagnostics(self) -> None:
    self.assertIn("diagnostics_log: Option<String>", SINGLE)
    self.assertIn("startup_diagnostics::current_log_path_string()", SINGLE)
    self.assertIn("startup_diagnostics::log_for_path", SINGLE)
    self.assertIn("forwarded_path_is_safe", DIAGNOSTICS)
    self.assertIn('file_name.starts_with("startup-")', DIAGNOSTICS)
    self.assertIn("replay_forwarded_primary_lines_to_console", SINGLE)
    self.assertIn('line.contains(" role=primary ")', DIAGNOSTICS)

  def test_diagnostics_do_not_forward_flag_or_dump_argument_values(self) -> None:
    self.assertIn("STARTUP_DIAGNOSTICS_FLAG)", SINGLE)
    self.assertIn("argument values are intentionally not logged", DIAGNOSTICS)
    self.assertNotIn("std::env::vars()", DIAGNOSTICS)
    self.assertNotIn("std::env::vars_os()", DIAGNOSTICS)

  def test_startup_milestones_and_panics_are_recorded(self) -> None:
    for marker in (
      '"boot.begin"',
      '"tauri.builder"',
      '"tauri.setup.begin"',
      '"identity.migration"',
      '"settings.loaded"',
      '"tray.ready"',
      '"menu.ready"',
      '"window.startup_visibility"',
      '"tauri.setup.completed"',
    ):
      self.assertIn(marker, MAIN)
    self.assertIn('log("process", "panic"', DIAGNOSTICS)

  def test_failed_activation_is_explicitly_rejected_and_diagnosable(self) -> None:
    self.assertIn("const ACTIVATION_NACK: u8 = 0", SINGLE)
    self.assertIn('"activation.rejected"', SINGLE)
    self.assertIn("write_all(pipe, &[ACTIVATION_NACK])", SINGLE)
    self.assertIn('"activation.redirect.rejected"', SINGLE)
    self.assertIn('"activation.pipe.connect_retry"', SINGLE)
    self.assertIn('"activation.pipe.wait_retry"', SINGLE)
    self.assertGreaterEqual(SINGLE.count("replay_forwarded_primary_lines_to_console()"), 3)



if __name__ == "__main__":
  unittest.main()
