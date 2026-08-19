#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.4.3 color-picker precision fix."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0403Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
    cls.ui = (ROOT / "src/lib/ui.ts").read_text(encoding="utf-8")
    cls.ui_test = (ROOT / "src/lib/ui.test.ts").read_text(encoding="utf-8")

  def test_hex_to_hsl_preserves_fractional_precision(self) -> None:
    self.assertIn("hue,", self.ui)
    self.assertIn("saturation: saturation * 100", self.ui)
    self.assertIn("lightness: lightness * 100", self.ui)
    self.assertNotIn("hue: Math.round(hue)", self.ui)
    self.assertNotIn("saturation: Math.round(saturation * 100)", self.ui)
    self.assertNotIn("lightness: Math.round(lightness * 100)", self.ui)

  def test_frontend_requires_true_color_round_trip(self) -> None:
    self.assertIn('for (const color of ["#ffc131", "#4f46e5", "#16a34a", "#000000", "#ffffff"])', self.ui_test)
    self.assertIn("toBe(color)", self.ui_test)
    self.assertNotIn('toBe("#ffc133")', self.ui_test)

  def test_color_slider_labels_remain_human_readable(self) -> None:
    self.assertIn("{Math.round(colorHue)}°", self.app)
    self.assertIn("{Math.round(colorSaturation)}%", self.app)
    self.assertIn("{Math.round(colorLightness)}%", self.app)


if __name__ == "__main__":
  unittest.main()
