#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.6.4 workspace quick-switcher highlighting."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")


class Patch0604Tests(unittest.TestCase):
  def test_current_workspace_is_marked_independently_from_keyboard_cursor(self) -> None:
    switcher = APP.split('{#if quickSwitcherMode}', 1)[1].split('{#snippet row', 1)[0]
    self.assertIn('class:active={index === quickSwitcherIndex}', switcher)
    self.assertIn(
      'class:current={quickSwitcherMode === "workspace" && item.id === (activeWorkspace ?? "__all__")}',
      switcher,
    )
    self.assertIn(
      'aria-current={quickSwitcherMode === "workspace" && item.id === (activeWorkspace ?? "__all__") ? "true" : undefined}',
      switcher,
    )

  def test_all_services_is_highlighted_when_no_workspace_is_active(self) -> None:
    self.assertIn(
      'return [{ id: "__all__", name: "All services" }, ...quickSwitcherWorkspaces]',
      APP,
    )
    self.assertIn('item.id === (activeWorkspace ?? "__all__")', APP)

  def test_current_workspace_reuses_selected_service_accent_language(self) -> None:
    self.assertIn('.srow.active { background: var(--accent); color: var(--accent-fg); }', APP)
    self.assertIn(
      '.quick-switcher-item.current { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }',
      APP,
    )
    self.assertIn(
      '.quick-switcher-item.current small { color: var(--accent-fg); opacity: 0.78; }',
      APP,
    )


if __name__ == "__main__":
  unittest.main()
