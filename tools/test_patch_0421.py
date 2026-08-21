#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.4.21 Windows HTML5 sidebar dragging."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
TAURI_CONFIG = json.loads((ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))


class Patch0421Tests(unittest.TestCase):
  def test_main_shell_disables_tauri_native_drag_drop_interception(self) -> None:
    windows = TAURI_CONFIG["app"]["windows"]
    main = next(window for window in windows if window.get("label") == "main")
    self.assertIs(main.get("dragDropEnabled"), False)

  def test_sidebar_reorder_remains_html5_drag_drop_with_move_semantics(self) -> None:
    row = APP.split("{#snippet row(s: Service)}", 1)[1].split("{/snippet}", 1)[0]
    start = APP.split("function onDragStart", 1)[1].split("function onDragOver", 1)[0]
    over = APP.split("function onDragOver", 1)[1].split("function onDragLeave", 1)[0]
    drop = APP.split("async function onDrop", 1)[1].split("function openServiceSettings", 1)[0]

    self.assertIn("draggable={appSettings.sidebarServiceDragReorder && !serviceOrderBusy}", row)
    self.assertIn('e.dataTransfer.effectAllowed = "move"', start)
    self.assertIn('e.dataTransfer.setData("text/plain", s.id)', start)
    self.assertIn("e.preventDefault()", over)
    self.assertIn('e.dataTransfer.dropEffect = "move"', over)
    self.assertIn("e.preventDefault()", drop)

  def test_sidebar_ordering_does_not_depend_on_tauri_native_file_drop_events(self) -> None:
    self.assertNotIn("onDragDropEvent", APP)
    self.assertNotIn("tauri://drag", APP)


if __name__ == "__main__":
  unittest.main()
