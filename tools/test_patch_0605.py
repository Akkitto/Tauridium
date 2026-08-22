#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.6.5 native title presentation settings."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
TITLE_TEMPLATE = (ROOT / "src/lib/title-template.ts").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")


class Patch0605Tests(unittest.TestCase):
  def test_title_settings_have_requested_safe_defaults(self) -> None:
    for marker in (
      "showWorkspaceInWindowTitle: boolean;",
      "showWorkspaceInTaskbarTitle: boolean;",
      "customTitleTemplatesEnabled: boolean;",
      "windowTitleTemplate: string;",
      "taskbarTitleTemplate: string;",
      "showWorkspaceInWindowTitle: true,",
      "showWorkspaceInTaskbarTitle: false,",
      "customTitleTemplatesEnabled: false,",
      'settings.insert("showWorkspaceInWindowTitle".into(), true.into());',
      'settings.insert("showWorkspaceInTaskbarTitle".into(), false.into());',
      'settings.insert("customTitleTemplatesEnabled".into(), false.into());',
    ):
      self.assertIn(marker, APP + API + MAIN)

  def test_title_templates_support_app_workspace_and_service_variables(self) -> None:
    for marker in (
      'DEFAULT_WINDOW_TITLE_TEMPLATE = "{app} ~ {workspace}"',
      'DEFAULT_TASKBAR_TITLE_TEMPLATE = "{app} ~ {workspace}"',
      "app: /\\{app\\}/g",
      "workspace: /\\{workspace\\}/g",
      "service: /\\{service\\}/g",
      "renderTitleTemplate",
    ):
      self.assertIn(marker, TITLE_TEMPLATE)
    self.assertIn('service: activeService ? serviceLabel(activeService) : "No service"', APP)
    self.assertIn('workspace: activeWorkspaceName', APP)

  def test_native_titles_update_reactively_and_use_backend_boundary(self) -> None:
    self.assertIn("$effect(() => {\n    syncPresentationTitles();\n  });", APP)
    self.assertIn("setPresentationTitles(windowTitle, taskbarTitle)", APP)
    self.assertIn('return invoke("set_presentation_titles", { windowTitle, taskbarTitle });', API)
    self.assertIn("fn set_presentation_titles(", MAIN)
    self.assertIn('.set_title(&window_title)', MAIN)
    self.assertIn('TrayIconBuilder::with_id("main-tray")', MAIN)
    self.assertIn('app.tray_by_id("main-tray")', MAIN)

  def test_appearance_exposes_three_title_toggles_and_advanced_templates(self) -> None:
    section = APP.split('id="settings-appearance-titles"', 1)[1].split('id="settings-appearance-sidebar"', 1)[0]
    for label in (
      "Workspace in window title",
      "Workspace in taskbar title",
      "Custom title templates",
      "Window title template",
      "Taskbar title template",
    ):
      self.assertIn(label, section)
    for variable in ('{"{app}"}', '{"{workspace}"}', '{"{service}"}'):
      self.assertIn(variable, section)
    self.assertIn("Windows taskbar buttons mirror the native window title", section)

  def test_backend_validates_title_lengths_and_documents_native_taskbar_constraint(self) -> None:
    self.assertIn('if value.chars().count() > 240 || value.chars().any(char::is_control)', MAIN)
    self.assertIn("Windows and most Linux desktops derive taskbar button text from the native window title", MAIN)
    self.assertIn('tray.set_tooltip(Some(&taskbar_title))', MAIN)
    self.assertIn('tray.set_title(Some(&taskbar_title))', MAIN)


if __name__ == "__main__":
  unittest.main()
