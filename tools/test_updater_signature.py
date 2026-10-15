"""Real cryptographic updater producer gates; test private keys are ephemeral."""
import base64
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import updater_signature

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("security_release_assets", ROOT / "tools/release_assets.py")
ASSETS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ASSETS)


class SignatureFailureSafetyTests(unittest.TestCase):
    def test_dummy_signature_cannot_replace_existing_trusted_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / "new.exe", root / "published.exe"
            source.write_bytes(b"synthetic new payload")
            source.with_name(source.name + ".sig").write_text("NOT A VALID SIGNATURE", encoding="ascii")
            destination.write_bytes(b"trusted previous payload")
            with self.assertRaisesRegex(SystemExit, "updater signature rejected"):
                ASSETS.copy_with_signature(source, destination, True)
            self.assertEqual(destination.read_bytes(), b"trusted previous payload")
            self.assertEqual(sorted(path.name for path in root.iterdir()), ["new.exe", "new.exe.sig", "published.exe"])

    def test_signature_envelopes_are_bounded_before_crypto(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact, signature = root / "artifact", root / "artifact.sig"
            artifact.write_bytes(b"synthetic")
            signature.write_bytes(b"A" * (updater_signature.MAX_ENVELOPE_BYTES + 1))
            with self.assertRaisesRegex(SystemExit, "size limit"):
                updater_signature.verify(artifact, signature, "9.9.9")


@unittest.skipUnless(updater_signature.find_minisign(), "Real Minisign required; run just init or nix develop")
class CryptographicSignatureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="tauridium-signature-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.key, self.pub = self.root / "test.key", self.root / "test.pub"
        self.run_minisign(["-G", "-W", "-s", str(self.key), "-p", str(self.pub)])
        self.public_key = base64.b64encode(self.pub.read_bytes()).decode("ascii")
        self.release_version = "9.9.9"

    def run_minisign(self, args):
        subprocess.run([updater_signature.find_minisign()] + args, check=True, capture_output=True, timeout=60)

    def signed(self, name="artifact.bin"):
        artifact = self.root / name
        artifact.write_bytes(b"Synthetic public updater payload")
        raw = self.root / "test.minisig"
        comment = f"timestamp:0\tfile:{name}\tversion:{self.release_version}"
        self.run_minisign(["-S", "-W", "-s", str(self.key), "-m", str(artifact), "-x", str(raw), "-t", comment])
        signature = artifact.with_name(artifact.name + ".sig")
        signature.write_bytes(base64.b64encode(raw.read_bytes()))
        return artifact, signature

    def test_valid_signature_and_exact_version_are_required(self):
        artifact, signature = self.signed()
        self.assertEqual(updater_signature.verify(artifact, signature, self.release_version, public_key=self.public_key),
                         signature.read_text(encoding="ascii"))
        with self.assertRaisesRegex(SystemExit, "exact release version"):
            updater_signature.verify(artifact, signature, "9.9.10", public_key=self.public_key)
        artifact.write_bytes(b"tampered")
        with self.assertRaisesRegex(SystemExit, "Cryptographic"):
            updater_signature.verify(artifact, signature, self.release_version, public_key=self.public_key)

    def test_forged_trusted_comment_cannot_relabel_an_older_signed_release(self):
        artifact, signature = self.signed()
        raw = base64.b64decode(signature.read_bytes())
        signature.write_bytes(base64.b64encode(raw.replace(b"version:9.9.9", b"version:9.9.8")))
        with self.assertRaisesRegex(SystemExit, "Cryptographic"):
            updater_signature.verify(artifact, signature, "9.9.8", public_key=self.public_key)

    def test_wrong_configured_key_is_rejected(self):
        artifact, signature = self.signed()
        second_key, second_pub = self.root / "second.key", self.root / "second.pub"
        self.run_minisign(["-G", "-W", "-s", str(second_key), "-p", str(second_pub)])
        public_key = base64.b64encode(second_pub.read_bytes()).decode("ascii")
        with self.assertRaisesRegex(SystemExit, "configured updater public key"):
            updater_signature.verify(artifact, signature, self.release_version, public_key=public_key)

    @unittest.skipUnless(shutil.which("cargo-tauri"), "Pinned Tauri CLI required; run just init")
    def test_actual_tauri_signer_output_verifies_with_independent_minisign(self):
        executable = shutil.which("cargo-tauri")
        key = self.root / "native-tauri.key"
        env = {name: value for name, value in os.environ.items()
               if not name.startswith(("TAURI_SIGNING_PRIVATE_KEY", "TAURI_PRIVATE_KEY"))}
        subprocess.run([executable, "signer", "generate", "--ci", "--password", "", "--write-keys", str(key)],
                       cwd=self.root, env=env, check=True, capture_output=True, timeout=60)
        artifact = self.root / "native-tauri-artifact.bin"
        artifact.write_bytes(b"Synthetic native Tauri signer compatibility fixture")
        subprocess.run([executable, "signer", "sign", "--private-key-path", str(key), "--password", "",
                        "--app-version", self.release_version, str(artifact)],
                       cwd=self.root, env=env, check=True, capture_output=True, timeout=60)
        public_key = key.with_name(key.name + ".pub").read_text(encoding="utf-8").strip()
        signature = artifact.with_name(artifact.name + ".sig")
        self.assertEqual(updater_signature.verify(artifact, signature, self.release_version, public_key=public_key),
                         signature.read_text(encoding="ascii").strip())

    def test_complete_set_is_signed_only_after_every_pair_is_verified(self):
        with mock.patch.object(updater_signature, "configured_public_key", return_value=self.public_key):
            for name in ASSETS.expected_updater_artifact_names(self.release_version):
                self.signed(name)
            self.assertEqual(ASSETS.signed_updater_state(self.root, self.release_version), "signed")
            name = ASSETS.expected_updater_artifact_names(self.release_version)[0]
            entry = ASSETS.signed_entry(self.root, name, self.release_version)
            self.assertIn("signature", entry)
            (self.root / name).write_bytes(b"tampered payload")
            with self.assertRaisesRegex(SystemExit, "Cryptographic"):
                ASSETS.signed_updater_state(self.root, self.release_version)

    def test_collector_verifies_real_staged_bytes_before_replacing_output(self):
        artifact, _signature = self.signed("original-installer.exe")
        destination = self.root / "canonical-installer.exe"
        with (mock.patch.object(updater_signature, "configured_public_key", return_value=self.public_key),
              mock.patch.object(ASSETS, "version", return_value=self.release_version)):
            written = ASSETS.copy_with_signature(artifact, destination, True)
            self.assertEqual(written, [destination, destination.with_name(destination.name + ".sig")])
            self.assertEqual(destination.read_bytes(), artifact.read_bytes())
            self.assertIsNotNone(ASSETS.signed_entry(self.root, destination.name, self.release_version))
