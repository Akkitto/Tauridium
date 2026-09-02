#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.7.4 Windows GUI build-info probing."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE = (ROOT / "tools/test_scoop_install.ps1").read_text(encoding="utf-8")


class Patch0704Tests(unittest.TestCase):
  def test_gui_build_info_probe_waits_for_process_completion(self) -> None:
    self.assertIn("$BuildInfoProcess = Start-Process -FilePath $InstalledExe", SMOKE)
    self.assertIn('-ArgumentList @("--build-info-file", $BuildInfoPath)', SMOKE)
    self.assertIn("-Wait `", SMOKE)
    self.assertIn("-PassThru", SMOKE)
    self.assertIn("$BuildInfoProcess.ExitCode -ne 0", SMOKE)
    self.assertNotIn("& $InstalledExe --build-info-file $BuildInfoPath", SMOKE)

  def test_build_info_file_is_checked_before_reading(self) -> None:
    launch = SMOKE.index("$BuildInfoProcess = Start-Process")
    exists = SMOKE.index("Test-Path -LiteralPath $BuildInfoPath -PathType Leaf", launch)
    read = SMOKE.index("Get-Content -LiteralPath $BuildInfoPath -Raw", exists)
    self.assertLess(launch, exists)
    self.assertLess(exists, read)
    self.assertIn("build-info probe produced no output file", SMOKE)

  def test_runtime_identity_and_target_checks_remain_mandatory(self) -> None:
    self.assertIn('$BuildInfo.name -ne "Tauridium"', SMOKE)
    self.assertIn("$BuildInfo.version -ne $Version", SMOKE)
    self.assertIn('$BuildInfo.buildMode -ne "production"', SMOKE)
    self.assertIn("$BuildInfo.target -ne $Target", SMOKE)


if __name__ == "__main__":
  unittest.main()
