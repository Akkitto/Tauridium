#!/usr/bin/env python3
"""Regression coverage for the v0.8.1 cross-platform Cargo lock fix."""
from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0801Tests(unittest.TestCase):
  def read(self, path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")

  def test_release_identity_remains_synchronized_after_0801(self) -> None:
    version = json.loads(self.read("package.json"))["version"]
    self.assertGreaterEqual(tuple(map(int, version.split("."))), (0, 8, 1))
    self.assertEqual(json.loads(self.read("src-tauri/tauri.conf.json"))["version"], version)
    self.assertIn(f'version = "{version}"', self.read("src-tauri/Cargo.toml"))
    self.assertIn(f'name = "tauridium"\nversion = "{version}"', self.read("src-tauri/Cargo.lock"))
    self.assertIn(f'INIT_VERSION = "{version}"', self.read("tools/init.py"))
    self.assertIn(f'$InitVersion = "{version}"', self.read("tools/init.ps1"))

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
    windows_check = justfile.split("[windows]\ncheck:", 1)[1].split("\n[", 1)[0]
    self.assertIn(strict, windows_check)
    self.assertNotIn("cargo check --manifest-path src-tauri/Cargo.toml --all-targets --all-features --offline", justfile)

  def test_all_feature_lock_graph_is_current(self) -> None:
    result = subprocess.run(
      [
        "cargo",
        "metadata",
        "--manifest-path",
        "src-tauri/Cargo.toml",
        "--all-features",
        "--locked",
        "--offline",
        "--no-deps",
        "--format-version",
        "1",
      ],
      cwd=ROOT,
      text=True,
      capture_output=True,
      check=False,
    )
    self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

  def test_patch_release_metadata_is_present(self) -> None:
    self.assertIn("## [0.8.1] - 2026-09-22", self.read("CHANGELOG.md"))
    self.assertIn('<release version="0.8.1" date="2026-09-22">', self.read("data/dev.brani.tauridium.metainfo.xml"))


if __name__ == "__main__":
  unittest.main()
