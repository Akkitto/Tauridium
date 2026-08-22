#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.6.8 Windows instance-coordination bindings."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARGO = (ROOT / "src-tauri/Cargo.toml").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
VALIDATE = (ROOT / "tools/validate_release.py").read_text(encoding="utf-8")


class Patch0608Tests(unittest.TestCase):
  def test_windows_instance_coordination_enables_security_bindings(self) -> None:
    dependency = CARGO.split("[target.'cfg(windows)'.dependencies]", 1)[1].split("[[bin]]", 1)[0]
    self.assertIn('windows-sys = { version = ">=0.59, <=0.61"', dependency)
    for feature in ("Win32_Foundation", "Win32_Security", "Win32_System_Threading"):
      self.assertIn(f'"{feature}"', dependency)

  def test_security_feature_covers_security_attributes_threading_apis(self) -> None:
    for api in ("CreateEventW", "CreateMutexW"):
      self.assertIn(api, MAIN)
    self.assertIn("'\"Win32_Security\"' not in cargo", VALIDATE)
    self.assertIn("Windows instance coordination requires the windows-sys Win32_Security feature", VALIDATE)


if __name__ == "__main__":
  unittest.main()
