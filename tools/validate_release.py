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


def validate_just_recipe_platforms(justfile: str) -> None:
  """Reject duplicate recipes unless each definition is platform-disjoint."""
  pending_platforms: set[str] = set()
  definitions: dict[str, list[set[str]]] = {}
  recipe_header = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)(?:\s+[^:]*)?:\s*(?:#.*)?$")

  for raw_line in justfile.splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
      continue
    if raw_line[:1].isspace():
      continue
    if line.startswith("[") and line.endswith("]"):
      attribute = line[1:-1].strip()
      if attribute in {"unix", "windows"}:
        pending_platforms.add(attribute)
      continue

    match = recipe_header.match(line)
    if match:
      definitions.setdefault(match.group(1), []).append(set(pending_platforms))
    pending_platforms.clear()

  for name, variants in definitions.items():
    if len(variants) < 2:
      continue
    if any(len(platforms) != 1 for platforms in variants):
      fail(
        f"duplicate just recipe {name!r} must give every definition exactly one "
        "[unix] or [windows] attribute"
      )
    platforms = [next(iter(value)) for value in variants]
    if len(platforms) != len(set(platforms)):
      fail(f"duplicate just recipe {name!r} has overlapping platform definitions")


def main() -> int:
  tauri = json.loads(read("src-tauri/tauri.conf.json"))
  package = json.loads(read("package.json"))
  lock = json.loads(read("package-lock.json"))
  cargo = read("src-tauri/Cargo.toml")
  cargo_lock = read("src-tauri/Cargo.lock")
  rust_toolchain = read("rust-toolchain.toml")
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

  for marker in ('channel = "1.97.1"', 'profile = "minimal"', 'components = ["rustfmt", "clippy"]'):
    if marker not in rust_toolchain:
      fail(f"pinned Rust formatter toolchain invariant is missing: {marker}")

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
  validate_just_recipe_platforms(justfile)
  init_py = read("tools/init.py")
  init_ps1 = read("tools/init.ps1")
  python_ps1 = read("tools/python.ps1")
  clean_ps1 = read("tools/clean.ps1")
  windows_tests = read("tools/test_windows_workflow.py")
  package_release = read("tools/package_release.py")
  package_release_test = read("tools/test_package_release.py")
  release_workflow_test = read("tools/test_release_workflow.py")
  check_clean = read("tools/check_clean.py")
  patch_0318_test = read("tools/test_patch_0318.py")
  patch_0319_test = read("tools/test_patch_0319.py")
  settings_ui_test = read("tools/test_settings_ui.py")
  feature_0400_test = read("tools/test_feature_0400.py")
  patch_0402_test = read("tools/test_patch_0402.py")
  patch_0403_test = read("tools/test_patch_0403.py")
  patch_0404_test = read("tools/test_patch_0404.py")
  patch_0407_test = read("tools/test_patch_0407.py")
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
    "ensure_pinned_rust_toolchain()\n      ensure_tauri_cli()\n      install_javascript_dependencies()",
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
  for marker in (
    "def require_pinned_rustfmt_clean() -> None:",
    '"cargo",\n        "fmt",\n        "--manifest-path",\n        "src-tauri/Cargo.toml",\n        "--all",\n        "--",\n        "--check",',
    "require_pinned_rustfmt_clean()",
  ):
    if marker not in package_release:
      fail(f"release packager can bypass the pinned rustfmt gate: {marker}")
  package_main = package_release.split("def main() -> int:", 1)[-1]
  if package_main.index("require_pinned_rustfmt_clean()") > package_main.index("context = source_context(release_version)"):
    fail("release packaging validates source context before enforcing pinned rustfmt")
  if "git status" not in check_clean or "--porcelain" not in check_clean:
    fail("release clean-worktree checker is incomplete")
  for test_marker in (
    "test_release_uses_non_mutating_format_check_and_clean_gates",
    "test_production_runtime_uses_tauri_cli_and_raw_release_is_guarded",
    "test_committed_rust_sources_match_native_rustfmt_baseline",
    "test_download_notification_uses_valid_quoted_format_string",
    "test_release_packaging_requires_pinned_rustfmt_check",
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
    "rustup.exe toolchain install 1.97.1 --profile minimal --component rustfmt --component clippy",
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
    "def add_directory(",
    "def git_metadata_directories(",
    'add_directory(zf, prefix + ".git/")',
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
    "test_source_zip_preserves_required_empty_git_directories_after_pack_refs",
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
  window_state_test = read("tools/test_window_state.py")
  errno_lock = (
    'name = "errno"\n'
    'version = "0.3.14"\n'
    'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
    'checksum = "39cab71617ae0d63f51a36d69f866391735b51691dbda63cf6f96d042b63efeb"'
  )
  if errno_lock not in cargo_lock:
    fail("Cargo.lock does not preserve the verified errno 0.3.14 version/checksum pair")
  if (
    'name = "errno"\nversion = "0.3.13"' in cargo_lock
    and '39cab71617ae0d63f51a36d69f866391735b51691dbda63cf6f96d042b63efeb' in cargo_lock
  ):
    fail("Cargo.lock contains the known errno 0.3.13/0.3.14 checksum corruption")

  for marker in (
    'tauri-plugin-window-state = "=2.4.1"',
    'name = "tauri-plugin-window-state"\nversion = "2.4.1"',
    'checksum = "73736611e14142408d15353e21e3cca2f12a3cfb523ad0ce85999b6d2ef1a704"',
  ):
    source = cargo if marker.startswith("tauri-plugin") else cargo_lock
    if marker not in source:
      fail(f"persistent window-state dependency invariant is missing: {marker}")
  for marker in (
    "StateFlags::SIZE | StateFlags::POSITION | StateFlags::MAXIMIZED | StateFlags::FULLSCREEN",
    ".with_state_flags(persisted_window_state_flags())",
    '.with_filter(|label| label == "main")',
    '.with_filename("window-state.json")',
    "save_main_window_state(&handle);",
    "restore_main_window_state(&w);",
    "persisted_window_state_tracks_geometry_without_visibility",
  ):
    if marker not in main_rs:
      fail(f"persistent window-state lifecycle invariant is missing: {marker}")
  flags_body = main_rs.split("fn persisted_window_state_flags()", 1)[1].split("\n}", 1)[0]
  if "StateFlags::VISIBLE" in flags_body:
    fail("window-state persistence must not store visibility; startup visibility has separate settings")
  for test_marker in (
    "test_official_window_state_plugin_is_pinned_and_locked",
    "test_window_state_lockfile_preserves_valid_errno_resolution",
    "test_persistence_tracks_geometry_and_window_mode_but_not_visibility",
    "test_close_to_tray_saves_before_hiding",
    "test_tray_toggle_saves_before_hide_and_restores_before_show",
    "test_show_and_tray_quit_preserve_state",
  ):
    if test_marker not in window_state_test:
      fail(f"persistent window-state regression coverage is missing: {test_marker}")

  if (
    'env!("TAURIDIUM_BUILD_MODE")' not in main_rs
    or 'env!("TAURIDIUM_TARGET")' not in main_rs
    or '"--build-info-file"' not in main_rs
  ):
    fail("runtime does not expose compile-time Tauri build and target information")
  if "FORBIDDEN_RUNTIME_MARKERS" in package_release:
    fail("release packager still rejects inert configured devUrl bytes")
  menu_builder = main_rs.split("fn build_native_application_menu", 1)[-1].split("#[derive(Clone, Copy)]", 1)[0]
  native_menu = main_rs.split("// Native application menu", 1)[-1].split("// Request notification", 1)[0]
  for marker in ('"open-settings"', '"Settings"', '"open-add-service"', '"Add Service"', '"open-add-workspace"', '"Add Workspace"'):
    if marker not in menu_builder:
      fail(f"native Tauridium menu builder is incomplete: {marker}")
  for marker in (
    'app.emit("open-settings", ())',
    'app.emit("open-add-service", ())',
    'hide_service_webviews(app, &state);',
  ):
    if marker not in native_menu:
      fail(f"native Tauridium menu action is incomplete: {marker}")
  if '"About Tauridium"' in menu_builder + native_menu or "PredefinedMenuItem::about" in menu_builder + native_menu:
    fail("native Tauridium menu still exposes the obsolete About action")
  for marker in (
    "struct NativeServiceMenuEntry",
    "fn native_service_menu_label",
    "for (index, service) in services.iter().enumerate()",
    '"No services configured"',
    "fn sync_services_menu",
        'app.emit("select-service-id", service_id.to_string())',
  ):
    if marker not in main_rs:
      fail(f"dynamic native Services menu invariant is missing: {marker}")
  if 'format!("Service {i}")' in main_rs or "for i in 1..=9u32" in main_rs:
    fail("native Services menu still uses fixed generic numbered slots")
  api_ts = read("src/lib/api.ts")
  api_test_ts = read("src/lib/api.test.ts")
  app = read("src/App.svelte")
  local_profile = read("src-tauri/src/local_profile.rs")
  recipes_rs = read("src-tauri/src/recipes.rs")
  backup_rs = read("src-tauri/src/backup.rs")
  audit_rs = read("src-tauri/src/audit.rs")
  portable_rs = read("src-tauri/src/portable.rs")
  for marker in (
    'invoke("sync_services_menu", { services })',
    'listen<string>("select-service-id"',
    "services.find((candidate) => candidate.id === e.payload)",
    "await refreshNativeServicesMenu();",
  ):
    if marker not in api_ts + app:
      fail(f"frontend dynamic native Services menu invariant is missing: {marker}")

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
    "set_service_order",
    "set_workspace_order",
    "export_backup",
    "restore_backup",
    "create_automatic_backup",
    "export_portable_bundle",
    "get_audit_log",
    "export_audit_log",
    "clear_audit_log",
    "get_service_icon",
    "get_app_metadata",
  )
  handler = main_rs.split("tauri::generate_handler![", 1)[-1].split("]", 1)[0]
  for command in required_backend:
    if command not in handler:
      fail(f"Tauri handler is missing {command}")

  for marker in (
    'oncontextmenu={(e) => openServiceContextMenu(e, s)}',
    '>Settings</button>',
    '>Reload</button>',
    '"Enable" : "Disable"',
    'Fetch preferred website icons automatically',
    'Enable custom URL placeholders for all services',
    'Show reload notifications',
  ):
    if marker not in app:
      fail(f"0.4.7 service-control UI invariant is missing: {marker}")
  for marker in (
    'test_sidebar_uses_full_row_without_cogwheel_and_has_context_menu',
    'test_website_icons_are_persistently_positive_and_negative_cached',
    'test_reload_shortcut_and_context_menu_share_optional_toast_path',
  ):
    if marker not in patch_0407_test:
      fail(f"0.4.7 regression coverage is missing: {marker}")
  if 'class="cog"' in app:
    fail("sidebar service cogwheel was reintroduced")

  patch_0408_test = read("tools/test_patch_0408.py")
  for marker in (
    'if (service && service.isEnabled !== false) selectService(service);',
    '<K extends keyof ServiceCustomUrlTemplate>',
    'onerror={() => markIconFailed(service)}',
    'role="menu" tabindex="-1"',
  ):
    if marker not in app:
      fail(f"0.4.8 frontend quality invariant is missing: {marker}")
  for marker in (
    'test_native_menu_selection_narrows_optional_service_before_use',
    'test_custom_url_template_setter_preserves_field_types_without_unsafe_record_cast',
    'test_managed_service_icon_failure_passes_service_not_service_id',
    'test_context_menu_role_is_programmatically_focusable',
  ):
    if marker not in patch_0408_test:
      fail(f"0.4.8 regression coverage is missing: {marker}")
  if 'markIconFailed(service.id)' in app:
    fail("managed service icon failure handler regressed to passing only a service id")

  patch_0409_test = read("tools/test_patch_0409.py")
  for marker in (
    'openContextServiceSettings(contextService)',
    '>Duplicate</button>',
    '? "Enable" : "Disable"',
    'async function duplicateServiceFromUi(service: Service)',
    'service.isLocalRecipe === true && service.recipeId === "custom-website"',
    'return createCustomWebsiteService(name, url);',
    'if (duplicate && duplicate.isEnabled !== false) selectService(duplicate);',
  ):
    if marker not in app:
      fail(f"0.4.9 context-menu invariant is missing: {marker}")
  for marker in (
    'plugin:webview|internal_toggle_devtools',
    '.initialization_script(REMOTE_TAURI_COMPAT_JS)',
  ):
    if marker not in main_rs:
      fail(f"0.4.9 remote-service compatibility invariant is missing: {marker}")
  for marker in (
    'test_context_settings_captures_service_before_clearing_menu_state',
    'test_context_menu_has_requested_order_and_short_toggle_labels',
    'test_duplicate_clones_service_workspace_and_tauridium_metadata_transactionally',
    'test_remote_tauri_devtools_compat_is_narrow_and_does_not_expand_acl',
  ):
    if marker not in patch_0409_test:
      fail(f"0.4.9 regression coverage is missing: {marker}")
  if 'closeServiceContextMenu(); openServiceSettings(contextService)' in app:
    fail("0.4.9 context Settings action can still invalidate contextService before use")
  if 'duplicate?.isEnabled !== false' in app:
    fail("0.4.9 duplicate selection still accepts a null service")

  patch_0410_test = read("tools/test_patch_0410.py")
  for marker in (
    'const preferred = services.filter((service) => service.useFavicon === true);',
    'await copyServiceIconCache(service.id, newId);',
    'async function closeServiceSettings()',
    'confirmAsk("Discard unsaved service changes?")',
    'async function persistService(reload = false): Promise<boolean>',
    'if (!saved) return;',
    'placeholder="Search workspaces…"',
    'class="accent-picker-control"',
    'Shift is required only when <strong>Shift</strong> is explicitly present',
  ):
    if marker not in app:
      fail(f"0.4.10 frontend invariant is missing: {marker}")
  for marker in (
    'let should_fetch = request.prefer_website_icon;',
    'fn service_shortcut_bridge_js(settings: &Value, service_id: &str, nonce: &str)',
    'service_shortcut_action_from_url',
    'tauridium-shortcut://bridge/',
    'app.emit("shortcut-action", "reloadService".to_string())',
    'fn copy_service_icon_cache(',
  ):
    if marker not in main_rs:
      fail(f"0.4.10 backend invariant is missing: {marker}")
  if 'if !should_fetch {' not in read("src-tauri/src/icons.rs"):
    fail("0.4.10 icon backend can still fetch when website-icon preference is disabled")
  for marker in (
    'test_automatic_and_bulk_icon_fetching_respect_service_preference',
    'test_duplicate_preserves_assigned_icon_and_cached_website_icon_policy',
    'test_native_reload_routes_through_frontend_toast_path',
    'test_devtools_shortcut_reaches_focused_service_webview_and_windows_opens',
    'test_failed_service_save_keeps_dirty_state_and_does_not_optimistically_commit',
    'test_service_settings_workspace_manager_is_searchable_scrollable_and_transactional',
  ):
    if marker not in patch_0410_test:
      fail(f"0.4.10 regression coverage is missing: {marker}")

  patch_0411_test = read("tools/test_patch_0411.py")
  for marker in (
    '{@const settingsServiceId = settingsSvc.id}',
    '{@const joined = workspace.services.includes(settingsServiceId)}',
    'toggleCurrentServiceWorkspace(workspace',
  ):
    if marker not in app:
      fail(f"0.4.11 Service Settings nullability invariant is missing: {marker}")
  for marker in (
    'test_service_settings_captures_non_nullable_service_id_for_workspace_callbacks',
    'test_fix_does_not_use_non_null_assertion_or_type_suppression',
  ):
    if marker not in patch_0411_test:
      fail(f"0.4.11 regression coverage is missing: {marker}")
  if 'workspace.services.includes(settingsSvc.id)' in app:
    fail("0.4.11 workspace UI still captures nullable settingsSvc inside callbacks")
  if 'settingsSvc!.id' in app:
    fail("0.4.11 Service Settings nullability fix regressed to a non-null assertion")

  patch_0412_test = read("tools/test_patch_0412.py")
  icon_request_block = main_rs.split("struct ServiceIconRequest {", 1)[1].split("}\n\n#[tauri::command]", 1)[0]
  if "is_local_recipe" in icon_request_block:
    fail("0.4.12 service icon request still contains the unused is_local_recipe field")
  for marker in (
    "test_service_icon_request_contains_only_runtime_used_fields",
    "test_frontend_does_not_send_removed_icon_request_field",
  ):
    if marker not in patch_0412_test:
      fail(f"0.4.12 regression coverage is missing: {marker}")

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
  for marker in (
    'class="panel settings-panel"',
    'class="settings-content"',
    'class="setting-card',
    'grid-template-columns: minmax(0, 1fr) auto',
    '@media (max-width: 760px)',
    'class="about-hero"',
    'class="about-logo"',
    'Source code ↗',
    'Releases ↗',
    'Report an issue ↗',
    '>Repository</span>',
    'appMetadata?.license',
    'appMetadata?.maintainer',
    'Contributors ↗',
    'Tauri v2',
    'Ferdium',
  ):
    if marker not in app:
      fail(f"settings/About UI quality invariant is missing: {marker}")
  if 'invoke("open_external_url", { url })' not in api_ts:
    fail("About project links do not use the native external-browser command")
  for marker in (
    'fn open_external_url(url: String) -> Result<(), String>',
    'matches!(parsed.scheme(), "http" | "https")',
    'open_external(parsed.as_str())',
  ):
    if marker not in main_rs:
      fail(f"native external-browser path is incomplete: {marker}")
  if not (ROOT / "src/assets/tauridium.svg").is_file():
    fail("About page is missing its bundled Tauridium icon")
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
    '"https://opencode.ai/go"',
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
    'const BACKUP_SCHEMA_CURRENT: u32 = 2',
    'const BACKUP_SCHEMA_MIN: u32 = 1',
    'const INTEGRITY_ALGORITHM: &str = "sha256"',
    'contains_sensitive_data: true',
    '"ferdiumSessionCredentials"',
    '"websiteCookiesAndStorage"',
    '"remoteRecipeCache"',
    '"windowMonitorGeometry"',
    'Backup integrity check failed; the file is corrupted or was modified',
    'replace_file(&staging, path)',
    'file.sync_all()',
    'let verified =\n            load(&staging)',
    'MAX_BACKUP_BYTES',
    'with_recovery_backup_path',
  ):
    if marker not in backup_rs:
      fail(f"portable backup implementation is missing: {marker}")
  for marker in (
    'merge_custom_recipe_backups',
    'replace_custom_recipes_exact',
    '.restore-tmp',
    '.restore-bak',
    'Backup contains duplicate custom recipe id',
  ):
    if marker not in recipes_rs:
      fail(f"transactional recipe backup restore is missing: {marker}")
  for marker in (
    'Backup contains duplicate local service id',
    'Backup contains duplicate local workspace id',
    'references unknown local service id',
    'contains duplicate service id',
  ):
    if marker not in local_profile:
      fail(f"local-profile backup validation is missing: {marker}")
  restore_body = main_rs.split("fn perform_restore_backup", 1)[-1].split("#[tauri::command]\nfn restore_backup", 1)[0]
  for marker in (
    'restore_recovery_backup_path',
    'pre-restore-{stamp}.json',
    'backup::save(&recovery_path, &recovery_document)',
    'replace_custom_recipes_exact(app, &previous_recipes)',
    'persist_app_settings(app, state, &previous_settings)',
  ):
    if marker not in restore_body and marker not in main_rs:
      fail(f"backup restore safety invariant is missing: {marker}")
  for marker in (
    '["backup", "Backup"]',
    '{:else if settingsTab === "backup"}',
    'value="startup">On program startup</option>',
    'value="daily">Daily</option>',
    'value="weekly">Weekly</option>',
    'value="monthly">Monthly</option>',
    'automaticBackupRetention',
    'createAutomaticBackup',
  ):
    if marker not in app:
      fail(f"automatic/dedicated Backup settings invariant is missing: {marker}")
  if 'invoke("create_automatic_backup", { filename })' not in api_ts:
    fail("frontend API does not expose automatic backup creation")
  for marker in (
    'fn create_automatic_backup(',
    'prune_automatic_backups(&root, retention_mode, retention, max_age_days, &path)',
    'backup::save(&path, &document)?',
    'automaticBackupSchedule',
    'automaticBackupRetention',
    'lastAutomaticBackupAt',
    'protected_path: &Path',
    'Some(protected_path)',
    'stamp.len() != 21',
    'days_in_month(year, month)',
  ):
    if marker not in main_rs:
      fail(f"automatic backup backend invariant is missing: {marker}")
  auto_body = main_rs.split("fn create_automatic_backup", 1)[-1].split("#[tauri::command]", 1)[0]
  if auto_body.index("backup::save(&path, &document)?") > auto_body.index("prune_automatic_backups(&root, retention_mode, retention, max_age_days, &path)"):
    fail("automatic backup retention pruning can occur before verified backup save")
  if 'let autostart_changed = patch.contains_key("autostart");' not in main_rs:
    fail("settings persistence does not isolate autostart side effects")
  set_settings_body = main_rs.split("fn set_app_settings", 1)[-1].split("#[tauri::command]", 1)[0]
  if 'if autostart_changed {' not in set_settings_body or 'apply_autostart_setting(&app, &value)?;' not in set_settings_body:
    fail("autostart updates are not conditional on an autostart patch")
  for marker in (
    "test_manual_backup_name_contains_local_date_time_seconds_and_milliseconds",
    "test_automatic_backup_has_all_requested_schedules_and_retention",
    "test_automatic_backup_serializes_and_prunes_only_after_verified_save",
    "test_automatic_backup_scheduler_avoids_concurrent_runs",
    "test_appearance_updates_do_not_touch_autostart",
    "test_automatic_backup_filename_is_path_traversal_safe",
    "test_local_only_wording_is_absent_from_current_tracked_text",
  ):
    if marker not in patch_0318_test:
      fail(f"0.3.18 regression coverage is missing: {marker}")
  for marker in (
    "test_backup_has_its_own_settings_tab",
    "test_service_settings_close_returns_to_services_when_opened_from_settings",
    "test_deprecated_local_only_wording_is_absent",
  ):
    if marker not in settings_ui_test:
      fail(f"0.3.18 Settings regression coverage is missing: {marker}")

  for marker in (
    "test_monthly_backup_schedule_uses_calendar_months",
    "test_monthly_backup_regression_covers_real_boundaries",
  ):
    if marker not in patch_0319_test:
      fail(f"0.3.19 backup-scheduling regression coverage is missing: {marker}")

  for marker in (
    "test_oled_and_custom_appearance_are_persisted",
    "test_service_management_scales_and_preserves_global_slots",
    "test_keybindings_include_requested_defaults_and_chords",
    "test_shared_sandboxes_are_backend_authoritative",
    "test_all_new_settings_flow_through_integrity_protected_backup",
    "test_release_identity_sync_covers_every_versioned_surface",
  ):
    if marker not in feature_0400_test:
      fail(f"0.4.0 feature regression coverage is missing: {marker}")
  for marker in (
    "test_quick_switcher_uses_dialog_compatible_container",
    "test_shared_storage_identifier_is_exercised_by_tests",
    "test_services_in_sandbox_avoids_filter_map_bool_then_lint",
    "test_single_accent_color_validation_is_direct",
  ):
    if marker not in patch_0402_test:
      fail(f"0.4.2 quality regression coverage is missing: {marker}")

  for marker in (
    '<div class="quick-switcher" role="dialog"',
    '.filter(|(_, value)| value.as_str() == Some(sandbox_id))',
    'let accent_color = object',
    'fn shared_sandbox_storage_identifier_is_stable_and_distinct()',
  ):
    if marker not in app + main_rs:
      fail(f"0.4.2 quality invariant is missing: {marker}")

  for marker in (
    "test_hex_to_hsl_preserves_fractional_precision",
    "test_frontend_requires_true_color_round_trip",
    "test_color_slider_labels_remain_human_readable",
  ):
    if marker not in patch_0403_test:
      fail(f"0.4.3 color-picker regression coverage is missing: {marker}")

  for marker in (
    "saturation: saturation * 100",
    "lightness: lightness * 100",
    "{Math.round(colorHue)}°",
    "{Math.round(colorSaturation)}%",
    "{Math.round(colorLightness)}%",
  ):
    if marker not in app + read("src/lib/ui.ts"):
      fail(f"0.4.3 color-picker invariant is missing: {marker}")

  for marker in (
    "test_restore_does_not_roll_back_machine_autostart",
    "test_automatic_backup_directory_is_persisted_validated_and_user_selectable",
    "test_settings_panel_uses_wider_dynamic_width_and_wrapping_tabs",
    "test_backup_retention_supports_count_age_combined_and_tiered_modes",
    "test_audit_tab_can_filter_refresh_export_and_clear",
    "test_sandbox_exports_support_individual_and_all_with_referenced_services",
    "test_workspace_exports_support_individual_and_all",
    "test_percentage_sidebar_width_is_bounded_and_resize_throttled",
    "test_service_position_wording_is_replaced",
    "test_portable_exports_are_integrity_protected_and_atomically_replaced",
  ):
    if marker not in patch_0404_test:
      fail(f"0.4.4 regression coverage is missing: {marker}")

  for marker in (
    'settings.insert("automaticBackupDirectory".into(), "".into());',
    'settings.insert("automaticBackupRetentionMode".into(), "count".into());',
    'settings.insert("automaticBackupMaxAgeDays".into(), 90.into());',
    'settings.insert("sidebarWidthMode".into(), "pixels".into());',
    'settings.insert("sidebarWidthPercent".into(), 20.into());',
    'apply_autostart_setting(app, &app_settings)',
    'Backup data restored successfully',
    'prune_automatic_backups(&root, retention_mode, retention, max_age_days, &path)',
  ):
    if marker not in main_rs:
      fail(f"0.4.4 backend invariant is missing: {marker}")

  for marker in (
    'const MAX_AUDIT_FILE_BYTES: u64 = 5 * 1024 * 1024;',
    'Value::String("[redacted]".into())',
    'file.sync_data()',
  ):
    if marker not in audit_rs:
      fail(f"0.4.4 audit invariant is missing: {marker}")

  for marker in (
    'const PORTABLE_FORMAT: &str = "tauridium-portable-collection";',
    'payload_sha256',
    'replace_file(&staging, path)',
    'select_custom_recipes',
  ):
    if marker not in portable_rs:
      fail(f"0.4.4 portable export invariant is missing: {marker}")

  for marker in (
    '["audit", "Audit log"]',
    'flex-wrap: wrap',
    'width: min(1180px, calc(100% - 32px))',
    'Service list alignment',
    'MAX_SIDEBAR_WIDTH_PX = 1200',
    'Choose automatic backup folder',
    'Tiered history (GFS-style)',
    'Export all sandboxes…',
    'doPortableExport("workspaces", "all workspaces"',
  ):
    if marker not in app:
      fail(f"0.4.4 frontend invariant is missing: {marker}")
  if "Service position" in app:
    fail("obsolete Service position wording remains in the Settings UI")

  workspace_test = read("tools/test_workspace_settings_0413.py")
  for marker in (
    '["workspaces", "Workspaces"]',
    'workspaceQuickSwitchOrder: "custom" | "customReverse" | "alphabetical" | "alphabeticalReverse" | "recent" | "recentReverse"',
    'workspaceLastUsed: Record<string, number>',
    'orderWorkspacesForQuickSwitch(',
    'managedWorkspaceServiceRows',
    'toggleManagedWorkspaceService',
    'moveManagedWorkspace',
    'closeManagedWorkspace',
    'workspaceUsagePersist = workspaceUsagePersist.then(async () => {',
    'workspaceIds.has(workspaceId)',
  ):
    if marker not in app + api_ts + read("src/lib/ui.ts"):
      fail(f"0.4.13 workspace-management invariant is missing: {marker}")
  if 'class="wspills"' in app or 'view === "workspaces"' in app:
    fail("0.4.13 sidebar/standalone workspace UI was reintroduced")
  for marker in (
    'settings.insert("workspaceQuickSwitchOrder".into(), "custom".into());',
    '"workspaceLastUsed".into(),',
    'App setting workspaceQuickSwitchOrder is invalid',
  ):
    if marker not in main_rs:
      fail(f"0.4.13 workspace settings backend invariant is missing: {marker}")
  for test_marker in (
    "test_sidebar_workspace_strip_is_removed",
    "test_settings_has_workspace_management_tab",
    "test_workspace_management_scales_and_preserves_canonical_order",
    "test_quick_switch_order_is_independent_and_portable",
  ):
    if test_marker not in workspace_test:
      fail(f"0.4.13 workspace regression coverage is missing: {test_marker}")

  patch_0414 = read("tools/test_patch_0414.py")
  for marker in (
    'captureServiceShortcuts: boolean;',
    'serviceShortcutCaptureOverrides: Record<string, boolean>;',
    'Capture Tauridium shortcuts inside services',
    'serviceShortcutCaptureMode(serviceId: string)',
    'serviceWorkspaceRows',
    'Workspace membership',
    '"Add Workspace"',
    'open-add-workspace',
  ):
    if marker not in app + api_ts + main_rs:
      fail(f"0.4.14 frontend/menu invariant is missing: {marker}")
  for marker in (
    'fn effective_service_shortcut_capture',
    'fn service_shortcut_bridge_js',
    'service_shortcut_action_from_url',
    'tauridium-shortcut://bridge/',
    'settings.insert("captureServiceShortcuts".into(), true.into());',
    '"serviceShortcutCaptureOverrides".into(),',
    'App setting serviceShortcutCaptureOverrides is invalid',
  ):
    if marker not in main_rs:
      fail(f"0.4.14 shortcut backend invariant is missing: {marker}")
  if '"Settings…"' in main_rs or '"Add Service…"' in main_rs:
    fail("0.4.14 obsolete native menu ellipsis wording remains")
  for test_marker in (
    "test_service_shortcut_capture_defaults_on_and_is_portable",
    "test_service_webview_bridge_captures_single_shortcuts_and_chords",
    "test_native_menu_wording_and_add_workspace_action",
    "test_service_workspace_manager_has_clear_membership_actions_and_pagination",
  ):
    if test_marker not in patch_0414:
      fail(f"0.4.14 regression coverage is missing: {test_marker}")

  patch_0415 = read("tools/test_patch_0415.py")
  default_settings_block = main_rs.split("fn default_app_settings_value() -> Value {", 1)[1].split(
    "\nfn is_hex_color", 1
  )[0]
  for marker in (
    "serde_json::Map::<String, Value>::new()",
    "Value::Object(settings)",
  ):
    if marker not in default_settings_block:
      fail(f"0.4.15 settings-default construction invariant is missing: {marker}")
  if "serde_json::json!" in default_settings_block:
    fail("0.4.15 recursive json! macro was reintroduced into default app settings")
  if "#![recursion_limit" in main_rs:
    fail("0.4.15 must fix settings construction without a crate-wide recursion-limit override")
  for test_marker in (
    "test_default_settings_avoid_large_recursive_json_macro",
    "test_default_settings_preserve_critical_0414_values",
    "test_stale_searchrow_css_is_removed",
  ):
    if test_marker not in patch_0415:
      fail(f"0.4.15 regression coverage is missing: {test_marker}")

  patch_0416 = read("tools/test_patch_0416.py")
  service_workspace_block = app.split('<div class="set-title">Workspaces</div>', 1)[1].split(
    '<div class="set-title">Appearance</div>', 1
  )[0]
  for marker in (
    'class="service-workspace-filters" role="group"',
    '<ul class="service-workspace-list"',
    '<label class="service-workspace-option"',
    'class="service-workspace-checkbox"',
    '{joined ? "Included" : "Not included"}',
    'Create and include',
  ):
    if marker not in service_workspace_block:
      fail(f"0.4.16 service-workspace UX invariant is missing: {marker}")
  for marker in (
    'grid-template-columns: 20px 34px minmax(0, 1fr) auto',
    '.service-workspace-filters button { min-height: 32px;',
    '.service-workspace-toolbar { flex-direction: column; }',
  ):
    if marker not in app:
      fail(f"0.4.16 service-workspace layout invariant is missing: {marker}")
  if 'class="service-workspace-row"' in service_workspace_block:
    fail("0.4.16 obsolete service-workspace action row was reintroduced")
  if '{joined ? "Remove" : "Add"}' in service_workspace_block:
    fail("0.4.16 narrow per-row Add/Remove controls were reintroduced")
  for test_marker in (
    "test_workspace_membership_uses_full_row_checkbox_targets",
    "test_workspace_rows_have_stable_alignment_and_membership_state",
    "test_workspace_filter_is_large_segmented_control",
    "test_workspace_manager_explains_direct_interaction_and_scales",
    "test_workspace_layout_has_narrow_screen_fallback",
  ):
    if test_marker not in patch_0416:
      fail(f"0.4.16 regression coverage is missing: {test_marker}")

  patch_0417 = read("tools/test_patch_0417.py")
  service_shortcut_block = app.split('<div class="set-title">Keyboard shortcuts</div>', 1)[1].split(
    '<div class="set-title">Workspaces</div>', 1
  )[0]
  for marker in (
    'class="service-shortcut-copy"',
    'Shortcut priority',
    'aria-label={`Shortcut priority for ${serviceLabel(settingsSvc)}`}',
  ):
    if marker not in service_shortcut_block:
      fail(f"0.4.17 shortcut-priority UX invariant is missing: {marker}")
  for marker in (
    '.service-shortcut-policy { display: grid; grid-template-columns: minmax(0, 1fr) minmax(230px, 320px);',
    '.service-shortcut-policy .desc { margin-left: 0; }',
    '.service-shortcut-effective { grid-column: 1 / -1; margin-top: 0; }',
    '.service-shortcut-policy { grid-template-columns: 1fr; }',
  ):
    if marker not in app:
      fail(f"0.4.17 shortcut-priority layout invariant is missing: {marker}")
  if '.service-shortcut-policy > div { min-width: 0; flex: 1 1 320px; }' in app:
    fail("0.4.17 obsolete shortcut flex-basis spacing regression was reintroduced")
  for test_marker in (
    "test_shortcut_priority_uses_compact_grid_without_flex_height_reservation",
    "test_shortcut_priority_copy_and_control_align_without_inherited_offsets",
    "test_shortcut_priority_stacks_cleanly_on_narrow_windows",
  ):
    if test_marker not in patch_0417:
      fail(f"0.4.17 regression coverage is missing: {test_marker}")

  patch_0418 = read("tools/test_patch_0418.py")
  ui_ts = read("src/lib/ui.ts")
  api_ts = read("src/lib/api.ts")
  recipes_rs = read("src-tauri/src/recipes.rs")
  tauri_conf = json.loads(read("src-tauri/tauri.conf.json"))

  for marker in (
    'addWorkspace: "Ctrl+Shift+N"',
    'case "addWorkspace": openAddWorkspace(); break;',
    '["addWorkspace", "Add workspace", "Create a new workspace."]',
  ):
    if marker not in ui_ts + app:
      fail(f"0.4.18 Add Workspace keybinding invariant is missing: {marker}")
  for marker in (
    'keybindings.insert("addWorkspace".into(), "Ctrl+Shift+N".into());',
    'shortcut("addWorkspace")',
    'if key == "keybindings"',
    'app_settings_merge_preserves_existing_keybindings_and_adds_new_defaults',
  ):
    if marker not in main_rs:
      fail(f"0.4.18 shortcut backend/migration invariant is missing: {marker}")

  reload_ui = app.split("async function reloadServiceFromUi", 1)[1].split(
    "async function refetchAllServiceIcons", 1
  )[0]
  for marker in (
    'pendingReloadToasts.set(service.id',
    'pendingReloadToasts.get(e.payload.id)',
    'showToast(reloadToast)',
    'showServiceToastOverlay(activeId, message)',
  ):
    if marker not in app:
      fail(f"0.4.18 service-independent reload-toast invariant is missing: {marker}")
  if 'showToast(`${serviceLabel(service)} reloaded.`)' in reload_ui:
    fail("0.4.18 reload toast must begin after the replacement service reaches ready state")
  for marker in (
    'invoke("show_service_toast_overlay", { serviceId, message })',
    'fn service_toast_overlay_script(',
    "host.attachShadow({{mode:'closed'}})",
    'fn show_service_toast_overlay(',
  ):
    if marker not in api_ts + main_rs:
      fail(f"0.4.18 service toast overlay invariant is missing: {marker}")
  if "window.__tauridiumShowToast" in main_rs.split("#[cfg(test)]", 1)[0]:
    fail("0.4.18 hosted pages must not receive a callable Tauridium toast API")

  requested_recipes = {
    "woodpecker": "http://localhost:8000/",
    "codeberg": "https://codeberg.org/",
    "sourcehut": "https://sr.ht/",
    "fritzbox": "http://192.168.178.1/",
    "artifacts-mmo": "https://artifactsmmo.com/",
    "lumo": "https://lumo.proton.me/",
    "suno": "https://suno.com/create",
    "midjourney": "https://www.midjourney.com/imagine",
    "sora": "https://sora.chatgpt.com/sunset",
    "grafana": "http://localhost:3000/",
    "graylog": "http://localhost:9000/",
    "kibana": "http://localhost:5601/",
    "anytype": "https://anytype.io/",
  }
  for recipe_id, url in requested_recipes.items():
    if f'"{recipe_id}",' not in recipes_rs or f'"{url}",' not in recipes_rs:
      fail(f"0.4.18 bundled recipe invariant is missing for {recipe_id}")
  for marker in (
    '"codeberg" => Some("https://codeberg.org/{teamId}")',
    '"sourcehut" => Some("https://sr.ht/~{teamId}/")',
    'feature_0418_recipes_use_expected_endpoints_and_custom_instance_policy',
    'feature_0418_forge_recipes_support_namespace_workspace_routes',
  ):
    if marker not in recipes_rs:
      fail(f"0.4.18 bundled recipe routing invariant is missing: {marker}")

  main_windows = tauri_conf.get("app", {}).get("windows", [])
  if not main_windows or main_windows[0].get("visible") is not False:
    fail("0.4.18 main window must start hidden for off-screen state restoration")
  reveal_window = main_rs.split("fn reveal_main_window_after_startup_restore", 1)[1].split(
    "fn show_main", 1
  )[0]
  if reveal_window.index("restore_main_window_state(&window);") > reveal_window.index("window.show();"):
    fail("0.4.18 main window must restore state before first show")
  for marker in (
    'reveal_main_window_after_startup_restore(app.handle(), start_minimized);',
    'StateFlags::FULLSCREEN',
  ):
    if marker not in main_rs:
      fail(f"0.4.18 direct fullscreen restoration invariant is missing: {marker}")

  for test_marker in (
    "test_add_workspace_has_default_shortcut_everywhere",
    "test_keybinding_merge_adds_new_defaults_without_resetting_existing_bindings",
    "test_reload_toast_waits_for_replacement_webview_ready_and_uses_overlay",
    "test_requested_bundled_recipes_have_expected_service_urls",
    "test_codeberg_and_sourcehut_support_workspace_namespace_routes",
    "test_main_window_starts_hidden_until_restored_state_is_applied",
  ):
    if test_marker not in patch_0418:
      fail(f"0.4.18 regression coverage is missing: {test_marker}")

  patch_0419 = read("tools/test_patch_0419.py")
  toast_test = main_rs.split(
    "fn service_toast_overlay_script_encodes_untrusted_text_without_page_global()", 1
  )[1].split("#[test]", 1)[0]
  for marker in (
    'let encoded = serde_json::to_string(message).unwrap();',
    'assert!(script.contains(&format!(")({encoded},2600);")));',
    'assert!(!script.contains(message));',
  ):
    if marker not in toast_test:
      fail(f"0.4.19 service-toast encoding-test invariant is missing: {marker}")
  for test_marker in (
    "test_service_toast_security_test_uses_canonical_json_encoding",
    "test_service_toast_overlay_still_encodes_before_native_eval",
  ):
    if test_marker not in patch_0419:
      fail(f"0.4.19 regression coverage is missing: {test_marker}")

  patch_0420 = read("tools/test_patch_0420.py")
  for marker in (
    'sidebarServiceDragReorder: boolean;',
    'sidebarServiceDragReorder: true,',
    'settings.insert("sidebarServiceDragReorder".into(), true.into());',
    'draggable={appSettings.sidebarServiceDragReorder && !serviceOrderBusy}',
    'reorderVisibleSubsetAt(previousIds, visibleIds, movingIds[0], target.id, placement)',
    'settings_write: Mutex<()>',
  ):
    if marker not in api_ts + app + main_rs:
      fail(f"0.4.20 sidebar drag-order invariant is missing: {marker}")
  for test_marker in (
    "test_drag_reordering_setting_is_default_on_typed_and_validated",
    "test_advanced_toggle_controls_only_sidebar_dragging",
    "test_drag_handlers_are_gated_and_persist_only_on_drop",
    "test_reorder_helper_is_stale_safe_and_preserves_filtered_slots",
    "test_drop_indicator_matches_before_after_placement",
    "test_backend_serializes_settings_transactions_with_order_writes",
    "test_disabling_drag_reorder_clears_in_progress_drag_state",
  ):
    if test_marker not in patch_0420:
      fail(f"0.4.20 regression coverage is missing: {test_marker}")

  patch_0421 = read("tools/test_patch_0421.py")
  tauri_config = json.loads(read("src-tauri/tauri.conf.json"))
  main_window = next(
    (window for window in tauri_config.get("app", {}).get("windows", []) if window.get("label") == "main"),
    None,
  )
  if main_window is None or main_window.get("dragDropEnabled") is not False:
    fail("0.4.21 main shell must disable Tauri native drag/drop interception for HTML5 sidebar dragging")
  for test_marker in (
    "test_main_shell_disables_tauri_native_drag_drop_interception",
    "test_sidebar_reorder_remains_html5_drag_drop_with_move_semantics",
    "test_sidebar_ordering_does_not_depend_on_tauri_native_file_drop_events",
  ):
    if test_marker not in patch_0421:
      fail(f"0.4.21 regression coverage is missing: {test_marker}")

  patch_0422 = read("tools/test_patch_0422.py")
  for marker in (
    "if (service.useFavicon !== true) return null;",
    "return preferredWebsiteIcon(service) ?? iconSrc(service);",
    "src={displayedServiceIcon(service)}",
    "serviceIconFailed(service)",
    "previous?.useFavicon !== true || !preferredWebsiteIcon(s)",
  ):
    if marker not in app:
      fail(f"0.4.22 configured-service icon invariant is missing: {marker}")
  managed_services = app.split('aria-label="Configured services"', 1)[-1].split("managed-empty", 1)[0]
  if "src={iconSrc(service)}" in managed_services:
    fail("Configured services regressed to bypassing per-service icon preference resolution")
  for test_marker in (
    "test_resolved_service_icon_honours_per_service_website_icon_preference",
    "test_configured_services_use_same_resolved_icon_path_as_sidebar",
    "test_enabling_website_icon_preference_hydrates_icon_without_restart",
    "test_stale_cached_website_icon_is_ignored_when_preference_is_disabled",
  ):
    if test_marker not in patch_0422:
      fail(f"0.4.22 regression coverage is missing: {test_marker}")

  patch_0423 = read("tools/test_patch_0423.py")
  for marker in (
    "function setTrailingDropTarget",
    "contiguousIdRange(visibleIds, anchorId, service.id)",
    "reorderVisibleGroupAt(previousIds, visibleIds, movingIds, target.id, placement)",
    '<div class="set-title">Sandbox</div>',
    'if (view === "service" && activeId === serviceId)',
    "Tauridium could not verify the saved sandbox assignment",
  ):
    if marker not in app:
      fail(f"0.4.23 sidebar QoL/sandbox invariant is missing: {marker}")
  for marker in (
    "export function contiguousIdRange",
    "export function reorderVisibleGroupAt",
  ):
    if marker not in read("src/lib/ui.ts"):
      fail(f"0.4.23 ordering helper invariant is missing: {marker}")
  for test_marker in (
    "test_trailing_sidebar_space_is_a_real_drop_at_end_target",
    "test_shift_click_selects_range_for_drag_without_switching_active_service",
    "test_group_drag_preserves_order_and_filtered_slots",
    "test_dragging_selected_rows_keeps_move_cursor_and_persists_once",
    "test_service_settings_has_immediate_sandbox_assignment_list",
    "test_global_sandbox_assignment_does_not_navigate_out_of_settings",
  ):
    if test_marker not in patch_0423:
      fail(f"0.4.23 regression coverage is missing: {test_marker}")

  patch_0424 = read("tools/test_patch_0424.py")
  for marker in (
    'class="service-workspace-search service-sandbox-search"',
    'class="svcarea" role="region" aria-label="Service list drop area"',
    'workspaceIcons: Record<string, string>',
    'function saveManagedWorkspaceIcon(iconUrl: string | null)',
    'assignManagedWorkspaceIconFromService(service)',
    'function portableWorkspace(workspace: Workspace): Workspace',
    'settings.insert(\n        "workspaceIcons".into()',
    'fn feature_0424_settings_validate_workspace_icons()',
  ):
    if marker not in app + api_ts + main_rs:
      fail(f"0.4.24 workspace-icon/settings invariant is missing: {marker}")
  for test_marker in (
    "test_service_sandbox_search_matches_compact_workspace_search_scale",
    "test_sidebar_drop_region_is_accessibility_annotated",
    "test_workspace_icons_are_backend_validated_and_migrate_with_defaults",
    "test_workspace_settings_can_assign_existing_resolved_service_icons",
    "test_workspace_icons_are_visible_in_workspace_surfaces_with_fallback",
    "test_workspace_icons_are_cleaned_up_with_deleted_or_stale_workspaces",
    "test_portable_workspace_exports_embed_the_selected_icon",
    "test_full_backups_already_include_app_settings",
  ):
    if test_marker not in patch_0424:
      fail(f"0.4.24 regression coverage is missing: {test_marker}")

  for marker in (
    '["keybindings", "Keybinds"]',
    '["sandbox", "Sandbox"]',
    'appSettings.theme === "oled"',
    'const MANAGED_SERVICE_PAGE_SIZE = 100;',
    'quickWorkspaceSwitch: "Ctrl+D"',
    'quickServiceSwitch: "Ctrl+S"',
  ):
    if marker not in app + read("src/lib/ui.ts"):
      fail(f"0.4.0 frontend feature invariant is missing: {marker}")
  for marker in (
    'fn sandbox_for_service',
    'fn clear_sandbox',
    'settings.insert("sandboxes".into(), Value::Array(Vec::new()));',
    '"serviceSandboxes".into(),',
  ):
    if marker not in main_rs:
      fail(f"0.4.0 sandbox backend invariant is missing: {marker}")
  for marker in (
    'def build_runtime_handoff(',
    '"--build-handoff"',
    'run-build-handoff.zip',
    'no native runtime is claimed',
  ):
    if marker not in package_release:
      fail(f"explicit non-native runtime handoff invariant is missing: {marker}")
  if "test_build_handoff_is_explicitly_non_native_and_contains_exact_source" not in package_release_test:
    fail("release handoff regression coverage is missing")

  for marker in (
    'Export backup…',
    'Restore backup…',
    'tauridium-backup-',
    'Backups can contain sensitive local service configuration',
  ):
    if marker not in app:
      fail(f"backup UI is missing: {marker}")

  ordering_test = read("tools/test_ordering_ui.py")
  backup_test = read("tools/test_backup.py")
  for marker in (
    'serviceOrder: string[]',
    'workspaceOrder: string[]',
    'invoke("set_service_order", { serviceIds })',
    'invoke("set_workspace_order", { workspaceIds })',
  ):
    if marker not in api_ts:
      fail(f"canonical frontend ordering API is missing: {marker}")
  for marker in (
    'async function reconcileSavedOrders()',
    'setAppSettings({ serviceOrder, workspaceOrder, workspaceLastUsed, workspaceIcons })',
    'setServiceOrder(nextIds)',
    'setWorkspaceOrder(nextIds)',
    'reorderVisibleSubsetAt(previousIds, visibleIds, movingIds[0], target.id, placement)',
    'No services configured',
  ):
    if marker not in app:
      fail(f"service/workspace ordering UI invariant is missing: {marker}")
  sidebar = app.split('<aside class="sidebar">', 1)[-1].split("</aside>", 1)[0]
  if "+ Add a service" in sidebar or "openAppSettings" in sidebar:
    fail("sidebar still consumes service-list space with Add Service or Settings buttons")
  svc_css = app.split(".svcarea {", 1)[-1].split(".account {", 1)[0]
  for marker in ("flex: 1", "min-height: 0", "overflow-y: auto"):
    if marker not in svc_css:
      fail(f"sidebar service list is not dynamically scrollable: {marker}")
  for test_marker in (
    "test_drag_reorder_is_one_atomic_persistence_operation",
    "test_workspace_reorder_uses_same_verified_atomic_order_store",
    "test_sidebar_reclaims_real_estate_and_scrolls_only_when_needed",
    "test_native_tauridium_menu_owns_settings_and_add_service",
    "test_native_services_menu_tracks_actual_services_and_stable_ids",
    "test_native_services_menu_escapes_names_and_has_no_phantom_slots",
  ):
    if test_marker not in ordering_test:
      fail(f"ordering/sidebar regression coverage is missing: {test_marker}")
  for test_marker in (
    "test_backup_schema_is_versioned_and_has_a_migration_floor",
    "test_current_backups_are_sha256_integrity_protected",
    "test_restore_creates_recovery_snapshot_before_mutation",
    "test_restore_is_transactional_and_rolls_back_every_owned_component",
    "test_export_is_fsync_verified_before_replacing_existing_backup",
    "test_interrupted_recipe_transaction_has_startup_recovery",
  ):
    if test_marker not in backup_test:
      fail(f"backup reliability regression coverage is missing: {test_marker}")

  ci = read(".github/workflows/ci.yml")
  release_workflow = read(".github/workflows/release.yml")
  if "branches: [main]" in ci or "branches: [master]" not in ci:
    fail("CI does not target master")
  if "-D warnings" not in ci or "--all-features" not in ci:
    fail("CI Rust gates are weaker than release policy")
  for marker in (
    "cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --all-features --locked -- -D warnings",
    "cargo test --manifest-path src-tauri/Cargo.toml --all-features --locked",
    "cargo check --manifest-path src-tauri/Cargo.toml --all-targets --all-features --locked",
  ):
    if marker not in ci:
      fail(f"CI Cargo gate can ignore Cargo.lock: {marker}")
  if "dtolnay/rust-toolchain@stable" in ci + release_workflow:
    fail("CI/release workflows must not float Rust stable; use pinned Rust 1.97.1")
  if ci.count("dtolnay/rust-toolchain@1.97.1") < 3:
    fail("CI does not pin every Rust job to Rust 1.97.1")
  if release_workflow.count("dtolnay/rust-toolchain@1.97.1") < 2:
    fail("tagged release workflow does not pin Rust 1.97.1 in test/build jobs")
  release_test_block = release_workflow.split("test:\n", 1)[-1].split("create-release:", 1)[0]
  for marker in (
    "python3 -m unittest discover -s tools -p 'test_*.py'",
    "npm run check",
    "npm test",
    "cargo fmt --manifest-path src-tauri/Cargo.toml --all -- --check",
    "cargo check --manifest-path src-tauri/Cargo.toml --all-targets --all-features --locked",
    "cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --all-features --locked -- -D warnings",
    "cargo test --manifest-path src-tauri/Cargo.toml --all-features --locked",
  ):
    if marker not in release_test_block:
      fail(f"tagged release can be created without required gate: {marker}")
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

  readme = read("README.md")
  for marker in (
    f'git tag -a v{version} -m "Tauridium {version}"',
    f'git push origin v{version}',
    f'tauridium-{version}-run-win-x64.zip',
  ):
    if marker not in readme:
      fail(f"README release example differs from release version: {marker}")

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
