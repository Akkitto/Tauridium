#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.4.2 quality fixes."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0402Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
    cls.main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")

  def test_quick_switcher_uses_dialog_compatible_container(self) -> None:
    self.assertIn('<div class="quick-switcher" role="dialog"', self.app)
    self.assertNotIn('<section class="quick-switcher" role="dialog"', self.app)

  def test_shared_storage_identifier_is_exercised_by_tests(self) -> None:
    self.assertIn("fn shared_sandbox_storage_identifier_is_stable_and_distinct()", self.main)
    self.assertIn('storage_identifier("service-a", Some("proton"))', self.main)

  def test_services_in_sandbox_avoids_filter_map_bool_then_lint(self) -> None:
    self.assertIn('.filter(|(_, value)| value.as_str() == Some(sandbox_id))', self.main)
    self.assertIn('.map(|(service_id, _)| service_id.clone())', self.main)
    self.assertNotIn('.then(|| service_id.clone())', self.main)

  def test_single_accent_color_validation_is_direct(self) -> None:
    self.assertIn('let accent_color = object', self.main)
    self.assertNotIn('for key in ["accentColor"]', self.main)


if __name__ == "__main__":
  unittest.main()
