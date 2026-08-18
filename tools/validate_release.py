#!/usr/bin/env python3
"""Validate release-critical Tauridium source invariants without network access."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = "master"


def fail(message: str) -> None:
  raise SystemExit(f"error: {message}")


def read(path: str) -> str:
  return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
  tauri = json.loads(read("src-tauri/tauri.conf.json"))
  package = json.loads(read("package.json"))
  lock = json.loads(read("package-lock.json"))
  cargo = read("src-tauri/Cargo.toml")
  cargo_lock = read("src-tauri/Cargo.lock")
  version = tauri["version"]

  if not re.fullmatch(r"\d+\.\d+\.\d+", version):
    fail(f"invalid SemVer release version: {version}")
  if package.get("version") != version:
    fail("package.json version differs from tauri.conf.json")
  if lock.get("version") != version or lock.get("packages", {}).get("", {}).get("version") != version:
    fail("package-lock.json root version differs from tauri.conf.json")
  if f'version = "{version}"' not in cargo:
    fail("Cargo.toml version differs from tauri.conf.json")
  tauridium_lock = re.search(r'\[\[package\]\]\nname = "tauridium"\nversion = "([^"]+)"', cargo_lock)
  if not tauridium_lock or tauridium_lock.group(1) != version:
    fail("Cargo.lock Tauridium version differs from tauri.conf.json")

  allow_scripts = package.get("allowScripts")
  if allow_scripts != {"esbuild@0.25.12": True}:
    fail("package.json must approve exactly esbuild@0.25.12 install scripts")

  expected_frontend_fixes = {
    "node_modules/esbuild": "0.25.12",
    "node_modules/nanoid": "3.3.18",
    "node_modules/postcss": "8.5.25",
  }
  locked_packages = lock.get("packages", {})
  for package_path, expected_version in expected_frontend_fixes.items():
    actual_version = locked_packages.get(package_path, {}).get("version")
    if actual_version != expected_version:
      fail(
        f"{package_path} must be locked at reviewed version {expected_version}; "
        f"found {actual_version!r}"
      )

  justfile = read("justfile")
  init_py = read("tools/init.py")
  init_ps1 = read("tools/init.ps1")
  python_ps1 = read("tools/python.ps1")
  clean_ps1 = read("tools/clean.ps1")
  windows_tests = read("tools/test_windows_workflow.py")
  package_release = read("tools/package_release.py")
  package_release_test = read("tools/test_package_release.py")
  release_workflow_test = read("tools/test_release_workflow.py")
  check_clean = read("tools/check_clean.py")
  if f'INIT_VERSION = "{version}"' not in init_py:
    fail("initializer release identity differs from release version")
  if "required pkg-config modules are" in init_py:
    fail("initializer contains stale pkg-config-only failure wording")
  if "extract the release into a new empty directory" not in init_py:
    fail("initializer does not detect mixed/stale release extraction")
  if "--native-only" not in init_py:
    fail("initializer lacks native-only diagnostic mode")
  if '["npm", "exec", "--offline", "--", "esbuild", "--version"]' not in init_py:
    fail("initializer does not validate esbuild through npm's platform-aware executable path")
  if '["node", str(esbuild), "--version"]' in init_py:
    fail("initializer still attempts to parse the native esbuild binary with Node.js")
  for marker in (
    "def ensure_tauri_cli() -> None:",
    '["cargo", "tauri", "--version"]',
    '["cargo", "install", "tauri-cli", "--locked", "--version", "^2"]',
    "ensure_tauri_cli()\n      install_javascript_dependencies()",
  ):
    if marker not in init_py:
      fail(f"Unix initializer is missing Tauri CLI bootstrap coverage: {marker}")
  if "init:\n  python3 tools/init.py" not in justfile:
    fail("just init does not delegate to the self-contained initializer")
  if "python3 -m unittest discover -s tools -p 'test_*.py'" not in justfile:
    fail("Python regression tests are not part of just test")

  if '[windows]\nset shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command"]' not in justfile:
    fail("Windows just recipes do not use native PowerShell")
  if 'set minimum-version := "1.56.0"' not in justfile:
    fail("justfile does not require the conditional-shell capable just version")
  for marker in (
    "tools/init.ps1",
    "tools/init.ps1 -SelfTest",
    "tools/python.ps1 tools/validate_release.py",
    'tools/python.ps1 -m unittest discover -s tools -p "test_*.py"',
    "tools/python.ps1 tools/package_release.py",
    "tools/clean.ps1",
  ):
    if marker not in justfile:
      fail(f"Windows just workflow is incomplete: {marker}")

  for marker in (
    "fmt-check:\n  cargo fmt --manifest-path src-tauri/Cargo.toml --all -- --check",
    "release: release-clean fmt-check lint check test build release-clean package",
    "tools/python.ps1 tools/check_clean.py",
    "--all-targets --all-features --locked -- -D warnings",
    "--all-targets --all-features --locked",
    "--all-features --locked",
    "cargo tauri build --no-bundle --ci",
  ):
    if marker not in justfile:
      fail(f"release workflow is missing non-mutating/locked gate: {marker}")
  if "release: fmt lint" in justfile:
    fail("release workflow must not mutate Rust source with cargo fmt")
  if "git status" not in check_clean or "--porcelain" not in check_clean:
    fail("release clean-worktree checker is incomplete")
  for test_marker in (
    "test_release_uses_non_mutating_format_check_and_clean_gates",
    "test_production_runtime_uses_tauri_cli_and_raw_release_is_guarded",
    "test_committed_rust_sources_match_native_rustfmt_baseline",
    "test_download_notification_uses_valid_quoted_format_string",
  ):
    if test_marker not in release_workflow_test:
      fail(f"release workflow regression coverage is missing: {test_marker}")

  if f'$InitVersion = "{version}"' not in init_ps1:
    fail("PowerShell initializer release identity differs from release version")
  for marker in (
    "Microsoft.VisualStudio.BuildTools",
    "Microsoft.EdgeWebView2Runtime",
    "Rustlang.Rustup",
    "OpenJS.NodeJS.LTS",
    "Python.Python.3.13",
    "stable-msvc",
    'cargo.exe install tauri-cli --locked --version "^2"',
    "System.Management.Automation.Language.Parser",
    "[switch]$SelfTest",
    "VBSCRIPT",
  ):
    if marker not in init_ps1:
      fail(f"PowerShell initializer is missing Windows prerequisite coverage: {marker}")
  if "function " in init_ps1.lower():
    fail("PowerShell initializer must remain function-free to avoid Windows PowerShell bootstrap dispatch regressions")
  if "$MsvcBuildToolsTask" in init_ps1:
    fail("PowerShell initializer regressed to indirect MSVC script-block dispatch")
  if "`" in init_ps1:
    fail("PowerShell initializer contains backtick escape syntax; keep bootstrap diagnostics parser-safe")
  if "`" in python_ps1:
    fail("PowerShell Python resolver contains backtick escape syntax; keep Windows tooling parser-safe")
  for marker in (
    '$DefaultScoopShims = Join-Path $HOME "scoop\\shims"',
    '+ Windows package manager: Scoop preferred',
    '+ scoop install nodejs-lts',
    '+ scoop install python',
    '+ scoop install git',
    '+ scoop install rustup',
    '+ winget.exe install OpenJS.NodeJS.LTS (fallback)',
    '+ winget.exe install Python.Python.3.13 (fallback)',
    '+ winget.exe install Git.Git (fallback)',
    '+ winget.exe install Rustlang.Rustup (fallback)',
  ):
    if marker not in init_ps1:
      fail(f"PowerShell initializer is missing Scoop-first package handling: {marker}")
  for marker in ('"py.exe"', '"python.exe"', '"python3.exe"', '"-3"', '"--version"'):
    if marker not in python_ps1:
      fail(f"PowerShell Python resolver is missing candidate/probe coverage: {marker}")
  if init_ps1.index('[Environment]::GetEnvironmentVariable("Path", "Machine")') > init_ps1.index('$NodeCommand = Get-Command -Name "node.exe"'):
    fail("PowerShell initializer checks Node.js before refreshing persisted Windows PATH")
  for marker in (
    '$SavedErrorActionPreference = $ErrorActionPreference',
    '$ErrorActionPreference = "SilentlyContinue"',
    '$NativeProbeExitCode',
    '$PythonProbeExitCode',
    '$CargoTauriProbeExitCode',
    '$CargoAuditProbeExitCode',
  ):
    if marker not in init_ps1:
      fail(f"PowerShell initializer is missing native-probe isolation: {marker}")
  for forbidden in ("wsl.exe", "bash.exe", "nu.exe", "nushell"):
    if forbidden in init_ps1.lower() or forbidden in clean_ps1.lower():
      fail(f"Windows PowerShell tooling unexpectedly depends on {forbidden}")
  if "test_windows_shell_is_builtin_powershell_not_sh" not in windows_tests:
    fail("Windows PowerShell workflow regression coverage is missing")

  vsconfig = json.loads(read(".vsconfig"))
  vs_components = set(vsconfig.get("components", []))
  for component in (
    "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
    "Microsoft.VisualStudio.Component.VC.Tools.ARM64",
    "Microsoft.VisualStudio.Component.Windows11SDK.26100",
  ):
    if component not in vs_components:
      fail(f".vsconfig is missing required Windows component: {component}")

  for package_marker in (
    'SOURCE_MANIFEST_NAME = ".tauridium-source-manifest.json"',
    '["git", "rev-parse", "--show-toplevel"]',
    "return load_source_manifest(release_version)",
    "source-manifest checksum mismatch",
    "context.manifest_bytes",
    '["git", "ls-files", "--stage", "-z"]',
    'def git_metadata_files()',
    'prefix + ".git/" + archive_path',
    'r"(?m)^(\\s*filemode\\s*=\\s*).*$"',
    'requires a real Git checkout',
    'changed paths:',
    'mode=0o755',
    'BUILD_INFO_ARGUMENT = "--build-info-file"',
    'def validate_build_info(',
    'def inspect_runtime(',
    'def runtime_zip_name(',
    'def target_suffix(',
    'def group_runtimes_by_target(',
  ):
    if package_marker not in package_release:
      fail(f"release packager is missing source-ZIP fallback protection: {package_marker}")
  for marker in (
    'f"tauridium-{release_version}-run-{suffix}.zip"',
    '"x86_64-pc-windows-msvc": "win-x64"',
    '"x86_64-unknown-linux-gnu": "linux-x64"',
    '"aarch64-apple-darwin": "macos-arm64"',
  ):
    if marker not in package_release:
      fail(f"release packager is missing target-qualified runtime naming: {marker}")

  for test_marker in (
    "test_extracted_source_uses_manifest_without_git",
    "test_extracted_source_rejects_modified_source",
    "test_extracted_source_requires_manifest_when_git_is_absent",
    "test_source_zip_preserves_manifest_and_manifest_file_set",
    "test_source_zip_requires_git_history",
    "test_dirty_git_source_error_names_changed_path",
    "test_docs_use_manifest_git_log_without_git_repository",
    "test_git_index_modes_are_used_instead_of_host_filesystem_modes",
    "test_validate_build_info_rejects_development_mode",
    "test_validate_build_info_accepts_production_mode_even_with_configured_dev_url",
    "test_runtime_probe_executes_binary_and_validates_production_mode",
    "test_runtime_probe_rejects_development_binary",
    "test_runtime_target_suffixes_are_short_and_distinct",
    "test_multiple_runtime_targets_are_grouped_into_separate_run_archives",
    "test_build_info_requires_compilation_target",
  ):
    if test_marker not in package_release_test:
      fail(f"release packager regression coverage is missing: {test_marker}")
  for prerequisite in (
    "libwebkit2gtk-4.1-dev",
    "webkit2gtk4.1-devel",
    "webkit2gtk-4.1",
    "javascriptcoregtk-4.1",
    "libsoup-3.0",
    "gdk-pixbuf-2.0",
  ):
    if prerequisite not in init_py:
      fail(f"initializer is missing native prerequisite coverage: {prerequisite}")

  pkg_modules = init_py.split("LINUX_PKG_CONFIG_MODULES = (", 1)[1].split(")", 1)[0]
  if '"xdo"' in pkg_modules:
    fail("initializer must not require Debian libxdo through nonexistent xdo.pc metadata")
  for xdo_probe_marker in (
    "def libxdo_development_available",
    '"#include <xdo.h>\\n',
    '"-lxdo"',
    'missing.append("libxdo-dev")',
  ):
    if xdo_probe_marker not in init_py:
      fail(f"initializer is missing robust libxdo detection: {xdo_probe_marker}")

  build_rs = read("src-tauri/build.rs")
  if "build:\n  cargo tauri build --no-bundle --ci" not in justfile:
    fail("production runtime build does not use the Tauri CLI")
  if 'std::env::var("PROFILE")' not in build_rs or "tauri_build::is_dev()" not in build_rs:
    fail("build script does not reject development-mode release binaries")
  if "cargo:rustc-env=TAURIDIUM_BUILD_MODE" not in build_rs:
    fail("build script does not expose compile-time Tauri build provenance")
  if "cargo:rustc-env=TAURIDIUM_TARGET" not in build_rs:
    fail("build script does not expose the actual Rust compilation target")
  if "Refusing a development-mode release binary" not in build_rs:
    fail("build script lacks an actionable development-mode release failure")

  main_rs = read("src-tauri/src/main.rs")
  if (
    'env!("TAURIDIUM_BUILD_MODE")' not in main_rs
    or 'env!("TAURIDIUM_TARGET")' not in main_rs
    or '"--build-info-file"' not in main_rs
  ):
    fail("runtime does not expose compile-time Tauri build and target information")
  if "FORBIDDEN_RUNTIME_MARKERS" in package_release:
    fail("release packager still rejects inert configured devUrl bytes")
  for marker in (
    '"about-tauridium"',
    '"About Tauridium"',
    'app.emit("open-about", ())',
    'hide_service_webviews(app, &state);',
  ):
    if marker not in main_rs:
      fail(f"native About action is incomplete: {marker}")
  if "PredefinedMenuItem::about" in main_rs:
    fail("About still delegates to the platform-dependent predefined menu item")
  api_ts = read("src/lib/api.ts")
  api_test_ts = read("src/lib/api.test.ts")
  app = read("src/App.svelte")
  local_profile = read("src-tauri/src/local_profile.rs")
  recipes_rs = read("src-tauri/src/recipes.rs")
  backup_rs = read("src-tauri/src/backup.rs")

  required_backend = (
    "start_local_session",
    "get_services",
    "get_workspaces",
    "create_service",
    "update_service",
    "delete_service",
    "list_recipes",
    "create_custom_website_service",
    "get_recipe_storage_info",
    "save_custom_recipe",
    "import_custom_recipe",
    "create_workspace",
    "update_workspace",
    "delete_workspace",
    "export_backup",
    "restore_backup",
  )
  handler = main_rs.split("tauri::generate_handler![", 1)[-1].split("]", 1)[0]
  for command in required_backend:
    if command not in handler:
      fail(f"Tauri handler is missing {command}")

  if 'invoke("start_local_session")' not in api_ts:
    fail("frontend API does not expose the accountless session command")
  if "vi.hoisted" not in api_test_ts or "invoke: vi.fn()" not in api_test_ts:
    fail("frontend Tauri API test mock is not created with vi.hoisted")
  if "const invoke = vi.fn()" in api_test_ts:
    fail("frontend Tauri API test reintroduces a hoist-unsafe top-level invoke mock")
  if "Use Tauridium without an account" not in app:
    fail("login UI does not expose accountless mode")
  for marker in (
    'listen("open-about", openAbout)',
    'function openAbout()',
    'hideServices().catch',
    'settingsTab = "about"',
    '["about", "About"]',
    '{:else if settingsTab === "about"}',
  ):
    if marker not in app:
      fail(f"frontend About section is incomplete: {marker}")
  if 'serde_json::json!({ "mode": "local", "version": 1 })' not in main_rs:
    fail("local session marker is missing")
  if 'v.get("mode").and_then(Value::as_str) == Some("local")' not in main_rs:
    fail("local session restore path is missing")
  if "local_profile.json" not in main_rs:
    fail("local profile path is missing")
  if "replace_file(&tmp, path)" not in local_profile:
    fail("local profile does not use durable replacement")
  if "validate_recipe_id" not in local_profile:
    fail("local recipe identifiers are not validated")

  for marker in (
    'const CUSTOM_RECIPE_DIR: &str = "recipes"',
    '"custom-website"',
    '"https://nano-gpt.com/chat"',
    '"https://chutes.ai/chat"',
    '"http://127.0.0.1:4096"',
    'Recipe id is reserved by Tauridium',
    'package["id"] = Value::String(id.clone())',
  ):
    if marker not in recipes_rs:
      fail(f"local recipe implementation is missing: {marker}")
  for marker in (
    'Add a custom website',
    'Recipe creator',
    'Import folder…',
    'Import package.json…',
    'A recipe webview.js runs inside the loaded website',
  ):
    if marker not in app:
      fail(f"local recipe UI is missing: {marker}")
  for marker in (
    'invoke("create_custom_website_service"',
    'invoke("get_recipe_storage_info"',
    'invoke("save_custom_recipe"',
    'invoke("import_custom_recipe"',
  ):
    if marker not in api_ts:
      fail(f"frontend recipe API is missing: {marker}")

  for marker in (
    'invoke("export_backup", { path })',
    'invoke("restore_backup", { path })',
  ):
    if marker not in api_ts:
      fail(f"frontend backup API is missing: {marker}")
  for marker in (
    'const BACKUP_FORMAT: &str = "tauridium-backup"',
    'contains_sensitive_data: true',
    '"ferdiumSessionCredentials"',
    '"websiteCookiesAndStorage"',
    '"remoteRecipeCache"',
    'write_atomic(path',
    'MAX_BACKUP_BYTES',
  ):
    if marker not in backup_rs:
      fail(f"portable backup implementation is missing: {marker}")
  for marker in (
    'Export backup…',
    'Restore backup…',
    'tauridium-backup-',
    'Backups can contain sensitive local service configuration',
  ):
    if marker not in app:
      fail(f"backup UI is missing: {marker}")

  ci = read(".github/workflows/ci.yml")
  release_workflow = read(".github/workflows/release.yml")
  if "branches: [main]" in ci or "branches: [master]" not in ci:
    fail("CI does not target master")
  if "-D warnings" not in ci or "--all-features" not in ci:
    fail("CI Rust gates are weaker than release policy")
  if "cargo tauri build --no-bundle --ci" not in ci:
    fail("CI does not exercise a production Tauri runtime build")
  if "cargo build --manifest-path src-tauri/Cargo.toml --release --all-features" in ci:
    fail("CI still creates a raw Cargo release binary instead of a Tauri production runtime")
  if "windows-native:" not in ci or "shell: pwsh" not in ci:
    fail("CI does not exercise the native Windows PowerShell workflow")
  for command in ("just init-native", "just check", "just test", "just build", "just package"):
    if command not in ci:
      fail(f"Windows CI is missing native workflow gate: {command}")
  sync_block = release_workflow.split("- name: Sync app version to the tag", 1)[-1].split(
    "- name: Install Linux WebView deps", 1
  )[0]
  if "shell: bash" in sync_block:
    fail("release version synchronization still forces Bash on Windows jobs")
  if 'node tools/sync_version.mjs "${{ github.ref_name }}"' not in sync_block:
    fail("release version synchronization is not cross-platform")

  english = subprocess.run(
    [sys.executable, "tools/check_english.py"],
    cwd=ROOT,
    text=True,
    capture_output=True,
    check=False,
  )
  if english.returncode:
    sys.stderr.write(english.stdout)
    sys.stderr.write(english.stderr)
    fail("English-only tracked-source audit failed")

  changelog = read("CHANGELOG.md")
  if f"## [{version}]" not in changelog:
    fail(f"CHANGELOG.md has no {version} release section")

  if (ROOT / ".git").exists():
    status = subprocess.run(
      ["git", "diff", "--check"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    if status.returncode:
      sys.stderr.write(status.stdout)
      sys.stderr.write(status.stderr)
      fail("git diff --check failed")

  print(f"Tauridium {version} release invariants validated.")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
