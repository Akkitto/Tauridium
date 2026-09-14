#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.7.11 GitHub Linguist classification."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATTRIBUTES = (ROOT / ".gitattributes").read_text(encoding="utf-8")


def git_attribute(attribute: str, path: str) -> str:
  result = subprocess.run(
    ["git", "check-attr", attribute, "--", path],
    cwd=ROOT,
    text=True,
    capture_output=True,
    check=True,
  )
  return result.stdout.strip().rsplit(": ", 1)[-1]


class Patch0711Tests(unittest.TestCase):
  def test_auxiliary_repository_code_is_not_detectable(self) -> None:
    for path in (
      "tools/scoop.py",
      "tools/test_feature_0700.py",
      "tools/test_scoop_install.ps1",
      "packaging/scoop/tauridium.json.template",
      ".github/workflows/ci.yml",
      "src/lib/api.test.ts",
      "justfile",
      "vite.config.ts",
      "svelte.config.js",
    ):
      self.assertEqual(git_attribute("linguist-detectable", path), "false", path)

  def test_vendor_generated_and_documentation_paths_are_classified_truthfully(self) -> None:
    self.assertEqual(git_attribute("linguist-vendored", "vendor/tauri/src/app.rs"), "set")
    self.assertEqual(
      git_attribute("linguist-vendored", "src-tauri/assets/darkreader.js"),
      "set",
    )
    self.assertEqual(
      git_attribute("linguist-generated", "src-tauri/gen/schemas/windows-schema.json"),
      "set",
    )
    self.assertEqual(
      git_attribute("linguist-generated", ".tauridium-source-manifest.json"),
      "set",
    )
    self.assertEqual(git_attribute("linguist-generated", "vite-env.d.ts"), "set")
    self.assertEqual(
      git_attribute("linguist-documentation", "docs/installation.md"),
      "set",
    )

  def test_genuine_application_sources_remain_detectable(self) -> None:
    for path in (
      "src-tauri/src/main.rs",
      "src-tauri/src/single_instance.rs",
      "src/App.svelte",
      "src/main.ts",
      "src/lib/api.ts",
      "recipes/example/webview.js",
    ):
      self.assertNotEqual(git_attribute("linguist-detectable", path), "false", path)
      self.assertEqual(git_attribute("linguist-language", path), "unspecified", path)

  def test_configuration_uses_path_roles_not_language_relabelling(self) -> None:
    self.assertNotIn("linguist-language=Rust", ATTRIBUTES)
    self.assertNotIn("*.py linguist-detectable=false", ATTRIBUTES)
    self.assertNotIn("*.js linguist-detectable=false", ATTRIBUTES)
    self.assertNotIn("*.ts linguist-detectable=false", ATTRIBUTES)
    self.assertNotIn("*.svelte linguist-detectable=false", ATTRIBUTES)
    self.assertIn("tools/** linguist-detectable=false", ATTRIBUTES)
    self.assertIn("vendor/** linguist-vendored", ATTRIBUTES)


if __name__ == "__main__":
  unittest.main()
