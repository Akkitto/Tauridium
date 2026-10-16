"""Custody hashes are trusted out-of-band, not self-declared by downloaded files."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import release_policy
import release_snapshot as snapshot


class ReleaseSnapshotTests(unittest.TestCase):
  def test_each_custody_stage_rejects_mutation_identity_changes_and_extra_files(self):
    for stage in ("unsigned", "signed", "final"):
      with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for name in snapshot.names("9.9.9", stage):
          (root / name).write_bytes(b"Synthetic opaque bytes, not executable archives")
        with mock.patch.object(release_policy, "inspect_file", side_effect=AssertionError("no parsers under custody")):
          digest = snapshot.seal(root, "9.9.9", "a" * 40, stage)
          snapshot.verify(root, "9.9.9", "a" * 40, stage, digest)
          for version, commit, expected in (("9.9.8", "a" * 40, digest), ("9.9.9", "b" * 40, digest),
                                             ("9.9.9", "a" * 40, "0" * 64)):
            with self.assertRaises(SystemExit):
              snapshot.verify(root, version, commit, stage, expected)
          with self.assertRaisesRegex(SystemExit, "immutable"):
            snapshot.seal(root, "9.9.9", "a" * 40, stage)
          (root / "release-notes.md").write_bytes(b"Changed notes")
          with self.assertRaisesRegex(SystemExit, "changed"):
            snapshot.verify(root, "9.9.9", "a" * 40, stage, digest)
          (root / "private.key").write_bytes(b"Synthetic forbidden auxiliary file")
          with self.assertRaisesRegex(SystemExit, "inventory differs"):
            snapshot.verify(root, "9.9.9", "a" * 40, stage, digest)

  def test_seal_rejects_symlinks_and_unbound_release_identity(self):
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      with self.assertRaisesRegex(SystemExit, "immutable version/commit"):
        snapshot.seal(root, "9.9.9", "master", "unsigned")
      for name in snapshot.names("9.9.9", "unsigned"):
        (root / name).write_bytes(b"Synthetic")
      path = root / "release-notes.md"
      path.unlink()
      try:
        path.symlink_to(root / sorted(snapshot.names("9.9.9", "unsigned") - {path.name})[0])
      except OSError:
        self.skipTest("OS does not allow this test's temporary symlink")
      with self.assertRaisesRegex(SystemExit, "never a link"):
        snapshot.seal(root, "9.9.9", "a" * 40, "unsigned")


if __name__ == "__main__":
  unittest.main()
