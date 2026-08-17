#!/usr/bin/env python3
"""Regression coverage for the English-only source gate."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("check_english", ROOT / "tools/check_english.py")
assert SPEC and SPEC.loader
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class EnglishOnlyTests(unittest.TestCase):
  def test_current_tracked_tree_passes(self) -> None:
    failures = []
    for path in CHECK.tracked_files():
      failures.extend((path, *item) for item in CHECK.scan_file(path))
    self.assertEqual(failures, [])

  def test_legacy_language_prose_is_rejected(self) -> None:
    # Encoded fixture prevents the regression test from introducing banned prose itself.
    sample = bytes.fromhex("6c6520736572766575722065737420696e6a6f69676e61626c6520646570756973206c612066656e65747265").decode("ascii")
    self.assertTrue(CHECK.scan_text(sample))

  def test_plain_english_is_accepted(self) -> None:
    self.assertEqual(CHECK.scan_text("The server is unreachable from the application window."), [])


if __name__ == "__main__":
  unittest.main()
