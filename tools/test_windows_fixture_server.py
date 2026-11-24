"""Exercise the actual windowless Windows HTTP fixture and its failure cleanup."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt", "Requires native Windows process/window behavior")
class WindowsFixtureServerTests(unittest.TestCase):
  def run_fixture(self, body: str) -> None:
    shells = [shutil.which("powershell.exe"), shutil.which("pwsh.exe")]
    shells = list(dict.fromkeys(shell for shell in shells if shell))
    self.assertTrue(shells, "Native Windows PowerShell is required")

    def quote(value: str) -> str:
      return "'" + value.replace("'", "''") + "'"

    for shell in shells:
      with self.subTest(shell=shell), tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fixture = root / "fixture space \u00e9"
        fixture.mkdir()
        (fixture / "fixture.html").write_text("synthetic service", encoding="utf-8")
        script = root / "fixture-test.ps1"
        script.write_text(
          "$ErrorActionPreference = 'Stop'\n"
          "Set-StrictMode -Version Latest\n"
          f". {quote(str(ROOT / 'tools/windows_fixture_server.ps1'))}\n"
          f"$Python = {quote(sys.executable)}\n"
          f"$Directory = {quote(str(fixture))}\n"
          "$Listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,0)\n"
          "$Listener.Start(); $Port = $Listener.LocalEndpoint.Port\n"
          + body,
          encoding="utf-8-sig",  # Windows PowerShell 5.1 requires BOM for Unicode.
        )
        result = subprocess.run(
          [shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
           "Bypass", "-File", str(script)],
          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

  def test_serves_paths_with_spaces_without_a_window_and_collects_logs(self) -> None:
    self.run_fixture(r"""
$Listener.Stop()
$Server = Start-HttpFixtureServer -Python $Python -Directory $Directory -Port $Port
$ServerId = $Server.Process.Id
try {
  Wait-HttpFixtureServer $Server
  if (-not $Server.Process.StartInfo.CreateNoWindow -or $Server.Process.StartInfo.UseShellExecute) {
    throw 'Fixture can create a console.'
  }
  $Server.Process.Refresh()
  if ($Server.Process.MainWindowHandle -ne [IntPtr]::Zero) { throw 'Fixture created a visible window.' }
  $Response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/fixture.html" -TimeoutSec 2
  if ($Response.Content -ne 'synthetic service') { throw 'Wrong fixture response.' }
} finally { Stop-HttpFixtureServer $Server }
Stop-HttpFixtureServer $Server
if (Get-Process -Id $ServerId -ErrorAction SilentlyContinue) { throw 'Fixture process leaked.' }
$Log = [IO.File]::ReadAllText((Join-Path $Directory 'server-errors.log'))
if ($Log -notmatch 'GET /fixture.html HTTP/1.1" 200') { throw 'HTTP request log was not collected.' }
if (-not (Test-Path -LiteralPath (Join-Path $Directory 'server.log'))) { throw 'Missing stdout log.' }
""")

  def test_server_exit_is_reported_and_cleaned_up(self) -> None:
    self.run_fixture(r"""
$Server = $null
$Failed = $false
try {
  # Keep the socket occupied so Python must exit rather than bind successfully.
  $Server = Start-HttpFixtureServer -Python $Python -Directory $Directory -Port $Port
  try { Wait-HttpFixtureServer $Server -Seconds 5 }
  catch {
    if ($_.Exception.Message -notmatch 'HTTP fixture server exited with code') { throw }
    $Failed = $true
  }
  if (-not $Failed) { throw 'Occupied port was incorrectly accepted.' }
} finally {
  $Listener.Stop()
  if ($Server) { Stop-HttpFixtureServer $Server }
}
if ([IO.File]::ReadAllText((Join-Path $Directory 'server-errors.log')).Length -eq 0) {
  throw 'Server failure diagnostics were lost.'
}
""")

  def test_http_errors_are_not_hidden_as_startup_timeouts(self) -> None:
    self.run_fixture(r"""
$Listener.Stop()
Remove-Item -LiteralPath (Join-Path $Directory 'fixture.html')
$Server = Start-HttpFixtureServer -Python $Python -Directory $Directory -Port $Port
$Failed = $false
try {
  try { Wait-HttpFixtureServer $Server -Seconds 5 }
  catch {
    if ($_.Exception.Message -notmatch '404') { throw }
    $Failed = $true
  }
  if (-not $Failed) { throw 'Missing fixture was incorrectly accepted.' }
} finally { Stop-HttpFixtureServer $Server }
""")

  def test_cleanup_runs_when_the_consumer_fails(self) -> None:
    self.run_fixture(r"""
$Listener.Stop()
$Server = Start-HttpFixtureServer -Python $Python -Directory $Directory -Port $Port
$ServerId = $Server.Process.Id
$Caught = $false
try {
  try {
    Wait-HttpFixtureServer $Server
    throw 'Synthetic consumer failure'
  } finally { Stop-HttpFixtureServer $Server }
} catch {
  if ($_.Exception.Message -ne 'Synthetic consumer failure') { throw }
  $Caught = $true
}
if (-not $Caught) { throw 'Consumer failure was swallowed.' }
if (Get-Process -Id $ServerId -ErrorAction SilentlyContinue) { throw 'Fixture survived consumer failure.' }
""")


if __name__ == "__main__":
  unittest.main()
