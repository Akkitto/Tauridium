#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.7.1 release staging."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")


class Patch0701Tests(unittest.TestCase):
  def test_release_validation_uses_actions_artifacts_not_draft_release_assets(self) -> None:
    self.assertIn("name: Stage release handoff", WORKFLOW)
    self.assertIn("uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9", WORKFLOW)
    self.assertIn("name: release-handoff", WORKFLOW)
    self.assertIn("name: native-${{ matrix.target }}", WORKFLOW)
    self.assertIn("uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333", WORKFLOW)
    self.assertIn("name: native-${{ matrix.target }}", WORKFLOW)
    self.assertNotIn("gh release download", WORKFLOW)
    self.assertNotIn("--draft", WORKFLOW)

  def test_scoop_consumes_the_exact_native_artifact_from_the_same_run(self) -> None:
    scoop = WORKFLOW.split("  scoop:", 1)[1].split("  verify:", 1)[0]
    self.assertIn("needs: build", scoop)
    self.assertIn("name: native-${{ matrix.target }}", scoop)
    self.assertIn("path: release/scoop-assets", scoop)
    self.assertNotIn("GH_TOKEN", scoop)
    self.assertNotIn("gh release", scoop)

  def test_public_release_is_created_only_after_all_validation_jobs(self) -> None:
    verify = WORKFLOW.split("  verify:", 1)[1].split("  sign:", 1)[0]
    self.assertIn("needs: [handoff, build, scoop, nix]", verify)
    self.assertIn("python3 tools/assemble_release.py", verify)
    self.assertNotIn("merge-multiple: true", WORKFLOW)
    self.assertIn("needs: verify", WORKFLOW.split("  sign:", 1)[1].split("  finalize:", 1)[0])
    self.assertIn("needs: sign", WORKFLOW.split("  finalize:", 1)[1].split("  publish:", 1)[0])
    publish = WORKFLOW.split("  publish:", 1)[1]
    self.assertIn("needs: finalize", publish)
    self.assertIn("environment: release-publishing", publish)
    self.assertIn("--input-sha256", publish)
    self.assertNotIn("tools/artifact_security.py", publish)
    self.assertNotIn("cargo", publish)

  def test_release_job_refuses_to_mutate_an_existing_public_release(self) -> None:
    publish = (ROOT / "tools/publish_release.py").read_text(encoding="utf-8")
    self.assertIn("refusing to overwrite or replace any assets", publish)
    self.assertIn("verify_remote_assets(staged, snapshot)", publish)
    self.assertNotIn('"upload"', publish)


if __name__ == "__main__":
  unittest.main()
