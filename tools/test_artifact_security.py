"""Synthetic leak controls and independent NSIS parsing; no real credential fixtures."""
import base64
import hashlib
import json
import lzma
import os
from pathlib import Path
import secrets
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile
import zlib

import artifact_security as security
import package_release

TOOLS = Path(os.environ["TAURIDIUM_ARTIFACT_SECURITY_TOOLS"]) if os.environ.get("TAURIDIUM_ARTIFACT_SECURITY_TOOLS") else None


def synthetic_nsis(payload: bytes):
  header = b"H" * 64
  decoded = struct.pack("<I", len(header)) + header + struct.pack("<I", len(payload)) + payload
  compressed = lzma.compress(decoded, format=lzma.FORMAT_RAW, filters=[{
      "id": lzma.FILTER_LZMA1, "dict_size": 1024**2, "lc": 3, "lp": 0, "pb": 2}])
  properties = b"\x5d" + struct.pack("<I", 1024**2)
  first = struct.pack("<I", 0) + b"\xef\xbe\xad\xdeNullsoftInst" + struct.pack("<II", len(header), 28 + 5 + len(compressed) + 4)
  body = first + properties + compressed
  return b"MZ" + b"\0" * 510 + body + struct.pack("<I", zlib.crc32(body)), decoded


class ArtifactParserTests(unittest.TestCase):
  def test_decoder_uses_disposable_cwd_and_rejects_any_auxiliary_write(self):
    with self.assertRaisesRegex(RuntimeError, "unexpectedly wrote"):
      security.bounded_command([sys.executable, "-c", "from pathlib import Path; Path('synthetic-output').write_text('synthetic')"])
    self.assertFalse(Path("synthetic-output").exists())

  def test_empty_msi_table_fallback_requires_proven_non_object_schema(self):
    harmless = security.DecoderFailure(1, b"CREATE TABLE `Empty` (`Name` CHAR(72))\n", False)
    with mock.patch.object(security, "bounded_command", side_effect=[harmless, b"Name\ns72\nEmpty\n"]) as run:
      security.Scanner.msi_table("msiinfo", Path("synthetic.msi"), "Empty")
      self.assertEqual(run.call_args_list[1].args[0][1], "export")
      self.assertNotIn("-s", run.call_args_list[1].args[0])
    binary = security.DecoderFailure(1, b"CREATE TABLE `Empty` (`Data` OBJECT)\n", False)
    with mock.patch.object(security, "bounded_command", side_effect=binary) as run:
      with self.assertRaises(security.DecoderFailure):
        security.Scanner.msi_table("msiinfo", Path("synthetic.msi"), "Empty")
      self.assertEqual(run.call_count, 1)

  def test_independent_nsis_solid_reader_covers_entire_data_and_actual_record_length(self):
    data, expected = synthetic_nsis(b"harmless file record")
    decoded, base = security.nsis_solid_stream(data)
    self.assertEqual(decoded, expected)
    self.assertEqual(struct.unpack_from("<I", decoded, base)[0], len(b"harmless file record"))

  def test_nsis_dictionary_and_actual_expansion_are_bounded(self):
    data, _ = synthetic_nsis(b"A" * 10000)
    with mock.patch.object(security, "MAX_PAYLOAD", 100):
      with self.assertRaisesRegex(RuntimeError, "expansion exceeded"):
        security.nsis_solid_stream(data)
    corrupted = bytearray(data)
    struct.pack_into("<I", corrupted, 512 + 29, 2**31)
    struct.pack_into("<I", corrupted, len(corrupted)-4, zlib.crc32(corrupted[512:-4]))
    with self.assertRaisesRegex(RuntimeError, "properties"):
      security.nsis_solid_stream(bytes(corrupted))

  def test_private_key_exemption_requires_both_exact_public_hash_and_module_scope(self):
    fixture = b"-----BEGIN PRIVATE KEY-----\nSYNTHETIC-NOT-A-KEY\n-----END PRIVATE KEY-----"
    digest = hashlib.sha256(security.normalized_pem(fixture)).hexdigest()
    self.assertEqual(security.public_selftests(fixture, "home/user/secret.pem", {digest}), (fixture, 0))
    self.assertEqual(security.public_selftests(fixture, "usr/lib/libgnutls.so.30", set()), (fixture, 0))
    cleaned, count = security.public_selftests(fixture, "usr/lib/libgnutls.so.30", {digest})
    self.assertEqual(count, 1)
    self.assertNotIn(b"BEGIN PRIVATE KEY", cleaned)

  def test_unapproved_git_hooks_are_rejected_before_git_is_invoked(self):
    with tempfile.TemporaryDirectory() as temporary:
      scanner = security.Scanner(Path(temporary), Path("/unused-tools"))
      files = {"hooks/pre-commit": b"must never execute"}
      manifest = {"version": "9.9.9", "gitFiles": [{"path": ".git/" + name, "sha256": hashlib.sha256(data).hexdigest()}
                                                     for name, data in files.items()]}
      with mock.patch.object(security, "bounded_command") as command:
        with self.assertRaisesRegex(RuntimeError, "unapproved local state"):
          scanner.git_objects(files, manifest)
        command.assert_not_called()


