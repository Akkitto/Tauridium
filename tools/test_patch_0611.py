#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.6.11 release-tool portability fixes."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0611Tests(unittest.TestCase):
  def test_release_archiving_never_reconstructs_relative_paths_lexically(self) -> None:
    package_release = (ROOT / "tools" / "package_release.py").read_text(encoding="utf-8")
    self.assertIn("def tree_entries(root: Path)", package_release)
    self.assertNotIn(".relative_to(", package_release)

  def test_readme_regression_uses_semantic_contract_instead_of_stale_whole_file_hash(self) -> None:
    regression = (ROOT / "tools" / "test_patch_0505.py").read_text(encoding="utf-8")
    self.assertNotIn("README_SHA256", regression)
    self.assertNotIn("hashlib.sha256", regression)
    self.assertIn("**Vite 6 / Vitest 3**", regression)
    self.assertIn("## Licence", regression)


if __name__ == "__main__":
  unittest.main()
