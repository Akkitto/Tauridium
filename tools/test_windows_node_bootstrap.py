"""Execute the actual Windows Node bootstrap block against authored package-manager mocks."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe") if os.name == "nt" else shutil.which("pwsh")


@unittest.skipUnless(POWERSHELL, "Requires Windows PowerShell or PowerShell 7 for native bootstrap mocks")
class WindowsNodeBootstrapTests(unittest.TestCase):
    def run_bootstrap(self, *, installed=False, version="20.19.0", update_fails=False,
                      winget=False, no_changes=False):
        init = (ROOT / "tools/init.ps1").read_text(encoding="utf-8")
        start = init.index("    $NodeReady = $false")
        end = init.index('    Write-Host ("+ Node.js:', start)
        block = init[start:end]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "test.ps1"
            quote = lambda text: "'" + text.replace("'", "''") + "'"
            boolean = lambda value: "$true" if value else "$false"
            fixture = r"""
$ErrorActionPreference = 'Stop'
$script:Calls = New-Object 'System.Collections.Generic.List[string]'
$script:Version = INITIAL_VERSION
$script:Installed = INITIAL_INSTALLED
$script:UpdateFails = UPDATE_FAILS
$ScoopAvailable = $true
$WingetAvailable = WINGET_AVAILABLE
$NoSystemChanges = NO_CHANGES
$DefaultScoopShims = Join-Path $PSScriptRoot 'absent-scoop-shims'
$CargoBin = Join-Path $PSScriptRoot 'absent-cargo-bin'
function node.exe {
  if ($args[0] -ne '--version') { throw 'Unexpected Node invocation' }
  $global:LASTEXITCODE = 0
  Write-Output ('v' + $script:Version)
}
function npm.cmd { throw 'npm must not run during prerequisite selection' }
function scoop {
  if ($args[1] -ne 'nodejs-lts') { throw 'Unexpected Scoop package' }
  $script:Calls.Add('scoop ' + ($args -join ' '))
  switch ($args[0]) {
    'prefix' {
      if ($script:Installed) {
        $global:LASTEXITCODE = 0
        Write-Output $PSScriptRoot
      } else { $global:LASTEXITCODE = 1 }
    }
    'update' {
      if (-not $script:Installed) { throw 'Cannot update absent package' }
      if ($script:UpdateFails) { $global:LASTEXITCODE = 1 }
      else { $script:Version = '24.21.0'; $global:LASTEXITCODE = 0 }
    }
    'install' {
      if ($script:Installed) { throw 'Installing again cannot upgrade an existing package' }
      $script:Installed = $true
      $script:Version = '24.21.0'
      $global:LASTEXITCODE = 0
    }
    default { throw 'Unexpected Scoop command' }
  }
}
function winget.exe {
  $script:Calls.Add('winget fallback')
  $script:Version = '24.21.0'
  $global:LASTEXITCODE = 0
}
try {
ACTUAL_NODE_BOOTSTRAP
  $Result = @{ success = $true; calls = @($script:Calls.ToArray()); version = $script:Version }
} catch {
  $Result = @{ success = $false; calls = @($script:Calls.ToArray()); error = $_.Exception.Message }
}
Write-Output ('TAURIDIUM_RESULT:' + ($Result | ConvertTo-Json -Compress))
"""
            substitutions = {
                "INITIAL_VERSION": quote(version), "INITIAL_INSTALLED": boolean(installed),
                "UPDATE_FAILS": boolean(update_fails), "WINGET_AVAILABLE": boolean(winget),
                "NO_CHANGES": boolean(no_changes), "ACTUAL_NODE_BOOTSTRAP": block,
            }
            for marker, replacement in substitutions.items():
                fixture = fixture.replace(marker, replacement)
            script.write_text(fixture, encoding="utf-8")
            result = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive",
                                     "-ExecutionPolicy", "Bypass", "-File", str(script)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = [line.removeprefix("TAURIDIUM_RESULT:") for line in result.stdout.splitlines()
                     if line.startswith("TAURIDIUM_RESULT:")]
            self.assertEqual(len(lines), 1, result.stdout + result.stderr)
            return json.loads(lines[0])

    def test_existing_unsupported_scoop_lts_is_updated(self):
        for version in ("20.19.0", "22.11.0", "23.0.0", "25.0.0"):
            with self.subTest(version=version):
                result = self.run_bootstrap(installed=True, version=version)
                self.assertTrue(result["success"], result)
                self.assertEqual(result["version"], "24.21.0")
                self.assertEqual(result["calls"], ["scoop prefix nodejs-lts", "scoop update nodejs-lts"])

    def test_missing_scoop_package_is_installed(self):
        result = self.run_bootstrap()
        self.assertTrue(result["success"], result)
        self.assertEqual(result["calls"], ["scoop prefix nodejs-lts", "scoop install nodejs-lts"])

    def test_failed_scoop_upgrade_preserves_winget_fallback(self):
        result = self.run_bootstrap(installed=True, update_fails=True, winget=True)
        self.assertTrue(result["success"], result)
        self.assertEqual(result["calls"], ["scoop prefix nodejs-lts", "scoop update nodejs-lts", "winget fallback"])

    def test_no_system_changes_refuses_old_node_before_package_manager_calls(self):
        result = self.run_bootstrap(installed=True, no_changes=True)
        self.assertFalse(result["success"])
        self.assertIn("-NoSystemChanges", result["error"])
        self.assertEqual(result["calls"], [])

    def test_supported_existing_node_does_not_invoke_package_managers(self):
        for version in ("22.12.0", "24.21.0", "26.0.0"):
            with self.subTest(version=version):
                result = self.run_bootstrap(installed=True, version=version)
                self.assertTrue(result["success"], result)
                self.assertEqual(result["calls"], [])