@unittest.skipUnless(TOOLS and (TOOLS / "gitleaks").is_file() and (TOOLS / "7zz").is_file(),
                     "Set TAURIDIUM_ARTIFACT_SECURITY_TOOLS to checksum-verified scanner directory")
class RealArtifactScannerTests(unittest.TestCase):
  def scanner(self, root):
    return security.Scanner(root, TOOLS)

  def token(self):
    # Generated locally, never issued by a provider or used for authentication.
    return "ghp_" + "".join(secrets.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(36))

  def test_plaintext_utf16_and_base64_secrets_fail_without_secret_diagnostics(self):
    for encoding in ("ascii", "utf-16-le", "utf-16-be", "base64"):
      with self.subTest(encoding=encoding), tempfile.TemporaryDirectory() as temporary:
        scanner = self.scanner(Path(temporary))
        token = self.token()
        data = (token.encode(encoding) if encoding != "base64"
                else base64.b64encode(("token = " + token).encode()))
        scanner.save(data, "synthetic.bin", decode=False)
        with self.assertRaisesRegex(RuntimeError, "secret scan rejected") as caught:
          scanner.scan()
        self.assertNotIn(token, str(caught.exception))

  def test_nested_archive_secret_and_inline_ignore_comment_cannot_bypass_gate(self):
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      token = self.token()
      archive = root / "input.zip"
      with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as target:
        target.writestr("public/readme.txt", "token = " + token + " # gitleaks:allow\n")
      scanner_root = root / "private"
      scanner_root.mkdir()
      scanner = self.scanner(scanner_root)
      scanner.add(archive)
      with self.assertRaisesRegex(RuntimeError, "secret scan rejected"):
        scanner.scan()

  def test_deleted_secret_in_approved_git_history_is_still_scanned(self):
    from test_package_release import PackageReleaseTests
    fixture = PackageReleaseTests()
    fixture.setUp()
    self.addCleanup(fixture.tearDown)
    fixture.init_git_repository()
    token = self.token()
    path = fixture.root / "historical.txt"
    path.write_text("token = " + token + "\n", encoding="ascii")
    def git(*args):
      subprocess.run(["git", *args], cwd=fixture.root, capture_output=True, check=True)
    git("add", "historical.txt")
    git("commit", "-qm", "Test: Add synthetic historical token")
    git("rm", "-q", "historical.txt")
    git("commit", "-qm", "Test: Remove synthetic token from current tree")
    git("tag", "-f", "v0.2.0")
    source = fixture.root / "source.zip"
    with mock.patch.object(package_release, "ROOT", fixture.root):
      context = package_release.source_context("0.2.0")
      package_release.build_source(source, "0.2.0", context)
    with tempfile.TemporaryDirectory() as temporary:
      scanner = self.scanner(Path(temporary))
      scanner.add(source)
      self.assertGreater(scanner.decoded["git-blob"], 0)
      with self.assertRaisesRegex(RuntimeError, "secret scan rejected"):
        scanner.scan()

  def test_harmless_control_passes(self):
    with tempfile.TemporaryDirectory() as temporary:
      scanner = self.scanner(Path(temporary))
      scanner.save(b"Harmless synthetic public release\n", "README.md")
      self.assertTrue(scanner.scan()["passed"])


if __name__ == "__main__":
  unittest.main()
