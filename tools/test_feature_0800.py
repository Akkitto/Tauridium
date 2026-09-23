#!/usr/bin/env python3
"""Regression coverage for the v0.8.0 Flatpak distribution feature."""
from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FlatpakReleaseTests(unittest.TestCase):
  def read(self, path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")

  def test_release_identity_is_consistent(self) -> None:
    package_version = json.loads(self.read("package.json"))["version"]
    self.assertEqual(json.loads(self.read("src-tauri/tauri.conf.json"))["version"], package_version)
    self.assertIn(f'version = "{package_version}"', self.read("src-tauri/Cargo.toml"))

  def test_distribution_modes_are_compile_time_explicit(self) -> None:
    cargo = self.read("src-tauri/Cargo.toml")
    distribution = self.read("src-tauri/src/distribution.rs")
    self.assertIn('default = ["native-distribution"]', cargo)
    self.assertIn('flatpak = [', cargo)
    self.assertIn('dep:zbus', cargo)
    self.assertIn('rfd/xdg-portal', cargo)
    self.assertIn('rfd/wayland', cargo)
    self.assertIn('rfd/tokio', cargo)
    self.assertIn('cfg!(feature = "flatpak")', distribution)

  def test_flatpak_runner_disables_native_default_features(self) -> None:
    runner = self.read("flatpak/cargo-flatpak-runner.sh")
    self.assertIn('--no-default-features --features flatpak', runner)

  def test_flatpak_manifest_has_minimal_permission_budget(self) -> None:
    manifest = self.read("flatpak/dev.brani.tauridium.yml")
    for marker in (
      "runtime: org.gnome.Platform",
      "runtime-version: '51'",
      "org.freedesktop.Sdk.Extension.rust-stable",
      "org.freedesktop.Sdk.Extension.node24",
      "shared-modules/libayatana-appindicator/libayatana-appindicator-gtk3.json",
      "--share=network",
      "--share=ipc",
      "--socket=wayland",
      "--socket=fallback-x11",
      "--device=dri",
      "--socket=pulseaudio",
      "--talk-name=org.kde.StatusNotifierWatcher",
      f"tag: v{json.loads(self.read('package.json'))['version']}",
      "chmod +x source/flatpak/cargo-flatpak-runner.sh",
      "cargo tauri build --runner ../flatpak/cargo-flatpak-runner.sh --no-bundle --ci",
    ):
      self.assertIn(marker, manifest)
    for forbidden in (
      "--filesystem=home",
      "--filesystem=host",
      "--device=all",
      "--socket=session-bus",
      "--socket=system-bus",
      "--talk-name=org.freedesktop.portal.",
      "--filesystem=xdg-config/autostart",
    ):
      self.assertNotIn(forbidden, manifest)

  def test_updater_is_not_available_in_flatpak_runtime_path(self) -> None:
    main = self.read("src-tauri/src/main.rs")
    self.assertIn('#[cfg(all(feature = "native-distribution", not(feature = "flatpak")))]', main)
    self.assertIn('distribution::is_flatpak()', main)
    capability = self.read("src-tauri/capabilities/default.json")
    self.assertNotIn("updater", capability)

  def test_flatpak_vendors_tray_runtime_dependency(self) -> None:
    module = self.read(
      "flatpak/shared-modules/libayatana-appindicator/libayatana-appindicator-gtk3.json"
    )
    self.assertIn('"name": "libayatana-appindicator"', module)
    self.assertIn('"commit": "31e8bb083b307e1cc96af4874a94707727bd1e79"', module)
    self.assertIn('"commit": "611bb384b73fa6311777ba4c41381a06f5b99dad"', module)

  def test_flatpak_builder_output_is_ignored(self) -> None:
    ignore = self.read(".gitignore")
    for path in (".flatpak-builder/", "build-dir/", "repo/"):
      self.assertIn(path, ignore)

  def test_flatpak_uses_frontend_portals(self) -> None:
    portal = self.read("src-tauri/src/flatpak_portal.rs")
    self.assertIn("org.freedesktop.portal.Background", portal)
    self.assertIn("RequestBackground", portal)
    self.assertIn("org.freedesktop.portal.OpenURI", portal)
    self.assertIn("org.freedesktop.portal.Notification", portal)
    self.assertNotIn("org.freedesktop.impl.portal", portal)

  def test_desktop_metadata_is_consistent(self) -> None:
    desktop = self.read("data/dev.brani.tauridium.desktop")
    meta = self.read("data/dev.brani.tauridium.metainfo.xml")
    self.assertIn("Exec=tauridium", desktop)
    self.assertIn("Icon=dev.brani.tauridium", desktop)
    self.assertIn("<id>dev.brani.tauridium</id>", meta)
    self.assertIn("<metadata_license>CC0-1.0</metadata_license>", meta)
    self.assertIn("<project_license>MIT</project_license>", meta)
    self.assertIn('<launchable type="desktop-id">dev.brani.tauridium.desktop</launchable>', meta)
    self.assertIn(
      "https://raw.githubusercontent.com/Akkitto/Tauridium/v0.8.3/"
      "data/screenshots/tauridium-0.8.0-main.png",
      meta,
    )
    current = json.loads(self.read("package.json"))["version"]
    self.assertIn(f'<release version="{current}"', meta)

  def test_dependency_source_manifests_are_current(self) -> None:
    subprocess.run(
      ["python3", "tools/generate_flatpak_sources.py", "--check"],
      cwd=ROOT,
      check=True,
    )
    cargo_sources = json.loads(self.read("flatpak/cargo-sources.json"))
    node_sources = json.loads(self.read("flatpak/node-sources.json"))
    cli_sources = json.loads(self.read("flatpak/tauri-cli-cargo-sources.json"))
    self.assertGreater(len(cargo_sources), 500)
    self.assertGreater(len(node_sources), 100)
    self.assertGreater(len(cli_sources), 500)
    self.assertIn('directory = "cargo/vendor"', cargo_sources[-1]["contents"])
    self.assertIn('directory = "cargo/vendor"', cli_sources[-1]["contents"])

  def test_manifest_source_pin_must_be_materialized_before_release(self) -> None:
    manifest = self.read("flatpak/dev.brani.tauridium.yml")
    pins = re.findall(r"^\s*commit:\s*(\S+)$", manifest, flags=re.MULTILINE)
    self.assertEqual(pins, ["2ad65ffb0abf921696eec5555cb90b268dacac21"])


if __name__ == "__main__":
  unittest.main()
