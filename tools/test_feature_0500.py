#!/usr/bin/env python3
"""Regression coverage for the Tauridium 0.5.0 project-identity feature release."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Feature0500Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")
    cls.license = (ROOT / "LICENSE").read_text(encoding="utf-8")
    cls.cargo = (ROOT / "src-tauri/Cargo.toml").read_text(encoding="utf-8")
    cls.main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    cls.app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
    cls.api = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
    cls.package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    cls.tauri = json.loads((ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    cls.tauri_dev = json.loads((ROOT / "src-tauri/tauri.conf.dev.json").read_text(encoding="utf-8"))
    cls.funding = (ROOT / ".github/FUNDING.yml").read_text(encoding="utf-8")

  def test_mit_license_retains_upstream_notice_and_adds_current_copyright(self) -> None:
    self.assertTrue(self.license.startswith("MIT License\n\n"))
    copyrights = [line for line in self.license.splitlines() if line.startswith("Copyright (c)")]
    self.assertEqual(copyrights[0], "Copyright (c) 2026 Daniel Braniewski")
    self.assertEqual(len(copyrights), 2)
    self.assertNotEqual(copyrights[1], copyrights[0])
    self.assertIn("Permission is hereby granted, free of charge", self.license)

  def test_readme_uses_current_project_identity_and_putnam_style_licence_section(self) -> None:
    self.assertIn("https://github.com/Akkitto/Tauridium/releases/latest", self.readme)
    self.assertIn("github/v/release/Akkitto/Tauridium", self.readme)
    self.assertIn("https://github.com/Akkitto/Tauridium", self.readme)
    self.assertIn("https://github.com/Akkitto/Tauridium/commits/master", self.readme)
    self.assertIn("https://brani.dev", self.readme)
    self.assertIn("## Licence\n\nCopyright (c) 2026 [Daniel Braniewski](https://brani.dev)", self.readme)
    self.assertIn("[MIT License](LICENSE)", self.readme)
    self.assertNotIn("buymeacoffee", self.readme.lower())
    self.assertNotIn("This project is vibe-coded", self.readme)

  def test_package_and_cargo_metadata_are_owned_by_current_fork(self) -> None:
    self.assertEqual(self.package["author"], "Daniel Braniewski")
    self.assertEqual(self.package["homepage"], "https://github.com/Akkitto/Tauridium")
    self.assertEqual(self.package["repository"]["url"], "https://github.com/Akkitto/Tauridium.git")
    self.assertEqual(self.package["bugs"]["url"], "https://github.com/Akkitto/Tauridium/issues")
    self.assertIn('authors = ["Daniel Braniewski"]', self.cargo)
    self.assertIn('homepage = "https://github.com/Akkitto/Tauridium"', self.cargo)
    self.assertIn('repository = "https://github.com/Akkitto/Tauridium"', self.cargo)

  def test_runtime_identity_and_updater_use_current_namespace(self) -> None:
    self.assertEqual(self.tauri["identifier"], "dev.brani.tauridium")
    self.assertEqual(self.tauri_dev["identifier"], "dev.brani.tauridium.dev")
    self.assertEqual(
      self.tauri["plugins"]["updater"]["endpoints"],
      ["https://github.com/Akkitto/Tauridium/releases/latest/download/latest.json"],
    )
    self.assertIn('const PROJECT_HOMEPAGE: &str = "https://github.com/Akkitto/Tauridium";', self.main)
    self.assertIn('const PROJECT_SOURCE_CODE: &str = "https://github.com/Akkitto/Tauridium/tree/master";', self.main)
    self.assertIn('const AUTHOR_HOMEPAGE: &str = "https://brani.dev";', self.main)

  def test_identity_change_preserves_existing_tauridium_state_without_old_namespace_literal(self) -> None:
    self.assertIn("fn migrate_legacy_application_identity", self.main)
    self.assertIn("fn legacy_identity_candidate", self.main)
    self.assertIn("IDENTITY_DIRECTORY_MARKERS", self.main)
    self.assertIn("copy_identity_directory_contents", self.main)

  def test_about_metadata_uses_author_not_maintainer(self) -> None:
    self.assertIn("author: string;", self.api)
    self.assertNotIn("maintainer: string;", self.api)
    self.assertIn("author: env!(\"CARGO_PKG_AUTHORS\")", self.main)
    self.assertIn('openProjectLink("https://brani.dev")', self.app)
    self.assertIn('id="about-author-heading">Author</h3>', self.app)
    self.assertIn('appMetadata?.author ?? "Daniel Braniewski"', self.app)
    self.assertNotIn("appMetadata?.maintainer", self.app)

  def test_funding_no_longer_targets_previous_project_identity(self) -> None:
    self.assertRegex(self.funding, r"(?m)^github: Akkitto$")
    self.assertNotIn("buy_me_a_coffee", self.funding)

  def test_upstream_copyright_holder_is_not_repeated_outside_license(self) -> None:
    copyrights = [line for line in self.license.splitlines() if line.startswith("Copyright (c)")]
    upstream_holder = copyrights[1].split("2026 ", 1)[1]
    violations: list[str] = []
    for path in ROOT.rglob("*"):
      if not path.is_file() or ".git" in path.parts or "vendor" in path.parts:
        continue
      if path.name == ".tauridium-source-manifest.json" or path == ROOT / "LICENSE":
        continue
      try:
        text = path.read_text(encoding="utf-8")
      except (UnicodeDecodeError, OSError):
        continue
      if upstream_holder in text:
        violations.append(str(path.relative_to(ROOT)))
    self.assertEqual(violations, [])


if __name__ == "__main__":
  unittest.main()
