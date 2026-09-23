#!/usr/bin/env python3
"""Regression coverage for the v0.8.4 release-worktree isolation fix."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0804Tests(unittest.TestCase):
  def read(self, path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")

  def test_vitest_only_discovers_canonical_frontend_sources(self) -> None:
    config = self.read("vite.config.ts")
    self.assertIn('import { defineConfig } from "vitest/config";', config)
    self.assertIn('include: ["src/**/*.test.ts"]', config)
    self.assertNotIn('include: ["**/*.{test,spec}.?(c|m)[jt]s?(x)"]', config)

  def test_generated_flatpak_worktrees_remain_ignored(self) -> None:
    ignore = self.read(".gitignore")
    for path in (".flatpak-builder/", "build-dir/", "repo/"):
      self.assertIn(path, ignore)


if __name__ == "__main__":
  unittest.main()
