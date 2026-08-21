#!/usr/bin/env python3
"""Regression coverage for non-mutating local release orchestration."""

from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_release_validator():
  path = ROOT / "tools/validate_release.py"
  spec = importlib.util.spec_from_file_location("tauridium_validate_release", path)
  if spec is None or spec.loader is None:
    raise RuntimeError("unable to load release validator")
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


class ReleaseWorkflowTests(unittest.TestCase):
  def test_platform_specific_just_recipes_are_disjoint(self) -> None:
    validator = load_release_validator()
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    validator.validate_just_recipe_platforms(justfile)

    malformed = justfile.replace("[unix]\npackage-handoff:", "package-handoff:", 1)
    with self.assertRaisesRegex(SystemExit, "duplicate just recipe 'package-handoff'"):
      validator.validate_just_recipe_platforms(malformed)

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


  def test_ci_and_tagged_release_enforce_locked_full_quality_gates(self) -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    for marker in (
      "cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --all-features --locked -- -D warnings",
      "cargo test --manifest-path src-tauri/Cargo.toml --all-features --locked",
      "cargo check --manifest-path src-tauri/Cargo.toml --all-targets --all-features --locked",
    ):
      self.assertIn(marker, ci)
      self.assertIn(marker, release)
    for marker in (
      "python3 -m unittest discover -s tools -p 'test_*.py'",
      "npm run check",
      "npm test",
      "cargo fmt --manifest-path src-tauri/Cargo.toml --all -- --check",
    ):
      self.assertIn(marker, release)

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

    # These are the exact forms emitted by rustfmt 1.97.1 on Windows for the
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
    self.assertIn(
      '    let text =\n        fs::read_to_string(path).map_err(|error| format!("Unable to read backup: {error}"))?;',
      (ROOT / "src-tauri/src/backup.rs").read_text(encoding="utf-8"),
    )
    backup = (ROOT / "src-tauri/src/backup.rs").read_text(encoding="utf-8")
    self.assertIn(
      '        let root =\n            std::env::temp_dir().join(format!("tauridium-backup-test-{}", std::process::id()));',
      backup,
    )
    self.assertIn(
      'fn persist_app_settings(app: &AppHandle, state: &AppState, settings: &Value) -> Result<(), String> {',
      main,
    )
    self.assertIn(
      '        let entry =\n            entry.map_err(|error| format!("Unable to read custom recipe entry: {error}"))?;',
      recipes,
    )
    self.assertIn(
      '            return Err(format!(\n                "Custom recipe folder uses a reserved Tauridium id: {id}"\n            ));',
      recipes,
    )
    self.assertIn(
      'pub(crate) fn validate_custom_recipe_backups(backups: &[CustomRecipeBackup]) -> Result<(), String> {',
      recipes,
    )
    self.assertIn(
      '    let parsed = Url::parse(&url).map_err(|error| format!("Invalid external URL: {error}"))?;',
      main,
    )
    self.assertNotIn(
      '    let parsed =\n        Url::parse(&url).map_err(|error| format!("Invalid external URL: {error}"))?;',
      main,
    )
    backup = (ROOT / "src-tauri/src/backup.rs").read_text(encoding="utf-8")
    local_profile = (ROOT / "src-tauri/src/local_profile.rs").read_text(encoding="utf-8")
    self.assertIn(
      '        let verified =\n            load(&staging).map_err(|error| format!("Backup write verification failed: {error}"))?;',
      backup,
    )
    self.assertIn(
      '    Ok(path.with_file_name(format!(".{name}.tauridium-tmp-{}", std::process::id())))',
      backup,
    )
    self.assertIn(
      '        assert!(\n            !migrated\n                .summary(Path::new("legacy.json"))\n                .integrity_verified\n        );',
      backup,
    )
    self.assertIn(
      '        let root =\n            std::env::temp_dir().join(format!("tauridium-backup-size-test-{}", std::process::id()));',
      backup,
    )
    self.assertIn(
      '        let summary = sample().summary(path).with_recovery_backup_path(recovery);',
      backup,
    )
    self.assertIn(
      '                return Err(format!(\n                    "Backup contains duplicate local workspace id: {id}"\n                ));',
      local_profile,
    )
    self.assertIn(
      '    let raw = if raw.is_empty() {\n        service.id.trim()\n    } else {\n        raw\n    };',
      main,
    )
    self.assertIn(
      '    let theme = object\n        .get("theme")\n        .and_then(Value::as_str)\n        .unwrap_or_default();',
      main,
    )
    self.assertIn(
      '    for (key, label) in [("serviceOrder", "Service"), ("workspaceOrder", "Workspace")] {',
      main,
    )
    self.assertIn(
      'fn sync_services_menu(app: AppHandle, services: Vec<NativeServiceMenuEntry>) -> Result<(), String> {',
      main,
    )

  def test_download_notification_uses_valid_quoted_format_string(self) -> None:
    main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    self.assertIn(r'.body(format!("Downloaded \"{filename}\""))', main)
    self.assertIn('.and_then(Path::file_name)', main)
    self.assertNotIn('format!("Downloaded "{}""', main)

  def test_tauridium_menu_opens_settings_and_exposes_about_quick_links(self) -> None:
    main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
    menu_builder = main.split("fn build_native_application_menu", 1)[1].split("#[derive(Clone, Copy)]", 1)[0]
    native_menu = main.split("// Native application menu", 1)[1].split("// Request notification", 1)[0]

    self.assertIn('"open-settings"', menu_builder)
    self.assertIn('"Settings"', menu_builder)
    self.assertIn('app.emit("open-settings", ())', native_menu)
    self.assertIn('"open-add-service"', menu_builder)
    self.assertIn('"Add Service"', menu_builder)
    self.assertIn('"Add Workspace"', menu_builder)
    self.assertIn('app.emit("open-add-workspace", ())', native_menu)
    self.assertIn("hide_service_webviews(app, &state);", native_menu)
    self.assertIn('Submenu::with_items(', menu_builder)
    self.assertIn('"About"', menu_builder)
    self.assertIn('"Project Homepage"', menu_builder)
    self.assertIn('"Project Source Code"', menu_builder)
    self.assertIn('"Author Homepage"', menu_builder)
    self.assertIn('open_external(PROJECT_HOMEPAGE)', native_menu)
    self.assertIn('open_external(PROJECT_SOURCE_CODE)', native_menu)
    self.assertIn('open_external(AUTHOR_HOMEPAGE)', native_menu)
    self.assertNotIn("PredefinedMenuItem::about", menu_builder + native_menu)
    self.assertIn('listen("open-settings", openAppSettings)', app)
    self.assertIn('listen("open-about", openAbout)', app)
    about_body = app.split("function openAbout()", 1)[1].split("function backupFileName", 1)[0]
    self.assertIn("hideServices().catch", about_body)
    self.assertIn('settingsTab = "about"', about_body)
    self.assertIn('view = "appSettings"', about_body)
    self.assertIn('["about", "About"]', app)
    self.assertIn('{:else if settingsTab === "about"}', app)
    self.assertIn('>Repository</span>', app)
    self.assertIn('github.com/Akkitto/Tauridium', app)
    self.assertIn('appMetadata?.license', app)
    self.assertIn('appMetadata?.author', app)

  def test_unix_initializer_bootstraps_tauri_cli_for_release_builds(self) -> None:
    init_py = (ROOT / "tools/init.py").read_text(encoding="utf-8")
    self.assertIn('def ensure_tauri_cli() -> None:', init_py)
    self.assertIn('["cargo", "tauri", "--version"]', init_py)
    self.assertIn(
      '["cargo", "install", "tauri-cli", "--locked", "--version", "^2"]',
      init_py,
    )
    self.assertIn('ensure_pinned_rust_toolchain()\n      ensure_tauri_cli()\n      install_javascript_dependencies()', init_py)

  def test_release_packaging_requires_pinned_rustfmt_check(self) -> None:
    toolchain = (ROOT / "rust-toolchain.toml").read_text(encoding="utf-8")
    package_release = (ROOT / "tools/package_release.py").read_text(encoding="utf-8")
    self.assertIn('channel = "1.97.1"', toolchain)
    self.assertIn('components = ["rustfmt", "clippy"]', toolchain)
    self.assertIn('def require_pinned_rustfmt_clean() -> None:', package_release)
    self.assertIn('\"cargo\",\n        \"fmt\",', package_release)
    self.assertIn('require_pinned_rustfmt_clean()\n  release_version = version()', package_release)

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
