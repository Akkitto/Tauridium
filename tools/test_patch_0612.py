#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.6.12 updater-signing release fallback."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
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


class Patch0612Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    cls.justfile = (ROOT / "justfile").read_text(encoding="utf-8")

  def test_release_builds_without_updater_artifacts_when_signing_key_is_unavailable(self) -> None:
    self.assertIn("bundle-target-no-updater target:", self.justfile)
    self.assertIn("createUpdaterArtifacts\": false", self.justfile)
    self.assertIn("if: env.TAURI_UPDATER_SIGNING_ENABLED == 'true'", self.workflow)
    self.assertIn("if: env.TAURI_UPDATER_SIGNING_ENABLED != 'true'", self.workflow)
    self.assertIn("run: just bundle-target-no-updater ${{ matrix.target }}", self.workflow)
    self.assertIn("run: just package-native ${{ matrix.target }}", self.workflow)
    self.assertNotIn("Require updater signing key", self.workflow)

  def test_signed_release_path_stays_strict_when_signing_is_configured(self) -> None:
    self.assertIn("run: just bundle-target ${{ matrix.target }}", self.workflow)
    self.assertIn("run: just package-native-signed ${{ matrix.target }}", self.workflow)
    self.assertIn("TAURI_UPDATER_SIGNING_ENABLED: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY != '' }}", self.workflow)
    self.assertIn("TAURI_SIGNING_PRIVATE_KEY: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY }}", self.workflow)

  def test_publish_only_uploads_updater_manifest_when_one_was_generated(self) -> None:
    self.assertIn("just updater-manifest-if-signed release/published-assets", self.workflow)
    self.assertIn('if [[ -f release/published-assets/latest.json ]]; then', self.workflow)
    self.assertIn('files+=(release/published-assets/latest.json)', self.workflow)
    self.assertIn("updater-manifest-if-signed assets_dir=\"release/published-assets\":", self.justfile)

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
      self.assertEqual(release_assets.signed_updater_state(assets, release_version), "signed")


if __name__ == "__main__":
  unittest.main()
