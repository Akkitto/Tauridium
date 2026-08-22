#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.6.6 quick-switcher behavior and Windows title guidance."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")


class Patch0606Tests(unittest.TestCase):
  def test_current_service_reuses_workspace_accent_highlight(self) -> None:
    switcher = APP.split('{#if quickSwitcherMode}', 1)[1].split('{#snippet row', 1)[0]
    self.assertIn(
      '(quickSwitcherMode === "service" && item.id === activeId)',
      switcher,
    )
    self.assertIn('class:current=', switcher)
    self.assertIn('aria-current=', switcher)
    self.assertIn(
      '.quick-switcher-item.current { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }',
      APP,
    )

  def test_reopening_same_quick_switcher_toggles_it_closed(self) -> None:
    function = APP.split('function openQuickSwitcher(mode: QuickSwitcherMode)', 1)[1].split('function closeQuickSwitcher', 1)[0]
    self.assertIn('if (quickSwitcherMode === mode)', function)
    self.assertIn('closeQuickSwitcher();', function)
    self.assertIn('lastQuickSwitcherShortcutToggle.mode === mode', function)
    self.assertIn('now - lastQuickSwitcherShortcutToggle.at < 120', function)
    self.assertIn('case "quickWorkspaceSwitch": openQuickSwitcher("workspace"); break;', APP)
    self.assertIn('case "quickServiceSwitch": openQuickSwitcher("service"); break;', APP)

  def test_escape_and_configured_shortcut_close_modal_from_search_input(self) -> None:
    keydown = APP.split('function handleGlobalKeydown(event: KeyboardEvent)', 1)[1].split('async function createSandboxGroup', 1)[0]
    self.assertIn('if (quickSwitcherMode)', keydown)
    self.assertIn('if (event.key === "Escape")', keydown)
    self.assertIn('closeQuickSwitcher();', keydown)
    self.assertIn('handleQuickSwitcherToggleShortcut(event)', keydown)

    toggle = APP.split('function handleQuickSwitcherToggleShortcut(event: KeyboardEvent)', 1)[1].split('function executeShortcutAction', 1)[0]
    self.assertIn('? "quickWorkspaceSwitch"', toggle)
    self.assertIn(': "quickServiceSwitch";', toggle)
    self.assertIn('bindingStrokes(appSettings.keybindings[action] ?? "")', toggle)
    self.assertIn('strokes.length === 1 && strokes[0] === stroke', toggle)
    self.assertIn('strokes.length === 2', toggle)
    self.assertIn('event.stopPropagation();', toggle)
    self.assertIn('openQuickSwitcher(mode);', toggle)

  def test_windows_taskbar_limit_is_documented_without_risky_workaround(self) -> None:
    section = APP.split('id="settings-appearance-titles"', 1)[1].split('id="settings-appearance-sidebar"', 1)[0]
    self.assertIn(
      'Windows taskbar buttons always mirror the native window title; independent taskbar titles are unsupported on Windows.',
      section,
    )
    self.assertIn('Windows taskbar buttons use the native window title', MAIN)
    self.assertIn('.set_title(&window_title)', MAIN)
    self.assertNotIn('WS_EX_TOOLWINDOW', MAIN)
    self.assertNotIn('SetWindowLongPtr', MAIN)


if __name__ == "__main__":
  unittest.main()
