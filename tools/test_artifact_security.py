"""Synthetic leak controls and independent NSIS parsing; no real credential fixtures."""
import base64
import hashlib
import io
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
  def test_public_errors_withhold_arbitrary_parser_paths_and_process_arguments(self):
    marker = "private-filename-never-publish"
    for error in (RuntimeError(marker), OSError(marker), ValueError(marker),
                  zipfile.BadZipFile(marker), security.DecoderFailure(1, marker.encode(), True),
                  subprocess.CalledProcessError(1, [marker]), TypeError(marker)):
      with self.subTest(error=type(error).__name__):
        self.assertNotIn(marker, security.public_failure(error))
    self.assertEqual(security.public_failure(security.ArtifactRejection("Static budget rejection")),
                     "Static budget rejection")

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

  def historical_source(self, payload, filename):
    from test_package_release import PackageReleaseTests
    fixture = PackageReleaseTests()
    fixture.setUp()
    self.addCleanup(fixture.tearDown)
    fixture.init_git_repository()
    path = fixture.root / filename
    path.write_bytes(payload)
    def git(*args):
      subprocess.run(["git", *args], cwd=fixture.root, capture_output=True, check=True)
    git("add", filename)
    git("commit", "-qm", "Test: Add synthetic historical token")
    git("rm", "-q", filename)
    git("commit", "-qm", "Test: Remove synthetic token from current tree")
    git("tag", "-f", "v0.2.0")
    source = fixture.root / "source.zip"
    with mock.patch.object(package_release, "ROOT", fixture.root):
      context = package_release.source_context("0.2.0")
      package_release.build_source(source, "0.2.0", context)
    return source

  def test_deleted_secret_in_approved_git_history_is_still_scanned(self):
    token = self.token()
    source = self.historical_source(("token = " + token + "\n").encode(), "historical.txt")
    with tempfile.TemporaryDirectory() as temporary:
      scanner = self.scanner(Path(temporary))
      scanner.add(source)
      self.assertGreater(scanner.decoded["git-blob"], 0)
      with self.assertRaisesRegex(RuntimeError, "secret scan rejected"):
        scanner.scan()

  def test_deleted_compressed_secret_in_exported_history_is_recursively_scanned(self):
    token = self.token()
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w", compression=zipfile.ZIP_DEFLATED) as archive:
      archive.writestr("secret.txt", "token = " + token)
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
      archive.writestr("nested.zip", inner.getvalue())
    source = self.historical_source(outer.getvalue(), "deleted.zip")
    with tempfile.TemporaryDirectory() as temporary:
      scanner = self.scanner(Path(temporary))
      scanner.add(source)
      self.assertGreaterEqual(scanner.decoded["zip"], 3)
      with self.assertRaisesRegex(RuntimeError, "secret scan rejected") as caught:
        scanner.scan()
      self.assertNotIn(token, str(caught.exception))

  def test_git_archives_keep_enclosing_depth_and_aggregate_expansion_budgets(self):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
      archive.writestr("readme.txt", "Harmless bounded historical input" * 100)
    source = self.historical_source(payload.getvalue(), "deleted.zip")
    for mode in ("depth", "bytes"):
      with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
        scanner = self.scanner(Path(temporary))
        with self.assertRaisesRegex(RuntimeError, "expansion exceeded"):
          if mode == "depth":
            scanner.save(source.read_bytes(), "outer-source.zip", depth=7)
          else:
            with mock.patch.object(security, "MAX_EXPANDED", source.stat().st_size):
              scanner.add(source)

  def test_nested_corrupt_archive_cli_failure_never_prints_sensitive_member_name(self):
    token = self.token()
    nested = io.BytesIO()
    payload = b"Harmless nested CRC control"
    with zipfile.ZipFile(nested, "w", compression=zipfile.ZIP_STORED) as archive:
      archive.writestr(token + ".txt", payload)
    corrupted = bytearray(nested.getvalue())
    corrupted[corrupted.index(payload)] ^= 1
    with tempfile.TemporaryDirectory() as temporary:
      assets = Path(temporary) / "assets"
      assets.mkdir()
      outer = assets / "synthetic.zip"
      with zipfile.ZipFile(outer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("nested.zip", corrupted)
      security.policy.inspect_file(outer)
      result = subprocess.run([sys.executable, str(security.ROOT / "tools/artifact_security.py"),
                               str(assets), "--tools", str(TOOLS)], capture_output=True, text=True, timeout=60)
      self.assertEqual(result.returncode, 1)
      output = result.stdout + result.stderr
      self.assertIn("ZIP structure or integrity validation failed", output)
      self.assertNotIn(token, output)
      self.assertNotIn("Traceback", output)

  def test_harmless_control_passes(self):
    with tempfile.TemporaryDirectory() as temporary:
      scanner = self.scanner(Path(temporary))
      scanner.save(b"Harmless synthetic public release\n", "README.md")
      self.assertTrue(scanner.scan()["passed"])


if __name__ == "__main__":
  unittest.main()
