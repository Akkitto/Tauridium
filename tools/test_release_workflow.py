#!/usr/bin/env python3
"""Regression coverage for non-mutating local release orchestration."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseWorkflowTests(unittest.TestCase):
  def test_release_uses_non_mutating_format_check_and_clean_gates(self) -> None:
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    self.assertIn(
      "release: release-clean fmt-check lint check test build release-clean package",
      justfile,
    )
    self.assertIn(
      "fmt-check:\n  cargo fmt --manifest-path src-tauri/Cargo.toml --all -- --check",
      justfile,
    )
    self.assertNotIn("release: fmt lint", justfile)

  def test_release_cargo_gates_preserve_lockfile(self) -> None:
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    for marker in (
      "cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --all-features --locked -- -D warnings",
      "cargo check --manifest-path src-tauri/Cargo.toml --all-targets --all-features --locked",
      "cargo test --manifest-path src-tauri/Cargo.toml --all-features --locked",
      "cargo build --manifest-path src-tauri/Cargo.toml --release --all-features --locked",
    ):
      self.assertIn(marker, justfile)

  def test_committed_rust_sources_match_native_rustfmt_baseline(self) -> None:
    main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    recipes = (ROOT / "src-tauri/src/recipes.rs").read_text(encoding="utf-8")

    # These are the exact forms emitted by rustfmt 1.94.0 on Windows for the
    # recipe code added in 0.3.x. Keep this lightweight guard so artifact
    # packaging environments without Rust still reject the known drift.
    self.assertIn(
      "async fn recipe_config(app: &AppHandle, app_data: &Path, recipe_id: &str) -> Result<Value, String> {",
      main,
    )
    self.assertIn(
      "async fn recipe_webview_js(app: &AppHandle, app_data: &Path, recipe_id: &str) -> Option<String> {",
      main,
    )
    self.assertIn(
      'let Some(id) = recipe.get("id").and_then(Value::as_str).map(str::to_owned) else {',
      recipes,
    )
    self.assertNotIn(
      'let Some(id) = recipe\n                .get("id")',
      recipes,
    )

  def test_clean_checker_reports_exact_dirty_path(self) -> None:
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      tools = root / "tools"
      tools.mkdir()
      checker = tools / "check_clean.py"
      checker.write_text((ROOT / "tools/check_clean.py").read_text(encoding="utf-8"), encoding="utf-8")
      (root / "tracked.txt").write_text("clean\n", encoding="utf-8")
      subprocess.run(["git", "init", "-q", "-b", "master"], cwd=root, check=True)
      subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
      subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True
      )
      subprocess.run(["git", "add", "."], cwd=root, check=True)
      subprocess.run(["git", "commit", "-q", "-m", "Proj: Test"], cwd=root, check=True)

      clean = subprocess.run(
        ["python3", str(checker)], cwd=root, text=True, capture_output=True, check=False
      )
      self.assertEqual(clean.returncode, 0)
      self.assertIn("Git worktree is clean", clean.stdout)

      (root / "tracked.txt").write_text("dirty\n", encoding="utf-8")
      dirty = subprocess.run(
        ["python3", str(checker)], cwd=root, text=True, capture_output=True, check=False
      )
      self.assertNotEqual(dirty.returncode, 0)
      self.assertIn("tracked.txt", dirty.stderr + dirty.stdout)


if __name__ == "__main__":
  unittest.main()
