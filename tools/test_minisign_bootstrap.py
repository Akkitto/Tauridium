"""Checksum-bound Linux bootstrap works without a distro Minisign package."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import security_tools as tools
import updater_signature


class MinisignBootstrapTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.policy = json.loads((tools.ROOT / "data/security-tools.json").read_text(encoding="utf-8"))
    (self.root / "data").mkdir()
    self.write_policy()
    for patcher in (mock.patch.object(tools, "ROOT", self.root),
                    mock.patch.object(tools.platform, "system", return_value="Linux"),
                    mock.patch.object(tools.platform, "machine", return_value="x86_64"),
                    mock.patch.dict(os.environ, {
                      "USERPROFILE": str(self.root / "absent-windows-profile"),
                      "LOCALAPPDATA": str(self.root / "absent-windows-appdata"),
                    })):
      patcher.start()
      self.addCleanup(patcher.stop)

  def write_policy(self):
    (self.root / "data/security-tools.json").write_text(json.dumps(self.policy), encoding="utf-8")

  def test_official_archive_has_distinct_exact_architecture_members_and_hashes(self):
    x64, arm = tools.minisign_entry("amd64"), tools.minisign_entry("arm64")
    self.assertEqual(x64["url"], arm["url"])
    self.assertEqual(x64["sha256"], arm["sha256"])
    self.assertEqual(x64["member"], "minisign-linux/x86_64/minisign")
    self.assertEqual(arm["member"], "minisign-linux/aarch64/minisign")
    self.assertNotEqual(x64["binarySha256"], arm["binarySha256"])
    for entry in (x64, arm):
      self.assertRegex(entry["binarySha256"], r"^[0-9a-f]{64}$")
    with self.assertRaisesRegex(SystemExit, "x64 and ARM64"):
      tools.minisign_entry("unreviewed")

  def test_arm64_support_does_not_enable_x64_artifact_scanners(self):
    with mock.patch.object(tools.platform, "machine", return_value="aarch64"):
      self.assertTrue(tools.minisign_cache().name.endswith("-aarch64"))
      for only in (None, "gitleaks", "7zz"):
        with self.assertRaisesRegex(SystemExit, "Linux x64"):
          tools.install(self.root / "must-not-exist", only)
      self.assertFalse((self.root / "must-not-exist").exists())

  def test_cached_tool_is_found_by_new_process_policy_and_tampering_is_rejected(self):
    binary = b"Synthetic inert executable fixture, never executed"
    self.policy["minisign"]["binarySha256"] = hashlib.sha256(binary).hexdigest()
    self.write_policy()
    path = tools.minisign_cache() / "minisign"
    path.parent.mkdir(parents=True)
    path.write_bytes(binary)
    with mock.patch.object(updater_signature.shutil, "which", return_value=None):
      self.assertEqual(updater_signature.find_minisign(), str(path))
      path.write_bytes(binary + b" changed")
      self.assertIsNone(updater_signature.find_minisign())

  def test_nonregular_cached_tool_is_never_selected(self):
    path = tools.minisign_cache() / "minisign"
    path.mkdir(parents=True)
    self.assertIsNone(tools.cached_minisign())

  def test_wrong_archive_checksum_leaves_no_installed_tool(self):
    output = self.root / "fresh-install"
    opener = mock.Mock()
    opener.open.return_value = io.BytesIO(b"Not the pinned official archive")
    with mock.patch.object(tools, "build_opener", return_value=opener):
      with self.assertRaisesRegex(SystemExit, "checksum/size"):
        tools.install(output, "minisign")
    self.assertFalse(output.exists())

  def test_existing_cache_is_never_replaced(self):
    output = self.root / "existing"
    output.mkdir()
    canary = output / "owner-file"
    canary.write_bytes(b"Preserve existing content")
    with mock.patch.object(tools, "build_opener") as opener:
      with self.assertRaisesRegex(SystemExit, "fresh directory"):
        tools.install(output, "minisign")
      opener.assert_not_called()
    self.assertEqual(canary.read_bytes(), b"Preserve existing content")


if __name__ == "__main__":
  unittest.main()
