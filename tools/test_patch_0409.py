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

  def test_context_settings_captures_service_before_clearing_menu_state(self) -> None:
    body = self.app.split("function openContextServiceSettings", 1)[1].split("function openServiceContextMenu", 1)[0]
    self.assertLess(body.index("openServiceSettings(service);"), body.index("closeServiceContextMenu();"))
    menu = self.app.split('class="service-context-menu"', 1)[1].split('{/if}', 1)[0]
    self.assertIn("openContextServiceSettings(contextService)", menu)
    self.assertNotIn("closeServiceContextMenu(); openServiceSettings(contextService)", menu)

  def test_context_menu_has_requested_order_and_short_toggle_labels(self) -> None:
    menu = self.app.split('class="service-context-menu"', 1)[1].split('{/if}', 1)[0]
    settings = menu.index(">Settings</button>")
    reload = menu.index(">Reload</button>")
    duplicate = menu.index(">Duplicate</button>")
    toggle = menu.index('? "Enable" : "Disable"')
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

  def test_context_menu_geometry_accounts_for_four_actions(self) -> None:
    mouse = self.app.split("function openServiceContextMenu(event", 1)[1].split("function openServiceContextMenuFromKeyboard", 1)[0]
    keyboard = self.app.split("function openServiceContextMenuFromKeyboard", 1)[1].split("function handleServiceContextMenuKeydown", 1)[0]
    self.assertIn("const height = 194;", mouse)
    self.assertIn("window.innerHeight - 202", keyboard)

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
