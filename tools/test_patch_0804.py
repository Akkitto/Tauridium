#!/usr/bin/env python3
"""Regression coverage for the v0.8.4 release-worktree isolation fix."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0804Tests(unittest.TestCase):
  def read(self, path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")

  def test_vitest_only_discovers_canonical_frontend_sources(self) -> None:
    config = self.read("vite.config.ts")
    self.assertIn('import { defineConfig } from "vitest/config";', config)
    self.assertIn('include: ["src/**/*.test.ts"]', config)
    self.assertNotIn('include: ["**/*.{test,spec}.?(c|m)[jt]s?(x)"]', config)

  def test_generated_flatpak_worktrees_remain_ignored(self) -> None:
    ignore = self.read(".gitignore")
    for path in (".flatpak-builder/", "build-dir/", "repo/"):
      self.assertIn(path, ignore)

  def test_release_identity_is_0804_everywhere(self) -> None:
    version = "0.8.4"
    self.assertEqual(json.loads(self.read("package.json"))["version"], version)
    self.assertEqual(json.loads(self.read("src-tauri/tauri.conf.json"))["version"], version)
    self.assertIn(f'version = "{version}"', self.read("src-tauri/Cargo.toml"))
    self.assertIn(f'name = "tauridium"\nversion = "{version}"', self.read("src-tauri/Cargo.lock"))
    self.assertIn(f'INIT_VERSION = "{version}"', self.read("tools/init.py"))
    self.assertIn(f'$InitVersion = "{version}"', self.read("tools/init.ps1"))

  def test_patch_release_metadata_is_present(self) -> None:
    self.assertIn("## [0.8.4] - 2026-09-23", self.read("CHANGELOG.md"))
    self.assertIn(
      '<release version="0.8.4" date="2026-09-23">',
      self.read("data/dev.brani.tauridium.metainfo.xml"),
    )
    manifest = self.read("flatpak/dev.brani.tauridium.yml")
    self.assertIn("tag: v0.8.4", manifest)
    pins = re.findall(r"^\s*commit:\s*(\S+)$", manifest, flags=re.MULTILINE)
    self.assertEqual(len(pins), 1)
    self.assertRegex(pins[0], r"^(?:__TAURIDIUM_V084_COMMIT__|[0-9a-f]{40})$")


if __name__ == "__main__":
  unittest.main()
