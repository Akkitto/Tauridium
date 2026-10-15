"""Publication rejects extra files, unsafe members and partial collections."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

import release_assets
import release_policy as policy


class ReleasePolicyTests(unittest.TestCase):
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
