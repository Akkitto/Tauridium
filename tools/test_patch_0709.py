#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.7.9 identity-migration marker restoration."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")


class Patch0709Tests(unittest.TestCase):
  def test_identity_directory_marker_set_is_defined_and_complete(self) -> None:
    expected_markers = (
      "app_settings.json",
      "local_profile.json",
      "session.json",
      "sessions",
      "service-icons",
      "recipes",
      "audit",
      "backups",
    )
    self.assertIn("const IDENTITY_DIRECTORY_MARKERS: [&str; 8] = [", MAIN)
    for marker in expected_markers:
      self.assertIn(f'"{marker}"', MAIN)

  def test_identity_migration_helpers_use_the_marker_set(self) -> None:
    self.assertIn("IDENTITY_DIRECTORY_MARKERS\n        .iter()", MAIN)
    self.assertGreaterEqual(MAIN.count("IDENTITY_DIRECTORY_MARKERS"), 3)


if __name__ == "__main__":
  unittest.main()
