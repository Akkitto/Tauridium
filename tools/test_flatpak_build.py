"""Local Flatpak snapshots are exact, private, input-matched and never installed."""
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

import flatpak_build as build


class FlatpakSnapshotTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name) / "checkout"
    self.root.mkdir()
    for name in (build.MANIFEST, *build.LOCKS, *build.GENERATED):
      target = self.root / name
      target.parent.mkdir(parents=True, exist_ok=True)
      target.write_bytes((build.ROOT / name).read_bytes())
    self.run_git("init", "-q", "-b", "master")
    self.run_git("config", "user.name", "Synthetic Test")
    self.run_git("config", "user.email", "synthetic@example.invalid")
    self.run_git("add", ".")
    self.run_git("commit", "-qm", "Test: Create synthetic source")
    initial = self.run_git("rev-parse", "HEAD").strip()
    manifest = self.root / build.MANIFEST
    match = build.PIN.search(manifest.read_text(encoding="utf-8"))
    self.assertIsNotNone(match)
    self.run_git("tag", match["tag"])
    manifest.write_text(manifest.read_text(encoding="utf-8").replace(match["commit"], initial), encoding="utf-8")
    self.run_git("commit", "-qam", "Test: Bind publication reference")
    self.patch = mock.patch.object(build, "ROOT", self.root)
    self.patch.start()
    self.addCleanup(self.patch.stop)

  def run_git(self, *args):
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return subprocess.check_output(["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + os.devnull, *args],
                                   cwd=self.root, env=environment, stderr=subprocess.DEVNULL, text=True)

  def test_local_snapshot_is_exact_head_and_excludes_private_untracked_data(self):
    # Ignored private state must not be swept into either the source or config.
    (self.root / ".git/info/exclude").write_text("private.ignore\n", encoding="utf-8")
    (self.root / "private.ignore").write_text("Harmless private canary", encoding="utf-8")
    output, manifest = build.prepare(False, Path(self.temporary.name) / "output")
    identity = json.loads((output / "identity.json").read_text(encoding="utf-8"))
    self.assertEqual(identity["commit"], self.run_git("rev-parse", "HEAD").strip())
    self.assertFalse(identity["installed"])
    text = manifest.read_text(encoding="utf-8")
    self.assertIn(str(output / "source.tar"), text)
    self.assertIn("archive-type: tar", text)
    self.assertNotRegex(text, r"(?m)^\s*tag:")
    with tarfile.open(output / "source.tar") as archive:
      self.assertNotIn("private.ignore", archive.getnames())
      self.assertFalse(any(name.startswith(".git/") for name in archive.getnames()))
    self.assertIsNotNone(build.PIN.search((self.root / build.MANIFEST).read_text(encoding="utf-8")))
    self.assertEqual((output / "configuration/flatpak/node-sources.json").read_bytes(),
                     (self.root / "flatpak/node-sources.json").read_bytes())

  def test_publication_pin_and_its_locks_must_match_new_offline_inputs(self):
    build.prepare(True, Path(self.temporary.name) / "matching")
    lock = self.root / "package-lock.json"
    value = json.loads(lock.read_text(encoding="utf-8"))
    value["packages"]["node_modules/synthetic"] = {
      "resolved": "https://registry.npmjs.org/synthetic/-/synthetic-1.0.0.tgz",
      "integrity": "sha512-" + base64.b64encode(bytes(64)).decode()}
    lock.write_text(json.dumps(value), encoding="utf-8")
    generated = self.root / "flatpak/node-sources.json"
    generated.write_text(json.dumps(build.sources.generate_node_sources(lock)), encoding="utf-8")
    self.run_git("commit", "-qam", "Test: Change current offline inputs")
    build.prepare(False, Path(self.temporary.name) / "new-local")
    with self.assertRaisesRegex(SystemExit, "offline inputs do not match"):
      build.prepare(True, Path(self.temporary.name) / "stale-publication")
    self.assertFalse((Path(self.temporary.name) / "stale-publication").exists())

  def test_publication_fixture_creates_the_declared_tag_at_its_source_commit(self):
    text = (self.root / build.MANIFEST).read_text(encoding="utf-8")
    match = build.PIN.search(text)
    self.assertIsNotNone(match)
    self.assertEqual(self.run_git("rev-parse", match["tag"] + "^{commit}").strip(), match["commit"])

  def test_dirty_and_hidden_index_snapshots_are_rejected(self):
    (self.root / "untracked.txt").write_text("Harmless edit", encoding="utf-8")
    with self.assertRaisesRegex(SystemExit, "clean committed"):
      build.prepare(False, Path(self.temporary.name) / "dirty")
    (self.root / "untracked.txt").unlink()
    self.run_git("update-index", "--assume-unchanged", "package-lock.json")
    with self.assertRaisesRegex(SystemExit, "hidden Git index"):
      build.prepare(False, Path(self.temporary.name) / "hidden")

  def test_sandbox_local_builder_policy_is_exact_and_drift_is_rejected(self):
    policy = self.root / "flatpak/tauri-cli-policy.json"
    self.assertEqual(json.loads(policy.read_text(encoding="utf-8")),
                     json.loads((self.root / "data/build-toolchain.json").read_text(encoding="utf-8")))
    policy.write_text("{}", encoding="utf-8")
    self.run_git("commit", "-qam", "Test: Tamper synthetic generated builder policy")
    with self.assertRaisesRegex(SystemExit, "offline inputs do not match"):
      build.prepare(False, Path(self.temporary.name) / "drift")

  def test_local_and_tracked_export_attributes_cannot_change_source_or_configuration(self):
    source = self.root / "substitution.txt"
    source.write_bytes(b"Literal $Format:%H$ stays unchanged\n")
    script = self.root / "flatpak/executable.sh"
    script.write_bytes(b"#!/bin/sh\nexit 0\n")
    script.chmod(0o755)
    (self.root / ".gitattributes").write_text("package-lock.json export-ignore\nsubstitution.txt export-subst\n", encoding="utf-8")
    self.run_git("add", ".")
    self.run_git("update-index", "--chmod=+x", "flatpak/executable.sh")
    self.run_git("commit", "-qm", "Test: Add tracked archive attributes")
    baseline = build.exact_tree_archive(self.run_git("rev-parse", "HEAD").strip())
    (self.root / ".git/info/attributes").write_text("flatpak/* export-ignore\nsubstitution.txt export-ignore\n", encoding="utf-8")
    self.run_git("config", "core.attributesFile", str(self.root / ".git/info/attributes"))
    output, _ = build.prepare(False, Path(self.temporary.name) / "attribute-proof")
    self.assertEqual((output / "source.tar").read_bytes(), baseline)
    with tarfile.open(output / "source.tar") as archive:
      for name in (*build.LOCKS, *build.GENERATED, "substitution.txt"):
        self.assertEqual(archive.extractfile(name).read(), self.run_git("show", "HEAD:" + name).encode())
      self.assertEqual(archive.getmember("flatpak/executable.sh").mode, 0o755)
    self.assertEqual((output / "configuration/flatpak/executable.sh").read_bytes(), script.read_bytes())
    if os.name == "posix":
      self.assertEqual((output / "configuration/flatpak/executable.sh").stat().st_mode & 0o777, 0o755)

  def test_source_snapshot_rejects_symlinks_and_gitlinks_instead_of_dereferencing_them(self):
    for mode, kind in ((b"120000", b"blob"), (b"160000", b"commit")):
      with self.subTest(mode=mode):
        listing = mode + b" " + kind + b" " + b"a" * 40 + b"\tunsafe\0"
        with mock.patch.object(build, "git", return_value=listing):
          with self.assertRaisesRegex(SystemExit, "safe regular"):
            build.exact_tree_archive("a" * 40)

  def test_old_publication_without_build_metadata_has_an_actionable_safe_error(self):
    actual_git = build.git
    def legacy_source(*arguments):
      if arguments[0] == "show" and arguments[1].endswith(":data/build-toolchain.json"):
        raise subprocess.CalledProcessError(128, ["git", "show", "private-path-withheld"])
      return actual_git(*arguments)
    with mock.patch.object(build, "git", side_effect=legacy_source):
      with self.assertRaisesRegex(SystemExit, "predates required reviewed build metadata") as caught:
        build.prepare(True, Path(self.temporary.name) / "missing-policy")
      self.assertNotIn("private-path-withheld", str(caught.exception))
    self.assertFalse((Path(self.temporary.name) / "missing-policy").exists())

  def test_configuration_rejects_archive_links_and_escape_paths(self):
    for name, kind in (("flatpak/../../outside", tarfile.REGTYPE), ("flatpak/link", tarfile.SYMTYPE)):
      with self.subTest(name=name):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w") as archive:
          entry = tarfile.TarInfo(name)
          entry.type = kind
          entry.linkname = "/outside"
          archive.addfile(entry)
        with self.assertRaisesRegex(SystemExit, "unsafe path"):
          build.snapshot_flatpak(data.getvalue(), Path(self.temporary.name) / "configuration")

  def test_unexpected_manifest_shape_fails_instead_of_building_wrong_source(self):
    with self.assertRaisesRegex(SystemExit, "one exact immutable"):
      build.local_manifest("not the reviewed manifest", Path("/synthetic/source.tar"), "a" * 64)

  def test_default_recipe_does_not_install_the_historical_publication_reference(self):
    repo = Path(__file__).resolve().parents[1]
    justfile = (repo / "justfile").read_text(encoding="utf-8")
    self.assertIn("flatpak-build:\n  python3 tools/flatpak_build.py", justfile)
    self.assertNotIn("--install", justfile.split("flatpak-build:", 1)[1].split("\n\n", 1)[0])

  def test_signing_credentials_are_rejected_before_snapshot_or_builder_execution(self):
    with (mock.patch.dict(os.environ, {"TAURI_SIGNING_PRIVATE_KEY": "synthetic-never-a-real-key"}),
          mock.patch("sys.argv", ["flatpak_build.py"]), mock.patch.object(build, "prepare") as prepare):
      with self.assertRaisesRegex(SystemExit, "signing"):
        build.main()
      prepare.assert_not_called()

