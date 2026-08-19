#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.4.6 tiered-retention determinism."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0406Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.backup = (ROOT / "src-tauri/src/backup.rs").read_text(encoding="utf-8")

  def test_equal_mtime_ties_prefer_newer_embedded_backup_timestamp(self) -> None:
    sort_body = self.backup.split("candidates.sort_by", 1)[1].split("if candidates.len() <= 1", 1)[0]
    self.assertIn("right.path.file_name().cmp(&left.path.file_name())", sort_body)
    self.assertIn("then_with(|| left.path.cmp(&right.path))", sort_body)

  def test_tiered_retention_has_equal_mtime_regression(self) -> None:
    self.assertIn("tiered_retention_uses_filename_timestamp_when_mtimes_match", self.backup)
    test_body = self.backup.split("fn tiered_retention_uses_filename_timestamp_when_mtimes_match", 1)[1]
    self.assertIn("2026-08-19-080000-000.json", test_body)
    self.assertIn("2026-08-19-120000-000.json", test_body)
    self.assertIn("RetentionMode::Tiered", test_body)

  def test_count_retention_tie_is_consistent_with_newer_filename_policy(self) -> None:
    test_body = self.backup.split("fn count_retention_is_deterministic_when_timestamps_match", 1)[1]
    test_body = test_body.split("#[test]", 1)[0]
    self.assertIn('vec!["tauridium-auto-backup-2026-08-19-120000-003.json"]', test_body)


if __name__ == "__main__":
  unittest.main()
