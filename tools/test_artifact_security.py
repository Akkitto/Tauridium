"""Synthetic leak controls and independent NSIS parsing; no real credential fixtures."""
import base64
import copy
import hashlib
import gzip
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
import tarfile
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
  def test_every_decoder_output_obeys_the_same_private_path_policy(self):
    for name in ("archive/.aws/config", "package/.ssh/config", "package/.ENV", "CAB/session.json"):
      with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
        scanner = security.Scanner(Path(temporary), Path("/unused-tools"))
        with self.assertRaisesRegex(RuntimeError, "private configuration material"):
          scanner.save(b"Harmless private configuration control", name, decode=False)
        self.assertFalse(any(scanner.corpus.iterdir()))

  def test_git_storage_requires_complete_typed_streams_and_exact_checksums(self):
    content = b"blob 16\0Harmless control"
    identity = hashlib.sha1(content, usedforsecurity=False).hexdigest()
    path = "objects/" + identity[:2] + "/" + identity[2:]
    valid = zlib.compress(content)
    security.Scanner.git_storage(path, valid)
    for data in (valid + b"Trailing control", valid + zlib.compress(b"Hidden control"), valid[:-1],
                 zlib.compress(b"blob 999\0Harmless control")):
      with self.subTest(size=len(data)):
        with self.assertRaisesRegex(RuntimeError, "storage checksum"):
          security.Scanner.git_storage(path, data)
    body = b"PACK" + struct.pack(">II", 2, 0)
    digest = hashlib.sha1(body, usedforsecurity=False).digest()
    pack = "objects/pack/pack-" + digest.hex() + ".pack"
    security.Scanner.git_storage(pack, body + digest)
    with self.assertRaisesRegex(RuntimeError, "storage checksum"):
      security.Scanner.git_storage(pack, body + digest + b"Trailing control")
    with self.assertRaisesRegex(RuntimeError, "storage checksum"):
      security.Scanner.git_storage(pack, body + bytes(20))

  def test_git_namespaces_and_source_manifests_cannot_shadow_one_another(self):
    variants = (
      [("first/.git/objects/aa/" + "1" * 38, b"compressed control"), ("second/.git/objects/aa/" + "1" * 38, b"replacement")],
      [("first/.git/", b""), ("second/.git/", b"")],
      [("source/.git/config", b"control"), ("other/.tauridium-source-manifest.json", b"{}")],
      [("first/.tauridium-source-manifest.json", b"{}"), ("second/.tauridium-source-manifest.json", b"{}")],
      [("source/.git/nested/.git/config", b"control")],
      [("source/.GIT/", b"")],
    )
    for entries in variants:
      with self.subTest(entries=[name for name, _ in entries]), tempfile.TemporaryDirectory() as temporary:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
          for name, data in entries:
            archive.writestr(name, data)
        scanner = security.Scanner(Path(temporary), Path("/unused-tools"))
        with self.assertRaisesRegex(RuntimeError, "Git roots|bound to|multiple source manifests|noncanonical Git"):
          scanner.save(stream.getvalue(), "ordinary.zip")

  def test_noncanonical_windows_git_casing_cannot_skip_approved_history_validation(self):
    for directory in (".Git", ".GIT", ".gIt"):
      with self.subTest(directory=directory), tempfile.TemporaryDirectory() as temporary:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
          archive.writestr(directory + "/config", "Harmless unapproved configuration")
        scanner = security.Scanner(Path(temporary), Path("/unused-tools"))
        with self.assertRaisesRegex(RuntimeError, "noncanonical Git"):
          scanner.save(stream.getvalue(), "renamed.bin")

  def test_container_context_replay_is_bounded_and_does_not_suppress_missing_ocr(self):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
      archive.writestr("renamed.bin", b"\x89PNG\r\n\x1a\nsynthetic-control")
    data = stream.getvalue()
    with tempfile.TemporaryDirectory() as temporary:
      scanner = security.Scanner(Path(temporary), Path("/unused-tools"))
      scanner.save(data, "assets/copy.zip")
      with mock.patch.object(security.shutil, "which", return_value=None):
        with self.assertRaisesRegex(RuntimeError, "requires the OCR"):
          scanner.save(data, "evidence/copy.zip")
      with (mock.patch.object(security.shutil, "which", return_value="synthetic-tesseract"),
            mock.patch.object(security, "bounded_command", return_value=b"Harmless OCR") as ocr):
        scanner.save(data, "evidence/retry.zip")
        for index in range(20):
          scanner.save(data, f"aliases/{index}/evidence/copy.zip")
          scanner.save(data, f"assets/{index}/copy.zip")
        self.assertEqual(ocr.call_count, 1)
        self.assertEqual(len(scanner.decoded_payloads), 2)

  def test_container_parsing_uses_original_bytes_not_a_scoped_public_vector_view(self):
    vector = b"-----BEGIN PRIVATE KEY-----\nSYNTHETIC-NOT-A-KEY\n-----END PRIVATE KEY-----"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
      archive.writestr("unapproved/key.pem", vector)
    data = stream.getvalue()
    with tempfile.TemporaryDirectory() as temporary:
      scanner = security.Scanner(Path(temporary), Path("/unused-tools"))
      scanner.approved = {hashlib.sha256(security.normalized_pem(vector)).hexdigest()}
      scanner.save(data, "libgnutls-container.bin")
      self.assertEqual(scanner.decoded["zip"], 1)
      self.assertTrue(any(vector == path.read_bytes() for path in scanner.sources.values()))

  def test_prefixed_zip_recognition_and_policy_apply_without_a_filename_shortcut(self):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
      archive.writestr("readme.txt", "Harmless control")
    normal = stream.getvalue()
    for prefix in (b"Harmless preamble", b"MZ" + bytes(128), b"!<arch>\n"):
      with self.subTest(prefix=prefix[:8]), tempfile.TemporaryDirectory() as temporary:
        data = prefix + normal
        self.assertTrue(security.container(data))
        scanner = security.Scanner(Path(temporary), Path("/unused-tools"))
        with self.assertRaisesRegex(SystemExit, "preambles or concatenated"):
          scanner.save(data, "GIT-OBJECT/renamed")

  def test_recognized_corrupt_and_encrypted_prefixed_zip_fail_closed(self):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
      archive.writestr("readme.txt", "Harmless control")
    data = stream.getvalue()
    corrupt = data.replace(b"PK\x01\x02", b"BAD!", 1)
    encrypted = bytearray(data)
    struct.pack_into("<H", encrypted, 6, 1)
    struct.pack_into("<H", encrypted, encrypted.index(b"PK\x01\x02") + 8, 1)
    for payload in (corrupt, bytes(encrypted)):
      with self.subTest(payload=payload[:4]), tempfile.TemporaryDirectory() as temporary:
        scanner = security.Scanner(Path(temporary), Path("/unused-tools"))
        prefixed = b"Harmless prefix" + payload
        self.assertTrue(security.container(prefixed))
        with mock.patch.object(security.zipfile, "is_zipfile", return_value=False):
          self.assertTrue(security.container(prefixed))
        with self.assertRaises((SystemExit, zipfile.BadZipFile, security.ArtifactRejection)):
          scanner.save(prefixed, "nested/renamed.bin")

  def test_recursive_dispatch_recognizes_packages_without_relying_on_filenames(self):
    for data in (b"!<arch>\n", bytes.fromhex("edabeedb"), bytes.fromhex("d0cf11e0a1b11ae1"),
                 b"\x7fELF" + bytes(4) + b"AI\x02"):
      self.assertTrue(security.container(data))
    self.assertFalse(security.container(b"\x7fELF" + bytes(64)))

  def test_nested_renamed_msi_requires_the_auxiliary_table_gate(self):
    with tempfile.TemporaryDirectory() as temporary:
      scanner = security.Scanner(Path(temporary), Path("/unused-tools"))
      with (mock.patch.object(security, "bounded_command", return_value=b"Type = Compound\nExtension = msi\n----------\n"),
            mock.patch.object(scanner, "msi") as msi):
        scanner.save(bytes.fromhex("d0cf11e0a1b11ae1") + bytes(64), "GIT-OBJECT/renamed", depth=3)
        self.assertEqual(msi.call_args.args[1:], ("GIT-OBJECT/renamed", 3))

  def test_decode_and_ocr_obligations_survive_prior_content_only_inspection(self):
    with tempfile.TemporaryDirectory() as temporary:
      scanner = security.Scanner(Path(temporary), Path("/unused-tools"))
      png = b"\x89PNG\r\n\x1a\nsynthetic-control"
      scanner.save(png, "assets/copy.png")
      with mock.patch.object(security.shutil, "which", return_value=None):
        with self.assertRaisesRegex(RuntimeError, "requires the OCR"):
          scanner.save(png, "evidence/screenshot.png")
      with (mock.patch.object(security.shutil, "which", return_value="synthetic-tesseract"),
            mock.patch.object(security, "bounded_command", return_value=b"Harmless OCR") as ocr):
        scanner.save(png, "evidence/screenshot.png")
        scanner.save(png, "other/evidence/screenshot.png")
        self.assertEqual(ocr.call_count, 1)
      with mock.patch.object(scanner, "decode") as decode:
        scanner.save(b"!<arch>\nsynthetic", "listing.bin", decode=False)
        scanner.save(b"!<arch>\nsynthetic", "nested.bin")
        decode.assert_called_once()

  def test_scoped_public_vectors_do_not_suppress_an_unapproved_duplicate(self):
    fixture = b"-----BEGIN PRIVATE KEY-----\nSYNTHETIC-NOT-A-KEY\n-----END PRIVATE KEY-----"
    with tempfile.TemporaryDirectory() as temporary:
      scanner = security.Scanner(Path(temporary), Path("/unused-tools"))
      scanner.approved = {hashlib.sha256(security.normalized_pem(fixture)).hexdigest()}
      scanner.save(fixture, "usr/lib/libgnutls.so.30")
      scanner.save(fixture, "unapproved/key.pem")
      self.assertTrue(any(fixture == path.read_bytes() for path in scanner.sources.values()))

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
  def test_unindexed_compressed_zip_secret_is_rejected_not_silently_skipped(self):
    token = self.token()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
      archive.writestr("visible.txt", "Harmless visible control")
      archive.writestr("unindexed.txt", "token = " + token)
      hidden = archive.filelist.pop()
      archive.NameToInfo.pop(hidden.filename)
    data = stream.getvalue()
    self.assertNotIn(token.encode(), data)
    with tempfile.TemporaryDirectory() as temporary:
      scanner = self.scanner(Path(temporary))
      with self.assertRaisesRegex(SystemExit, "unindexed, overlapping or trailing") as caught:
        scanner.save(data, "GIT-OBJECT/renamed")
      self.assertNotIn(token, str(caught.exception))

  def test_prefixed_zip_is_rejected_directly_nested_and_in_deleted_approved_history(self):
    token = self.token()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
      archive.writestr("secret.txt", "token = " + token)
    normal = stream.getvalue()
    prefixed = b"Harmless ordinary ZIP preamble\n" + normal
    self.assertTrue(zipfile.is_zipfile(io.BytesIO(prefixed)))
    self.assertNotIn(token.encode(), prefixed)
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      baseline = root / "baseline"
      baseline.mkdir()
      scanner = self.scanner(baseline)
      scanner.save(normal, "normal.zip")
      with self.assertRaisesRegex(RuntimeError, "secret scan rejected"):
        scanner.scan()
      direct = root / "prefixed.zip"
      direct.write_bytes(prefixed)
      nested = root / "nested.zip"
      with zipfile.ZipFile(nested, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("renamed.bin", prefixed)
      history = self.historical_source(prefixed, "deleted-prefixed.zip")
      for index, path in enumerate((direct, nested, history)):
        with self.subTest(placement=index):
          state = root / f"scanner-{index}"
          state.mkdir()
          with self.assertRaisesRegex(SystemExit, "preambles or concatenated") as caught:
            self.scanner(state).add(path)
          self.assertNotIn(token, str(caught.exception))

  @unittest.skipUnless(shutil.which("wixl") and shutil.which("msiinfo"), "Real MSI control requires wixl and msiinfo")
  def test_renamed_nested_msi_property_tables_are_scanned(self):
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      token = self.token()
      (root / "payload.txt").write_text("Harmless data, never executed", encoding="utf-8")
      (root / "fixture.wxs").write_text(f'''<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
<Product Id="*" Name="Synthetic" Language="1033" Version="1.0.0" Manufacturer="Synthetic"
 UpgradeCode="9A9AA0F3-B491-4096-8987-A7DCFA47E155">
<Package InstallerVersion="200" Compressed="yes"/>
<Property Id="SYNTHETIC_TOKEN" Value="{token}"/>
<Binary Id="SyntheticBinary" SourceFile="payload.txt"/>
<Icon Id="SyntheticIcon" SourceFile="payload.txt"/>
<Media Id="1" Cabinet="fixture.cab" EmbedCab="yes"/>
<Directory Id="TARGETDIR" Name="SourceDir"><Directory Id="ProgramFilesFolder">
<Directory Id="INSTALLFOLDER" Name="Synthetic"><Component Id="Payload" Guid="*">
<File Id="PayloadFile" Source="payload.txt" KeyPath="yes"/></Component></Directory></Directory></Directory>
<Feature Id="Main" Level="1"><ComponentRef Id="Payload"/></Feature>
</Product></Wix>''', encoding="utf-8")
      subprocess.run(["wixl", "-o", "fixture.msi", "fixture.wxs"], cwd=root, capture_output=True, check=True, timeout=30)
      outer = root / "renamed.zip"
      with zipfile.ZipFile(outer, "w", compression=zipfile.ZIP_DEFLATED) as target:
        target.writestr("renamed-object.bin", (root / "fixture.msi").read_bytes())
      state = root / "scanner"
      state.mkdir()
      scanner = self.scanner(state)
      scanner.add(outer)
      self.assertEqual(scanner.decoded["msi-metadata"], 1)
      with self.assertRaisesRegex(RuntimeError, "secret scan rejected") as caught:
        scanner.scan()
      self.assertNotIn(token, str(caught.exception))

  def test_deb_secret_is_rejected_directly_nested_and_in_deleted_history(self):
    def packed_tar(name, payload):
      stream = io.BytesIO()
      with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        entry = tarfile.TarInfo(name)
        entry.size = len(payload)
        archive.addfile(entry, io.BytesIO(payload))
      return stream.getvalue()
    def member(name, payload):
      header = f'{name + "/":<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(payload):<10}`\n'.encode()
      return header + payload + (b"\n" if len(payload) % 2 else b"")
    token = self.token()
    deb = (b"!<arch>\n" + member("debian-binary", b"2.0\n")
           + member("control.tar.gz", packed_tar("control", b"Package: synthetic\nVersion: 1.0\nArchitecture: all\n"))
           + member("data.tar.gz", packed_tar("usr/share/synthetic", ("token = " + token).encode())))
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      direct = root / "synthetic.deb"
      direct.write_bytes(deb)
      nested = root / "nested.zip"
      with zipfile.ZipFile(nested, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("renamed-package.bin", deb)
      history = self.historical_source(deb, "deleted.deb")
      for index, path in enumerate((direct, nested, history)):
        with self.subTest(placement=index):
          state = root / f"scanner-{index}"
          state.mkdir()
          scanner = self.scanner(state)
          scanner.add(path)
          with self.assertRaisesRegex(RuntimeError, "secret scan rejected") as caught:
            scanner.scan()
          self.assertNotIn(token, str(caught.exception))

  @unittest.skipUnless(shutil.which("tesseract") and (shutil.which("magick") or shutil.which("convert"))
                       and Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf").is_file(),
                       "Real evidence OCR control requires Tesseract, ImageMagick and DejaVu Mono")
  def test_real_evidence_ocr_rejects_both_duplicate_orders_and_cross_artifact_reuse(self):
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      token, data = self.rendered_token_png(root)
      for order in ("ordinary-first", "evidence-first", "cross-artifact"):
        with self.subTest(order=order):
          state = root / order
          state.mkdir()
          scanner = self.scanner(state)
          names = ["assets/copied.png", "evidence/screenshot.png"]
          if order == "evidence-first":
            names.reverse()
          if order == "cross-artifact":
            scanner.save(data, "earlier.zip/assets/copied.png")
          archive = root / f"{order}.zip"
          with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for name in names:
              target.writestr(name, data)
          scanner.add(archive)
          with self.assertRaisesRegex(RuntimeError, "secret scan rejected") as caught:
            scanner.scan()
          self.assertNotIn(token, str(caught.exception))

  @unittest.skipUnless(shutil.which("tesseract") and (shutil.which("magick") or shutil.which("convert"))
                       and Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf").is_file(),
                       "Real evidence OCR control requires Tesseract, ImageMagick and DejaVu Mono")
  def test_nested_evidence_ocr_rejects_all_alias_orders_renamed_pngs_and_deleted_history(self):
    def packed(entries):
      stream = io.BytesIO()
      with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
          archive.writestr(name, data)
      return stream.getvalue()
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      token, image = self.rendered_token_png(root)
      for filename in ("screenshot.png", "renamed.bin"):
        for layers in (1, 2):
          nested = packed([(filename, image)])
          if layers == 2:
            nested = packed([("renamed-container.bin", nested)])
          for order in ("evidence-only", "ordinary-first", "evidence-first", "cross-artifact"):
            with self.subTest(filename=filename, layers=layers, order=order):
              state = root / f"state-{filename}-{layers}-{order}"
              state.mkdir()
              scanner = self.scanner(state)
              names = ["assets/copy.zip", "evidence/copy.zip"]
              if order == "evidence-first":
                names.reverse()
              elif order in ("evidence-only", "cross-artifact"):
                names = ["evidence/copy.zip"]
              if order == "cross-artifact":
                scanner.save(packed([("assets/copy.zip", nested)]), "earlier.zip")
              scanner.save(packed([(name, nested) for name in names]), "later.zip")
              self.assertEqual(len(scanner.ocr_completed), 1)
              with self.assertRaisesRegex(RuntimeError, "secret scan rejected") as caught:
                scanner.scan()
              self.assertNotIn(token, str(caught.exception))
      # Context must also survive the transition from archive paths to Git object
      # identities, where the original PNG extension is no longer available.
      history = self.historical_source(image, "deleted-image.png").read_bytes()
      state = root / "history-state"
      state.mkdir()
      scanner = self.scanner(state)
      scanner.save(packed([("assets/source.zip", history), ("evidence/source.zip", history)]), "outer.zip")
      self.assertEqual(len(scanner.ocr_completed), 1)
      with self.assertRaisesRegex(RuntimeError, "secret scan rejected") as caught:
        scanner.scan()
      self.assertNotIn(token, str(caught.exception))

  def rendered_token_png(self, root):
    image = root / "synthetic.png"
    for _ in range(10):
      # Sampling without replacement avoids accidental low-entropy fixtures that
      # the real detector intentionally filters; do not rely on a lucky token.
      token = "AKIA" + "".join(secrets.SystemRandom().sample("ACEFHJKLPRTVXY347", 16))
      subprocess.run([shutil.which("magick") or shutil.which("convert"), "-size", "2600x180", "xc:white",
                      "-font", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "-pointsize", "64",
                      "-fill", "black", "-gravity", "center", "-annotate", "0", "token = " + token, str(image)],
                     capture_output=True, check=True, timeout=30)
      text = subprocess.check_output(["tesseract", str(image), "stdout"], stderr=subprocess.DEVNULL, timeout=30)
      if token.encode() in text:
        break
    self.assertTrue(token.encode() in text, "OCR positive control could not read the synthetic token exactly")
    control = root / "ocr-positive-control"
    control.mkdir()
    scanner = self.scanner(control)
    scanner.save(text, "OCR-CONTROL", decode=False)
    with self.assertRaisesRegex(RuntimeError, "secret scan rejected"):
      scanner.scan()
    return token, image.read_bytes()

  @unittest.skipUnless(shutil.which("tesseract") and (shutil.which("magick") or shutil.which("convert"))
                       and Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf").is_file(),
                       "Real historical OCR control requires Tesseract, ImageMagick and DejaVu Mono")
  def test_deleted_historical_evidence_retains_ocr_without_an_outer_evidence_alias(self):
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      token, image = self.rendered_token_png(root)
      stream = io.BytesIO()
      with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("renamed-image.bin", image)
      cases = (("release/evidence/deleted.PNG", image), ("release/evidence/renamed.bin", image),
               ("release/evidence/deleted-container.zip", stream.getvalue()),
               ("release/evidence/deleted-container.bin", gzip.compress(image, mtime=0)),
               ("release/evidence/deleted-nested.bin", gzip.compress(gzip.compress(image, mtime=0), mtime=0)))
      for filename, payload in cases:
        with self.subTest(filename=filename):
          source = self.historical_source(payload, filename)
          state = root / ("state-" + Path(filename).name)
          state.mkdir()
          scanner = self.scanner(state)
          scanner.save(source.read_bytes(), "ordinary/source.zip")
          self.assertEqual(len(scanner.ocr_completed), 1)
          with self.assertRaisesRegex(RuntimeError, "secret scan rejected") as caught:
            scanner.scan()
          self.assertNotIn(token, str(caught.exception))

  def test_git_pack_hidden_suffix_is_rejected_even_with_recomputed_storage_checksums(self):
    source = self.historical_source(b"Harmless historical control", "deleted.txt", packed=True)
    with tempfile.TemporaryDirectory() as temporary:
      scanner = self.scanner(Path(temporary))
      scanner.add(source)
      self.assertTrue(scanner.scan()["passed"])
    with zipfile.ZipFile(source) as archive:
      entries = [(copy.copy(member), archive.read(member)) for member in archive.infolist()]
    pack_name, pack = next((member.filename, data) for member, data in entries if member.filename.endswith(".pack"))
    index_name, index = next((member.filename, data) for member, data in entries if member.filename.endswith(".idx"))
    token = self.token().encode()
    hidden = zlib.compress(b"Harmless repeated padding\n" * 100 + b"token = " + token)
    self.assertNotIn(token, hidden)
    pack_body = pack[:-20] + hidden
    pack_digest = hashlib.sha1(pack_body, usedforsecurity=False).digest()
    new_pack = pack_body + pack_digest
    index_body = index[:-40] + pack_digest
    new_index = index_body + hashlib.sha1(index_body, usedforsecurity=False).digest()
    prefix = pack_name.rsplit("/", 1)[0] + "/pack-" + pack_digest.hex()
    replacements = {pack_name: (prefix + ".pack", new_pack), index_name: (prefix + ".idx", new_index)}
    # These outer checksums are deliberately valid. The native strict Git
    # parser must reject bytes outside its declared object stream, not merely
    # rely on a digest or on a generic ZIP probe inside opaque pack storage.
    security.Scanner.git_storage("objects/pack/pack-" + pack_digest.hex() + ".pack", new_pack)
    security.Scanner.git_storage("objects/pack/pack-" + pack_digest.hex() + ".idx", new_index)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
      for member, data in entries:
        if member.filename in replacements:
          member.filename, data = replacements[member.filename]
        elif member.filename.endswith(".tauridium-source-manifest.json"):
          manifest = json.loads(data)
          for record in manifest["gitFiles"]:
            for old, (new, payload) in replacements.items():
              if old.endswith("/" + record["path"]):
                record["path"] = ".git/" + new.split("/.git/", 1)[1]
                record["sha256"] = hashlib.sha256(payload).hexdigest()
          data = json.dumps(manifest).encode()
        archive.writestr(member, data)
    with tempfile.TemporaryDirectory() as temporary:
      scanner = self.scanner(Path(temporary))
      with self.assertRaises(security.DecoderFailure):
        scanner.save(stream.getvalue(), "ordinary/source.zip")

  def test_deleted_historical_private_configuration_paths_are_never_public(self):
    for filename in ("private/.env", "private/.aws/config", "private/app_settings.json"):
      with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temporary:
        source = self.historical_source(b"Harmless synthetic private configuration", filename)
        scanner = self.scanner(Path(temporary))
        with self.assertRaisesRegex(RuntimeError, "private configuration material"):
          scanner.save(source.read_bytes(), "ordinary/source.zip")

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

  def historical_source(self, payload, filename, *, packed=False):
    from test_package_release import PackageReleaseTests
    fixture = PackageReleaseTests()
    fixture.setUp()
    self.addCleanup(fixture.tearDown)
    fixture.init_git_repository()
    path = fixture.root / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    def git(*args):
      subprocess.run(["git", *args], cwd=fixture.root, capture_output=True, check=True)
    if packed:
      # The clean export's fetch unpacks small repositories. Exceed Git's normal
      # 100-object threshold so this is a genuine packed public-history fixture.
      directory = fixture.root / "synthetic-packed-fixture"
      directory.mkdir()
      for index in range(120):
        (directory / str(index)).write_bytes(("Harmless packed fixture " + str(index)).encode())
      git("add", "synthetic-packed-fixture")
      git("commit", "-qm", "Test: Populate harmless packed-history control")
    git("add", "-f", filename)
    git("commit", "-qm", "Test: Add synthetic historical token")
    git("rm", "-q", filename)
    git("commit", "-qm", "Test: Remove synthetic token from current tree")
    git("tag", "-f", "v0.2.0")
    if packed:
      git("repack", "-a", "-d")
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
