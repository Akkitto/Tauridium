"""Checksum-bound Linux bootstrap works without a distro Minisign package."""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import stat
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile
import base64

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


class WindowsMinisignBootstrapTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.policy = json.loads((tools.ROOT / "data/security-tools.json").read_text(encoding="utf-8"))
    (self.root / "data").mkdir()
    for patcher in (mock.patch.object(tools, "ROOT", self.root),
                    mock.patch.object(tools.platform, "system", return_value="Windows"),
                    mock.patch.object(tools.platform, "machine", return_value="AMD64")):
      patcher.start()
      self.addCleanup(patcher.stop)
    self.binary = self.pe_binary(0x8664)
    self.policy["minisign"]["windows"]["architectures"]["x86_64"]["binarySha256"] = hashlib.sha256(self.binary).hexdigest()
    self.write_policy()

  @staticmethod
  def pe_binary(machine):
    binary = bytearray(128)
    binary[:2] = b"MZ"
    struct.pack_into("<I", binary, 0x3c, 64)
    binary[64:68] = b"PE\0\0"
    struct.pack_into("<H", binary, 68, machine)
    return bytes(binary)

  def write_policy(self):
    (self.root / "data/security-tools.json").write_text(json.dumps(self.policy), encoding="utf-8")

  def archive(self, *, binary=None, duplicate=False, mode=stat.S_IFREG | 0o755, attributes=0):
    data = self.binary if binary is None else binary
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
      for _ in range(2 if duplicate else 1):
        info = zipfile.ZipInfo(tools.minisign_entry()["member"])
        info.external_attr = (mode << 16) | attributes
        archive.writestr(info, data)
    payload = stream.getvalue()
    self.policy["minisign"]["windows"]["sha256"] = hashlib.sha256(payload).hexdigest()
    self.write_policy()
    return payload

  def download(self, payload):
    opener = mock.Mock()
    opener.open.return_value = io.BytesIO(payload)
    return mock.patch.object(tools, "build_opener", return_value=opener)

  def cache_binary(self, binary=None):
    path = tools.minisign_cache() / "minisign.exe"
    path.parent.mkdir(parents=True)
    path.write_bytes(self.binary if binary is None else binary)
    return path

  def test_windows_policy_selects_native_members_without_changing_linux_signer(self):
    x64, arm = tools.minisign_entry("AMD64"), tools.minisign_entry("ARM64")
    self.assertEqual(x64["url"], arm["url"])
    self.assertEqual(x64["sha256"], arm["sha256"])
    self.assertEqual(x64["member"], "minisign-win64/x86_64/minisign.exe")
    self.assertEqual(arm["member"], "minisign-win64/aarch64/minisign.exe")
    self.assertEqual(x64["peMachine"], 0x8664)
    self.assertEqual(arm["peMachine"], 0xAA64)
    self.assertNotEqual(x64["binarySha256"], arm["binarySha256"])
    self.assertEqual(tools.minisign_entry("AMD64", "Linux")["binarySha256"],
                     "2c74dffcc1c9a5ee55957c60971998ace2b89f22585631594ec2152c588af8db")
    with mock.patch.object(tools.platform, "machine", return_value="ARM64"):
      self.assertTrue(tools.minisign_cache().name.endswith("-windows-aarch64"))

  def test_windows_cannot_install_linux_artifact_scanners(self):
    for only in (None, "gitleaks", "7zz"):
      with self.assertRaisesRegex(SystemExit, "Linux x64"):
        tools.install(self.root / "must-not-exist", only)
    self.assertFalse((self.root / "must-not-exist").exists())

  def test_arm64_fallback_installs_and_discovers_the_native_pe(self):
    self.binary = self.pe_binary(0xAA64)
    self.policy["minisign"]["windows"]["architectures"]["aarch64"]["binarySha256"] = hashlib.sha256(self.binary).hexdigest()
    self.write_policy()
    with mock.patch.object(tools.platform, "machine", return_value="ARM64"):
      payload = self.archive()
      with self.download(payload):
        tools.install(tools.minisign_cache(), "minisign")
      path = tools.cached_minisign()
      self.assertIsNotNone(path)
      self.assertIn("-windows-aarch64", path)
      self.assertEqual(Path(path).read_bytes(), self.binary)

  def test_portable_fallback_does_not_need_path_or_a_package_manager(self):
    payload = self.archive()
    with self.download(payload), mock.patch.object(tools.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=b"minisign 0.12\n")) as probe:
      executable = tools.ensure_minisign()
    self.assertEqual(Path(executable).name, "minisign.exe")
    self.assertEqual(Path(executable).read_bytes(), self.binary)
    self.assertEqual(probe.call_args.args[0], [executable, "-v"])
    with mock.patch.object(updater_signature.shutil, "which", return_value=None):
      self.assertEqual(updater_signature.find_minisign(), executable)

  def test_verified_cache_works_without_downloads_or_signing_environment(self):
    path = self.cache_binary()
    with (mock.patch.object(tools, "build_opener") as opener,
          mock.patch.object(tools.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=b"minisign 0.12\n")) as probe,
          mock.patch.dict(os.environ, {"TAURI_SIGNING_PRIVATE_KEY": "synthetic-not-a-real-key", "UNRELATED_TOKEN": "synthetic-not-a-token"})):
      self.assertEqual(tools.ensure_minisign(download=False), str(path))
    opener.assert_not_called()
    self.assertNotIn("TAURI_SIGNING_PRIVATE_KEY", probe.call_args.kwargs["env"])
    self.assertNotIn("UNRELATED_TOKEN", probe.call_args.kwargs["env"])

  def test_missing_no_download_cache_never_uses_network_or_executes(self):
    with mock.patch.object(tools, "build_opener") as opener, mock.patch.object(tools.subprocess, "run") as probe:
      with self.assertRaisesRegex(SystemExit, "downloads are disabled"):
        tools.ensure_minisign(download=False)
    opener.assert_not_called()
    probe.assert_not_called()
    self.assertFalse(tools.minisign_cache().exists())

  def test_tampered_existing_cache_is_preserved_and_never_executed(self):
    path = self.cache_binary(b"Preserve this corrupted cache for owner review")
    for download in (False, True):
      with mock.patch.object(tools, "build_opener") as opener, mock.patch.object(tools.subprocess, "run") as probe:
        with self.assertRaisesRegex(SystemExit, "cached Minisign failed integrity"):
          tools.ensure_minisign(download=download)
      opener.assert_not_called()
      probe.assert_not_called()
    self.assertEqual(path.read_bytes(), b"Preserve this corrupted cache for owner review")

  def test_wrong_windows_archive_checksum_leaves_no_cache(self):
    with self.download(b"Not the reviewed official ZIP"):
      with self.assertRaisesRegex(SystemExit, "archive checksum/size"):
        tools.install(tools.minisign_cache(), "minisign")
    self.assertFalse(tools.minisign_cache().exists())

  def test_wrong_binary_hash_leaves_no_cache(self):
    payload = self.archive(binary=self.binary + b"changed")
    with self.download(payload):
      with self.assertRaisesRegex(SystemExit, "executable checksum/architecture"):
        tools.install(tools.minisign_cache(), "minisign")
    self.assertFalse(tools.minisign_cache().exists())

  def test_pe_architecture_is_checked_independently_of_hash(self):
    arm = self.pe_binary(0xAA64)
    self.policy["minisign"]["windows"]["architectures"]["x86_64"]["binarySha256"] = hashlib.sha256(arm).hexdigest()
    payload = self.archive(binary=arm)
    with self.download(payload):
      with self.assertRaisesRegex(SystemExit, "executable checksum/architecture"):
        tools.install(tools.minisign_cache(), "minisign")
    self.assertFalse(tools.minisign_cache().exists())

  def test_duplicate_zip_executable_is_rejected(self):
    with self.assertWarnsRegex(UserWarning, "Duplicate name"):
      payload = self.archive(duplicate=True)
    with self.download(payload):
      with self.assertRaisesRegex(SystemExit, "unique regular executable"):
        tools.install(tools.minisign_cache(), "minisign")
    self.assertFalse(tools.minisign_cache().exists())

  def test_link_and_reparse_zip_members_are_rejected(self):
    for settings in ({"mode": stat.S_IFLNK | 0o777}, {"attributes": 0x400}):
      payload = self.archive(**settings)
      with self.download(payload):
        with self.assertRaisesRegex(SystemExit, "unique regular executable"):
          tools.install(tools.minisign_cache(), "minisign")
      self.assertFalse(tools.minisign_cache().exists())

  def test_windows_reparse_metadata_is_rejected(self):
    metadata = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_file_attributes=0x400)
    with mock.patch.object(Path, "lstat", return_value=metadata):
      self.assertTrue(tools.unsafe_link(self.root / "junction"))
    path = self.cache_binary()
    with mock.patch.object(tools, "unsafe_link", side_effect=lambda p: p == path.parent):
      self.assertIsNone(tools.cached_minisign())

  def test_cached_version_probe_must_succeed_and_match_exactly(self):
    self.cache_binary()
    for result in (SimpleNamespace(returncode=1, stdout=b"minisign 0.12\n"),
                   SimpleNamespace(returncode=0, stdout=b"minisign 0.13\n")):
      with mock.patch.object(tools.subprocess, "run", return_value=result):
        with self.assertRaisesRegex(SystemExit, "unexpected version"):
          tools.ensure_minisign(download=False)


