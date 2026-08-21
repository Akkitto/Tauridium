#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.4.20 sidebar drag ordering."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
UI = (ROOT / "src/lib/ui.ts").read_text(encoding="utf-8")
UI_TEST = (ROOT / "src/lib/ui.test.ts").read_text(encoding="utf-8")
RUST = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")


class Patch0420Tests(unittest.TestCase):
  def test_drag_reordering_setting_is_default_on_typed_and_validated(self) -> None:
    self.assertIn("sidebarServiceDragReorder: boolean;", API)
    self.assertIn("sidebarServiceDragReorder: true,", APP)
    self.assertIn('settings.insert("sidebarServiceDragReorder".into(), true.into());', RUST)
    validation = RUST.split("fn validate_app_settings_value", 1)[1].split("fn merge_app_settings_value", 1)[0]
    self.assertIn('"sidebarServiceDragReorder",', validation)
    self.assertIn("sidebar_service_drag_reorder_defaults_on_and_preserves_saved_opt_out", RUST)

  def test_advanced_toggle_controls_only_sidebar_dragging(self) -> None:
    advanced = APP.split('{:else if settingsTab === "advanced"}', 1)[1].split('{:else if settingsTab === "updates"}', 1)[0]
    self.assertIn("Sidebar service ordering", advanced)
    self.assertIn("Drag to reorder services", advanced)
    self.assertIn('"sidebarServiceDragReorder", appSettings.sidebarServiceDragReorder', advanced)
    row = APP.split("{#snippet row(s: Service)}", 1)[1].split("{/snippet}", 1)[0]
    self.assertIn("draggable={appSettings.sidebarServiceDragReorder && !serviceOrderBusy}", row)
    self.assertNotIn('draggable="true"', row)
    self.assertIn("class:draggable={appSettings.sidebarServiceDragReorder && !serviceOrderBusy}", row)

  def test_drag_handlers_are_gated_and_persist_only_on_drop(self) -> None:
    persist = APP.split("async function persistServiceIds", 1)[1].split("async function moveService", 1)[0]
    start = APP.split("function onDragStart", 1)[1].split("function onDragOver", 1)[0]
    over = APP.split("function onDragOver", 1)[1].split("function onDragLeave", 1)[0]
    drop = APP.split("async function persistServiceDrop", 1)[1].split("async function onServiceAreaDrop", 1)[0]
    self.assertIn("if (serviceOrderBusy) return;", persist)
    self.assertIn("serviceOrderBusy = true;", persist)
    self.assertIn("serviceOrderBusy = false;", persist)
    self.assertEqual(persist.count("setServiceOrder(nextIds)"), 1)
    self.assertIn("if (!appSettings.sidebarServiceDragReorder || serviceOrderBusy)", start)
    self.assertIn('e.dataTransfer.setData("text/plain", s.id)', start)
    self.assertIn("!appSettings.sidebarServiceDragReorder", over)
    self.assertIn('e.dataTransfer.dropEffect = "move"', over)
    self.assertIn('e.clientY < rect.top + rect.height / 2 ? "before" : "after"', over)
    self.assertNotIn("setServiceOrder", start + over)
    final_drop = APP.split("async function onDrop", 1)[1].split("function openServiceSettings", 1)[0]
    self.assertIn("if (!appSettings.sidebarServiceDragReorder || serviceOrderBusy)", final_drop)
    self.assertIn("reorderVisibleSubsetAt(previousIds, visibleIds, movingIds[0], target.id, placement)", drop)
    self.assertIn("reorderVisibleGroupAt(previousIds, visibleIds, movingIds, target.id, placement)", drop)
    self.assertIn("await persistServiceIds(nextIds, previousIds)", drop)

  def test_reorder_helper_is_stale_safe_and_preserves_filtered_slots(self) -> None:
    helper = UI.split("export function reorderVisibleSubsetAt", 1)[1].split("export function reorderVisibleSubset(", 1)[0]
    self.assertIn("fullSet.size !== fullIds.length", helper)
    self.assertIn("seenVisible", helper)
    self.assertIn('placement === "after" ? targetIndex + 1 : targetIndex', helper)
    self.assertIn("fullIds.map", helper)
    self.assertIn("supports explicit before/after sidebar drop placement without disturbing hidden slots", UI_TEST)
    self.assertIn("treats stale or duplicate drag-order input as a safe no-op", UI_TEST)

  def test_drop_indicator_matches_before_after_placement(self) -> None:
    row = APP.split("{#snippet row(s: Service)}", 1)[1].split("{/snippet}", 1)[0]
    self.assertIn('dragPlacement === "before"', row)
    self.assertIn('dragPlacement === "after"', row)
    css = APP.split(".srow-wrap {", 1)[1].split("\n  .srow { width", 1)[0]
    self.assertIn(".srow-wrap.drag-before::before", css)
    self.assertIn(".srow-wrap.drag-after::after", css)
    self.assertIn("pointer-events: none", css)

  def test_backend_serializes_settings_transactions_with_order_writes(self) -> None:
    state = RUST.split("struct AppState", 1)[1].split("}", 1)[0]
    self.assertIn("settings_write: Mutex<()>", state)
    order = RUST.split("fn persist_order_setting", 1)[1].split("#[tauri::command]", 1)[0]
    settings = RUST.split("fn set_app_settings", 1)[1].split("#[tauri::command]", 1)[0]
    restore = RUST.split("fn perform_restore_backup", 1)[1].split("fn restore_backup", 1)[0]
    self.assertIn("state.settings_write.lock().unwrap()", order)
    self.assertIn("state.settings_write.lock().unwrap()", settings)
    self.assertIn("state.settings_write.lock().unwrap()", restore)

  def test_disabling_drag_reorder_clears_in_progress_drag_state(self) -> None:
    save = APP.split("async function saveAppSetting", 1)[1].split("async function moveManagedService", 1)[0]
    self.assertIn('key === "sidebarServiceDragReorder" && value === false', save)
    self.assertIn("clearServiceDragState()", save)


if __name__ == "__main__":
  unittest.main()
