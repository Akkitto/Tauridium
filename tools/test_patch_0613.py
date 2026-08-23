#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.6.13 cross-shell updater config handling."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0613Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    cls.config_path = ROOT / "src-tauri/tauri.no-updater.conf.json"
    cls.config = json.loads(cls.config_path.read_text(encoding="utf-8"))

  def test_unsigned_bundle_uses_config_file_instead_of_inline_json(self) -> None:
    self.assertIn(
      "cargo tauri build --ci --target {{target}} --config src-tauri/tauri.no-updater.conf.json",
      self.justfile,
    )
    self.assertNotIn("--config '{", self.justfile)
    self.assertNotIn('--config "{', self.justfile)

  def test_unsigned_bundle_config_disables_updater_artifacts(self) -> None:
    self.assertEqual(self.config, {"bundle": {"createUpdaterArtifacts": False}})


if __name__ == "__main__":
  unittest.main()
