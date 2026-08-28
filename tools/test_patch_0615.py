#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.6.15 updater diagnostics and durable icon caching."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPDATER = (ROOT / "src/lib/updater.ts").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
ICONS = (ROOT / "src-tauri/src/icons.rs").read_text(encoding="utf-8")
UPDATER_TEST = (ROOT / "src/lib/updater.test.ts").read_text(encoding="utf-8")


class Patch0615Tests(unittest.TestCase):
  def test_updater_failures_reach_developer_console_and_audit_log(self) -> None:
    self.assertIn('console.error(`[Tauridium updater] ${action} failed: ${message}`, error);', UPDATER)
    self.assertIn('await invoke("record_updater_error", { action, message });', UPDATER)
    self.assertIn('await reportUpdaterError("check", error);', UPDATER)
    self.assertIn('await reportUpdaterError("install", error);', UPDATER)
    self.assertIn('fn record_updater_error(app: AppHandle, action: String, message: String)', MAIN)
    self.assertIn('"error",\n        "updater",', MAIN)
    self.assertIn('format!("Update {action} failed: {message}")', MAIN)
    self.assertIn('record_updater_error,', MAIN)

  def test_updater_failure_logging_never_masks_original_failure(self) -> None:
    self.assertGreaterEqual(UPDATER.count("throw error;"), 2)
    self.assertIn("Unable to persist updater failure to the audit log", UPDATER)
    self.assertIn("keeps the updater failure visible even if audit persistence also fails", UPDATER_TEST)

  def test_cached_service_icons_return_before_network_discovery(self) -> None:
    cache_read = ICONS.index("let previous = read_cache(&path);")
    cached_return = ICONS.index("return Ok(ServiceIconLoad::Cached(cached));")
    network_parse = ICONS.index("let parsed = Url::parse(page_url)", cache_read)
    network_discovery = ICONS.index("match discover_icon(client, &parsed).await", network_parse)
    self.assertLess(cache_read, cached_return)
    self.assertLess(cached_return, network_parse)
    self.assertLess(network_parse, network_discovery)
    self.assertIn("Ok(ServiceIconLoad::Fetched(icon))", ICONS)

  def test_audit_records_only_real_icon_network_fetches(self) -> None:
    icon_command = MAIN.split("async fn get_service_icon", 1)[1].split("fn copy_service_icon_cache", 1)[0]
    self.assertIn("Ok(icons::ServiceIconLoad::Fetched(_)) => audit::best_effort", icon_command)
    self.assertNotIn("ServiceIconLoad::Cached(_) => audit::best_effort", icon_command)
    self.assertIn('"Website icon fetched and cached"', icon_command)
    self.assertIn('"Website icon refetched and cached"', icon_command)


if __name__ == "__main__":
  unittest.main()
