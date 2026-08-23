#!/usr/bin/env python3
"""Regression tests for Tauridium release packaging."""

from __future__ import annotations

import importlib.util
import json
import sys
import subprocess
import tempfile
import unittest
from unittest import mock
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
    (self.root / "AGENTS.md").write_text("AGENTS\n", encoding="utf-8")
    (self.root / "LICENSE").write_text("LICENSE\n", encoding="utf-8")
    (self.root / "source.txt").write_text("source\n", encoding="utf-8")

  def tearDown(self) -> None:
    PACKAGE.ROOT = self.original_root
    self.temp_dir.cleanup()

  def write_manifest(self) -> dict[str, object]:
    files = []
    for relative in (
      "AGENTS.md",
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

    self.assertEqual(len(context.entries), 6)
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


  def test_git_source_requires_exact_release_tag(self) -> None:
    self.init_git_repository()
    subprocess.run(["git", "tag", "-d", "v0.2.0"], cwd=self.root, check=True, capture_output=True)

    with self.assertRaisesRegex(SystemExit, "requires HEAD to carry exact tag v0.2.0"):
      PACKAGE.source_context("0.2.0")

  def test_manifest_source_requires_exact_release_tag(self) -> None:
    manifest = self.write_manifest()
    manifest["git"]["tag"] = None
    (self.root / PACKAGE.SOURCE_MANIFEST_NAME).write_bytes(PACKAGE.manifest_bytes(manifest))

    with self.assertRaisesRegex(SystemExit, "not anchored to exact release tag v0.2.0"):
      PACKAGE.source_context("0.2.0")

  def test_dirty_git_source_error_names_changed_path(self) -> None:
    self.init_git_repository()
    (self.root / "source.txt").write_text("dirty\n", encoding="utf-8")

    with self.assertRaises(SystemExit) as caught:
      PACKAGE.source_context("0.2.0")

    message = str(caught.exception)
    self.assertIn("changed paths", message)
    self.assertIn("source.txt", message)

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

  def test_source_zip_preserves_required_empty_git_directories_after_pack_refs(self) -> None:
    self.init_git_repository()
    subprocess.run(["git", "pack-refs", "--all", "--prune"], cwd=self.root, check=True)
    context = PACKAGE.source_context("0.2.0")
    output = self.root / "source.zip"

    PACKAGE.build_source(output, "0.2.0", context)

    extract_root = self.root / "packed-extracted"
    with zipfile.ZipFile(output) as archive:
      names = set(archive.namelist())
      self.assertIn("tauridium-0.2.0/.git/refs/", names)
      self.assertIn("tauridium-0.2.0/.git/refs/heads/", names)
      self.assertIn("tauridium-0.2.0/.git/refs/tags/", names)
      archive.extractall(extract_root)

    extracted = extract_root / "tauridium-0.2.0"
    self.assertEqual(
      subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=extracted, text=True).strip(),
      subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root, text=True).strip(),
    )
    self.assertEqual(
      subprocess.check_output(
        ["git", "describe", "--tags", "--exact-match", "HEAD"], cwd=extracted, text=True
      ).strip(),
      "v0.2.0",
    )
    subprocess.run(
      ["git", "fsck", "--full"],
      cwd=extracted,
      check=True,
      capture_output=True,
      text=True,
    )

  def test_source_zip_does_not_depend_on_path_relative_to(self) -> None:
    self.init_git_repository()
    context = PACKAGE.source_context("0.2.0")
    output = self.root / "source.zip"

    with mock.patch.object(Path, "relative_to", side_effect=AssertionError("relative_to used")):
      PACKAGE.build_source(output, "0.2.0", context)

    with zipfile.ZipFile(output) as archive:
      self.assertIn("tauridium-0.2.0/.git/HEAD", archive.namelist())

  def test_docs_evidence_does_not_depend_on_path_relative_to(self) -> None:
    self.init_git_repository()
    context = PACKAGE.source_context("0.2.0")
    source_zip = self.root / "source.zip"
    runtime_zip = self.root / "run.zip"
    source_zip.write_bytes(b"source")
    runtime_zip.write_bytes(b"runtime")
    evidence_file = self.root / "release" / "evidence" / "windows" / "ci.txt"
    evidence_file.parent.mkdir(parents=True)
    evidence_file.write_text("ok\n", encoding="utf-8")
    output = self.root / "docs.zip"

    with mock.patch.object(Path, "relative_to", side_effect=AssertionError("relative_to used")):
      PACKAGE.build_docs(output, "0.2.0", source_zip, [runtime_zip], context)

    with zipfile.ZipFile(output) as archive:
      self.assertIn("tauridium-0.2.0-doc/evidence/windows/ci.txt", archive.namelist())

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

  def test_validate_build_info_rejects_development_mode(self) -> None:
    with self.assertRaisesRegex(SystemExit, "not compiled in Tauri production mode"):
      PACKAGE.validate_build_info(
        {
          "name": "Tauridium",
          "version": "0.2.0",
          "buildMode": "development",
          "target": "x86_64-pc-windows-msvc",
        },
        "0.2.0",
      )

  def test_validate_build_info_accepts_production_mode_even_with_configured_dev_url(self) -> None:
    # The configured devUrl can remain as inert bytes in a production executable;
    # acceptance is based on the executable's compile-time Tauri mode instead.
    target, suffix = PACKAGE.validate_build_info(
      {
        "name": "Tauridium",
        "version": "0.2.0",
        "buildMode": "production",
        "target": "x86_64-pc-windows-msvc",
      },
      "0.2.0",
    )
    self.assertEqual(target, "x86_64-pc-windows-msvc")
    self.assertEqual(suffix, "win-x64")


  def test_runtime_target_suffixes_are_short_and_distinct(self) -> None:
    expected = {
      "x86_64-pc-windows-msvc": "win-x64",
      "aarch64-pc-windows-msvc": "win-arm64",
      "x86_64-unknown-linux-gnu": "linux-x64",
      "aarch64-unknown-linux-gnu": "linux-arm64",
      "x86_64-unknown-linux-musl": "linux-x64-musl",
      "aarch64-apple-darwin": "macos-arm64",
      "x86_64-apple-darwin": "macos-x64",
    }
    for target, suffix in expected.items():
      with self.subTest(target=target):
        self.assertEqual(PACKAGE.target_suffix(target), suffix)
        self.assertEqual(
          PACKAGE.runtime_zip_name("0.3.7", suffix),
          f"tauridium-0.3.7-run-{suffix}.zip",
        )

  def test_multiple_runtime_targets_are_grouped_into_separate_run_archives(self) -> None:
    windows = PACKAGE.RuntimeArtifact(
      path=self.root / "tauridium.exe",
      target="x86_64-pc-windows-msvc",
      suffix="win-x64",
    )
    linux = PACKAGE.RuntimeArtifact(
      path=self.root / "tauridium",
      target="x86_64-unknown-linux-gnu",
      suffix="linux-x64",
    )
    groups = PACKAGE.group_runtimes_by_target([windows, linux])
    self.assertEqual(set(groups), {"win-x64", "linux-x64"})
    self.assertEqual(groups["win-x64"], [windows])
    self.assertEqual(groups["linux-x64"], [linux])

  def test_build_info_requires_compilation_target(self) -> None:
    with self.assertRaisesRegex(SystemExit, "no Rust target triple"):
      PACKAGE.validate_build_info(
        {"name": "Tauridium", "version": "0.2.0", "buildMode": "production"},
        "0.2.0",
      )

  def test_runtime_probe_executes_binary_and_validates_production_mode(self) -> None:
    runtime = self.root / "tauridium.exe"
    runtime.write_bytes(b"MZ\x00http://localhost:1420 may be embedded configuration")

    def fake_run(command, **_kwargs):
      self.assertEqual(command[0], str(runtime))
      self.assertEqual(command[1], PACKAGE.BUILD_INFO_ARGUMENT)
      Path(command[2]).write_text(
        json.dumps({
          "name": "Tauridium",
          "version": "0.2.0",
          "buildMode": "production",
          "target": "x86_64-pc-windows-msvc",
        }),
        encoding="utf-8",
      )
      return subprocess.CompletedProcess(command, 0, "", "")

    with mock.patch.object(PACKAGE.subprocess, "run", side_effect=fake_run):
      artifact = PACKAGE.inspect_runtime(runtime, "0.2.0")

    self.assertEqual(artifact.target, "x86_64-pc-windows-msvc")
    self.assertEqual(artifact.suffix, "win-x64")
    PACKAGE.build_runtime(self.root / "run.zip", "0.2.0", [artifact])

    with zipfile.ZipFile(self.root / "run.zip") as archive:
      self.assertIn("tauridium-0.2.0/tauridium.exe", archive.namelist())
      self.assertIn(
        "Rust target: x86_64-pc-windows-msvc",
        archive.read("tauridium-0.2.0/README.txt").decode(),
      )

  def test_runtime_probe_rejects_development_binary(self) -> None:
    runtime = self.root / "tauridium.exe"
    runtime.write_bytes(b"MZ")

    def fake_run(command, **_kwargs):
      Path(command[2]).write_text(
        json.dumps({
          "name": "Tauridium",
          "version": "0.2.0",
          "buildMode": "development",
          "target": "x86_64-pc-windows-msvc",
        }),
        encoding="utf-8",
      )
      return subprocess.CompletedProcess(command, 0, "", "")

    with mock.patch.object(PACKAGE.subprocess, "run", side_effect=fake_run):
      with self.assertRaisesRegex(SystemExit, "not compiled in Tauri production mode"):
        PACKAGE.inspect_runtime(runtime, "0.2.0")

  def test_build_handoff_is_explicitly_non_native_and_contains_exact_source(self) -> None:
    self.init_git_repository()
    context = PACKAGE.source_context("0.2.0")
    output = self.root / "tauridium-0.2.0-run-build-handoff.zip"

    PACKAGE.build_runtime_handoff(output, "0.2.0", context)

    with zipfile.ZipFile(output) as archive:
      names = set(archive.namelist())
      self.assertIn("tauridium-0.2.0/source.txt", names)
      self.assertIn("tauridium-0.2.0/RUNTIME-HANDOFF.txt", names)
      self.assertIn(f"tauridium-0.2.0/{PACKAGE.SOURCE_MANIFEST_NAME}", names)
      self.assertFalse(any(name.startswith("tauridium-0.2.0/.git/") for name in names))
      handoff = archive.read("tauridium-0.2.0/RUNTIME-HANDOFF.txt").decode()
      self.assertIn("no native runtime is claimed", handoff)
      self.assertIn("PowerShell/pwsh", handoff)

  def test_docs_use_manifest_git_log_without_git_repository(self) -> None:
    self.write_manifest()
    context = PACKAGE.source_context("0.2.0")
    source_zip = self.root / "src.zip"
    run_zip = self.root / "tauridium-0.2.0-run-win-x64.zip"
    second_run_zip = self.root / "tauridium-0.2.0-run-linux-x64.zip"
    source_zip.write_bytes(b"source")
    run_zip.write_bytes(b"windows runtime")
    second_run_zip.write_bytes(b"linux runtime")
    output = self.root / "doc.zip"

    PACKAGE.build_docs(output, "0.2.0", source_zip, [run_zip, second_run_zip], context)

    with zipfile.ZipFile(output) as archive:
      log = archive.read("tauridium-0.2.0-doc/GIT-LOG.txt").decode()
      checksums = archive.read("tauridium-0.2.0-doc/SHA256SUMS").decode()
      self.assertIn("Proj: Test release", log)
      self.assertIn(run_zip.name, checksums)
      self.assertIn(second_run_zip.name, checksums)
      self.assertIn(
        f"tauridium-0.2.0-doc/{PACKAGE.SOURCE_MANIFEST_NAME}",
        archive.namelist(),
      )


if __name__ == "__main__":
  unittest.main()
