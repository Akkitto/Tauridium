#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.4.28 icon, context-menu, sandbox and download fixes."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
UI = (ROOT / "src/lib/ui.ts").read_text(encoding="utf-8")
UI_TEST = (ROOT / "src/lib/ui.test.ts").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")


class Patch0428Tests(unittest.TestCase):
  def test_service_icon_inversion_is_persisted_and_applied_consistently(self) -> None:
    self.assertIn("serviceIconInversions: Record<string, boolean>", API)
    self.assertIn('"serviceIconInversions".into()', MAIN)
    self.assertIn("function serviceIconInverted(serviceId: string)", APP)
    self.assertIn("Invert service icon colors", APP)
    self.assertGreaterEqual(APP.count("class:service-icon-inverted={serviceIconInverted("), 3)
    self.assertIn(".service-icon-inverted { filter: invert(1); }", APP)
    self.assertIn("delete serviceIconInversions[s.id];", APP)
    self.assertIn("serviceIconInversions[newId] = true", APP)

  def test_service_context_menu_is_native_so_child_webviews_cannot_cover_it(self) -> None:
    self.assertIn('import { Menu } from "@tauri-apps/api/menu";', APP)
    self.assertIn("const menu = await Menu.new({", APP)
    self.assertIn("await menu.popup(new LogicalPosition(x, y));", APP)
    self.assertIn("await menu.close().catch(() => {});", APP)
    self.assertNotIn("service-context-backdrop", APP)
    self.assertNotIn('class="service-context-menu"', APP)

  def test_sandbox_search_has_compact_non_growing_layout(self) -> None:
    self.assertIn(
      ".service-workspace-search.service-sandbox-search { width: min(100%, 240px); max-width: 240px; min-height: 36px; flex: none; align-self: flex-start; margin: 0; }",
      APP,
    )
    self.assertIn(".service-sandbox-manager .service-workspace-overview { align-items: center; }", APP)

  def test_download_settings_verification_is_semantic_not_json_key_order_dependent(self) -> None:
    self.assertIn("export function sameDownloadPreference", UI)
    self.assertIn("sameDownloadPreference(persisted.serviceDownloadSettings[serviceId], preference)", APP)
    self.assertIn("sameDownloadPreference(persisted.workspaceDownloadSettings[workspaceId], preference)", APP)
    self.assertNotIn("JSON.stringify(persisted.serviceDownloadSettings", APP)
    self.assertIn("compares values rather than object key insertion order", UI_TEST)


if __name__ == "__main__":
  unittest.main()
