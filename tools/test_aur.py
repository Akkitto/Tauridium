"""Arch packaging boundary regressions; real makepkg/pacman gates run on Arch."""
import copy
import hashlib
import io
import json
from pathlib import Path
import stat
import struct
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock
import zipfile

import aur
import arch_check
import arch_build
import arch_namcap


def build_info():
  return {"name": "Tauridium", "version": "1.0.10", "target": "x86_64-unknown-linux-gnu", "buildMode": "production", "distribution": {"mode": "system-package", "updaterManagedExternally": True, **{key: False for key in ("portalFileAccess", "portalNotifications", "portalAutostart", "downloadsRequireDestination", "automaticBackupsUsePrivateStorage")}}}


def payload(path, mutate=None):
  elf = bytearray(64)
  elf[:6] = b"\x7fELF\x02\x01"
  struct.pack_into("<H", elf, 18, 62)
  record = {"schema": 1, "commit": "a" * 40, "build": build_info(), "binarySha256": hashlib.sha256(elf).hexdigest()}
  files = {key: bytes(elf) if source is None else b"harmless synthetic metadata" for key, source in aur.PAYLOAD.items()}
  if mutate:
    mutate(record, files)
  files["BUILD-INFO.json"] = json.dumps(record).encode()
  with zipfile.ZipFile(path, "w") as archive:
    for name, data in files.items():
      entry = zipfile.ZipInfo(name)
      entry.create_system = 3
      entry.external_attr = (stat.S_IFREG | (0o755 if name == "usr/bin/tauridium" else 0o644)) << 16
      archive.writestr(entry, data)


