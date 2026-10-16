"""Publication rejects extra files, unsafe members and partial collections."""
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock
import zipfile

import release_assets
import release_policy as policy


class ReleasePolicyTests(unittest.TestCase):
  def test_zip_directory_members_cannot_hide_nonempty_payloads(self):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
      archive.writestr("hidden/", "Harmless nonempty directory control")
    with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as archive:
      self.assertIsNone(archive.testzip())
      with self.assertRaisesRegex(SystemExit, "directory entries"):
        policy.zip_layout(archive)

  def test_zip_layout_accepts_streaming_descriptors_zip64_and_comments(self):
    class Streaming(io.BytesIO):
      def seek(self, *_args):
        raise io.UnsupportedOperation("Synthetic non-seekable output")
    for wide in (False, True):
      stream = Streaming()
      with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.comment = b"Harmless public comment"
        with archive.open("readme.txt", "w", force_zip64=wide) as output:
          output.write(b"Harmless streaming control" * 100)
      data = stream.getvalue()
      with zipfile.ZipFile(io.BytesIO(data)) as archive:
        policy.zip_layout(archive)
        self.assertIsNone(archive.testzip())
      # The descriptor signature is optional; sizes/CRC still have to agree.
      descriptor = data.index(b"PK\x07\x08")
      unsigned = bytearray(data[:descriptor] + data[descriptor + 4:])
      footer = unsigned.rfind(b"PK\x05\x06")
      struct.pack_into("<I", unsigned, footer + 16, struct.unpack_from("<I", unsigned, footer + 16)[0] - 4)
      with zipfile.ZipFile(io.BytesIO(unsigned)) as archive:
        policy.zip_layout(archive)
        self.assertIsNone(archive.testzip())
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
      archive.writestr("readme.txt", "Harmless ZIP64 directory control")
    data = stream.getvalue()
    footer = len(data) - 22
    fields = struct.unpack("<4s4H2IH", data[footer:])
    record = struct.pack("<4sQ2H2I4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, fields[4], fields[4], fields[5], fields[6])
    locator = struct.pack("<4sIQI", b"PK\x06\x07", 0, footer, 1)
    ending = struct.pack("<4s4H2IH", b"PK\x05\x06", 0, 0, 65535, 65535, 0xffffffff, 0xffffffff, 0)
    with zipfile.ZipFile(io.BytesIO(data[:footer] + record + locator + ending)) as archive:
      policy.zip_layout(archive)
      self.assertIsNone(archive.testzip())

  def test_zip_layout_rejects_unindexed_records_and_trailing_bytes(self):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
      archive.writestr("visible.txt", "Harmless visible control")
      archive.writestr("unindexed.txt", "Harmless unindexed control")
      hidden = archive.filelist.pop()
      archive.NameToInfo.pop(hidden.filename)
    with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as archive:
      self.assertEqual(archive.namelist(), ["visible.txt"])
      self.assertIsNone(archive.testzip())
      with self.assertRaisesRegex(SystemExit, "unindexed, overlapping or trailing"):
        policy.zip_layout(archive)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
      archive.writestr("readme.txt", "Harmless control")
    with zipfile.ZipFile(io.BytesIO(stream.getvalue() + b"Trailing unindexed data")) as archive:
      with self.assertRaisesRegex(SystemExit, "unindexed, overlapping or trailing"):
        policy.zip_layout(archive)

  def test_zip_layout_rejects_preambles_and_concatenation_but_accepts_normal_and_empty(self):
    def packed(entries):
      stream = io.BytesIO()
      with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
          archive.writestr(name, data)
      return stream.getvalue()
    normal = packed([("readme.txt", "Harmless control")])
    empty = packed([])
    for data in (normal, empty):
      with zipfile.ZipFile(io.BytesIO(data)) as archive:
        policy.zip_layout(archive)
    for data in (b"Harmless preamble" + normal, b"Harmless preamble" + empty,
                 normal + empty, empty + normal, normal + normal):
      with self.subTest(size=len(data)), tempfile.TemporaryDirectory() as temporary:
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(data)))
        path = Path(temporary) / "test.zip"
        path.write_bytes(data)
        with self.assertRaisesRegex(SystemExit, "preambles or concatenated"):
          policy.inspect_file(path)

  def test_public_inventory_is_exact_and_has_no_private_handoff_metadata(self):
    names = policy.public_names("9.9.9")
    self.assertEqual(len(names), 32)
    self.assertNotIn("release-notes.md", names)
    self.assertIn("latest.json", names)
    self.assertEqual(sum(name.endswith(".sig") for name in names), 6)
    self.assertFalse(any("WIP" in name or ".git" in name for name in names))

  def test_directory_rejects_surprise_file_and_links(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      (root / "allowed.json").write_text("{}", encoding="utf-8")
      policy.validate_directory(root, {"allowed.json"})
      (root / "unexpected.env").write_text("synthetic", encoding="utf-8")
      with self.assertRaisesRegex(SystemExit, "inventory differs"):
        policy.validate_directory(root, {"allowed.json"})
      (root / "unexpected.env").unlink()
      try:
        (root / "linked.json").symlink_to(root / "allowed.json")
      except OSError:
        self.skipTest("Symlink privilege unavailable")
      with self.assertRaisesRegex(SystemExit, "regular file"):
        policy.validate_directory(root, {"allowed.json", "linked.json"})

  def test_zip_rejects_traversal_duplicate_and_symlink(self):
    for name in ("../outside", "/absolute", "directory\\file", "drive:stream"):
      with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "test.zip"
        with zipfile.ZipFile(path, "w") as archive:
          archive.writestr(name, b"synthetic")
        with self.assertRaisesRegex(SystemExit, "unsafe"):
          policy.inspect_file(path)
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / "test.zip"
      entry = zipfile.ZipInfo("linked")
      entry.external_attr = 0o120777 << 16
      with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(entry, b"outside")
      with self.assertRaisesRegex(SystemExit, "link or special"):
        policy.inspect_file(path)

  def test_inventory_diagnostics_never_print_unapproved_filenames(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      name = "synthetic-private-value-in-filename.env"
      (root / name).write_bytes(b"Synthetic")
      with self.assertRaisesRegex(SystemExit, "unexpectedFileCount=1") as caught:
        policy.validate_directory(root, set())
      self.assertNotIn(name, str(caught.exception))

  def test_invalid_last_bundle_never_promotes_partial_collection(self):
    with tempfile.TemporaryDirectory() as directory:
      output = Path(directory) / "native"
      def incomplete(_target, staged, _require):
        path = staged / "partial.json"
        path.write_text("{}", encoding="utf-8")
        return [path]
      with mock.patch.object(release_assets, "_collect_native_into", side_effect=incomplete):
        with self.assertRaisesRegex(SystemExit, "inventory differs"):
          release_assets.collect_native("x86_64-pc-windows-msvc", output, False)
      self.assertFalse(output.exists())
      output.mkdir()
      (output / "keep.txt").write_text("keep", encoding="utf-8")
      with self.assertRaisesRegex(SystemExit, "fresh output"):
        release_assets.collect_native("x86_64-pc-windows-msvc", output, False)
      self.assertEqual((output / "keep.txt").read_text(encoding="utf-8"), "keep")

  def test_checksums_cover_published_updater_but_not_unpublished_release_notes(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      (root / "latest.json").write_text("{}", encoding="utf-8")
      (root / "release-notes.md").write_text("internal transport", encoding="utf-8")
      release_assets.write_checksums(root, root / "SHA256SUMS")
      data = (root / "SHA256SUMS").read_text(encoding="utf-8")
      self.assertIn("  latest.json\n", data)
      self.assertNotIn("release-notes", data)


if __name__ == "__main__":
  unittest.main()
