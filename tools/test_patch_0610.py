#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.6.10 build-quality hardening."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0610Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")
    cls.package = (ROOT / "package.json").read_text(encoding="utf-8")
    cls.justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    cls.gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    cls.ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    cls.release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    cls.packager = (ROOT / "tools/package_release.py").read_text(encoding="utf-8")

  def test_vite_and_svelte_configuration_are_retained_for_active_frontend_pipeline(self) -> None:
    self.assertTrue((ROOT / "vite.config.ts").is_file())
    self.assertTrue((ROOT / "svelte.config.js").is_file())
    self.assertTrue((ROOT / "vite-env.d.ts").is_file())
    self.assertIn('"dev": "vite"', self.package)
    self.assertIn('"build": "vite build"', self.package)
    self.assertIn('"test": "vitest run"', self.package)
    self.assertIn("**Vite 6 / Vitest 3**", self.readme)

  def test_proven_dormant_project_files_are_removed(self) -> None:
    self.assertFalse((ROOT / "src-tauri/icons/tauridium_custom.svg").exists())
    self.assertFalse((ROOT / "src-tauri/tauri.conf.dev.json").exists())

  def test_gitignore_is_project_specific_and_keeps_required_outputs_ignored(self) -> None:
    self.assertLessEqual(len(self.gitignore.splitlines()), 60)
    self.assertNotIn("toptal.com/developers/gitignore", self.gitignore)
    for marker in (
      "node_modules/",
      "dist/",
      "target/",
      "__pycache__/",
      "release/",
      ".tauridium-source-manifest.json",
    ):
      self.assertIn(marker, self.gitignore)

  def test_supply_chain_guard_is_a_canonical_quality_and_packaging_gate(self) -> None:
    self.assertIn("quality: rust-supply-chain fmt-check lint check test", self.justfile)
    self.assertIn("audit: rust-supply-chain-host", self.justfile)
    self.assertIn("tools/check_rust_supply_chain.py --cache", self.justfile)
    self.assertIn("require_rust_supply_chain_clean()", self.packager)
    self.assertIn('[sys.executable, "tools/check_rust_supply_chain.py"]', self.packager)

  def test_ci_scans_restored_cargo_cache_before_building(self) -> None:
    self.assertEqual(self.ci.count("run: just rust-supply-chain-host"), 2)
    self.assertEqual(self.release.count("run: just rust-supply-chain-host"), 2)


if __name__ == "__main__":
  unittest.main()