class ArchPackagingTests(unittest.TestCase):
  def test_namcap_error_findings_are_fatal_even_on_zero_exit(self):
    with mock.patch.object(arch_namcap.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "tauridium E: missing license\n", "")):
      with self.assertRaisesRegex(RuntimeError, "packaging errors"):
        arch_namcap.check(["PKGBUILD"])
    with mock.patch.object(arch_namcap.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "tauridium W: optional dynamic library\n", "")):
      arch_namcap.check(["PKGBUILD"])

  def test_managed_builder_uses_locked_production_features_without_bundler(self):
    with mock.patch.object(arch_build.subprocess, "run") as run:
      arch_build.build("x86_64-unknown-linux-gnu", {})
    command = run.call_args.args[0]
    for argument in ("--release", "--offline", "--locked", "--no-default-features", "system-package,tauri/custom-protocol"):
      self.assertIn(argument, command)
    self.assertEqual(command[0], "cargo")
    self.assertIn("CARGO_ENCODED_RUSTFLAGS", run.call_args.kwargs["env"])

  def test_build_info_rejects_native_updater_debug_wrong_version_and_portal_policy(self):
    arch_check.validate(build_info(), "1.0.10", "x86_64-unknown-linux-gnu")
    for field, value in (("version", "1.0.9"), ("target", "aarch64-unknown-linux-gnu"), ("buildMode", "development")):
      data = build_info(); data[field] = value
      with self.subTest(field=field), self.assertRaises(ValueError):
        arch_check.validate(data, "1.0.10", "x86_64-unknown-linux-gnu")
    for field, value in (("mode", "native"), ("updaterManagedExternally", False), ("portalFileAccess", True)):
      data = build_info(); data["distribution"][field] = value
      with self.subTest(field=field), self.assertRaises(ValueError):
        arch_check.validate(data, "1.0.10", "x86_64-unknown-linux-gnu")

  def test_payload_rejects_substituted_elf_unexpected_files_and_native_build(self):
    with tempfile.TemporaryDirectory() as temporary:
      path = Path(temporary) / "fixture.zip"
      payload(path)
      self.assertEqual(aur.validate_payload(path, "1.0.10", "x86_64-unknown-linux-gnu")["commit"], "a" * 40)
      for mutate in (
        lambda r, f: f.update({"usr/bin/tauridium": b"not an ELF"}),
        lambda r, f: f.update({"unapproved.txt": b"harmless control"}),
        lambda r, f: r["build"]["distribution"].update(mode="native"),
        lambda r, f: r.update(binarySha256="b" * 64),
        lambda r, f: r.update(commit="master"),
      ):
        payload(path, mutate)
        with self.assertRaises(ValueError):
          aur.validate_payload(path, "1.0.10", "x86_64-unknown-linux-gnu")
      payload(path)
      with self.assertRaises(ValueError):
        aur.validate_payload(path, "1.0.10", "aarch64-unknown-linux-gnu")

  def test_recipe_render_rejects_shell_injection_and_unresolved_fields(self):
    for value in ("$(id)", "a';id;'", "name\ncommand", "name name", "`id`"):
      with self.subTest(value=value), self.assertRaises(ValueError):
        aur.render("@SOURCE@", {"SOURCE": value})
    with self.assertRaises(ValueError):
      aur.render("@SHA256@", {})

  def test_binary_recipe_is_bounded_local_and_existing_outputs_survive(self):
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      path = root / "tauridium-1.0.10-linux-x64-system.zip"
      payload(path)
      with mock.patch.object(aur, "version", return_value="1.0.10"):
        with self.assertRaisesRegex(ValueError, "source commit differs"):
          aur.prepare_binary(path, root / "wrong", expected_commit="b" * 40)
        output = aur.prepare_binary(path, root / "out", expected_commit="a" * 40)
        text = (output / "PKGBUILD").read_text(encoding="utf-8")
        self.assertIn("pkgname=tauridium-bin", text)
        self.assertIn("provides=(\"tauridium=$pkgver\")", text)
        self.assertIn(hashlib.sha256(path.read_bytes()).hexdigest(), text)
        self.assertNotIn("SKIP", text)
        self.assertNotIn("replaces=", text)
        self.assertNotIn("aarch64", text)
        with self.assertRaises(ValueError):
          aur.prepare_binary(path, output)
        self.assertEqual((output / path.name).read_bytes(), path.read_bytes())

  def make_repository(self, root):
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for key, value in (("user.name", "Synthetic Packager"), ("user.email", "test@example.invalid"), ("commit.gpgsign", "false")):
      subprocess.run(["git", "config", key, value], cwd=root, check=True)
    (root / "package.json").write_text('{"version":"1.0.10"}', encoding="utf-8")
    (root / "safe.txt").write_text("benign tracked source", encoding="utf-8")
    (root / ".gitignore").write_text(".env\nrelease/\n", encoding="utf-8")
    (root / ".env").write_text("harmless private control never exported", encoding="utf-8")
    (root / "packaging/aur").mkdir(parents=True)
    (root / "packaging/aur/PKGBUILD.source.in").write_text("version=@VERSION@\nsource=@SOURCE@\ncommit=@COMMIT@\npkgrel=@PKGREL@\nsha256=@SHA256@\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "Build: Add synthetic source"], cwd=root, check=True)

  def test_source_export_is_reproducible_clean_tracked_and_allowlisted(self):
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary) / "repo"
      self.make_repository(root)
      with mock.patch.object(aur, "SOURCE_FILES", {"package.json", "safe.txt"}), mock.patch.object(aur, "SOURCE_ROOTS", ()):
        first = aur.prepare_source(root / "release/first", root)
        second = aur.prepare_source(root / "release/second", root)
        a, b = next(first.glob("*.tar.gz")), next(second.glob("*.tar.gz"))
        self.assertEqual(a.read_bytes(), b.read_bytes())
        with tarfile.open(a) as archive:
          self.assertEqual(set(archive.getnames()), {"tauridium/package.json", "tauridium/safe.txt"})
          self.assertTrue(all(m.isfile() and m.uid == m.gid == 0 for m in archive))
        self.assertIn("pkgrel=0.1", (first / "PKGBUILD").read_text(encoding="utf-8"))
        with self.assertRaises(ValueError):
          aur.prepare_source(first, root)
        (root / "safe.txt").write_text("uncommitted edit", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "commit changes"):
          aur.prepare_source(root / "release/dirty", root)

  def test_source_export_rejects_tracked_symlinks(self):
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary) / "repo"
      self.make_repository(root)
      (root / "safe.txt").unlink()
      (root / "safe.txt").symlink_to("/etc/hostname")
      subprocess.run(["git", "add", "safe.txt"], cwd=root, check=True)
      subprocess.run(["git", "commit", "-qm", "Test: Add synthetic symlink"], cwd=root, check=True)
      with mock.patch.object(aur, "SOURCE_FILES", {"package.json", "safe.txt"}), mock.patch.object(aur, "SOURCE_ROOTS", ()):
        with self.assertRaisesRegex(ValueError, "regular tracked"):
          aur.prepare_source(root / "release/rejected", root)
        self.assertFalse((root / "release/rejected").exists())


if __name__ == "__main__":
  unittest.main()
