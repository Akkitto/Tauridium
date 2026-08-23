#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.6.9 Linux portability fixes."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
VALIDATE = (ROOT / "tools/validate_release.py").read_text(encoding="utf-8")
CI = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")


class Patch0609Tests(unittest.TestCase):
  def test_windows_only_instance_preference_helper_is_not_dead_code_on_linux(self) -> None:
    marker = '#[cfg(any(windows, test))]\nfn reuse_existing_session_setting'
    self.assertIn(marker, MAIN)
    self.assertIn("Windows-only instance preference helper must be cfg-gated on Linux", VALIDATE)

  def test_linux_tray_does_not_rely_on_unsupported_click_events(self) -> None:
    self.assertIn(
      '#[cfg(not(target_os = "linux"))]\nuse tauri::tray::{MouseButton, MouseButtonState, TrayIconEvent};',
      MAIN,
    )
    self.assertIn('#[cfg(not(target_os = "linux"))]\nfn toggle_main', MAIN)
    tray = MAIN.split('let mut tray = TrayIconBuilder::with_id("main-tray")', 1)[1].split(
      'tray.build(app)?;', 1
    )[0]
    self.assertIn('#[cfg(not(target_os = "linux"))]', tray)
    self.assertIn('.show_menu_on_left_click(false)', tray)
    self.assertIn('.on_tray_icon_event(', tray)
    self.assertIn('"show" => show_main(app)', tray)
    self.assertIn("Linux tray click handling must remain platform-gated", VALIDATE)

  def test_linux_external_links_have_gio_fallback(self) -> None:
    external = MAIN.split('fn open_external(url: &str)', 1)[1].split('\n}\n\n#[tauri::command]', 1)[0]
    self.assertIn('Command::new("xdg-open")', external)
    self.assertIn('Command::new("gio")', external)
    self.assertIn('.arg("open")', external)

  def test_linux_ci_runs_clippy_as_part_of_canonical_gates(self) -> None:
    linux_job = CI.split("  linux:", 1)[1].split("  windows-native:", 1)[0]
    self.assertIn("run: just ci", linux_job)
    self.assertIn("components: rustfmt, clippy", linux_job)


if __name__ == "__main__":
  unittest.main()
