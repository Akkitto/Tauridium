#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.7.14 dependency reliability fixes."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARGO = (ROOT / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
PACKAGE = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
LOCK = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))


class Patch0714Tests(unittest.TestCase):
  def test_flate2_backend_is_explicit_and_cross_platform(self) -> None:
    self.assertIn(
      'flate2 = { version = "=1.1.9", default-features = false, features = ["rust_backend"] }',
      CARGO,
    )
    self.assertIn(
      'zip = { version = "=4.6.1", default-features = false, features = ["deflate-flate2"] }',
      CARGO,
    )

  def test_vitest_is_pinned_to_first_patched_v4_release(self) -> None:
    self.assertEqual(PACKAGE["devDependencies"]["vitest"], "4.1.11")
    self.assertEqual(LOCK["packages"]["node_modules/vitest"]["version"], "4.1.11")
    self.assertEqual(LOCK["packages"]["node_modules/@vitest/mocker"]["version"], "4.1.11")

  def test_devalue_is_pinned_past_reported_advisory_boundary(self) -> None:
    self.assertEqual(PACKAGE["overrides"]["devalue"], "5.9.2")
    self.assertEqual(LOCK["packages"]["node_modules/devalue"]["version"], "5.9.2")

  def test_vitest_4_lock_tree_contains_required_runtime_packages(self) -> None:
    packages = LOCK["packages"]
    expected = {
      "@standard-schema/spec": "1.1.0",
      "chai": "6.2.2",
      "convert-source-map": "2.0.0",
      "es-module-lexer": "2.3.2",
      "obug": "2.1.4",
      "std-env": "4.2.0",
      "tinyexec": "1.3.0",
      "tinyrainbow": "3.1.1",
    }
    for package, version in expected.items():
      self.assertEqual(packages[f"node_modules/{package}"]["version"], version)

  def test_obsolete_vitest_3_vite_node_is_not_locked(self) -> None:
    self.assertNotIn("node_modules/vite-node", LOCK["packages"])


if __name__ == "__main__":
  unittest.main()
