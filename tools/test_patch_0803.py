#!/usr/bin/env python3
"""Regression coverage for the v0.8.3 Linux release feature matrices."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0803Tests(unittest.TestCase):
  def read(self, path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")

  def recipe(self, platform: str, name: str) -> str:
    justfile = self.read("justfile")
    return justfile.split(f"[{platform}]\n{name}:", 1)[1].split("\n[", 1)[0]

  def test_release_identity_is_0803_everywhere(self) -> None:
    version = "0.8.3"
    self.assertEqual(json.loads(self.read("package.json"))["version"], version)
    self.assertEqual(json.loads(self.read("src-tauri/tauri.conf.json"))["version"], version)
    self.assertIn(f'version = "{version}"', self.read("src-tauri/Cargo.toml"))
    self.assertIn(f'name = "tauridium"\nversion = "{version}"', self.read("src-tauri/Cargo.lock"))
    self.assertIn(f'INIT_VERSION = "{version}"', self.read("tools/init.py"))
    self.assertIn(f'$InitVersion = "{version}"', self.read("tools/init.ps1"))

  def test_unix_cargo_gates_keep_dialog_backends_disjoint(self) -> None:
    for name in ("lint", "check", "test", "doc"):
      recipe = self.recipe("unix", name)
      self.assertNotIn("--all-features", recipe)
      self.assertIn("--locked", recipe)
      self.assertIn("--no-default-features --features flatpak", recipe)

  def test_windows_cargo_gates_remain_strict_all_features(self) -> None:
    for name in ("lint", "check", "test", "doc"):
      recipe = self.recipe("windows", name)
      self.assertIn("--all-features --locked", recipe)

  def test_patch_release_metadata_is_present(self) -> None:
    self.assertIn("## [0.8.3] - 2026-09-23", self.read("CHANGELOG.md"))
    self.assertIn(
      '<release version="0.8.3" date="2026-09-23">',
      self.read("data/dev.brani.tauridium.metainfo.xml"),
    )
    manifest = self.read("flatpak/dev.brani.tauridium.yml")
    self.assertIn("tag: v0.8.3", manifest)
    self.assertIn("__TAURIDIUM_V083_COMMIT__", manifest)


if __name__ == "__main__":
  unittest.main()
