#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.7.19 incremental Audit Log paging."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
AUDIT = (ROOT / "src-tauri" / "src" / "audit.rs").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")


class Patch0719Tests(unittest.TestCase):
  def test_initial_audit_load_is_bounded_to_named_page_size(self) -> None:
    for marker in (
      "const AUDIT_PAGE_SIZE = 100;",
      "getAuditLogPage(null, AUDIT_PAGE_SIZE)",
      "pub(crate) const AUDIT_PAGE_DEFAULT: usize = 100;",
      "pub(crate) const AUDIT_PAGE_MAX: usize = 500;",
    ):
      self.assertIn(marker, APP if "AUDIT_PAGE_SIZE" in marker or "getAuditLogPage" in marker else AUDIT)
    self.assertNotIn("getAuditLog(5000)", APP)
    self.assertNotIn("loads the latest 5,000 events", APP)

  def test_backend_uses_reverse_bounded_io_for_view_pages(self) -> None:
    for marker in (
      "fn read_reverse_entries(",
      "SeekFrom::Start",
      "AUDIT_REVERSE_CHUNK_BYTES",
      "fn read_page_from_path(",
      "fn audit_file_fingerprint(",
      "URL_SAFE_NO_PAD",
    ):
      self.assertIn(marker, AUDIT)
    page_reader = AUDIT.split("fn read_page_from_path(", 1)[1].split("fn rotate_if_needed", 1)[0]
    self.assertNotIn("read_to_string", page_reader)

  def test_full_history_export_still_uses_complete_retained_reader(self) -> None:
    export = AUDIT.split("pub(crate) fn export(", 1)[1].split("pub(crate) fn clear(", 1)[0]
    self.assertIn("let entries = read_all_entries(app)?;", export)

  def test_cursor_is_opaque_and_frontend_does_not_receive_paths(self) -> None:
    self.assertIn('return invoke("get_audit_log_page", { cursor, limit });', API)
    self.assertIn("struct AuditCursor", AUDIT)
    self.assertNotIn("PathBuf", API.split("export interface AuditLogPage", 1)[1].split("export function exportAuditLog", 1)[0])
    self.assertIn("generation > AUDIT_ROTATIONS", AUDIT)

  def test_incremental_ui_uses_intersection_observer_and_manual_fallback(self) -> None:
    for marker in (
      "new IntersectionObserver(",
      'rootMargin: "0px 0px 180px 0px"',
      "use:auditLoadMoreObserver",
      "Load older events",
      "if (auditBusy || !auditHasMore || !auditCursor) return;",
    ):
      self.assertIn(marker, APP)

  def test_filtering_only_applies_to_loaded_history(self) -> None:
    self.assertIn(
      "Filters apply to loaded events. Load older events to expand the searchable history.",
      APP,
    )
    self.assertIn("&& !auditQuery.trim()", APP)
    self.assertIn('&& auditLevel === "all"', APP)

  def test_reenter_reuses_loaded_state_and_refresh_resets_cursor(self) -> None:
    self.assertIn(
      'if (settingsTab === "audit" && !auditInitialized) void refreshAuditLog();',
      APP,
    )
    refresh = APP.split("async function refreshAuditLog()", 1)[1].split("async function loadOlderAuditLog()", 1)[0]
    for marker in (
      "auditEntries = page.entries;",
      "auditCursor = page.nextCursor;",
      "auditHasMore = page.hasMore;",
      "auditInitialized = true;",
    ):
      self.assertIn(marker, refresh)

  def test_clear_resets_cached_pagination_before_reloading_tail(self) -> None:
    clear = APP.split("async function doClearAuditLog()", 1)[1].split("function selectSettingsTab", 1)[0]
    for marker in (
      "auditEntries = [];",
      "auditCursor = null;",
      "auditHasMore = false;",
      "auditInitialized = false;",
      "const requestGeneration = ++auditRequestGeneration;",
      "await refreshAuditLog();",
    ):
      self.assertIn(marker, clear)

  def test_rendering_avoids_eager_layout_for_all_loaded_rows(self) -> None:
    for marker in (
      "content-visibility: auto;",
      "contain-intrinsic-size: 88px;",
      "scrollbar-gutter: stable;",
    ):
      self.assertIn(marker, APP)

  def test_new_tauri_page_command_is_registered_without_removing_legacy_reader(self) -> None:
    for marker in ("fn get_audit_log(", "fn get_audit_log_page(", "get_audit_log_page,"):
      self.assertIn(marker, MAIN)


if __name__ == "__main__":
  unittest.main()
