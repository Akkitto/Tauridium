#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.4.5 Windows-native quality fixes."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0405Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.audit = (ROOT / "src-tauri/src/audit.rs").read_text(encoding="utf-8")

  def test_audit_limit_invariants_are_compile_time_assertions(self) -> None:
    constants = self.audit.split("const MAX_AUDIT_FILE_BYTES", 1)[1].split("static AUDIT_LOCK", 1)[0]
    self.assertIn("const _: () = {", constants)
    self.assertIn("assert!(MAX_READ_ENTRIES >= 5_000);", constants)
    self.assertIn("assert!(MAX_AUDIT_FILE_BYTES >= 1024 * 1024);", constants)
    self.assertIn("assert!(AUDIT_ROTATIONS == 4);", constants)

    test_body = self.audit.split("fn audit_rotation_generations_are_bounded", 1)[1]
    self.assertNotIn("assert!(MAX_READ_ENTRIES", test_body)
    self.assertNotIn("assert!(MAX_AUDIT_FILE_BYTES", test_body)
    self.assertNotIn("assert_eq!(AUDIT_ROTATIONS", test_body)

  def test_patch_does_not_suppress_clippy_constant_assertion_lint(self) -> None:
    self.assertNotIn("allow(clippy::assertions_on_constants)", self.audit)
    self.assertNotIn("expect(clippy::assertions_on_constants)", self.audit)


if __name__ == "__main__":
  unittest.main()
