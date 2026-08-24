#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.6.14 service context-menu action capture."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")


class Patch0614Tests(unittest.TestCase):
  def test_pretty_context_actions_capture_service_before_closing_menu(self) -> None:
    helper = APP.split("function runServiceContextAction", 1)[1].split("function openContextServiceSettings", 1)[0]
    self.assertIn("service: Service", helper)
    self.assertIn("closeServiceContextMenu();", helper)
    self.assertIn("void action(service);", helper)

    menu = APP.split('{#if serviceContextMenu}', 1)[1].split('{#if toastMessage}', 1)[0]
    self.assertIn(
      "runServiceContextAction(contextService, duplicateServiceFromUi)",
      menu,
    )
    self.assertIn(
      "runServiceContextAction(contextService, reloadServiceFromUi)",
      menu,
    )
    self.assertIn(
      "runServiceContextAction(contextService, toggleServiceEnabled)",
      menu,
    )

  def test_pretty_context_actions_never_close_then_read_reactive_context_service(self) -> None:
    menu = APP.split('{#if serviceContextMenu}', 1)[1].split('{#if toastMessage}', 1)[0]
    self.assertNotIn(
      "closeServiceContextMenu(); void duplicateServiceFromUi(contextService)",
      menu,
    )
    self.assertNotIn(
      "closeServiceContextMenu(); void reloadServiceFromUi(contextService)",
      menu,
    )
    self.assertNotIn(
      "closeServiceContextMenu(); void toggleServiceEnabled(contextService)",
      menu,
    )


if __name__ == "__main__":
  unittest.main()
