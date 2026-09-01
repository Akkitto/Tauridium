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
    self.assertIn("uses: actions/upload-artifact@v7.0.1", WORKFLOW)
    self.assertIn("name: release-handoff", WORKFLOW)
    self.assertIn("name: native-${{ matrix.target }}", WORKFLOW)
    self.assertIn("uses: actions/download-artifact@v8.0.1", WORKFLOW)
    self.assertIn("name: native-${{ matrix.target }}", WORKFLOW)
    self.assertNotIn("gh release download", WORKFLOW)
    self.assertNotIn("--draft", WORKFLOW)

  def test_scoop_consumes_the_exact_native_artifact_from_the_same_run(self) -> None:
    scoop = WORKFLOW.split("  scoop:", 1)[1].split("  publish:", 1)[0]
    self.assertIn("needs: build", scoop)
    self.assertIn("name: native-${{ matrix.target }}", scoop)
    self.assertIn("path: release/scoop-assets", scoop)
    self.assertNotIn("GH_TOKEN", scoop)
    self.assertNotIn("gh release", scoop)

  def test_public_release_is_created_only_after_all_validation_jobs(self) -> None:
    publish = WORKFLOW.split("  publish:", 1)[1]
    self.assertIn("needs: [handoff, build, scoop]", publish)
    self.assertIn("pattern: native-*", publish)
    self.assertIn("merge-multiple: true", publish)
    self.assertIn("just scoop-release-manifest release/published-assets", publish)
    self.assertIn("just release-checksums release/published-assets", publish)
    self.assertIn('gh release create "$GITHUB_REF_NAME" "${files[@]}"', publish)
    self.assertIn("--verify-tag", publish)
    self.assertIn("--latest", publish)
    self.assertNotIn("gh release upload", publish)
    self.assertNotIn("gh release edit", publish)

  def test_release_job_refuses_to_mutate_an_existing_public_release(self) -> None:
    publish = WORKFLOW.split("  publish:", 1)[1]
    self.assertIn('if gh release view "$GITHUB_REF_NAME" >/dev/null 2>&1; then', publish)
    self.assertIn("refusing to mutate published assets", publish)


if __name__ == "__main__":
  unittest.main()
