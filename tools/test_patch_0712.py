#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.7.12 Rust-only GitHub Linguist stats."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATTRIBUTES = (ROOT / ".gitattributes").read_text(encoding="utf-8")
PACKAGER = (ROOT / "tools" / "package_release.py").read_text(encoding="utf-8")


def git_attribute(attribute: str, path: str) -> str:
  result = subprocess.run(
    ["git", "check-attr", attribute, "--", path],
    cwd=ROOT,
    text=True,
    capture_output=True,
    check=True,
  )
  return result.stdout.strip().rsplit(": ", 1)[-1]


class Patch0712Tests(unittest.TestCase):
  def test_only_rust_is_detectable_for_language_statistics(self) -> None:
    for path in (
      "src/App.svelte",
      "src/main.ts",
      "src/lib/api.ts",
      "recipes/example/webview.js",
      "tools/scoop.py",
      "tools/test_scoop_install.ps1",
      ".github/workflows/ci.yml",
      "package.json",
      "README.md",
    ):
      self.assertEqual(git_attribute("linguist-detectable", path), "false", path)

    for path in (
      "src-tauri/src/main.rs",
      "src-tauri/src/single_instance.rs",
      "vendor/tauri/src/app.rs",
    ):
      self.assertEqual(git_attribute("linguist-detectable", path), "true", path)

  def test_all_tracked_non_rust_files_are_non_detectable(self) -> None:
    tracked = subprocess.run(
      ["git", "ls-files", "-z"],
      cwd=ROOT,
      capture_output=True,
      check=True,
    ).stdout.decode("utf-8").split("\0")

    for path in filter(None, tracked):
      if path.endswith(".rs"):
        continue
      self.assertEqual(git_attribute("linguist-detectable", path), "false", path)

  def test_rust_only_stats_do_not_relabel_other_languages_as_rust(self) -> None:
    self.assertIn("* linguist-detectable=false", ATTRIBUTES)
    self.assertIn("*.rs linguist-detectable=true", ATTRIBUTES)
    self.assertNotIn("linguist-language=Rust", ATTRIBUTES)

    for path in (
      "src/App.svelte",
      "src/main.ts",
      "recipes/example/webview.js",
    ):
      self.assertEqual(git_attribute("linguist-language", path), "unspecified", path)

  def test_language_policy_document_is_in_documentation_package(self) -> None:
    self.assertIn(
      '(ROOT / "docs" / "github-language-statistics.md", "docs/github-language-statistics.md")',
      PACKAGER,
    )

  def test_provenance_classification_remains_intact(self) -> None:
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
      git_attribute("linguist-documentation", "docs/installation.md"),
      "set",
    )


if __name__ == "__main__":
  unittest.main()
