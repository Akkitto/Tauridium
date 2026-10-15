"""No build script receives signing credentials, even on local default recipes."""
import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

import tauri_build


class KeyFreeBuildTests(unittest.TestCase):
  def test_every_signing_credential_prefix_is_rejected_before_starting_build_code(self):
    for prefix in tauri_build.SIGNING_PREFIXES:
      with self.subTest(prefix=prefix):
        with self.assertRaisesRegex(SystemExit, "never accept signing") as caught:
          tauri_build.build_environment({prefix + "SYNTHETIC": "not-a-real-key"})
        self.assertNotIn("not-a-real-key", str(caught.exception))

  def test_preserves_encoded_cargo_flags_and_remaps_private_build_roots(self):
    result = tauri_build.build_environment({"CARGO_ENCODED_RUSTFLAGS": "-C\x1fdebuginfo=0"})
    self.assertTrue(result["CARGO_ENCODED_RUSTFLAGS"].startswith("-C\x1fdebuginfo=0\x1f"))
    self.assertIn("=/build/tauridium", result["CARGO_ENCODED_RUSTFLAGS"])
    self.assertIn("=/build/home", result["CARGO_ENCODED_RUSTFLAGS"])
    self.assertNotIn("RUSTFLAGS", result)

  def test_canonical_build_calls_direct_pinned_cli_and_final_unsigned_config(self):
    responses = [subprocess.CompletedProcess([], 0, "tauri-cli 2.12.3\n", ""), subprocess.CompletedProcess([], 0)]
    with (mock.patch.dict(os.environ, {"PATH": "synthetic"}, clear=True),
          mock.patch.object(tauri_build.shutil, "which", return_value="/synthetic/cargo-tauri"),
          mock.patch.object(tauri_build.subprocess, "run", side_effect=responses) as run):
      self.assertEqual(tauri_build.build(["--no-bundle", "--ci"]), 0)
      command = run.call_args_list[1].args[0]
      self.assertEqual(command[0], str(Path("/synthetic/cargo-tauri").resolve()))
      self.assertEqual(command[1:4], ["build", "--no-bundle", "--ci"])
      self.assertEqual(command[-2], "--config")
      self.assertTrue(command[-1].endswith("tauri.no-updater.conf.json"))
      self.assertFalse(any(name.startswith(tauri_build.SIGNING_PREFIXES) for name in run.call_args.kwargs["env"]))


if __name__ == "__main__":
  unittest.main()
