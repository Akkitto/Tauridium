#!/usr/bin/env python3
"""Regression tests for Tauridium's self-contained initialization helper."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("init.py")
SPEC = importlib.util.spec_from_file_location("tauridium_init", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
INIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INIT)


class ParseOsReleaseTests(unittest.TestCase):
  def test_parses_quoted_and_plain_values(self) -> None:
    values = INIT.parse_os_release(
      'ID=debian\nPRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nID_LIKE="debian"\n'
    )
    self.assertEqual(values["ID"], "debian")
    self.assertEqual(values["PRETTY_NAME"], "Debian GNU/Linux 13 (trixie)")
    self.assertEqual(values["ID_LIKE"], "debian")


class PackageManagerTests(unittest.TestCase):
  def test_debian_uses_apt_packages(self) -> None:
    commands = INIT.package_manager_commands(
      {"ID": "debian"},
      root=True,
      available={"apt-get"},
    )
    self.assertEqual(commands[0][0], "apt-get")
    self.assertEqual(commands[0][-1], "update")
    self.assertEqual(commands[1][0], "apt-get")
    self.assertIn("install", commands[1])
    self.assertIn("-y", commands[1])
    self.assertIn("pkg-config", commands[1])
    self.assertIn("libwebkit2gtk-4.1-dev", commands[1])
    self.assertIn("libayatana-appindicator3-dev", commands[1])
    self.assertIn("libxdo-dev", commands[1])

  def test_non_root_commands_are_prefixed_with_sudo(self) -> None:
    commands = INIT.package_manager_commands(
      {"ID": "alpine"},
      root=False,
      available={"apk"},
    )
    self.assertEqual(commands[0][:3], ["sudo", "apk", "add"])

  def test_unknown_distribution_fails_instead_of_guessing(self) -> None:
    with self.assertRaises(INIT.InitError):
      INIT.package_manager_commands(
        {"ID": "unknown", "PRETTY_NAME": "Unknown Linux"},
        root=True,
        available={"apt-get"},
      )


class DependencyDetectionTests(unittest.TestCase):
  @patch.object(INIT.subprocess, "run")
  @patch.object(INIT.shutil, "which", return_value="/usr/bin/cc")
  def test_libxdo_probe_compiles_header_and_links_library(self, _which, run) -> None:
    run.return_value = type("Result", (), {"returncode": 0})()

    self.assertTrue(INIT.libxdo_development_available())

    command = run.call_args.args[0]
    self.assertIn("-lxdo", command)
    self.assertIn("#include <xdo.h>", run.call_args.kwargs["input"])

  @patch.object(INIT.shutil, "which", return_value="/usr/bin/pkg-config")
  @patch.object(INIT.subprocess, "run")
  def test_reports_only_missing_pkg_config_modules(self, run, _which) -> None:
    run.side_effect = [
      type("Result", (), {"returncode": 0})(),
      type("Result", (), {"returncode": 1})(),
    ]
    self.assertEqual(INIT.pkg_config_missing(("present", "missing")), ["missing"])

  @patch.object(INIT.shutil, "which", return_value=None)
  def test_all_modules_are_missing_without_pkg_config(self, _which) -> None:
    self.assertEqual(
      INIT.pkg_config_missing(("one", "two")),
      ["one", "two"],
    )

  @patch.object(INIT, "libxdo_development_available", return_value=True)
  @patch.object(INIT, "pkg_config_missing", return_value=[])
  @patch.object(INIT, "pkg_config_exists")
  @patch.object(INIT.shutil, "which", return_value="/usr/bin/tool")
  def test_appindicator_alternatives_accept_either_provider(
    self,
    _which,
    exists,
    _missing,
    _xdo,
  ) -> None:
    exists.side_effect = lambda module: module == "appindicator3-0.1"
    self.assertEqual(INIT.native_prerequisites_missing(), [])

  @patch.object(INIT, "libxdo_development_available", return_value=True)
  @patch.object(INIT, "pkg_config_missing", return_value=[])
  @patch.object(INIT, "pkg_config_exists", return_value=True)
  @patch.object(INIT.shutil, "which", return_value="/usr/bin/tool")
  def test_debian_libxdo_does_not_require_pkg_config_metadata(
    self,
    _which,
    _exists,
    _missing,
    _xdo,
  ) -> None:
    self.assertNotIn("xdo", INIT.LINUX_PKG_CONFIG_MODULES)
    self.assertEqual(INIT.native_prerequisites_missing(), [])

  @patch.object(INIT, "libxdo_development_available", return_value=False)
  @patch.object(INIT, "pkg_config_missing", return_value=[])
  @patch.object(INIT, "pkg_config_exists", return_value=True)
  @patch.object(INIT.shutil, "which", return_value="/usr/bin/tool")
  def test_missing_libxdo_is_reported_without_pkg_config_assumption(
    self,
    _which,
    _exists,
    _missing,
    _xdo,
  ) -> None:
    self.assertEqual(INIT.native_prerequisites_missing(), ["libxdo-dev"])


class ReleaseIdentityTests(unittest.TestCase):
  def test_release_identity_matches_package_version(self) -> None:
    self.assertEqual(INIT.INIT_VERSION, "0.3.8")
    INIT.validate_release_identity()

  def test_release_identity_rejects_stale_overlay(self) -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      (root / "package.json").write_text('{"version":"0.1.14"}\n', encoding="utf-8")
      with patch.object(INIT, "ROOT", root):
        with self.assertRaisesRegex(INIT.InitError, "extract the release into a new empty directory"):
          INIT.validate_release_identity()

  @patch.object(INIT, "install_linux_system_dependencies")
  @patch.object(INIT, "validate_release_identity")
  def test_native_only_runs_identity_then_native_without_developer_tools(self, identity, native) -> None:
    with patch.object(INIT, "ensure_tauri_cli") as tauri_cli, patch.object(
      INIT, "install_javascript_dependencies"
    ) as npm:
      self.assertEqual(INIT.main(["--native-only"]), 0)
    identity.assert_called_once_with()
    native.assert_called_once_with()
    tauri_cli.assert_not_called()
    npm.assert_not_called()


class TauriCliTests(unittest.TestCase):
  @patch.object(INIT, "command_succeeds", return_value=True)
  @patch.object(INIT.shutil, "which", return_value="/home/test/.cargo/bin/cargo")
  @patch.object(INIT, "run_checked")
  def test_existing_tauri_cli_is_reused(self, run_checked, _which, _succeeds) -> None:
    INIT.ensure_tauri_cli()
    run_checked.assert_not_called()

  @patch.object(INIT, "command_succeeds", side_effect=[False, True])
  @patch.object(INIT.shutil, "which", return_value="/home/test/.cargo/bin/cargo")
  @patch.object(INIT, "run_checked")
  def test_missing_tauri_cli_is_installed_and_reprobed(
    self, run_checked, _which, succeeds
  ) -> None:
    INIT.ensure_tauri_cli()
    run_checked.assert_called_once_with(
      ["cargo", "install", "tauri-cli", "--locked", "--version", "^2"]
    )
    self.assertEqual(succeeds.call_count, 2)

  @patch.object(INIT.shutil, "which", return_value=None)
  def test_missing_cargo_fails_with_actionable_error(self, _which) -> None:
    with self.assertRaisesRegex(INIT.InitError, "cargo was not found in PATH"):
      INIT.ensure_tauri_cli()

  @patch.object(INIT, "install_javascript_dependencies")
  @patch.object(INIT, "ensure_tauri_cli")
  @patch.object(INIT, "install_linux_system_dependencies")
  @patch.object(INIT, "validate_release_identity")
  def test_full_init_ensures_tauri_cli_before_npm(
    self, _identity, _native, tauri_cli, npm
  ) -> None:
    self.assertEqual(INIT.main([]), 0)
    tauri_cli.assert_called_once_with()
    npm.assert_called_once_with()


class NpmPolicyTests(unittest.TestCase):
  def test_release_policy_approves_only_pinned_esbuild(self) -> None:
    package = json.loads((INIT.ROOT / "package.json").read_text(encoding="utf-8"))
    self.assertEqual(package.get("allowScripts"), {"esbuild@0.25.12": True})

  @patch.object(INIT, "validate_npm_policy")
  @patch.object(INIT, "run_checked")
  @patch.object(INIT.shutil, "which", return_value="/usr/bin/tool")
  def test_esbuild_validation_executes_package_bin_instead_of_parsing_it_with_node(
    self,
    _which,
    run_checked,
    _policy,
  ) -> None:
    INIT.install_javascript_dependencies()

    commands = [call.args[0] for call in run_checked.call_args_list]
    self.assertEqual(commands[0], ["npm", "ci"])
    self.assertEqual(commands[1], ["npm", "audit", "--audit-level=high"])
    self.assertEqual(
      commands[2],
      ["npm", "exec", "--offline", "--", "esbuild", "--version"],
    )
    self.assertFalse(any(command and command[0] == "node" for command in commands))


if __name__ == "__main__":
  unittest.main()
