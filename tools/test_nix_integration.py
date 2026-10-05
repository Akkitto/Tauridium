"""Portable harness regressions; real evaluations run via just nix-integration."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("nix_integration", ROOT / "tools/nix_integration.py")
assert SPEC and SPEC.loader
INTEGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INTEGRATION)


def valid_report():
  return {
    "directAlias": True,
    "homeChecks": {name: {"activation": "/nix/store/example.drv"} for name in INTEGRATION.HOME_CASES},
    "nixosChecks": {name: {"activation" if name.startswith("integrated") else "package": "/nix/store/example.drv"} for name in INTEGRATION.NIXOS_CASES},
  }


class NixIntegrationTests(unittest.TestCase):
  def test_complete_report_is_accepted(self):
    INTEGRATION.validate_report(valid_report())

  def test_missing_or_extra_cases_are_rejected(self):
    for group in ("homeChecks", "nixosChecks"):
      for extra in (False, True):
        report = valid_report()
        if extra:
          report[group]["unverified"] = {"activation": "/nix/store/extra.drv"}
        else:
          del report[group]["direct"]
        with self.subTest(group=group, extra=extra), self.assertRaises(RuntimeError):
          INTEGRATION.validate_report(report)

  def test_alias_mismatch_is_rejected(self):
    report = valid_report()
    report["directAlias"] = False
    with self.assertRaises(RuntimeError):
      INTEGRATION.validate_report(report)

  def test_unevaluated_or_wrong_derivations_are_rejected(self):
    for value in ("", "activation", "/tmp/fake.drv", "/nix/store/not-a-derivation"):
      report = valid_report()
      report["homeChecks"]["direct"]["activation"] = value
      with self.subTest(value=value), self.assertRaises(RuntimeError):
        INTEGRATION.validate_report(report)

  def test_negative_checks_require_the_exact_missing_argument(self):
    for code, error, expected in (
      (1, "error: attribute 'tauridium' missing", True),
      (0, "error: attribute 'tauridium' missing", False),
      (1, "tauridium: network resource missing", False),
      (1, "error: attribute 'inputs' missing", False),
      (1, "", False),
    ):
      with self.subTest(code=code, error=error):
        result = subprocess.CompletedProcess([], code, "", error)
        self.assertEqual(INTEGRATION.missing_argument(result), expected)

  def test_eval_is_locked_read_only_and_uses_fixture_not_host(self):
    with mock.patch.object(INTEGRATION.subprocess, "run") as run:
      INTEGRATION.evaluate("reports.x86_64-linux")
    args, kwargs = run.call_args
    command = args[0]
    self.assertIn("--no-write-lock-file", command)
    self.assertIn("--no-update-lock-file", command)
    self.assertEqual(command[-1], "./tests/nix-integration#reports.x86_64-linux")
    self.assertNotIn("--impure", command)
    self.assertEqual(kwargs["cwd"], ROOT)

  def test_home_manager_dependency_is_test_only_and_immutable(self):
    package_lock = json.loads((ROOT / "flake.lock").read_text(encoding="utf-8"))
    self.assertNotIn("home-manager", package_lock["nodes"]["root"]["inputs"])
    lock = json.loads((ROOT / "tests/nix-integration/flake.lock").read_text(encoding="utf-8"))
    home = lock["nodes"]["home-manager"]
    self.assertEqual(len(home["locked"]["rev"]), 40)
    self.assertTrue(home["locked"]["narHash"].startswith("sha256-"))
    self.assertEqual(home["inputs"]["nixpkgs"], ["tauridium", "nixpkgs"])
    self.assertEqual(lock["nodes"]["tauridium"]["locked"]["path"], "../..")
    for name in ("nixpkgs", "rust-overlay"):
      self.assertEqual(lock["nodes"][name]["locked"], package_lock["nodes"][name]["locked"])

  def test_ci_and_nix_check_require_consumer_evaluations(self):
    workflow = (ROOT / ".github/workflows/nix.yml").read_text(encoding="utf-8")
    recipes = (ROOT / "justfile").read_text(encoding="utf-8")
    self.assertIn("--command just nix-integration", workflow)
    self.assertIn("release/evidence/nix-integration", workflow)
    self.assertIn("just nix-integration", recipes.split("nix-check:\n", 1)[1].split("[unix]", 1)[0])

  def test_documented_release_input_matches_package_version(self):
    version = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
    example = (ROOT / "docs/examples/nix/flake.nix").read_text(encoding="utf-8")
    self.assertIn(f'github:Akkitto/Tauridium/v{version}', example)

  @unittest.skipUnless(shutil.which("node"), "Node is required for the release version generator")
  def test_version_generator_updates_copyable_nix_references(self):
    paths = (
      "src-tauri/tauri.conf.json", "package.json", "package-lock.json",
      "src-tauri/Cargo.toml", "src-tauri/Cargo.lock", "tools/init.py",
      "tools/init.ps1", "README.md", "docs/NIX.md", "docs/examples/nix/flake.nix",
    )
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      for path in paths:
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, destination)
      subprocess.run([shutil.which("node"), str(ROOT / "tools/sync_version.mjs"), "99.98.97"], cwd=root, check=True, capture_output=True)
      for path in ("docs/NIX.md", "docs/examples/nix/flake.nix"):
        source = (root / path).read_text(encoding="utf-8")
        self.assertIn("github:Akkitto/Tauridium/v99.98.97", source)
        old_version = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
        self.assertNotIn(f"github:Akkitto/Tauridium/v{old_version}", source)
      self.assertIn("v99.98.97 cannot discover", (root / "docs/NIX.md").read_text(encoding="utf-8"))

  @unittest.skipUnless(shutil.which("node"), "Node is required for the release version generator")
  def test_version_generator_ignores_cp1252_default_encoding(self):
    original_open = Path.open
    original_read_text = Path.read_text

    def cp1252_open(path, mode="r", buffering=-1, encoding=None, errors=None, newline=None):
      if "b" not in mode and encoding in (None, "locale"):
        encoding = "cp1252"
      return original_open(path, mode, buffering, encoding, errors, newline)

    # Reproduce Windows' locale default without changing the real host locale,
    # Python UTF-8 mode, source files or the Node generator's UTF-8 behavior.
    self.assertRaises(UnicodeDecodeError, "”".encode("utf-8").decode, "cp1252")
    with mock.patch.object(Path, "open", cp1252_open):
      # Negative control: omitting the encoding reproduces the reported failure
      # on the actual generated documentation, even on a UTF-8-default host.
      def locale_read_text(path, *args, **kwargs):
        kwargs.pop("encoding", None)
        return original_read_text(path, *args, **kwargs)

      with mock.patch.object(Path, "read_text", locale_read_text):
        self.assertRaises(UnicodeDecodeError, self.test_version_generator_updates_copyable_nix_references)
      self.test_version_generator_updates_copyable_nix_references()


if __name__ == "__main__":
  unittest.main()
