#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.5.1 project/release documentation."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0501Tests(unittest.TestCase):
  def test_readme_platform_and_release_policy_is_concise_and_current(self) -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    self.assertIn("Windows 11 is the primary and most-tested platform", readme)
    self.assertIn("native release binary is considered stable", readme)
    self.assertIn("Linux is the second-most-tested platform", readme)
    self.assertIn("macOS is not a project focus and is not tested", readme)
    self.assertNotIn("## Build", readme)
    self.assertNotIn("APPLE_SIGNING_IDENTITY", readme)
    self.assertNotIn("Keychain", readme)
    self.assertIn("just init-self-test", readme)
    self.assertIn("just package-handoff", readme)
    self.assertNotRegex(readme, r"git tag -a v\d+\.\d+\.\d+")

  def test_agents_document_captures_non_negotiable_project_rules(self) -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    for marker in (
      "Windows 11 first",
      "Rust 1.97.1",
      "OpenAI Release Builder <release@openai.invalid>",
      "Default branch: `master`",
      "just fmt-check",
      "just lint",
      "just check",
      "just test",
      "just build",
      "real `.git` history",
      "run-build-handoff",
      "Never fabricate a runtime",
    ):
      self.assertIn(marker, agents)

  def test_release_validator_accepts_generic_readme_examples(self) -> None:
    validator = (ROOT / "tools/validate_release.py").read_text(encoding="utf-8")
    self.assertIn("node tools/sync_version.mjs X.Y.Z", validator)
    self.assertNotIn("README release example differs from release version", validator)

  def test_docs_archive_includes_agent_guidance(self) -> None:
    package_release = (ROOT / "tools/package_release.py").read_text(encoding="utf-8")
    self.assertIn(
      '("README.md", "CHANGELOG.md", "AGENTS.md", "LICENSE")',
      package_release,
    )


if __name__ == "__main__":
  unittest.main()
