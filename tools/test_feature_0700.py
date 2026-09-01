#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.7.0 Scoop distribution readiness."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
  sys.path.insert(0, str(TOOLS))


def load_scoop():
  path = TOOLS / "scoop.py"
  spec = importlib.util.spec_from_file_location("tauridium_scoop", path)
  if spec is None or spec.loader is None:
    raise RuntimeError("unable to load Scoop packaging module")
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


class Feature0700Tests(unittest.TestCase):
  def test_reference_manifest_matches_scoop_extras_shape(self) -> None:
    scoop = load_scoop()
    scoop.validate_template()
    manifest = json.loads((ROOT / "packaging/scoop/tauridium.json.template").read_text())

    self.assertEqual(tuple(manifest), scoop.ROOT_FIELD_ORDER)
    self.assertEqual(manifest["license"], "MIT")
    self.assertEqual(tuple(manifest["architecture"]), ("64bit", "arm64"))
    self.assertEqual(manifest["shortcuts"], [["tauridium.exe", "Tauridium"]])
    self.assertEqual(manifest["checkver"], "github")
    self.assertNotIn("bin", manifest)
    self.assertNotIn("persist", manifest)
    self.assertIn("$version", manifest["autoupdate"]["architecture"]["64bit"]["url"])
    self.assertIn("$version", manifest["autoupdate"]["architecture"]["arm64"]["url"])

  def test_portable_windows_archives_are_minimal_deterministic_and_hashed(self) -> None:
    scoop = load_scoop()
    targets = tuple(scoop.WINDOWS_TARGETS)
    with tempfile.TemporaryDirectory(prefix="tauridium-scoop-test-") as temp_dir:
      root = Path(temp_dir)
      runtime = root / "tauridium.exe"
      runtime.write_bytes(b"MZ\x00Tauridium portable fixture")

      for target in targets:
        with mock.patch.object(
          scoop,
          "inspect_runtime",
          return_value=SimpleNamespace(target=target),
        ):
          first, first_hash = scoop.package_portable(runtime, target, root / "first")
          second, second_hash = scoop.package_portable(runtime, target, root / "second")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(first_hash.read_text(), second_hash.read_text())
        self.assertEqual(scoop.sha256(first), scoop.read_checksum(first_hash))
        with zipfile.ZipFile(first) as archive:
          self.assertEqual(archive.namelist(), ["tauridium.exe"])
          self.assertEqual(archive.getinfo("tauridium.exe").date_time, scoop.ZIP_TIME)

  def test_rendered_release_manifest_uses_hashes_from_both_portable_archives(self) -> None:
    scoop = load_scoop()
    with tempfile.TemporaryDirectory(prefix="tauridium-scoop-manifest-") as temp_dir:
      assets = Path(temp_dir)
      runtime = assets / "fixture.exe"
      runtime.write_bytes(b"MZ\x00portable")
      expected: dict[str, str] = {}
      for target, (_asset_arch, scoop_arch) in scoop.WINDOWS_TARGETS.items():
        with mock.patch.object(
          scoop,
          "inspect_runtime",
          return_value=SimpleNamespace(target=target),
        ):
          portable, _sidecar = scoop.package_portable(runtime, target, assets)
        expected[scoop_arch] = scoop.sha256(portable)

      output = assets / f"tauridium-{scoop.version()}-scoop.json"
      document = scoop.generate_release_manifest(assets, output)
      scoop.validate_release_manifest(output, assets)
      self.assertEqual(document["architecture"]["64bit"]["hash"], expected["64bit"])
      self.assertEqual(document["architecture"]["arm64"]["hash"], expected["arm64"])
      self.assertIn(f"/download/v{scoop.version()}/", document["architecture"]["64bit"]["url"])

  def test_local_manifest_can_exercise_scoop_checkver_and_autoupdate(self) -> None:
    scoop = load_scoop()
    with tempfile.TemporaryDirectory(prefix="tauridium-scoop-local-") as temp_dir:
      root = Path(temp_dir)
      runtime = root / "fixture.exe"
      runtime.write_bytes(b"MZ\x00portable")
      target = "x86_64-pc-windows-msvc"
      with mock.patch.object(
        scoop,
        "inspect_runtime",
        return_value=SimpleNamespace(target=target),
      ):
        portable, _sidecar = scoop.package_portable(runtime, target, root)
      output = root / "tauridium.json"
      scoop.generate_local_manifest(
        portable,
        target,
        "http://127.0.0.1/current.zip",
        output,
        checkver_url="http://127.0.0.1/version.txt",
        autoupdate_url="http://127.0.0.1/tauridium-$version.zip",
      )
      manifest = json.loads(output.read_text(encoding="utf-8"))
      self.assertEqual(manifest["checkver"]["url"], "http://127.0.0.1/version.txt")
      self.assertEqual(manifest["checkver"]["regex"], r"([\d.]+)")
      self.assertIn("$version", manifest["autoupdate"]["architecture"]["64bit"]["url"])

  def test_release_collection_makes_portable_assets_mandatory_for_windows(self) -> None:
    release_assets = (TOOLS / "release_assets.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")

    self.assertIn("from scoop import package_portable", release_assets)
    self.assertIn("portable, portable_checksum = package_portable(runtime_path, target, output_dir)", release_assets)
    self.assertIn("just scoop-verify-collected ${{ matrix.target }}", workflow)
    self.assertIn("name: native-${{ matrix.target }}", workflow)
    self.assertIn("path: release/native/*", workflow)
    self.assertIn("scoop-verify-collected target", justfile)

  def test_release_runs_clean_scoop_integration_for_x64_and_arm64(self) -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    smoke = (TOOLS / "test_scoop_install.ps1").read_text(encoding="utf-8")

    self.assertIn("Scoop clean-machine ${{ matrix.label }}", workflow)
    self.assertIn("repository: ScoopInstaller/Scoop", workflow)
    self.assertIn("ref: v0.5.3", workflow)
    self.assertIn("os: windows-latest", workflow)
    self.assertIn("os: windows-11-arm", workflow)
    self.assertIn("needs: [handoff, build, scoop]", workflow)
    for marker in (
      "& $ScoopCommand install $AppSpec",
      "& $CheckverCommand -App $AutoupdateManifestPath -Update -ThrowError",
      "Scoop autoupdate produced an unexpected portable SHA-256.",
      "$PreviousInstallInfo.bucket -ne $BucketName",
      "& $ScoopCommand update tauridium",
      "$InstallInfo.bucket -ne $BucketName",
      "& $ScoopCommand uninstall tauridium",
      "--build-info-file",
      "Scoop did not create the Tauridium Start Menu shortcut.",
      "Tauridium application data did not survive Scoop update.",
      "External Tauridium application data did not survive Scoop reinstall.",
    ):
      self.assertIn(marker, smoke)

  def test_release_publishes_submission_ready_manifest_and_checksums(self) -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    release_assets = (TOOLS / "release_assets.py").read_text(encoding="utf-8")
    self.assertIn("just scoop-release-manifest release/published-assets", workflow)
    self.assertIn("just scoop-validate-manifest", workflow)
    self.assertIn('"release/published-assets/tauridium-${VERSION}-scoop.json"', workflow)
    self.assertIn("just release-checksums release/published-assets", workflow)
    self.assertIn("Windows releases", release_assets)
    self.assertIn("generated Scoop manifest", release_assets)

  def test_documentation_handoff_includes_scoop_distribution_guidance(self) -> None:
    package_release = (TOOLS / "package_release.py").read_text(encoding="utf-8")
    self.assertIn('ROOT / "docs" / "installation.md"', package_release)
    self.assertIn('"docs/installation.md"', package_release)
    self.assertIn('ROOT / "packaging" / "scoop" / "README.md"', package_release)
    self.assertIn('"docs/scoop-packaging.md"', package_release)

  def test_persistence_and_webview2_requirements_are_explicit(self) -> None:
    main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    installation = (ROOT / "docs/installation.md").read_text(encoding="utf-8")
    packaging = (ROOT / "packaging/scoop/README.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    self.assertIn("app.path().app_data_dir()", main)
    self.assertIn("app.path().app_config_dir()", main)
    self.assertIn("dev.brani.tauridium", installation)
    self.assertIn("intentionally has no `persist` entry", installation)
    self.assertIn("Microsoft Edge WebView2 Runtime", installation)
    self.assertIn("Scoop Extras", readme)
    self.assertIn("new-package issue first", packaging)
    self.assertIn("/verify", packaging)


if __name__ == "__main__":
  unittest.main()
