#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.7.16 configured-service row layout."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "App.svelte").read_text(encoding="utf-8")


class Patch0716Tests(unittest.TestCase):
  def test_service_row_restores_non_label_identity_layout(self) -> None:
    for marker in (
      'class="managed-row service-export-row"',
      'class="managed-identity service-export-identity"',
      '<strong>{serviceLabel(service)}</strong>',
      '<div class="managed-actions">',
    ):
      self.assertIn(marker, APP)
    self.assertNotIn(
      '<label class="managed-identity service-export-identity service-export-toggle">',
      APP,
    )

  def test_zero_layout_overlay_expands_selection_without_moving_content(self) -> None:
    for marker in (
      'class="service-export-row-toggle"',
      'for={`service-export-${service.id}`}',
      'id={`service-export-${service.id}`}',
      '.service-export-row { position: relative; isolation: isolate; }',
      '.service-export-row-toggle { position: absolute; inset: 0; z-index: 0;',
      '.service-export-identity { position: relative; z-index: 1; flex: 1 1 auto; pointer-events: none; }',
      'pointer-events: auto; cursor: pointer;',
    ):
      self.assertIn(marker, APP)

  def test_action_controls_stay_above_row_selection_overlay(self) -> None:
    self.assertIn(
      '.service-export-row .managed-actions { position: relative; z-index: 1; pointer-events: none; }',
      APP,
    )
    self.assertIn(
      '.service-export-row .managed-actions > * { pointer-events: auto; }',
      APP,
    )
    self.assertIn('>Service settings</button>', APP)
    self.assertIn('title="Move up"', APP)
    self.assertIn('title="Move down"', APP)

  def test_checkbox_geometry_remains_left_aligned_and_neutral(self) -> None:
    self.assertIn(
      '.service-export-checkbox { width: 17px; height: 17px; margin: 0; flex: none;',
      APP,
    )
    self.assertIn(
      '.managed-identity { min-width: 0; display: flex; align-items: center; gap: 10px; }',
      APP,
    )


if __name__ == "__main__":
  unittest.main()
