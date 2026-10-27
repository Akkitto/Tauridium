#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.5.5 release automation and README."""

from __future__ import annotations

import importlib.util
import base64
import json
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
  sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location("tauridium_release_assets", TOOLS / "release_assets.py")
if SPEC is None or SPEC.loader is None:
  raise RuntimeError("unable to load release_assets.py")
release_assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_assets)
import updater_signature


class Patch0505Tests(unittest.TestCase):
  def test_readme_preserves_requested_identity_and_documents_active_tooling(self) -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for marker in (
      '<h1 align="center">Tauridium</h1>',
      "Forget Franz, Ferdi, Ferdium and the rest.",
      "## Why",
      "## Features",
      "## Installation",
      "## Development",
      "## Technology",
      "**Tauri v2 / Rust**",
      "**Svelte 5 / TypeScript**",
      "**Vite 6 / Vitest 3**",
      "**reqwest + rustls**",
      "**wry**",
      "## Releases",
      "## Licence",
      "Copyright © 2026  [Daniel Braniewski](https://brani.dev/)",
    ):
      self.assertIn(marker, readme)
    self.assertIn("https://github.com/Akkitto/Tauridium/releases/latest", readme)
    self.assertIn("https://github.com/Akkitto/Tauridium", readme)

  def test_release_workflow_is_just_driven_and_has_no_macos_release_job(self) -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    for marker in (
      "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
      "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1",
      "actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0",
      "just ci",
      "just package-handoff",
      "just bundle-target ${{ matrix.target }}",
      "just package-native ${{ matrix.target }}",
      "python3 -I tools/sign_release.py",
      "python3 tools/finalize_release.py custody",
      "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9",
      "actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333",
      "python3 -I tools/publish_release.py",
      "windows-11-arm",
      "ubuntu-22.04-arm",
    ):
      self.assertIn(marker, workflow)
    self.assertNotIn("macos-latest", workflow)
    self.assertNotIn("tauri-apps/tauri-action", workflow)
    self.assertNotIn("Swatinem/rust-cache@", workflow)
    self.assertNotIn("cache: npm", workflow)
    self.assertIn("permissions:\n  contents: read", workflow)
    self.assertNotIn("TAURI_UPDATER_SIGNING_ENABLED", workflow)
    self.assertIn("package-native ${{ matrix.target }}", workflow)

  def test_just_exposes_release_build_and_metadata_steps(self) -> None:
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    for marker in (
      "ci: quality build",
      "bundle-target target:",
      "package-native-signed target:",
      "release-notes output=\"release/release-notes.md\":",
      "updater-manifest assets_dir=\"release/published-assets\":",
      "release-checksums assets_dir=\"release/published-assets\":",
    ):
      self.assertIn(marker, justfile)

  def test_updater_plugin_supports_installer_specific_manifest_keys(self) -> None:
    lock = (ROOT / "src-tauri/Cargo.lock").read_text(encoding="utf-8")
    self.assertIn('name = "tauri-plugin-updater"\nversion = "2.14.0"', lock)

  @unittest.skipUnless(updater_signature.find_minisign(), "Real Minisign required; run just init or nix develop")
  def test_updater_manifest_emits_generic_and_installer_specific_keys(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      assets = root / "assets"
      assets.mkdir()
      key, public = root / "test.key", root / "test.pub"
      minisign = updater_signature.find_minisign()
      subprocess.run([minisign, "-G", "-W", "-s", str(key), "-p", str(public)], check=True, capture_output=True)
      public_key = base64.b64encode(public.read_bytes()).decode("ascii")
      release_version = "0.5.5"
      for filename in (
        f"tauridium-{release_version}-windows-x64-setup.exe",
        f"tauridium-{release_version}-windows-x64.msi",
        f"tauridium-{release_version}-windows-arm64-setup.exe",
        f"tauridium-{release_version}-windows-arm64.msi",
        f"tauridium-{release_version}-linux-x64.AppImage",
        f"tauridium-{release_version}-linux-arm64.AppImage",
      ):
        (assets / filename).write_bytes(b"artifact")
        raw = root / "test.minisig"
        subprocess.run([minisign, "-S", "-W", "-s", str(key), "-m", str(assets / filename),
                        "-x", str(raw), "-t", f"timestamp:0\tversion:{release_version}"], check=True, capture_output=True)
        (assets / f"{filename}.sig").write_bytes(base64.b64encode(raw.read_bytes()))

      output = assets / "latest.json"
      with (
        patch.object(updater_signature, "configured_public_key", return_value=public_key),
        patch.object(release_assets, "version", return_value=release_version),
        patch.object(release_assets, "changelog_notes", return_value="notes"),
        patch.object(release_assets, "release_timestamp", return_value="2026-08-22T12:00:00Z"),
      ):
        release_assets.generate_updater_manifest(assets, output, require_all=True)

      manifest = json.loads(output.read_text(encoding="utf-8"))
      platforms = manifest["platforms"]
      for key in (
        "windows-x86_64",
        "windows-x86_64-nsis",
        "windows-x86_64-msi",
        "windows-aarch64",
        "windows-aarch64-nsis",
        "windows-aarch64-msi",
        "linux-x86_64",
        "linux-x86_64-appimage",
        "linux-aarch64",
        "linux-aarch64-appimage",
      ):
        self.assertIn(key, platforms)
      self.assertTrue(platforms["windows-x86_64"]["url"].endswith("-setup.exe"))

  def test_dependabot_keeps_action_dependencies_current(self) -> None:
    dependabot = (ROOT / ".github/dependabot.yml").read_text(encoding="utf-8")
    self.assertIn("package-ecosystem: github-actions", dependabot)
    self.assertIn("interval: weekly", dependabot)


if __name__ == "__main__":
  unittest.main()
