#!/usr/bin/env python3
"""Regression tests for Tauridium release packaging."""

from __future__ import annotations

import importlib.util
import hashlib
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

  def test_windows_git_commands_ignore_unsupported_worktree_file_modes(self) -> None:
    self.assertEqual(
      PACKAGE.git_command("status", "--porcelain", platform_name="nt"),
      ["git", "-c", "core.filemode=false", "status", "--porcelain"],
    )
    self.assertEqual(
      PACKAGE.git_command("status", "--porcelain", platform_name="posix"),
      ["git", "status", "--porcelain"],
    )

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
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=self.root, check=True)
    # These disposable repositories must not inherit the developer's newline policy.
    subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=self.root, check=True)
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

  def test_git_test_fixture_disables_inherited_newline_conversion(self) -> None:
    self.init_git_repository()
    self.assertEqual(
      subprocess.check_output(
        ["git", "config", "--local", "--get", "core.autocrlf"], cwd=self.root, text=True
      ).strip(),
      "false",
    )


  def test_git_source_requires_exact_release_tag(self) -> None:
    self.init_git_repository()
    subprocess.run(["git", "tag", "-d", "v0.2.0"], cwd=self.root, check=True, capture_output=True)

    with self.assertRaisesRegex(SystemExit, "requires HEAD to carry exact tag v0.2.0"):
      PACKAGE.source_context("0.2.0")

  def test_conditional_packaging_skips_an_untagged_git_checkout(self) -> None:
    self.init_git_repository()
    subprocess.run(["git", "tag", "-d", "v0.2.0"], cwd=self.root, check=True, capture_output=True)

    with mock.patch("builtins.print") as output:
      self.assertFalse(PACKAGE.should_package_release(True, "0.2.0"))

    output.assert_called_once()
    self.assertIn("HEAD is not the exact version tag v0.2.0", output.call_args.args[0])

  def test_conditional_packaging_continues_at_the_exact_version_tag(self) -> None:
    self.init_git_repository()

    self.assertTrue(PACKAGE.should_package_release(True, "0.2.0"))

  def test_direct_packaging_remains_strictly_enabled_when_untagged(self) -> None:
    self.init_git_repository()
    subprocess.run(["git", "tag", "-d", "v0.2.0"], cwd=self.root, check=True, capture_output=True)

    self.assertTrue(PACKAGE.should_package_release(False, "0.2.0"))

  def test_conditional_packaging_validates_extracted_release_sources(self) -> None:
    self.write_manifest()

    self.assertTrue(PACKAGE.should_package_release(True, "0.2.0"))

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
    evidence_file = self.root / "release" / "public-evidence" / "windows" / "ci.txt"
    evidence_file.parent.mkdir(parents=True)
    evidence_file.write_text("ok\n", encoding="utf-8")
    (self.root / "release" / "public-evidence.json").write_text(json.dumps({
      "schema": 1, "version": "0.2.0", "files": [
        {"path": "windows/ci.txt", "sha256": PACKAGE.sha256(evidence_file)}
      ]
    }), encoding="utf-8")
    output = self.root / "docs.zip"

    with mock.patch.object(Path, "relative_to", side_effect=AssertionError("relative_to used")):
      PACKAGE.build_docs(output, "0.2.0", source_zip, [runtime_zip], context, public_evidence=True)

    with zipfile.ZipFile(output) as archive:
      self.assertIn("tauridium-0.2.0-doc/evidence/windows/ci.txt", archive.namelist())

  def test_docs_never_publish_ignored_raw_evidence_or_later_document_edits(self) -> None:
    self.init_git_repository()
    context = PACKAGE.source_context("0.2.0")
    evidence = self.root / "release" / "evidence"
    evidence.mkdir(parents=True)
    (evidence / ".env").write_text("PRIVATE RAW DIAGNOSTICS", encoding="utf-8")
    (self.root / "README.md").write_text("Private later edit", encoding="utf-8")
    source = self.root / "source.zip"
    source.write_bytes(b"synthetic source")
    output = self.root / "docs.zip"
    PACKAGE.build_docs(output, "0.2.0", source, [], context)
    with zipfile.ZipFile(output) as archive:
      self.assertFalse(any("/evidence/" in name for name in archive.namelist()))
      self.assertEqual(archive.read("tauridium-0.2.0-doc/README.md"), b"README\n")

  def test_recursive_artifact_input_rejects_outside_root_symlinks(self) -> None:
    import os
    if os.name == "nt":
      self.skipTest("Native Windows reparse-point coverage requires a junction-capable runner")
    outside = self.root / "private-outside.txt"
    outside.write_text("PRIVATE OUTSIDE", encoding="utf-8")
    stage = self.root / "stage"
    stage.mkdir()
    (stage / "linked.txt").symlink_to(outside)
    with self.assertRaisesRegex(SystemExit, "symlink or reparse"):
      PACKAGE.tree_entries(stage)
    with self.assertRaisesRegex(SystemExit, "symlink or reparse"):
      with PACKAGE.release_zip(self.root / "linked.zip") as archive:
        PACKAGE.add_file(archive, stage / "linked.txt", "linked.txt")

  def test_security_guidance_is_exported_only_from_immutable_approved_source(self) -> None:
    names = ("SECURITY.md", "docs/BUILD-SECURITY.md", "docs/ARTIFACT-SECURITY.md",
             "docs/SECURE-RELEASES.md", "docs/BROWSER-PRIVACY.md")
    for name in names:
      path = self.root / name
      path.parent.mkdir(parents=True, exist_ok=True)
      path.write_text("Reviewed security guidance", encoding="utf-8")
    self.init_git_repository()
    context = PACKAGE.source_context("0.2.0")
    (self.root / "SECURITY.md").write_text("Private later draft", encoding="utf-8")
    source = self.root / "source.zip"
    source.write_bytes(b"synthetic source")
    output = self.root / "docs.zip"
    PACKAGE.build_docs(output, "0.2.0", source, [], context)
    with zipfile.ZipFile(output) as archive:
      for name in names:
        self.assertEqual(archive.read("tauridium-0.2.0-doc/" + name), b"Reviewed security guidance")

  def test_atomic_zip_failure_preserves_existing_artifact_and_removes_staging(self) -> None:
    output = self.root / "existing.zip"
    output.write_bytes(b"KEEP EXISTING")
    with self.assertRaisesRegex(SystemExit, "unsafe member"):
      with PACKAGE.release_zip(output) as archive:
        PACKAGE.add_bytes(archive, b"synthetic", "../outside.txt")
    self.assertEqual(output.read_bytes(), b"KEEP EXISTING")
    self.assertEqual(list(self.root.glob(".existing.zip-*.tmp")), [])

  def test_public_evidence_rejects_unknown_staged_files(self) -> None:
    stage = self.root / "release" / "public-evidence"
    stage.mkdir(parents=True)
    (stage / ".env").write_text("PRIVATE", encoding="utf-8")
    (self.root / "release" / "public-evidence.json").write_text(json.dumps({"schema":1,"version":"0.2.0","files":[]}), encoding="utf-8")
    with self.assertRaisesRegex(SystemExit, "differs from its approved manifest"):
      PACKAGE.public_evidence_files("0.2.0")

  def test_source_zip_requires_git_history(self) -> None:
    self.write_manifest()
    context = PACKAGE.source_context("0.2.0")

    with self.assertRaisesRegex(SystemExit, "requires a real Git checkout"):
      PACKAGE.build_source(self.root / "source.zip", "0.2.0", context)

  def test_public_git_excludes_local_config_hooks_private_files_and_dangling_objects(self) -> None:
    self.init_git_repository()
    subprocess.run(["git", "config", "http.https://example.invalid/.extraheader", "Authorization: SYNTHETIC"], cwd=self.root, check=True)
    (self.root / ".git" / "private-build-note").write_text("PRIVATE RECOVERY ONLY", encoding="utf-8")
    (self.root / ".git" / "hooks" / "pre-commit").write_text("# inert synthetic hook", encoding="utf-8")
    dangling = subprocess.check_output(["git", "hash-object", "-w", "--stdin"], cwd=self.root, input=b"Private unreachable recovery material").decode().strip()
    context = PACKAGE.source_context("0.2.0")
    output = self.root / "public-source.zip"
    PACKAGE.build_source(output, "0.2.0", context)
    extracted = self.root / "privacy-extracted"
    with zipfile.ZipFile(output) as archive:
      names = archive.namelist()
      self.assertFalse(any("/hooks/" in name or "/logs/" in name or "private-build-note" in name for name in names))
      self.assertNotIn("Authorization", archive.read("tauridium-0.2.0/.git/config").decode())
      self.assertTrue(context.manifest["gitFiles"])
      for entry in context.manifest["gitFiles"]:
        self.assertEqual(hashlib.sha256(archive.read("tauridium-0.2.0/" + entry["path"])).hexdigest(), entry["sha256"])
      archive.extractall(extracted)
    result = subprocess.run(["git", "cat-file", "-e", dangling], cwd=extracted / "tauridium-0.2.0", capture_output=True)
    self.assertNotEqual(result.returncode, 0)
    self.assertTrue((self.root / ".git" / "private-build-note").exists())

  def test_hidden_index_flags_are_rejected_even_when_status_is_clean(self) -> None:
    self.init_git_repository()
    for flag, reset in [("--assume-unchanged", "--no-assume-unchanged"), ("--skip-worktree", "--no-skip-worktree")]:
      subprocess.run(["git", "update-index", flag, "source.txt"], cwd=self.root, check=True)
      try:
        with self.assertRaisesRegex(SystemExit, "hidden index flags"):
          PACKAGE.source_context("0.2.0")
      finally:
        subprocess.run(["git", "update-index", reset, "source.txt"], cwd=self.root, check=True)

  def test_manifest_paths_reject_windows_drives_streams_and_git_metadata(self) -> None:
    for value in ["C:/outside", "a\\..\\outside", "file:stream", ".git/config", "dir./file", "dir /file", "."]:
      with self.subTest(value=value), self.assertRaisesRegex(SystemExit, "invalid source-manifest path"):
        PACKAGE.safe_manifest_path(value)

  def test_source_export_uses_captured_tag_bytes_not_later_disk_changes(self) -> None:
    self.init_git_repository()
    context = PACKAGE.source_context("0.2.0")
    (self.root / "source.txt").write_text("Unreviewed disk modification\n", encoding="utf-8")
    output = self.root / "snapshot.zip"
    PACKAGE.build_source(output, "0.2.0", context)
    with zipfile.ZipFile(output) as archive:
      self.assertEqual(archive.read("tauridium-0.2.0/source.txt"), b"source v2\n")

  def test_sanitized_source_is_reproducible_across_fresh_exports(self) -> None:
    self.init_git_repository()
    first = PACKAGE.source_context("0.2.0")
    second = PACKAGE.source_context("0.2.0")
    self.assertEqual(first.git_files, second.git_files)
    self.assertEqual(first.manifest_bytes, second.manifest_bytes)

  def test_packed_source_is_independent_of_producer_compression_and_delta_layout(self) -> None:
    self.init_git_repository()
    for index in range(120):
      (self.root / f"packed-{index}.txt").write_bytes(
        b"Deterministic synthetic shared source line\n" * 100 + str(index).encode() + b"\n")
    def git(*arguments):
      return subprocess.check_output(["git", *arguments], cwd=self.root, stderr=subprocess.DEVNULL)
    git("add", ".")
    git("commit", "-qm", "Test: Create enough approved objects to require packing")
    git("tag", "-f", "v0.2.0")
    git("config", "pack.threads", "4")
    git("config", "pack.compression", "0")
    git("repack", "-adF", "--depth=0", "--window=0")
    original_pack = tuple(path.name for path in (self.root / ".git/objects/pack").glob("*.pack"))
    first = PACKAGE.source_context("0.2.0")
    self.assertTrue(any(name.endswith(".pack") for name, _ in first.git_files))
    git("config", "pack.compression", "9")
    git("repack", "-adF", "--depth=30", "--window=20")
    changed_pack = tuple(path.name for path in (self.root / ".git/objects/pack").glob("*.pack"))
    self.assertNotEqual(original_pack, changed_pack)
    second = PACKAGE.source_context("0.2.0")
    self.assertEqual(first.git_files, second.git_files)
    self.assertEqual(first.manifest_bytes, second.manifest_bytes)

  def test_git_index_modes_are_used_instead_of_host_filesystem_modes(self) -> None:
    subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=self.root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=self.root, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=self.root, check=True)
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

  def test_linux_runtime_readme_explains_native_and_nix_requirements(self) -> None:
    runtime = self.root / "tauridium"
    runtime.write_bytes(b"native runtime fixture")
    artifact = PACKAGE.RuntimeArtifact(runtime, "x86_64-unknown-linux-gnu", "linux-x64")
    PACKAGE.build_runtime(self.root / "run.zip", "0.2.0", [artifact])
    with zipfile.ZipFile(self.root / "run.zip") as archive:
      readme = archive.read("tauridium-0.2.0/README.txt").decode()
      self.assertIn("compatible GTK/WebKit libraries", readme)
      self.assertIn("not a standalone Nix closure", readme)
      self.assertIn("develop --command /path/to/tauridium", readme)
      self.assertIn("run .#tauridium", readme)

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
      self.assertIn("paired tauridium-0.2.0-src.zip", handoff)
      self.assertIn("Do not run the release workflow directly from this Git-free archive", handoff)
      self.assertIn("just release", handoff)

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

  def test_docs_include_file_drop_guidance_current_report_and_fixture(self) -> None:
    paths = ("docs/NIX.md", "docs/examples/nix/flake.nix", "docs/examples/nix/consumer.nix", "docs/examples/nix/home.nix", "docs/examples/nix/nixos.nix", "docs/file-drops.md", "docs/download-notifications.md", "docs/releases/0.2.0-validation.md", "tools/fixtures/file-drop.html")
    source_zip = self.root / "src.zip"
    run_zip = self.root / "run.zip"
    source_zip.write_bytes(b"source")
    run_zip.write_bytes(b"runtime")
    output = self.root / "doc.zip"
    for newline in (b"\n", b"\r\n"):
      with self.subTest(newline=newline):
        for path in paths:
          target = self.root / path
          target.parent.mkdir(parents=True, exist_ok=True)
          target.write_bytes(f"contents of {path}".encode("utf-8") + newline)
        manifest = self.write_manifest()
        manifest["files"].extend({"path": path, "sha256": PACKAGE.sha256(self.root / path), "mode": 0o644} for path in paths)
        (self.root / PACKAGE.SOURCE_MANIFEST_NAME).write_bytes(PACKAGE.manifest_bytes(manifest))
        context = PACKAGE.source_context("0.2.0")
        PACKAGE.build_docs(output, "0.2.0", source_zip, [run_zip], context)
        with zipfile.ZipFile(output) as archive:
          for path in paths:
            self.assertEqual(
              archive.read(f"tauridium-0.2.0-doc/{path}"),
              f"contents of {path}".encode("utf-8") + newline,
            )


if __name__ == "__main__":
  unittest.main()
