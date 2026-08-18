#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0319Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.ui = (ROOT / "src/lib/ui.ts").read_text(encoding="utf-8")
    cls.ui_test = (ROOT / "src/lib/ui.test.ts").read_text(encoding="utf-8")

  def test_monthly_backup_schedule_uses_calendar_months(self) -> None:
    body = self.ui.split('if (schedule === "monthly") {', 1)[1].split('  }\n  const elapsed', 1)[0]
    for marker in (
      'const due = new Date(lastRun);',
      'const day = due.getDate();',
      'due.setDate(1);',
      'due.setMonth(due.getMonth() + 1);',
      'due.setDate(Math.min(day, lastDay));',
      'return now >= due.getTime();',
    ):
      self.assertIn(marker, body)

  def test_monthly_backup_regression_covers_real_boundaries(self) -> None:
    for marker in (
      'automaticBackupDue("monthly", day, day * 31, false, false)).toBe(false)',
      'automaticBackupDue("monthly", day, day * 32, false, false)).toBe(true)',
      'uses calendar-month boundaries and clamps month ends',
      'const jan31 = new Date(2026, 0, 31, 8, 5, 0, 0).getTime();',
      'const feb28 = new Date(2026, 1, 28, 8, 5, 0, 0).getTime();',
      'const leapJan31 = new Date(2028, 0, 31, 8, 5, 0, 0).getTime();',
      'const leapFeb29 = new Date(2028, 1, 29, 8, 5, 0, 0).getTime();',
    ):
      self.assertIn(marker, self.ui_test)


if __name__ == "__main__":
  unittest.main()
