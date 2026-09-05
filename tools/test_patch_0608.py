#!/usr/bin/env python3
"""Regression coverage for Tauridium Windows instance-coordination bindings."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARGO = (ROOT / "src-tauri/Cargo.toml").read_text(encoding="utf-8")
SINGLE_INSTANCE = (ROOT / "src-tauri/src/single_instance.rs").read_text(encoding="utf-8")
VALIDATE = (ROOT / "tools/validate_release.py").read_text(encoding="utf-8")


class Patch0608Tests(unittest.TestCase):
  def test_windows_instance_coordination_enables_required_bindings(self) -> None:
    dependency = CARGO.split("[target.'cfg(windows)'.dependencies]", 1)[1].split("[[bin]]", 1)[0]
    self.assertIn('windows-sys = { version = ">=0.59, <=0.61"', dependency)
    for feature in (
      "Win32_Foundation",
      "Win32_Security",
      "Win32_Storage_FileSystem",
      "Win32_System_IO",
      "Win32_System_Pipes",
      "Win32_System_RemoteDesktop",
      "Win32_System_Threading",
      "Win32_UI_WindowsAndMessaging",
    ):
      self.assertIn(f'"{feature}"', dependency)

  def test_security_feature_still_covers_named_mutex_and_pipe_security_attributes(self) -> None:
    for api in ("CreateMutexW", "CreateNamedPipeW", "CreateFileW"):
      self.assertIn(api, SINGLE_INSTANCE)
    self.assertIn("Windows single-instance coordination requires windows-sys feature", VALIDATE)


if __name__ == "__main__":
  unittest.main()
