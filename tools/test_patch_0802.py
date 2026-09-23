#!/usr/bin/env python3
"""Regression coverage for the v0.8.2 Windows release-gate fixes."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0802Tests(unittest.TestCase):
  def read(self, path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")

  def test_release_identity_remains_synchronized_after_0802(self) -> None:
    version = json.loads(self.read("package.json"))["version"]
    self.assertGreaterEqual(tuple(map(int, version.split("."))), (0, 8, 2))
    self.assertEqual(json.loads(self.read("src-tauri/tauri.conf.json"))["version"], version)
    self.assertIn(f'version = "{version}"', self.read("src-tauri/Cargo.toml"))
    self.assertIn(f'name = "tauridium"\nversion = "{version}"', self.read("src-tauri/Cargo.lock"))
    self.assertIn(f'INIT_VERSION = "{version}"', self.read("tools/init.py"))
    self.assertIn(f'$InitVersion = "{version}"', self.read("tools/init.ps1"))

  def test_windows_all_features_do_not_compile_an_unused_autostart_value(self) -> None:
    main = self.read("src-tauri/src/main.rs")
    body = main.split("fn apply_autostart_setting", 1)[1].split("fn persist_app_settings", 1)[0]
    value_cfg = """#[cfg(any(
        all(feature = \"native-distribution\", not(feature = \"flatpak\")),
        all(target_os = \"linux\", feature = \"flatpak\")
    ))]
    let enabled = settings"""
    self.assertIn(value_cfg, body)
    non_linux_flatpak = body.split(
      '#[cfg(all(not(target_os = "linux"), feature = "flatpak"))]', 1
    )[1]
    self.assertIn("let _ = settings;", non_linux_flatpak)

  def test_windows_capability_schema_is_canonical_and_non_mutating(self) -> None:
    windows = self.read("src-tauri/gen/schemas/windows-schema.json")
    desktop = self.read("src-tauri/gen/schemas/desktop-schema.json")
    self.assertEqual(windows, desktop)
    self.assertNotIn('"const": "process:', windows)

  def test_patch_metadata_and_strict_windows_gates_are_present(self) -> None:
    self.assertIn("## [0.8.2] - 2026-09-22", self.read("CHANGELOG.md"))
    self.assertIn(
      '<release version="0.8.2" date="2026-09-22">',
      self.read("data/dev.brani.tauridium.metainfo.xml"),
    )
    justfile = self.read("justfile")
    self.assertIn(
      "cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --all-features --locked -- -D warnings",
      justfile,
    )
    self.assertIn(
      "cargo check --manifest-path src-tauri/Cargo.toml --all-targets --all-features --locked",
      justfile,
    )


if __name__ == "__main__":
  unittest.main()