@unittest.skipUnless(platform.system() == "Windows", "Actual native Windows Minisign execution required")
class RealWindowsMinisignTests(unittest.TestCase):
  def test_native_portable_verifier_is_found_in_a_fresh_process_without_path(self):
    executable = tools.ensure_minisign()
    self.assertTrue(tools.verify_binary(Path(executable).read_bytes(), tools.minisign_entry()))
    with tempfile.TemporaryDirectory(prefix="tauridium-synthetic-minisign-") as temporary:
      root = Path(temporary)
      key, public, payload, raw, signature = (root / name for name in ("synthetic.key", "synthetic.pub", "payload.bin", "payload.minisig", "payload.sig"))
      payload.write_bytes(b"Harmless synthetic Windows bootstrap signature control")
      def run(arguments):
        return subprocess.run([executable, *map(str, arguments)], check=True, capture_output=True, timeout=60)
      run(["-G", "-W", "-s", key, "-p", public])
      run(["-S", "-W", "-s", key, "-m", payload, "-x", raw, "-t", "timestamp:0\tfile:payload.bin\tversion:9.9.9"])
      signature.write_bytes(base64.b64encode(raw.read_bytes()))
      allowed = {"SystemRoot", "SYSTEMROOT", "WINDIR", "USERPROFILE", "HOME", "TMP", "TEMP", "TMPDIR"}
      environment = {name: value for name, value in os.environ.items() if name in allowed}
      environment["PATH"] = ""
      script = (
        "import base64,sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
        "import updater_signature; executable=updater_signature.find_minisign(); "
        "assert executable; print(executable); "
        "updater_signature.verify(Path(sys.argv[2]),Path(sys.argv[3]),'9.9.9',"
        "public_key=base64.b64encode(Path(sys.argv[4]).read_bytes()).decode('ascii')); "
        "print('Fresh cached verifier cryptography passed')"
      )
      command = [sys.executable, "-I", "-c", script, str(tools.ROOT / "tools"), str(payload), str(signature), str(public)]
      result = subprocess.run(command, env=environment, check=True, capture_output=True, text=True, timeout=60)
      self.assertEqual(result.stdout.splitlines(), [executable, "Fresh cached verifier cryptography passed"])
      payload.write_bytes(b"Tampered synthetic payload must be rejected")
      rejected = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=60)
      self.assertNotEqual(rejected.returncode, 0)


if __name__ == "__main__":
  unittest.main()
