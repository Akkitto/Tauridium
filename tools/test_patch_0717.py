#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.7.17 portable-export action geometry."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "App.svelte").read_text(encoding="utf-8")


class Patch0717Tests(unittest.TestCase):
  def test_export_action_bar_reserves_deterministic_columns(self) -> None:
    for marker in (
      'class="setting-actions service-export-actions"',
      'class="status-badge service-export-selected-count"',
      'class="secondary sm service-export-select-all"',
      'class="secondary sm service-export-clear"',
      'class="primary sm service-export-submit"',
      '.service-export-actions {\n    display: grid;',
      'grid-template-columns: 104px 82px 62px 184px;',
      '.service-export-actions > * { width: 100%; box-sizing: border-box; }',
      '.service-export-selected-count { justify-content: center; white-space: nowrap; }',
      '.service-export-submit { white-space: nowrap; }',
    ):
      self.assertIn(marker, APP)
    self.assertNotIn('.service-export-actions { flex-wrap: wrap; }', APP)

  def test_dynamic_export_label_keeps_existing_behavior(self) -> None:
    self.assertIn(
      '{selectedServiceExports.length ? "Export selected…" : "Export personal recipes…"}',
      APP,
    )
    self.assertIn(
      'onclick={() => doServiceExport(selectedServiceExports)}',
      APP,
    )

  def test_narrow_settings_layout_stays_deterministic(self) -> None:
    for marker in (
      'grid-template-columns: repeat(3, minmax(0, 1fr));',
      '.service-export-submit { grid-column: 1 / -1; }',
    ):
      self.assertIn(marker, APP)

  def test_configured_service_row_geometry_fix_is_preserved(self) -> None:
    for marker in (
      'class="service-export-row-toggle"',
      'class="managed-identity service-export-identity"',
      '.service-export-row-toggle { position: absolute; inset: 0; z-index: 0;',
      '.service-export-checkbox { width: 17px; height: 17px; margin: 0; flex: none;',
    ):
      self.assertIn(marker, APP)


if __name__ == "__main__":
  unittest.main()
