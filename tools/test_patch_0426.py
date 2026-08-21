#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.4.26 service compatibility and settings polish."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
CARGO = (ROOT / "src-tauri/Cargo.toml").read_text(encoding="utf-8")
CARGO_LOCK = (ROOT / "src-tauri/Cargo.lock").read_text(encoding="utf-8")
WRY_WEBVIEW2 = (ROOT / "vendor/wry/src/webview2/mod.rs").read_text(encoding="utf-8")


class Patch0426Tests(unittest.TestCase):
  def test_windows_remote_webviews_allow_turnstile_storage_and_use_native_user_agent(self) -> None:
    self.assertIn("options.set_enable_tracking_prevention(!is_remote_http);", WRY_WEBVIEW2)
    self.assertIn('url.starts_with("https://") || url.starts_with("http://")', WRY_WEBVIEW2)
    self.assertIn("else if cfg!(windows) {", MAIN)
    self.assertIn("None", MAIN.split("else if cfg!(windows) {", 1)[1].split("} else {", 1)[0])
    self.assertIn("if let Some(ua) = ua.as_deref()", MAIN)
    service_builder = MAIN.split("async fn create_service_webview", 1)[1].split("async fn show_service", 1)[0]
    self.assertNotIn(".user_agent(&ua)", service_builder)

  def test_rfd_features_match_dialog_plugin_and_keep_windows_locked_resolution_stable(self) -> None:
    self.assertIn(
      'rfd = { version = "0.16", default-features = false, features = ["common-controls-v6"] }',
      CARGO,
    )
    tauridium = CARGO_LOCK.split('name = "tauridium"', 1)[1].split("[[package]]", 1)[0]
    self.assertIn('"rfd",', tauridium)

  def test_sidebar_unread_badge_respects_persisted_service_badge_preference(self) -> None:
    row = APP.split("{#snippet row(s: Service)}", 1)[1].split("{/snippet}", 1)[0]
    self.assertIn("s.isBadgeEnabled !== false", row)
    self.assertIn('(unreadMap[s.id] ?? 0) > 0', row)
    self.assertIn('toggle("Unread badge"', APP)
    self.assertIn("isBadgeEnabled: s.isBadgeEnabled", APP)

  def test_custom_url_placeholder_toggle_has_specific_customer_facing_label(self) -> None:
    section = APP.split('<div class="set-title">Custom URL placeholders</div>', 1)[1].split('{@render toggle("Notifications"', 1)[0]
    self.assertIn("Enable custom URL placeholders for this service", section)
    self.assertIn("Custom URL placeholders enabled globally", section)
    self.assertNotIn(">Enable for this service<", section)

  def test_per_service_workspace_and_sandbox_assignments_show_green_saved_toast(self) -> None:
    self.assertGreaterEqual(APP.count('showToast("Saved", "success")'), 3)
    workspace_toggle = APP.split("async function toggleCurrentServiceWorkspace", 1)[1].split("async function createWorkspaceForCurrentService", 1)[0]
    self.assertIn('showToast("Saved", "success")', workspace_toggle)
    workspace_create = APP.split("async function createWorkspaceForCurrentService", 1)[1].split("function filteredServiceSandboxes", 1)[0]
    self.assertIn('showToast("Saved", "success")', workspace_create)
    sandbox = APP.split("async function assignServiceSandbox", 1)[1].split("async function", 1)[0]
    self.assertIn("showServiceSettingsSaved(serviceId)", sandbox)
    helper = APP.split("function showServiceSettingsSaved", 1)[1].split("function preferredWebsiteIcon", 1)[0]
    self.assertIn('view === "svcSettings"', helper)
    self.assertIn('showToast("Saved", "success")', helper)
    self.assertIn('class:success={toastTone === "success"}', APP)
    self.assertIn('.toast.success { background: #187a45;', APP)


if __name__ == "__main__":
  unittest.main()
