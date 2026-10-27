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
      'flate2 = { version = "=1.1.10", default-features = false, features = ["rust_backend"] }',
      CARGO,
    )
    self.assertIn(
      'zip = { version = "=9.1.2", default-features = false, features = ["deflate-flate2"] }',
      CARGO,
    )

  def test_vitest_mocker_and_spy_are_pinned_to_the_reviewed_v5_cohort(self) -> None:
    # These packages share internal APIs and must advance together. The complete
    # upgraded tree is also checked by the current all-severity npm audit.
    self.assertEqual(PACKAGE["devDependencies"]["vitest"], "5.0.5")
    for package in ("vitest", "@vitest/mocker", "@vitest/spy"):
      self.assertEqual(LOCK["packages"][f"node_modules/{package}"]["version"], "5.0.5")

  def test_devalue_is_locked_past_reported_advisory_boundary_without_an_override(self) -> None:
    pinned = LOCK["packages"]["node_modules/devalue"]["version"]
    self.assertEqual(pinned, "5.9.4")
    self.assertNotIn("devalue", PACKAGE.get("overrides", {}))
    # October 2026 advisories extend the affected range through 5.9.2.
    self.assertGreaterEqual(tuple(int(part) for part in pinned.split(".")), (5, 9, 3))

  def test_vitest_5_lock_tree_contains_reviewed_runtime_packages(self) -> None:
    packages = LOCK["packages"]
    expected = {
      "node_modules/chai": "6.3.0",
      "node_modules/es-module-lexer": "2.3.2",
      "node_modules/vitest/node_modules/obug": "3.0.0",
      "node_modules/std-env": "4.3.0",
      "node_modules/tinyexec": "1.3.1",
      "node_modules/tinybench": "6.2.2",
    }
    for package, version in expected.items():
      self.assertEqual(packages[package]["version"], version)
    # Vitest 5 requires its nested obug 3 even while the Svelte plugin uses
    # obug 2; a top-level-only check would miss the actual runtime dependency.
    self.assertEqual(packages["node_modules/vitest"]["dependencies"]["obug"], "^3.0.0")

  def test_obsolete_vitest_3_vite_node_is_not_locked(self) -> None:
    self.assertNotIn("node_modules/vite-node", LOCK["packages"])


if __name__ == "__main__":
  unittest.main()
