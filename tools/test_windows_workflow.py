#!/usr/bin/env python3
"""Regression coverage for native Windows 11 + PowerShell development."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WindowsJustfileTests(unittest.TestCase):
  def setUp(self) -> None:
    self.justfile = (ROOT / "justfile").read_text(encoding="utf-8")

  def test_windows_shell_is_builtin_powershell_not_sh(self) -> None:
    self.assertIn(
      '[windows]\nset shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command"]',
      self.justfile,
    )
    self.assertIn('[unix]\nset shell := ["sh", "-eu", "-c"]', self.justfile)
    self.assertIn('set minimum-version := "1.56.0"', self.justfile)

  def test_windows_recipes_use_native_powershell_and_python_launcher(self) -> None:
    self.assertIn("powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/init.ps1", self.justfile)
    self.assertIn("powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/init.ps1 -SelfTest", self.justfile)
    self.assertIn('powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/python.ps1 tools/validate_release.py', self.justfile)
    self.assertIn('powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/python.ps1 -m unittest discover -s tools -p "test_*.py"', self.justfile)
    self.assertIn('powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/python.ps1 tools/package_release.py', self.justfile)
    self.assertIn('powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/clean.ps1', self.justfile)


class WindowsBootstrapTests(unittest.TestCase):
  def setUp(self) -> None:
    self.script = (ROOT / "tools/init.ps1").read_text(encoding="utf-8")

  def test_bootstrap_covers_windows_tauri_toolchain(self) -> None:
    for marker in (
      'Microsoft.VisualStudio.BuildTools',
      'Microsoft.VisualStudio.2022.BuildTools',
      'Microsoft.EdgeWebView2Runtime',
      'Rustlang.Rustup',
      'OpenJS.NodeJS.LTS',
      'Python.Python.3.13',
      'Git.Git',
      'stable-msvc',
      'cargo.exe install tauri-cli --locked --version "^2"',
      'cargo.exe install cargo-audit --locked',
      'VBSCRIPT',
      '& npm.cmd ci',
      '& npm.cmd audit --audit-level=high',
      '& npm.cmd exec --offline -- esbuild --version',
    ):
      self.assertIn(marker, self.script)

  def test_bootstrap_avoids_custom_function_and_scriptblock_dispatch(self) -> None:
    # Windows PowerShell 5.1 must execute the initializer linearly. This avoids
    # the missing-function failure from 0.2.0 and invalid call-operator target
    # failure from 0.2.1.
    self.assertNotIn('function ', self.script.lower())
    self.assertNotIn('$MsvcBuildToolsTask', self.script)
    self.assertIn('[switch]$SelfTest', self.script)
    self.assertIn('System.Management.Automation.Language.Parser', self.script)
    self.assertIn('Tauridium Windows PowerShell bootstrap self-test passed.', self.script)

  def test_bootstrap_contains_no_backtick_escape_hazards(self) -> None:
    # Backticks inside double-quoted diagnostics can escape the terminating quote
    # under Windows PowerShell 5.1 and make the whole initializer unparsable.
    self.assertNotIn("`", self.script)

  def test_expected_native_probe_failures_are_isolated(self) -> None:
    # Windows PowerShell 5.1 can promote redirected native stderr into a
    # terminating error when ErrorActionPreference is Stop. Capability probes
    # must capture exit status under SilentlyContinue and restore strict mode.
    for marker in (
      '$SavedErrorActionPreference = $ErrorActionPreference',
      '$ErrorActionPreference = "SilentlyContinue"',
      '$NativeProbeExitCode',
      '$PythonProbeExitCode',
      '$CargoTauriProbeExitCode',
      '$CargoAuditProbeExitCode',
    ):
      self.assertIn(marker, self.script)
    self.assertIn('echo Tauridium-native-probe-self-test 1>&2 & exit /b 7', self.script)


  def test_bootstrap_refreshes_persisted_path_before_node_detection(self) -> None:
    refresh = self.script.index('[Environment]::GetEnvironmentVariable("Path", "Machine")')
    node = self.script.index('$NodeCommand = Get-Command -Name "node.exe"')
    self.assertLess(refresh, node)
    self.assertIn('$DefaultScoopShims = Join-Path $HOME "scoop\\shims"', self.script)

  def test_bootstrap_prefers_scoop_then_falls_back_to_winget(self) -> None:
    package_pairs = (
      ('+ scoop install nodejs-lts', '+ winget.exe install OpenJS.NodeJS.LTS (fallback)'),
      ('+ scoop install python', '+ winget.exe install Python.Python.3.13 (fallback)'),
      ('+ scoop install git', '+ winget.exe install Git.Git (fallback)'),
      ('+ scoop install rustup', '+ winget.exe install Rustlang.Rustup (fallback)'),
    )
    for scoop_marker, winget_marker in package_pairs:
      self.assertIn(scoop_marker, self.script)
      self.assertIn(winget_marker, self.script)
      self.assertLess(self.script.index(scoop_marker), self.script.index(winget_marker))
    self.assertIn('+ Windows package manager: Scoop preferred', self.script)

  def test_python_runner_supports_launcher_and_scoop_python(self) -> None:
    runner = (ROOT / "tools/python.ps1").read_text(encoding="utf-8")
    for marker in ('"py.exe"', '"python.exe"', '"python3.exe"', '"-3"', '"--version"'):
      self.assertIn(marker, runner)
    self.assertNotIn("`", runner)
    self.assertIn('tools/python.ps1', self.script)

  def test_bootstrap_is_powershell_native(self) -> None:
    lowered = self.script.lower()
    for forbidden in ("wsl.exe", "bash.exe", "git-bash", "nu.exe", "nushell"):
      self.assertNotIn(forbidden, lowered)

  def test_visual_studio_config_covers_x64_arm64_and_windows_11_sdk(self) -> None:
    config = json.loads((ROOT / ".vsconfig").read_text(encoding="utf-8"))
    components = set(config["components"])
    self.assertIn("Microsoft.VisualStudio.Component.VC.Tools.x86.x64", components)
    self.assertIn("Microsoft.VisualStudio.Component.VC.Tools.ARM64", components)
    self.assertIn("Microsoft.VisualStudio.Component.Windows11SDK.26100", components)


class WindowsCiTests(unittest.TestCase):
  def test_windows_ci_runs_full_gates_under_pwsh(self) -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    self.assertIn("windows-native:", ci)
    self.assertIn("shell: pwsh", ci)
    for command in ("just init-self-test", "just init-native", "just check", "just test", "just build", "just package"):
      self.assertIn(command, ci)

  def test_release_windows_build_no_longer_forces_bash_for_version_sync(self) -> None:
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    block = release.split("- name: Sync app version to the tag", 1)[1].split(
      "- name: Install Linux WebView deps", 1
    )[0]
    self.assertIn('node tools/sync_version.mjs "${{ github.ref_name }}"', block)
    self.assertNotIn("shell: bash", block)


if __name__ == "__main__":
  unittest.main()
