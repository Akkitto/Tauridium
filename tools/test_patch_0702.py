#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.7.2 isolated Scoop layout."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE = (ROOT / "tools/test_scoop_install.ps1").read_text(encoding="utf-8")


class Patch0702Tests(unittest.TestCase):
  def test_isolated_scoop_root_contains_installer_created_mutable_directories(self) -> None:
    for directory in (
      '(Join-Path $ScoopRoot "buckets")',
      '(Join-Path $ScoopRoot "cache")',
      '(Join-Path $ScoopRoot "persist")',
      '(Join-Path $ScoopRoot "shims")',
    ):
      self.assertIn(directory, SMOKE)
    self.assertIn("New-Item -ItemType Directory -Path $Directory -Force", SMOKE)

  def test_scoop_core_is_staged_only_after_root_layout_exists(self) -> None:
    layout = SMOKE.index('(Join-Path $ScoopRoot "shims")')
    copy_core = SMOKE.index('Copy-Item -Path (Join-Path $ScoopCore "*") -Destination $ScoopCurrent -Recurse -Force')
    invoke = SMOKE.index('& $ScoopCommand install $AppSpec')
    self.assertLess(layout, copy_core)
    self.assertLess(copy_core, invoke)

  def test_scoop_harness_still_uses_isolated_root(self) -> None:
    self.assertIn('$env:SCOOP = $ScoopRoot', SMOKE)
    self.assertIn('$env:SCOOP_CACHE = Join-Path $RunRoot "cache"', SMOKE)
    self.assertIn('$env:XDG_CONFIG_HOME = $ConfigRoot', SMOKE)


if __name__ == "__main__":
  unittest.main()
