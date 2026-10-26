#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.6.12 updater-signing release fallback."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
  sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location("tauridium_release_assets_0612", ROOT / "tools/release_assets.py")
if SPEC is None or SPEC.loader is None:
  raise RuntimeError("unable to load release_assets.py")
release_assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_assets)

import publish_release as publisher


class Patch0612Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    cls.justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    cls.no_updater_config = (ROOT / "src-tauri/tauri.no-updater.conf.json").read_text(encoding="utf-8")

  def test_release_builds_without_updater_artifacts_when_signing_key_is_unavailable(self) -> None:
    self.assertIn("bundle-target-no-updater target:", self.justfile)
    self.assertIn("src-tauri/tauri.no-updater.conf.json", (ROOT / "tools/tauri_build.py").read_text(encoding="utf-8"))
    self.assertIn("\"createUpdaterArtifacts\": false", self.no_updater_config)
    build = self.workflow.split("  build:", 1)[1].split("  scoop:", 1)[0]
    self.assertNotIn("secrets.", build)
    self.assertNotIn("TAURI_UPDATER_SIGNING_ENABLED", self.workflow)
    self.assertIn("run: just bundle-target ${{ matrix.target }}", build)
    self.assertIn("run: just package-native ${{ matrix.target }}", self.workflow)
    self.assertNotIn("Require updater signing key", self.workflow)

  def test_signed_release_path_stays_strict_when_signing_is_configured(self) -> None:
    self.assertIn("run: just bundle-target ${{ matrix.target }}", self.workflow)
    self.assertIn("environment: release-signing", self.workflow)
    self.assertIn("python3 -I tools/sign_release.py", self.workflow)
    self.assertIn("TAURI_SIGNING_PRIVATE_KEY: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY }}", self.workflow)

  def test_publish_rejects_missing_updater_manifest_before_github_operations(self) -> None:
    self.assertIn("python3 tools/finalize_release.py custody", self.workflow)
    self.assertIn("updater-manifest-if-signed assets_dir=\"release/published-assets\":", self.justfile)
    release_version = "0.6.12"
    with tempfile.TemporaryDirectory() as temp_dir:
      assets = Path(temp_dir)
      for name in publisher.release_snapshot.names(release_version, "final") - {"latest.json"}:
        (assets / name).write_bytes(b"synthetic")
      seal = b"{}"
      (assets / publisher.release_snapshot.TRANSFER).write_bytes(seal)
      with mock.patch.object(publisher, "gh") as github:
        with self.assertRaisesRegex(SystemExit, "latest[.]json"):
          publisher.publish(assets, release_version, "a" * 40, hashlib.sha256(seal).hexdigest(),
                            "Akkitto/Tauridium")
        github.assert_not_called()

  def test_unsigned_and_partial_updater_asset_sets_are_distinguished(self) -> None:
    release_version = "0.6.12"
    with tempfile.TemporaryDirectory() as temp_dir:
      assets = Path(temp_dir)
      self.assertEqual(release_assets.signed_updater_state(assets, release_version), "unsigned")

      first = release_assets.expected_updater_artifact_names(release_version)[0]
      (assets / first).write_bytes(b"artifact")
      (assets / f"{first}.sig").write_text("signature\n", encoding="utf-8")
      with self.assertRaisesRegex(SystemExit, "signed updater release is incomplete"):
        release_assets.signed_updater_state(assets, release_version)

      for name in release_assets.expected_updater_artifact_names(release_version):
        (assets / name).write_bytes(b"artifact")
        (assets / f"{name}.sig").write_text("signature\n", encoding="utf-8")
      with self.assertRaisesRegex(SystemExit, "updater signature rejected"):
        release_assets.signed_updater_state(assets, release_version)


if __name__ == "__main__":
  unittest.main()
