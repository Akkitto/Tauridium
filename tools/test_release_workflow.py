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
      "cargo tauri build --no-bundle --ci",
    ):
      self.assertIn(marker, justfile)

  def test_production_runtime_uses_tauri_cli_and_raw_release_is_guarded(self) -> None:
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    build_rs = (ROOT / "src-tauri/build.rs").read_text(encoding="utf-8")
    self.assertIn("build:\n  cargo tauri build --no-bundle --ci", justfile)
    main_rs = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    package_release = (ROOT / "tools/package_release.py").read_text(encoding="utf-8")
    self.assertIn('std::env::var("PROFILE")', build_rs)
    self.assertIn("tauri_build::is_dev()", build_rs)
    self.assertIn("cargo:rustc-env=TAURIDIUM_BUILD_MODE", build_rs)
    self.assertIn("cargo:rustc-env=TAURIDIUM_TARGET", build_rs)
    self.assertIn("Refusing a development-mode release binary", build_rs)
    self.assertIn('env!("TAURIDIUM_BUILD_MODE")', main_rs)
    self.assertIn('env!("TAURIDIUM_TARGET")', main_rs)
    self.assertIn('"--build-info-file"', main_rs)
    self.assertIn("validate_build_info", package_release)
    self.assertIn("runtime_zip_name", package_release)
    self.assertIn('"win-x64"', package_release)
    self.assertIn('"linux-x64"', package_release)
    self.assertNotIn("FORBIDDEN_RUNTIME_MARKERS", package_release)

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
    self.assertIn(
      '    inflight: Mutex<HashSet<String>>,      // webviews being created (prevents duplicate add_child)',
      main,
    )
    self.assertIn(
      '    let win = app.get_window("main").ok_or("Main window not found")?;',
      main,
    )

  def test_download_notification_uses_valid_quoted_format_string(self) -> None:
    main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    self.assertIn(
      '.body(format!("Downloaded \\"{}\\"", download_filename(&url)))',
      main,
    )
    self.assertNotIn('format!("Downloaded "{}""', main)

  def test_about_menu_opens_in_app_about_section(self) -> None:
    main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")

    self.assertIn('"about-tauridium"', main)
    self.assertIn('"About Tauridium"', main)
    self.assertIn('app.emit("open-about", ())', main)
    self.assertNotIn("PredefinedMenuItem::about", main)
    self.assertIn('listen("open-about"', app)
    self.assertIn('settingsTab = "about"', app)
    self.assertIn('["about", "About"]', app)
    self.assertIn('{:else if settingsTab === "about"}', app)
    self.assertIn('Project: github.com/Gizmo091/Tauridium', app)

  def test_unix_initializer_bootstraps_tauri_cli_for_release_builds(self) -> None:
    init_py = (ROOT / "tools/init.py").read_text(encoding="utf-8")
    self.assertIn('def ensure_tauri_cli() -> None:', init_py)
    self.assertIn('["cargo", "tauri", "--version"]', init_py)
    self.assertIn(
      '["cargo", "install", "tauri-cli", "--locked", "--version", "^2"]',
      init_py,
    )
    self.assertIn('ensure_tauri_cli()\n      install_javascript_dependencies()', init_py)

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
