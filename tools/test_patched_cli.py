"""Verified source preparation must be identical, narrow and fail closed."""
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("prepare_tauri_cli", ROOT / "flatpak/prepare-tauri-cli.py")
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)


def packed(prefix, manifest, extra=()):
  stream = io.BytesIO()
  with tarfile.open(fileobj=stream, mode="w:gz") as archive:
    for name, payload, kind in [(prefix + "/Cargo.toml", manifest.encode(), tarfile.REGTYPE), *extra]:
      member = tarfile.TarInfo(name)
      member.size, member.type = len(payload), kind
      archive.addfile(member, io.BytesIO(payload))
  return stream.getvalue()


class PatchedCliTests(unittest.TestCase):
  def test_windows_git_checkout_keeps_the_reviewed_lock_byte_identical(self):
    payload = b"Synthetic reviewed builder lock\nSecond line\n"
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary) / "repo"
      root.mkdir()
      environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
      environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
      def git(*arguments):
        return subprocess.check_output(["git", "-c", "core.hooksPath=" + os.devnull,
          "-c", "commit.gpgsign=false", "-c", "user.name=Synthetic Test",
          "-c", "user.email=synthetic@example.invalid", *arguments], cwd=root,
          env=environment, stderr=subprocess.DEVNULL)
      git("init", "-q")
      git("config", "core.autocrlf", "false")
      git("config", "core.safecrlf", "false")
      (root / "flatpak").mkdir()
      (root / "flatpak/tauri-cli.Cargo.lock").write_bytes(payload)
      attributes = root / ".gitattributes"
      attributes.write_bytes((ROOT / ".gitattributes").read_bytes())
      git("add", ".")
      git("commit", "-qm", "Test: Bind canonical lock bytes")
      git("config", "core.autocrlf", "true")
      exported = Path(temporary) / "with-policy"
      git("checkout-index", "--all", "--prefix=" + exported.as_posix() + "/")
      self.assertEqual((exported / "flatpak/tauri-cli.Cargo.lock").read_bytes(), payload)
      # Prove this is a real newline-conversion reproduction, not a no-op export.
      attributes.write_bytes(b"")
      git("add", ".gitattributes")
      git("commit", "-qm", "Test: Remove newline policy for negative control")
      negative = Path(temporary) / "without-policy"
      git("checkout-index", "--all", "--prefix=" + negative.as_posix() + "/")
      self.assertEqual((negative / "flatpak/tauri-cli.Cargo.lock").read_bytes(), payload.replace(b"\n", b"\r\n"))

  def setUp(self):
    self.lock = b"Synthetic reviewed lock control\n"
    self.manifest = ('[package]\nname = "tauri-cli"\nversion = "2.12.3"\n'
                     '[dependencies.tauri-bundler]\nversion = "=2.10.3"\n'
                     '[dependencies.zip]\nversion = "8"\nfeatures = ["deflate"]\n')
    self.bundler_manifest = ('[package]\nname = "tauri-bundler"\nversion = "2.10.3"\n[dependencies.zip]\nversion = "8"\n'
                             '[target.\'cfg(target_os = "linux")\'.dependencies.rpm]\nversion = "0.30"\nfeatures = ["bzip2-compression"]\n')
    self.rpm = '''use rpm::{self, Dependency, FileOptions, signature::pgp};
  let pkg = if let Ok(raw_secret_key) = env::var("TAURI_SIGNING_RPM_KEY") {
    let mut signer = pgp::Signer::from_asc(&raw_secret_key)?;
    if let Ok(passphrase) = env::var("TAURI_SIGNING_RPM_KEY_PASSPHRASE") {
      signer = signer.with_key_passphrase(passphrase);
    }
    builder.build_and_sign(signer)?
  } else {
    builder.build()?
  };'''
    self.cli = packed("tauri-cli-2.12.3", self.manifest)
    self.bundler = packed("tauri-bundler-2.10.3", self.bundler_manifest,
                          [("tauri-bundler-2.10.3/src/bundle/linux/rpm.rs", self.rpm.encode(), tarfile.REGTYPE)])
    self.policy = {"tauriCli": "2.12.3", "tauriCliBuild": "2.12.3+tauridium.1", "tauriBundler": "2.10.3",
                   "tauriCliCrateSha256": hashlib.sha256(self.cli).hexdigest(),
                   "tauriBundlerCrateSha256": hashlib.sha256(self.bundler).hexdigest(),
                   "tauriCliLockSha256": hashlib.sha256(self.lock).hexdigest()}

  def test_only_reviewed_dependency_and_build_identity_changes_are_applied(self):
    with tempfile.TemporaryDirectory() as temporary:
      output = Path(temporary) / "prepared"
      PREPARE.prepare(output, self.cli, self.bundler, self.policy, self.lock)
      self.assertEqual((output / "Cargo.lock").read_bytes(), self.lock)
      expected = self.manifest.replace('version = "2.12.3"', 'version = "2.12.3+tauridium.1"')
      expected = expected.replace('[dependencies.tauri-bundler]\n', '[dependencies.tauri-bundler]\npath = "tauridium-bundler"\n')
      expected = expected.replace('[dependencies.zip]\nversion = "8"', '[dependencies.zip]\nversion = "=9.0.4"')
      self.assertEqual((output / "Cargo.toml").read_text(encoding="utf-8"), expected)
      self.assertEqual((output / "tauridium-bundler/Cargo.toml").read_text(encoding="utf-8"),
                       self.bundler_manifest.replace('[dependencies.zip]\nversion = "8"', '[dependencies.zip]\nversion = "=9.0.4"')
                       .replace('features = ["bzip2-compression"]', 'default-features = false\n'
                                'features = ["payload", "bzip2-compression", "gzip-compression", "zstd-compression", "xz-compression"]'))
      rpm = (output / "tauridium-bundler/src/bundle/linux/rpm.rs").read_text(encoding="utf-8")
      self.assertNotIn("pgp", rpm)
      self.assertNotIn("build_and_sign", rpm)
      self.assertIn("never accept RPM signing credentials", rpm)
      self.assertIn("let pkg = builder.build()?;", rpm)
      with self.assertRaisesRegex(SystemExit, "fresh output"):
        PREPARE.prepare(output, self.cli, self.bundler, self.policy, self.lock)

  def test_all_inputs_are_checksum_bound(self):
    for cli, bundler, lock in ((self.cli + b"x", self.bundler, self.lock),
                               (self.cli, self.bundler + b"x", self.lock),
                               (self.cli, self.bundler, self.lock + b"x")):
      with self.subTest(input=(len(cli), len(bundler), len(lock))), tempfile.TemporaryDirectory() as temporary:
        with self.assertRaisesRegex(SystemExit, "checksum|reviewed identity"):
          PREPARE.prepare(Path(temporary) / "out", cli, bundler, self.policy, lock)

  def test_links_traversal_duplicates_and_nonmatching_upstream_are_rejected(self):
    for name, kind in (("tauri-cli-2.12.3/../../escape", tarfile.REGTYPE),
                       ("tauri-cli-2.12.3/link", tarfile.SYMTYPE),
                       ("tauri-cli-2.12.3/link", tarfile.LNKTYPE),
                       ("tauri-cli-2.12.3/Cargo.toml", tarfile.REGTYPE)):
      data = packed("tauri-cli-2.12.3", self.manifest, [(name, b"", kind)])
      policy = dict(self.policy, tauriCliCrateSha256=hashlib.sha256(data).hexdigest())
      with self.subTest(name=name, kind=kind), tempfile.TemporaryDirectory() as temporary:
        with self.assertRaisesRegex(SystemExit, "unsafe"):
          PREPARE.prepare(Path(temporary) / "out", data, self.bundler, policy, self.lock)
    changed = packed("tauri-cli-2.12.3", self.manifest.replace('version = "8"', 'version = "9"'))
    policy = dict(self.policy, tauriCliCrateSha256=hashlib.sha256(changed).hexdigest())
    with tempfile.TemporaryDirectory() as temporary:
      with self.assertRaisesRegex(SystemExit, "no longer matches"):
        PREPARE.prepare(Path(temporary) / "out", changed, self.bundler, policy, self.lock)


if __name__ == "__main__":
  unittest.main()
