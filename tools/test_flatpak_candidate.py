"""A candidate is selected by successful source identity, never an installed app."""
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

import flatpak_build as build
import flatpak_candidate as candidate
from test_flatpak_policy import METADATA
import test_flatpak_build as fixtures


class FlatpakCandidateTests(unittest.TestCase):
  def setUp(self):
    self.fixture = fixtures.FlatpakSnapshotTests()
    self.fixture.setUp()
    self.addCleanup(self.fixture.doCleanups)
    self.root = self.fixture.root
    (self.root / ".git/info/exclude").write_text("release/\nrepo/\n", encoding="utf-8")
    self.output, _ = build.prepare(False, Path(self.fixture.temporary.name) / "candidate")
    (self.output / "build/files/bin").mkdir(parents=True)
    (self.output / "build/files/bin/tauridium").write_bytes(b"Harmless unit fixture, never executed")
    (self.output / "build/metadata").write_text(METADATA, encoding="utf-8")
    (self.output / "repo").mkdir()
    (self.output / "repo/config").write_text("Harmless repository fixture", encoding="utf-8")
    build.seal_candidate(self.output)

  def test_successful_pointer_and_explicit_candidate_select_the_same_exact_output(self):
    self.assertEqual(candidate.select(), self.output)
    self.assertEqual(candidate.select(str(self.output)), self.output)
    candidate.validate_permissions(self.output / "build/metadata")

  def test_missing_successful_pointer_never_falls_back_to_an_installed_app_or_root_repo(self):
    (self.root / "release/flatpak/latest.json").unlink()
    (self.root / "repo").mkdir()
    with self.assertRaisesRegex(SystemExit, "no successful current"):
      candidate.select()

  def test_stale_and_dirty_source_are_rejected(self):
    (self.root / "new.txt").write_text("Harmless source edit", encoding="utf-8")
    with self.assertRaisesRegex(SystemExit, "commit worktree"):
      candidate.select()
    self.fixture.run_git("add", ".")
    self.fixture.run_git("commit", "-qm", "Test: Move to new source")
    with self.assertRaisesRegex(SystemExit, "stale"):
      candidate.select()

  def test_changed_source_configuration_runtime_metadata_and_repo_fail_closed(self):
    for relative in ("source.tar", "identity.json", "configuration/flatpak/node-sources.json",
                     "build/files/bin/tauridium", "build/metadata", "repo/config"):
      with self.subTest(path=relative):
        path = self.output / relative
        original = path.read_bytes()
        path.write_bytes(original + b"\n")
        try:
          with self.assertRaisesRegex(SystemExit, "changed|differs"):
            candidate.select()
        finally:
          path.write_bytes(original)

  def test_prepare_only_and_failed_results_are_never_selected(self):
    result = self.output / "result.json"
    data = json.loads(result.read_text(encoding="utf-8"))
    data["passed"] = False
    result.write_text(json.dumps(data), encoding="utf-8")
    with self.assertRaisesRegex(SystemExit, "incomplete"):
      candidate.select()
    result.unlink()
    with self.assertRaisesRegex(SystemExit, "regular files"):
      candidate.select(str(self.output))

  def test_runtime_is_readonly_and_profile_scoped_without_installing_or_using_the_real_vault(self):
    profile = self.output / "temporary-profile"
    profile.mkdir()
    with mock.patch.object(candidate, "flatpak", return_value="flatpak"):
      command = candidate.runtime_command(self.output, profile)
    self.assertEqual(command[:2], ["flatpak", "build"])
    self.assertIn("--runtime", command)
    self.assertIn("--readonly", command)
    self.assertIn("--nofilesystem=host", command)
    self.assertIn("--nofilesystem=home", command)
    self.assertIn("--no-talk-name=org.freedesktop.secrets", command)
    self.assertIn(str(self.output / "build"), command)
    self.assertNotIn("--with-appdir", command)
    self.assertNotIn("install", command)

  def test_unreviewed_permission_addition_is_rejected(self):
    path = self.output / "build/metadata"
    path.write_text(METADATA.replace("devices=dri;", "devices=dri;\nfilesystems=host;"), encoding="utf-8")
    with self.assertRaisesRegex(SystemExit, "permissions differ"):
      candidate.validate_permissions(path)

  def test_unreviewed_metadata_cannot_replace_successful_candidate_custody(self):
    pointer = self.root / "release/flatpak/latest.json"
    result = self.output / "result.json"
    before = pointer.read_bytes(), result.read_bytes()
    (self.output / "build/metadata").write_text(METADATA + "[Environment]\nLD_PRELOAD=synthetic-private-value\n", encoding="utf-8")
    with self.assertRaisesRegex(SystemExit, "permissions differ"):
      build.seal_candidate(self.output)
    self.assertEqual((pointer.read_bytes(), result.read_bytes()), before)

  def test_all_consumers_reject_unreviewed_metadata_even_with_matching_legacy_seals(self):
    path = self.output / "build/metadata"
    path.write_text(METADATA + "[System Bus Policy]\norg.freedesktop.NetworkManager=talk\n", encoding="utf-8")
    result_path = self.output / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["metadataSha256"] = build.file_digest(path)
    build.atomic_json(result_path, result)
    build.atomic_json(self.root / "release/flatpak/latest.json", {
      "candidate": str(self.output), "resultSha256": build.file_digest(result_path)})
    for action in ("test", "run", "lint", "flathub-lint"):
      with self.subTest(action=action), mock.patch("sys.argv", ["flatpak_candidate.py", action]):
        with self.assertRaisesRegex(SystemExit, "permissions differ"):
          candidate.main()

  def test_lint_inspects_only_the_selected_manifest_repository_and_installed_metadata(self):
    # --show-manifest normalizes app-id to id and expands included sources.
    manifest = {"id": candidate.APP_ID, "modules": [{"name": "tauridium", "sources": [{"type": "archive", "dest": "source",
      "path": str(self.output / "source.tar"), "sha256": build.file_digest(self.output / "source.tar")},
      {"type": "inline", "contents": "Harmless offline-cache entry"}]}]}
    with (mock.patch.object(build, "builder_command", return_value=["flatpak-builder"]),
          mock.patch.object(candidate, "flatpak", return_value="flatpak"),
          mock.patch.object(candidate.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(manifest).encode())) as run):
      candidate.lint(self.output, {})
      commands = [call.args[0] for call in run.call_args_list]
    self.assertIn(str(self.output / "configuration" / build.MANIFEST), commands[0])
    self.assertIn(str(self.output / "repo"), commands[1])
    self.assertIn(str(self.output / "build"), commands[2])
    self.assertIn("--unshare=network", commands[2])
    self.assertFalse(any(command[:2] == ["flatpak", "info"] for command in commands))

  def test_signing_credentials_are_rejected_before_selecting_or_running_any_candidate(self):
    with (mock.patch.dict(os.environ, {"TAURI_SIGNING_PRIVATE_KEY": "synthetic-never-issued"}),
          mock.patch("sys.argv", ["flatpak_candidate.py", "test"]), mock.patch.object(candidate, "select") as select):
      with self.assertRaisesRegex(SystemExit, "signing"):
        candidate.main()
      select.assert_not_called()

  def test_recipes_bind_candidate_actions_instead_of_legacy_outputs(self):
    source = (Path(__file__).resolve().parents[1] / "justfile").read_text(encoding="utf-8")
    for action in ("test", "run", "lint", "flathub-lint"):
      self.assertIn(f"python3 tools/flatpak_candidate.py {action} --candidate", source)
    self.assertNotIn("flatpak info --show-permissions dev.brani.tauridium", source)
    self.assertNotIn("flatpak-builder-lint org.flatpak.Builder repo repo", source)


if __name__ == "__main__":
  unittest.main()
