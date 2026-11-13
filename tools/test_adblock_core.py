#!/usr/bin/env python3
"""Static regressions for ad and tracker blocking.

The behaviour itself is covered by the Rust unit tests in src-tauri/src/adblock*
and the Vitest cases in src/lib/adblock.test.ts. These checks pin the wiring and
the safety properties that are easy to lose in a refactor.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUST_DIR = ROOT / "src-tauri/src"
ADBLOCK_SOURCES = [RUST_DIR / "adblock.rs", *sorted((RUST_DIR / "adblock").glob("*.rs"))]
SETTING_KEYS = ("adblockEnabled", "adblockLists", "adblockCustomLists", "adblockAllowlist", "serviceAdblock")
COMMANDS = ("adblock_get_state", "adblock_update_lists", "adblock_check_list", "adblock_normalize_sites")


def production_source(path: Path) -> str:
  """Source without its unit-test module."""
  text = path.read_text(encoding="utf-8")
  return text.split("#[cfg(test)]", 1)[0]


class AdblockWiringTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.main = (RUST_DIR / "main.rs").read_text(encoding="utf-8")
    cls.api = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
    cls.app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
    cls.permissions = (ROOT / "src-tauri/permissions/application.toml").read_text(encoding="utf-8")
    cls.cargo = (ROOT / "src-tauri/Cargo.toml").read_text(encoding="utf-8")

  def test_settings_have_defaults_validation_and_typed_fields(self) -> None:
    for key in SETTING_KEYS:
      with self.subTest(key=key):
        self.assertRegex(self.main, rf'settings\.insert\(\s*"{key}"\.into\(\)')
        self.assertIn(f"{key}:", self.api)
        self.assertIn(key, self.app)
    self.assertIn("adblock::validate_settings(object)?;", self.main)

  def test_commands_are_registered_and_allowlisted_for_the_trusted_shell(self) -> None:
    for command in COMMANDS:
      with self.subTest(command=command):
        self.assertIn(f"fn {command}(", self.main)
        self.assertIn(f"            {command},\n", self.main)
        self.assertIn(f'"{command}"', self.permissions)
        self.assertIn(f'invoke("{command}"', self.api)

  def test_blocking_follows_settings_changes_restores_and_webview_creation(self) -> None:
    self.assertIn("adblock::patch_affects(&patch)", self.main)
    self.assertIn("adblock::runtime::settings_changed(&app);", self.main)
    self.assertIn("adblock::runtime::start(app.handle());", self.main)
    self.assertIn("adblock::runtime::apply_service(win.app_handle(), service_id, true);", self.main)

  def test_old_backups_keep_current_blocking_settings(self) -> None:
    self.assertIn("let app_settings = merge_app_settings_value(&document.app_settings())?;", self.main)
    self.assertIn("adblock::carry_forward_missing(", self.main)

  def test_service_delete_and_duplicate_clean_and_copy_overrides(self) -> None:
    self.assertIn("delete serviceAdblock[s.id];", self.app)
    self.assertIn("copyOwnEntry(serviceAdblock, service.id, newId);", self.app)
    self.assertIn("serviceAdblock: previousAdblock,", self.app)

  def test_controls_are_hidden_where_the_engine_is_unsupported(self) -> None:
    self.assertIn("adblockState && !adblockState.engine.supported", self.app)
    self.assertIn("{#if adblockState?.engine.supported}", self.app)
    self.assertIn("Ad blocking is not available on this platform yet.", self.app)

  def test_settings_changes_show_the_saved_confirmation(self) -> None:
    # Every control saves through saveAppSetting, which shows the green toast.
    for marker in ('saveAppSetting("adblockLists"', 'saveAppSetting("adblockAllowlist"', 'saveAppSetting("serviceAdblock"', '"adblockEnabled"'):
      self.assertIn(marker, self.app)

  def test_linux_ffi_dependency_is_pinned_and_featureless(self) -> None:
    self.assertRegex(self.cargo, r'webkit2gtk-sys = \{ version = "=2\.0\.2", default-features = false, features = \["v2_40"\] \}')
    self.assertRegex(self.cargo, r'adblock = \{ version = "=0\.13\.5", default-features = false')


class AdblockSafetyTests(unittest.TestCase):
  def test_unsafe_code_is_confined_to_the_linux_filter_module(self) -> None:
    for path in ADBLOCK_SOURCES:
      with self.subTest(path=path.name):
        has_unsafe = re.search(r"\bunsafe\b", production_source(path)) is not None
        self.assertEqual(has_unsafe, path.name == "linux_filter.rs")
    ffi = production_source(RUST_DIR / "adblock/linux_filter.rs")
    self.assertEqual(ffi.count("unsafe {") + ffi.count("unsafe fn") + ffi.count("unsafe extern"), ffi.count("SAFETY:") + ffi.count("# Safety") + ffi.count("unsafe extern"))

  def test_only_the_list_downloader_touches_the_network(self) -> None:
    for path in ADBLOCK_SOURCES:
      with self.subTest(path=path.name):
        uses_network = "reqwest" in production_source(path) or "http_security" in production_source(path)
        self.assertEqual(uses_network, path.name == "lists.rs")

  def test_downloads_pin_checked_addresses_and_follow_redirects_manually(self) -> None:
    lists = production_source(RUST_DIR / "adblock/lists.rs")
    for marker in ("resolve_public(", "resolve_to_addrs(", "redirect::Policy::none()", "MAX_REDIRECTS", "validate_list_url(next.as_str())", "is_public_ip("):
      self.assertIn(marker, lists)

  def test_nothing_in_the_feature_reports_browsing_activity(self) -> None:
    for path in ADBLOCK_SOURCES:
      text = production_source(path)
      for forbidden in (".post(", "multipart", "navigator.sendBeacon"):
        self.assertNotIn(forbidden, text, f"{path.name} must not send data anywhere")

  def test_cosmetic_and_scriptlet_rules_stay_out_of_this_release(self) -> None:
    compile_source = production_source(RUST_DIR / "adblock/compile.rs")
    self.assertIn("RuleTypes::NetworkOnly", compile_source)
    self.assertNotIn("CosmeticOnly", compile_source)

  def test_smoke_test_covers_blocking_persistence_and_offline_behaviour(self) -> None:
    smoke = (ROOT / "tools/adblock_smoke.py").read_text(encoding="utf-8")
    for case in ("block", "cold", "off", "service", "allowlist", "restart", "offline"):
      self.assertIn(f'"{case}"', smoke)
    app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
    self.assertIn("supportsCounters", app)
    self.assertIn("Blocked-request counts are not shown", app)
    self.assertIn("test-adblock:", (ROOT / "justfile").read_text(encoding="utf-8"))

  def test_docs_and_changelog_describe_the_feature_and_its_platform_limits(self) -> None:
    docs = (ROOT / "docs/ADBLOCK.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    for marker in ("Linux only", "never leave the device", "150,000", "no blocked-request counter", "Windows and macOS"):
      self.assertIn(marker.lower(), docs.lower())
    self.assertIn("ad and tracker blocking on Linux", changelog)


if __name__ == "__main__":
  unittest.main()
