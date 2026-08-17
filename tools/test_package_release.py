#!/usr/bin/env python3
"""Regression tests for Tauridium release packaging."""

from __future__ import annotations

import importlib.util
import json
import sys
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("package_release.py")
SPEC = importlib.util.spec_from_file_location("tauridium_package_release", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
  raise RuntimeError("unable to load package_release.py")
PACKAGE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PACKAGE
SPEC.loader.exec_module(PACKAGE)


class PackageReleaseTests(unittest.TestCase):
  def setUp(self) -> None:
    self.original_root = PACKAGE.ROOT
    self.temp_dir = tempfile.TemporaryDirectory()
    self.root = Path(self.temp_dir.name)
    PACKAGE.ROOT = self.root
    (self.root / "src-tauri").mkdir()
    (self.root / "src-tauri" / "tauri.conf.json").write_text(
      json.dumps({"version": "0.2.0"}), encoding="utf-8"
    )
    (self.root / "README.md").write_text("README\n", encoding="utf-8")
    (self.root / "CHANGELOG.md").write_text("CHANGELOG\n", encoding="utf-8")
    (self.root / "LICENSE").write_text("LICENSE\n", encoding="utf-8")
    (self.root / "source.txt").write_text("source\n", encoding="utf-8")

  def tearDown(self) -> None:
    PACKAGE.ROOT = self.original_root
    self.temp_dir.cleanup()

  def write_manifest(self) -> dict[str, object]:
    files = []
    for relative in (
      "CHANGELOG.md",
      "LICENSE",
      "README.md",
      "source.txt",
      "src-tauri/tauri.conf.json",
    ):
      path = self.root / relative
      files.append(
        {
          "path": relative,
          "sha256": PACKAGE.sha256(path),
          "mode": 0o644,
        }
      )
    manifest = {
      "schema": PACKAGE.SOURCE_MANIFEST_SCHEMA,
      "project": "Tauridium",
      "version": "0.2.0",
      "git": {
        "commit": "a" * 40,
        "tree": "b" * 40,
        "tag": "v0.2.0",
        "log": "abc1234 (tag: v0.2.0) Proj: Test release",
      },
      "files": files,
    }
    (self.root / PACKAGE.SOURCE_MANIFEST_NAME).write_bytes(PACKAGE.manifest_bytes(manifest))
    return manifest

  def test_extracted_source_uses_manifest_without_git(self) -> None:
    self.write_manifest()

    self.assertIsNone(PACKAGE.git_repository_root())
    context = PACKAGE.source_context("0.2.0")

    self.assertEqual(len(context.entries), 5)
    self.assertEqual(context.manifest["version"], "0.2.0")

  def test_extracted_source_rejects_modified_source(self) -> None:
    self.write_manifest()
    (self.root / "source.txt").write_text("modified\n", encoding="utf-8")

    with self.assertRaisesRegex(SystemExit, "source-manifest checksum mismatch: source.txt"):
      PACKAGE.source_context("0.2.0")

  def test_extracted_source_requires_manifest_when_git_is_absent(self) -> None:
    with self.assertRaisesRegex(SystemExit, "requires either a Git checkout"):
      PACKAGE.source_context("0.2.0")

  def init_git_repository(self) -> None:
    (self.root / ".gitignore").write_text(
      f"{PACKAGE.SOURCE_MANIFEST_NAME}\nsource.zip\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q", "-b", "master"], cwd=self.root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=self.root, check=True)
    subprocess.run(
      ["git", "config", "user.email", "test@example.invalid"], cwd=self.root, check=True
    )
    executable = self.root / "script.ps1"
    executable.write_text("Write-Host 'ok'\n", encoding="utf-8")
    executable.chmod(0o755)
    subprocess.run(["git", "add", "."], cwd=self.root, check=True)
    subprocess.run(["git", "update-index", "--chmod=+x", "script.ps1"], cwd=self.root, check=True)
    subprocess.run(
      ["git", "commit", "-q", "-m", "Proj: Initial test history"], cwd=self.root, check=True
    )
    (self.root / "source.txt").write_text("source v2\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.txt"], cwd=self.root, check=True)
    subprocess.run(
      ["git", "commit", "-q", "-m", "Fix: Update test source"], cwd=self.root, check=True
    )
    subprocess.run(["git", "tag", "v0.2.0"], cwd=self.root, check=True)

  def test_source_zip_preserves_manifest_and_manifest_file_set(self) -> None:
    self.init_git_repository()
    context = PACKAGE.source_context("0.2.0")
    output = self.root / "source.zip"

    PACKAGE.build_source(output, "0.2.0", context)

    extract_root = self.root / "extracted"
    with zipfile.ZipFile(output) as archive:
      names = set(archive.namelist())
      self.assertIn(
        f"tauridium-0.2.0/{PACKAGE.SOURCE_MANIFEST_NAME}",
        names,
      )
      self.assertIn("tauridium-0.2.0/source.txt", names)
      self.assertIn("tauridium-0.2.0/.git/HEAD", names)
      self.assertTrue(
        any(name.startswith("tauridium-0.2.0/.git/objects/") for name in names)
      )
      config = archive.read("tauridium-0.2.0/.git/config").decode()
      self.assertIn("filemode = false", config)
      self.assertNotIn("tauridium-0.2.0/source.zip", names)
      archive.extractall(extract_root)

    extracted = extract_root / "tauridium-0.2.0"
    self.assertEqual(
      subprocess.check_output(
        ["git", "rev-list", "--count", "HEAD"], cwd=extracted, text=True
      ).strip(),
      "2",
    )
    self.assertEqual(
      subprocess.check_output(
        ["git", "describe", "--tags", "--exact-match", "HEAD"], cwd=extracted, text=True
      ).strip(),
      "v0.2.0",
    )
    self.assertEqual(
      subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=extracted, text=True
      ).strip(),
      "",
    )
    subprocess.run(
      ["git", "fsck", "--full"],
      cwd=extracted,
      check=True,
      capture_output=True,
      text=True,
    )

  def test_source_zip_requires_git_history(self) -> None:
    self.write_manifest()
    context = PACKAGE.source_context("0.2.0")

    with self.assertRaisesRegex(SystemExit, "requires a real Git checkout"):
      PACKAGE.build_source(self.root / "source.zip", "0.2.0", context)

  def test_git_index_modes_are_used_instead_of_host_filesystem_modes(self) -> None:
    subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=self.root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=self.root, check=True)
    script = self.root / "script.ps1"
    script.write_text("Write-Host 'ok'\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=self.root, check=True)
    subprocess.run(["git", "update-index", "--chmod=+x", "script.ps1"], cwd=self.root, check=True)

    entries = {entry.archive_path: entry for entry in PACKAGE.tracked_entries()}

    self.assertEqual(entries["script.ps1"].mode, 0o755)

  def test_docs_use_manifest_git_log_without_git_repository(self) -> None:
    self.write_manifest()
    context = PACKAGE.source_context("0.2.0")
    source_zip = self.root / "src.zip"
    run_zip = self.root / "run.zip"
    source_zip.write_bytes(b"source")
    run_zip.write_bytes(b"runtime")
    output = self.root / "doc.zip"

    PACKAGE.build_docs(output, "0.2.0", source_zip, run_zip, context)

    with zipfile.ZipFile(output) as archive:
      log = archive.read("tauridium-0.2.0-doc/GIT-LOG.txt").decode()
      self.assertIn("Proj: Test release", log)
      self.assertIn(
        f"tauridium-0.2.0-doc/{PACKAGE.SOURCE_MANIFEST_NAME}",
        archive.namelist(),
      )


if __name__ == "__main__":
  unittest.main()
