#!/usr/bin/env python3
"""Regression coverage for the v0.8.1 cross-platform Cargo lock fix."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0801Tests(unittest.TestCase):
  def read(self, path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")

  def test_release_identity_is_0801_everywhere(self) -> None:
    self.assertEqual(json.loads(self.read("package.json"))["version"], "0.8.1")
    self.assertEqual(json.loads(self.read("src-tauri/tauri.conf.json"))["version"], "0.8.1")
    self.assertIn('version = "0.8.1"', self.read("src-tauri/Cargo.toml"))
    self.assertIn('name = "tauridium"\nversion = "0.8.1"', self.read("src-tauri/Cargo.lock"))
    self.assertIn('INIT_VERSION = "0.8.1"', self.read("tools/init.py"))
    self.assertIn('$InitVersion = "0.8.1"', self.read("tools/init.ps1"))

  def test_flatpak_explicitly_enables_zbus_tokio(self) -> None:
    cargo = self.read("src-tauri/Cargo.toml")
    match = re.search(r"flatpak = \[(.*?)\n\]", cargo, flags=re.DOTALL)
    self.assertIsNotNone(match)
    body = match.group(1)
    self.assertIn('"dep:zbus"', body)
    self.assertIn('"zbus/tokio"', body)
    self.assertIn('"rfd/tokio"', body)

  def test_windows_check_remains_strict_and_all_features(self) -> None:
    justfile = self.read("justfile")
    strict = "cargo check --manifest-path src-tauri/Cargo.toml --all-targets --all-features --locked"
    self.assertGreaterEqual(justfile.count(strict), 2)
    self.assertNotIn("cargo check --manifest-path src-tauri/Cargo.toml --all-targets --all-features --offline", justfile)

  def test_patch_release_metadata_is_present(self) -> None:
    self.assertIn("## [0.8.1] - 2026-09-22", self.read("CHANGELOG.md"))
    self.assertIn('<release version="0.8.1" date="2026-09-22">', self.read("data/dev.brani.tauridium.metainfo.xml"))
    manifest = self.read("flatpak/dev.brani.tauridium.yml")
    self.assertIn("tag: v0.8.1", manifest)
    self.assertIn("__TAURIDIUM_V081_COMMIT__", manifest)


if __name__ == "__main__":
  unittest.main()
