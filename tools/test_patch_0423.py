#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.4.23 sidebar QoL and sandbox assignment."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
UI = (ROOT / "src/lib/ui.ts").read_text(encoding="utf-8")
UI_TEST = (ROOT / "src/lib/ui.test.ts").read_text(encoding="utf-8")


class Patch0423Tests(unittest.TestCase):
  def test_trailing_sidebar_space_is_a_real_drop_at_end_target(self) -> None:
    sidebar = APP.split('<div class="svcarea"', 1)[1].split('<div class="count">', 1)[0]
    trailing = APP.split("function setTrailingDropTarget", 1)[1].split("function onServiceAreaDragOver", 1)[0]
    self.assertIn("ondragover={onServiceAreaDragOver}", sidebar)
    self.assertIn("ondrop={onServiceAreaDrop}", sidebar)
    self.assertIn("e.clientY < rect.bottom", trailing)
    self.assertIn("visibleServices.at(-1)", trailing)
    self.assertIn('dragPlacement = "after"', trailing)
    self.assertIn('e.dataTransfer.dropEffect = "move"', trailing)

  def test_shift_click_selects_range_for_drag_without_switching_active_service(self) -> None:
    click = APP.split("function onServiceRowClick", 1)[1].split("function retryActiveService", 1)[0]
    row = APP.split("{#snippet row(s: Service)}", 1)[1].split("{/snippet}", 1)[0]
    self.assertIn("event.shiftKey", click)
    self.assertIn("contiguousIdRange(visibleIds, anchorId, service.id)", click)
    self.assertIn("serviceDragSelection = range", click)
    self.assertIn("return;", click)
    self.assertIn("onclick={(e) => onServiceRowClick(e, s)}", row)
    self.assertIn("class:drag-selected", row)

  def test_group_drag_preserves_order_and_filtered_slots(self) -> None:
    self.assertIn("export function reorderVisibleGroupAt", UI)
    helper = UI.split("export function reorderVisibleGroupAt", 1)[1].split("export function reorderVisibleSubset(", 1)[0]
    self.assertIn("const selected = subset.filter", helper)
    self.assertIn("remaining.splice(insertIndex, 0, ...selected)", helper)
    self.assertIn("fullIds.map", helper)
    self.assertIn("moves a selected service group as one stable block while preserving hidden slots", UI_TEST)
    self.assertIn("treats drops onto the selected drag group as safe no-ops", UI_TEST)

  def test_dragging_selected_rows_keeps_move_cursor_and_persists_once(self) -> None:
    over = APP.split("function onDragOver", 1)[1].split("function onDragLeave", 1)[0]
    persist = APP.split("async function persistServiceDrop", 1)[1].split("async function onServiceAreaDrop", 1)[0]
    self.assertIn("dragIds.includes(s.id)", over)
    self.assertIn("e.preventDefault()", over)
    self.assertIn('e.dataTransfer.dropEffect = "move"', over)
    self.assertIn("reorderVisibleGroupAt", persist)
    self.assertEqual(persist.count("persistServiceIds(nextIds, previousIds)"), 1)

  def test_service_settings_has_immediate_sandbox_assignment_list(self) -> None:
    service_settings = APP.split('{:else if view === "svcSettings" && settingsSvc}', 1)[1].split('{:else if view === "add"}', 1)[0]
    self.assertIn('<div class="set-title">Sandbox</div>', service_settings)
    self.assertIn("Sandbox assignment", service_settings)
    self.assertIn('type="radio"', service_settings)
    self.assertIn("serviceSandboxRows", service_settings)
    self.assertIn("assignServiceSandbox(settingsServiceId, sandbox.id)", service_settings)
    self.assertIn("Shared sandboxes are created and managed globally", service_settings)

  def test_global_sandbox_assignment_does_not_navigate_out_of_settings(self) -> None:
    assign = APP.split("async function assignServiceSandbox", 1)[1].split("async function clearSandboxGroup", 1)[0]
    self.assertIn('if (view === "service" && activeId === serviceId)', assign)
    self.assertIn("await closeService(serviceId)", assign)
    self.assertIn("Tauridium could not verify the saved sandbox assignment", assign)
    self.assertNotIn('view = "service"', assign)
    sandbox_tab = APP.split('{:else if settingsTab === "sandbox"}', 1)[1].split('{:else if settingsTab === "privacy"}', 1)[0]
    self.assertIn("disabled={sandboxAssignmentBusy}", sandbox_tab)


if __name__ == "__main__":
  unittest.main()
