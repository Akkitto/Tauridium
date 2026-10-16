"""Key custody and deterministic build-input inventory regression coverage."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import assemble_release
import build_input_sbom
import release_assets
import release_policy
import sign_release
import updater_signature


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

  @unittest.skipUnless(os.name == "posix" and shutil.which("cargo-tauri") and os.environ.get("TAURIDIUM_TEST_MINISIGN"),
                       "Linux, Tauri test-key generator and pinned TAURIDIUM_TEST_MINISIGN required")
  def test_real_minisign_signer_accepts_encrypted_tauri_keys_and_binds_all_six_versions(self):
    with tempfile.TemporaryDirectory(prefix="tauridium-isolated-signer-test-") as temporary:
      root = Path(temporary)
      key = root / "ephemeral-test.key"
      cli = shutil.which("cargo-tauri")
      env = {name: value for name, value in os.environ.items()
             if not name.startswith(("TAURI_PRIVATE_KEY", "TAURI_SIGNING_PRIVATE_KEY"))}
      password = " synthetic passphrase with spaces and café "
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

  def test_key_custody_never_invokes_build_tools_or_complex_artifact_parsers(self):
    source = (sign_release.ROOT / "tools/sign_release.py").read_text(encoding="utf-8")
    self.assertNotIn("from package_release", source)
    self.assertNotIn("from release_assets", source)
    self.assertEqual(source.count("inspect=False"), 2)
    self.assertIn('input=password + b"\\n"', source)
    self.assertIn('dir="/dev/shm"', source)


if __name__ == "__main__":
  unittest.main()
