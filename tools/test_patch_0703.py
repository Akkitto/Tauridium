#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.7.3 fresh Scoop update state."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE = (ROOT / "tools/test_scoop_install.ps1").read_text(encoding="utf-8")


class Patch0703Tests(unittest.TestCase):
  def test_harness_recreates_installers_fresh_last_update_state(self) -> None:
    self.assertIn('$ScoopConfigPath = Join-Path $ScoopConfigRoot "config.json"', SMOKE)
    self.assertIn('last_update = [System.DateTime]::Now.ToString("o")', SMOKE)
    self.assertIn('Set-Content -LiteralPath $ScoopConfigPath -Encoding utf8NoBOM', SMOKE)

  def test_fresh_update_state_exists_before_any_scoop_app_command(self) -> None:
    config = SMOKE.index('last_update = [System.DateTime]::Now.ToString("o")')
    install = SMOKE.index('& $ScoopCommand install $AppSpec')
    update = SMOKE.index('& $ScoopCommand update tauridium')
    self.assertLess(config, install)
    self.assertLess(config, update)

  def test_harness_does_not_fabricate_or_fetch_default_main_bucket(self) -> None:
    self.assertNotIn('buckets\\main', SMOKE)
    self.assertNotIn('bucket add main', SMOKE.lower())
    self.assertNotIn('ScoopInstaller/Main', SMOKE)

  def test_shims_are_process_local_and_path_is_restored(self) -> None:
    self.assertIn('$OriginalPath = $env:PATH', SMOKE)
    self.assertIn('$env:PATH = "$(Join-Path $ScoopRoot \'shims\');$OriginalPath"', SMOKE)
    self.assertIn('$env:PATH = $OriginalPath', SMOKE)


if __name__ == "__main__":
  unittest.main()
