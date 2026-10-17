"""Key custody and deterministic build-input inventory regression coverage."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

import assemble_release
import build_input_sbom
import finalize_release
import release_assets
import release_policy
import sign_release
import release_snapshot
import updater_signature
from package_release import ZIP_TIME


class IsolatedReleaseTests(unittest.TestCase):
  def test_signer_environment_excludes_unrelated_secrets_and_removes_parent_custody(self):
    environment = {"PATH": "safe-path", "HOME": "safe-home", "GH_TOKEN": "synthetic-github-token",
                   "AWS_SECRET_ACCESS_KEY": "synthetic-cloud-token", "TAURI_SIGNING_PRIVATE_KEY": "synthetic-key",
                   "TAURI_SIGNING_PRIVATE_KEY_PASSWORD": "synthetic-password", "TAURI_PRIVATE_KEY": "obsolete"}
    with mock.patch.dict(os.environ, environment, clear=True):
      base, secret = sign_release.signing_environment()
      self.assertEqual(base, {"PATH": "safe-path", "HOME": "safe-home"})
      self.assertNotIn("GH_TOKEN", secret)
      self.assertNotIn("AWS_SECRET_ACCESS_KEY", secret)
      self.assertEqual(secret["TAURI_SIGNING_PRIVATE_KEY"], "synthetic-key")
      self.assertFalse(any(name.startswith(("TAURI_PRIVATE_KEY", "TAURI_SIGNING_PRIVATE_KEY")) for name in os.environ))

  def test_assembler_rejects_missing_or_unexpected_target_artifacts_without_promotion(self):
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      staging = root / "inputs"
      staging.mkdir()
      (staging / "rogue-artifact").mkdir()
      output = root / "output"
      with self.assertRaisesRegex(SystemExit, "unexpected/missing"):
        assemble_release.assemble(staging, output, "9.9.9")
      self.assertFalse(output.exists())

  def test_sbom_is_deterministic_and_honest_about_optional_platform_and_builder_candidates(self):
    first = build_input_sbom.generate(build_input_sbom.ROOT, "9.9.9", "a" * 40)
    self.assertEqual(first, build_input_sbom.generate(build_input_sbom.ROOT, "9.9.9", "a" * 40))
    self.assertEqual(first["specVersion"], "1.6")
    self.assertGreater(len(first["components"]), 500)
    self.assertEqual(len({entry["bom-ref"] for entry in first["components"]}), len(first["components"]))
    self.assertTrue(all(entry["scope"] == "optional" for entry in first["components"]))
    self.assertIn("not proof", first["metadata"]["properties"][1]["value"])

  @unittest.skipUnless(sys.platform == "linux" and Path("/dev/shm").is_dir(),
                       "Production signing custody requires Linux shared-memory staging")
  def test_failed_signer_never_promotes_output_or_prints_private_diagnostics(self):
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      assets = root / "assets"
      assets.mkdir()
      (assets / "release-notes.md").write_text("Synthetic notes", encoding="utf-8")
      first = assets / sorted(release_assets.expected_updater_artifact_names("9.9.9"))[0]
      first.write_bytes(b"synthetic")
      replies = [subprocess.CompletedProcess([], 1, b"synthetic-private-key", b"synthetic-private-key")]
      with (mock.patch.dict(os.environ, {"TAURI_SIGNING_PRIVATE_KEY": base64.b64encode(b"synthetic-private-key").decode()}, clear=True),
            mock.patch.object(sign_release, "pinned_signer", return_value="/synthetic/minisign"),
            mock.patch.object(sign_release.policy, "validate_directory", return_value=[first]),
            mock.patch.object(sign_release.subprocess, "run", side_effect=replies)):
        with self.assertRaisesRegex(SystemExit, "output withheld") as caught:
          sign_release.sign(assets, root / "output", "9.9.9", executable="/synthetic/minisign")
        self.assertNotIn("synthetic-private-key", str(caught.exception))
        self.assertFalse((root / "output").exists())
        self.assertFalse(any(path.name.startswith(".tauridium-signer-") for path in root.iterdir()))

  def test_signer_rejects_non_linux_before_key_staging_or_executable_validation(self):
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      with (mock.patch.dict(os.environ, {"TAURI_SIGNING_PRIVATE_KEY": "synthetic-never-a-real-key"}, clear=True),
            mock.patch.object(sign_release.sys, "platform", "win32"),
            mock.patch.object(sign_release, "pinned_signer") as signer):
        with self.assertRaisesRegex(SystemExit, "requires Linux shared-memory"):
          sign_release.sign(root / "absent", root / "output", "9.9.9", executable="absent")
        signer.assert_not_called()
        self.assertNotIn("TAURI_SIGNING_PRIVATE_KEY", os.environ)
      self.assertFalse((root / "output").exists())

  @unittest.skipUnless(os.name == "posix" and shutil.which("cargo-tauri") and os.environ.get("TAURIDIUM_TEST_MINISIGN"),
                       "Linux, Tauri test-key generator and pinned TAURIDIUM_TEST_MINISIGN required")
  def test_real_minisign_signer_accepts_encrypted_tauri_keys_and_binds_all_six_versions(self):
    with tempfile.TemporaryDirectory(prefix="tauridium-isolated-signer-test-") as temporary:
      root = Path(temporary)
      key = root / "ephemeral-test.key"
      cli = shutil.which("cargo-tauri")
      env = {name: value for name, value in os.environ.items()
             if not name.startswith(("TAURI_PRIVATE_KEY", "TAURI_SIGNING_PRIVATE_KEY"))}
      password = " synthetic passphrase with spaces and caf\u00e9 "
      subprocess.run([cli, "signer", "generate", "--ci", "--password", password, "--write-keys", str(key)],
                     cwd=root, env=env, check=True, capture_output=True, timeout=60)
      assets = root / "assets"
      assets.mkdir()
      files = []
      for name in release_assets.expected_updater_artifact_names("9.9.9"):
        path = assets / name
        path.write_bytes(b"Synthetic non-executable signer payload")
        files.append(path)
      (assets / "release-notes.md").write_text("Synthetic notes", encoding="utf-8")
      public_key = key.with_name(key.name + ".pub").read_text(encoding="utf-8").strip()
      # Format/inventory parsing is tested independently; this test exercises
      # the real signing process against harmless bytes, never actual installers.
      with (mock.patch.dict(os.environ, {**env, "TAURI_SIGNING_PRIVATE_KEY": key.read_text(encoding="utf-8").strip(),
                                         "TAURI_SIGNING_PRIVATE_KEY_PASSWORD": password}, clear=True),
            mock.patch.object(sign_release.policy, "validate_directory", return_value=files),
            mock.patch.object(updater_signature, "configured_public_key", return_value=public_key)):
        output = root / "signed"
        sign_release.sign(assets, output, "9.9.9", executable=os.environ["TAURIDIUM_TEST_MINISIGN"])
        for name in release_assets.expected_updater_artifact_names("9.9.9"):
          updater_signature.verify(output / name, output / (name + ".sig"), "9.9.9", public_key=public_key,
                                    executable=os.environ["TAURIDIUM_TEST_MINISIGN"])
        self.assertEqual(len(list(output.iterdir())), 13)

  def test_signer_refuses_an_unpinned_executable_before_execution(self):
    with tempfile.TemporaryDirectory() as temporary:
      path = Path(temporary) / "minisign"
      path.write_bytes(b"not the official executable")
      with self.assertRaisesRegex(SystemExit, "checksum-pinned"):
        sign_release.pinned_signer(str(path))

  @unittest.skipUnless(os.environ.get("TAURIDIUM_TEST_MINISIGN"), "Pinned Minisign required")
  def test_complete_private_candidate_crosses_all_custody_hash_boundaries_without_publication(self):
    with tempfile.TemporaryDirectory(prefix="tauridium-custody-control-") as temporary:
      root = Path(temporary)
      executable = os.environ["TAURIDIUM_TEST_MINISIGN"]
      key, public = root / "ephemeral.key", root / "ephemeral.pub"
      subprocess.run([executable, "-G", "-W", "-s", str(key), "-p", str(public)], capture_output=True, check=True, timeout=60)
      public_key = base64.b64encode(public.read_bytes()).decode()
      version = release_assets.version()
      commit = finalize_release.git_output("rev-parse", "HEAD")
      inputs = root / "inputs"
      for directory in {"release-handoff"} | {"native-" + target for target in release_policy.TARGETS}:
        staged = inputs / directory
        staged.mkdir(parents=True)
        names = (release_policy.handoff_names(version) | {"release-notes.md"} if directory == "release-handoff"
                 else release_policy.target_names(version, directory[len("native-"):]))
        for name in sorted(names):
          path = staged / name
          if name.endswith(".zip"):
            with zipfile.ZipFile(path, "w") as archive:
              entry = zipfile.ZipInfo("tauridium.exe" if "portable" in name else "README.md", ZIP_TIME)
              entry.compress_type = zipfile.ZIP_DEFLATED
              archive.writestr(entry, b"Synthetic inert custody fixture")
          elif name.endswith(".sha256"):
            path.write_text(release_policy.digest(staged / name[:-7]) + "  " + name[:-7] + "\n", encoding="utf-8")
          elif name.endswith(".exe"):
            header = bytearray(132)
            header[:2], header[60:64], header[128:] = b"MZ", (128).to_bytes(4, "little"), b"PE\0\0"
            path.write_bytes(header)
          else:
            magic = {".msi": bytes.fromhex("d0cf11e0a1b11ae1"), ".rpm": bytes.fromhex("edabeedb"),
                     ".deb": b"!<arch>\n", ".AppImage": b"\x7fELF\0\0\0\0AI\x02"}.get(path.suffix, b"Synthetic notes")
            path.write_bytes(magic)
      unsigned, signed, final = (root / name for name in ("unsigned", "signed", "final"))
      assemble_release.assemble(inputs, unsigned, version)
      unsigned_digest = release_snapshot.seal(unsigned, version, commit, "unsigned")
      release_snapshot.verify(unsigned, version, commit, "unsigned", unsigned_digest)
      environment = {**os.environ, "TAURI_SIGNING_PRIVATE_KEY": base64.b64encode(key.read_bytes()).decode(),
                     "TAURI_SIGNING_PRIVATE_KEY_PASSWORD": ""}
      with (mock.patch.dict(os.environ, environment, clear=True),
            mock.patch.object(updater_signature, "configured_public_key", return_value=public_key)):
        sign_release.sign(unsigned, signed, version, executable=executable)
        signed_digest = release_snapshot.seal(signed, version, commit, "signed")
        final_digest = finalize_release.custody(signed, final, signed_digest, commit)
      release_snapshot.verify(final, version, commit, "final", final_digest)
      self.assertEqual({path.name for path in final.iterdir()}, release_policy.public_names(version) | {"TRANSFER.json", "release-notes.md"})
      self.assertFalse(any("key" in path.name for path in final.iterdir()))
      self.assertNotIn("TRANSFER.json", (final / "SHA256SUMS").read_text(encoding="utf-8"))

  def test_key_custody_never_invokes_build_tools_or_complex_artifact_parsers(self):
    source = (sign_release.ROOT / "tools/sign_release.py").read_text(encoding="utf-8")
    self.assertNotIn("from package_release", source)
    self.assertNotIn("from release_assets", source)
    self.assertEqual(source.count("inspect=False"), 2)
    self.assertIn('input=password + b"\\n"', source)
    self.assertIn('dir="/dev/shm"', source)


if __name__ == "__main__":
  unittest.main()
