#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.7.18 workspace-list scrolling."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "App.svelte").read_text(encoding="utf-8")


class Patch0718Tests(unittest.TestCase):
  def test_configured_workspaces_have_independent_bounded_scrolling(self) -> None:
    for marker in (
      'class="managed-list workspace-managed-list" role="list" aria-label="Configured workspaces"',
      '.workspace-managed-list {\n    max-height: min(58vh, 680px);',
      'overflow-y: auto;',
      'overscroll-behavior: contain;',
      'scrollbar-gutter: stable;',
      'padding-right: 3px;',
    ):
      self.assertIn(marker, APP)

  def test_workspace_and_service_lists_share_bounded_scroll_geometry(self) -> None:
    geometry = (
      'max-height: min(58vh, 680px);',
      'overflow-y: auto;',
      'overscroll-behavior: contain;',
      'scrollbar-gutter: stable;',
      'padding-right: 3px;',
    )
    for selector in ('.service-managed-list {', '.workspace-managed-list {'):
      block = APP.split(selector, 1)[1].split('}', 1)[0]
      for marker in geometry:
        self.assertIn(marker, block)

  def test_workspace_search_and_existing_pagination_are_preserved(self) -> None:
    for marker in (
      'placeholder="Search configured workspaces…"',
      'bind:value={managedWorkspaceQuery}',
      'oninput={() => (managedWorkspacePage = 0)}',
      'const MANAGED_SERVICE_PAGE_SIZE = 100;',
      'paged(managedWorkspaces, managedWorkspacePage, MANAGED_SERVICE_PAGE_SIZE)',
      '{#if managedWorkspaces.length > MANAGED_SERVICE_PAGE_SIZE}',
      'aria-label="Configured workspace pages"',
    ):
      self.assertIn(marker, APP)

  def test_0717_portable_service_export_geometry_is_preserved(self) -> None:
    for marker in (
      'class="setting-actions service-export-actions"',
      'class="status-badge service-export-selected-count"',
      'class="secondary sm service-export-select-all"',
      'class="secondary sm service-export-clear"',
      'class="primary sm service-export-submit"',
      'grid-template-columns: 104px 82px 62px 184px;',
      '{selectedServiceExports.length ? "Export selected…" : "Export personal recipes…"}',
    ):
      self.assertIn(marker, APP)


if __name__ == "__main__":
  unittest.main()
