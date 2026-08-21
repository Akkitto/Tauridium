#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.4.9 context-menu and remote-service fixes."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0409Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
    cls.ui = (ROOT / "src/lib/ui.ts").read_text(encoding="utf-8")
    cls.ui_test = (ROOT / "src/lib/ui.test.ts").read_text(encoding="utf-8")
    cls.main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    cls.capability = json.loads((ROOT / "src-tauri/capabilities/default.json").read_text(encoding="utf-8"))

  def test_context_menu_uses_native_popup_above_service_webviews(self) -> None:
    body = self.app.split("async function popupNativeServiceContextMenu", 1)[1].split("function openServiceContextMenu(event", 1)[0]
    self.assertIn('const menu = await Menu.new({', body)
    self.assertIn('await menu.popup(new LogicalPosition(x, y));', body)
    self.assertIn('await menu.close().catch(() => {});', body)
    self.assertIn('if (!appSettings.prettyServiceContextMenu)', self.app)

  def test_context_menu_has_requested_order_and_short_toggle_labels(self) -> None:
    menu = self.app.split('const menu = await Menu.new({', 1)[1].split('});', 1)[0]
    settings = menu.index('text: "Settings"')
    reload = menu.index('text: "Reload"')
    duplicate = menu.index('text: "Duplicate"')
    toggle = menu.index('text: service.isEnabled === false ? "Enable" : "Disable"')
    self.assertLess(settings, reload)
    self.assertLess(reload, duplicate)
    self.assertLess(duplicate, toggle)
    self.assertNotIn("Disable Service", menu)

  def test_duplicate_clones_service_workspace_and_tauridium_metadata_transactionally(self) -> None:
    body = self.app.split("async function duplicateServiceFromUi", 1)[1].split("async function reloadServiceFromUi", 1)[0]
    for marker in (
      "await createDuplicateService(service, name)",
      "await updateService(newId, duplicatedServicePatch(service))",
      "candidate.services.includes(service.id)",
      "await updateWorkspace(workspace.id, workspace.name, members)",
      "serviceCustomUrlTemplates[newId]",
      "serviceSandboxes[newId]",
      "nextIds.splice(sourceIndex >= 0 ? sourceIndex + 1 : nextIds.length, 0, newId)",
      "await deleteService(newId).catch(() => {})",
      "await updateWorkspace(workspace.id, workspace.name, workspace.services).catch(() => {})",
    ):
      self.assertIn(marker, body)
    self.assertIn("if (duplicate && duplicate.isEnabled !== false) selectService(duplicate);", body)
    self.assertNotIn("duplicate?.isEnabled !== false", body)
    creation = self.app.split("function createDuplicateService", 1)[1].split("async function duplicateServiceFromUi", 1)[0]
    self.assertIn('service.isLocalRecipe === true && service.recipeId === "custom-website"', creation)
    self.assertIn("return createCustomWebsiteService(name, url);", creation)
    self.assertIn("return createService(name, service.recipeId);", creation)
    self.assertIn("export function duplicateServiceName", self.ui)
    self.assertIn('duplicateServiceName("Slack", ["Slack", "slack copy"])', self.ui_test)

  def test_context_menu_uses_logical_pointer_and_keyboard_positions(self) -> None:
    mouse = self.app.split("function openServiceContextMenu(event", 1)[1].split("function openServiceContextMenuFromKeyboard", 1)[0]
    keyboard = self.app.split("function openServiceContextMenuFromKeyboard", 1)[1].split("function sameIds", 1)[0]
    self.assertIn('popupNativeServiceContextMenu(service, event.clientX, event.clientY)', mouse)
    self.assertIn('rect ? rect.left + 28 : 12', keyboard)
    self.assertIn('rect ? rect.bottom : 12', keyboard)

  def test_remote_tauri_devtools_compat_is_narrow_and_does_not_expand_acl(self) -> None:
    shim = self.main.split("const REMOTE_TAURI_COMPAT_JS", 1)[1].split("const IPC_SHIM_JS", 1)[0]
    self.assertIn("plugin:webview|internal_toggle_devtools", shim)
    self.assertIn("Promise.resolve(null)", shim)
    for privileged in ("plugin:fs", "plugin:process", "plugin:shell", "plugin:window"):
      self.assertNotIn(privileged, shim)
    self.assertIn(".initialization_script(REMOTE_TAURI_COMPAT_JS)", self.main)
    self.assertEqual(self.capability.get("windows"), ["main"])
    self.assertNotIn("remote", self.capability)
    self.assertNotIn("webviews", self.capability)


if __name__ == "__main__":
  unittest.main()
