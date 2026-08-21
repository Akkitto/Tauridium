#!/usr/bin/env python3
"""Regression coverage for scalable sidebar and canonical service/workspace order."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class OrderingAndSidebarTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    cls.api = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
    cls.ui = (ROOT / "src/lib/ui.ts").read_text(encoding="utf-8")
    cls.ui_test = (ROOT / "src/lib/ui.test.ts").read_text(encoding="utf-8")
    cls.app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")

  def test_canonical_orders_are_typed_persisted_and_registered(self) -> None:
    for marker in (
      "serviceOrder: string[]",
      "workspaceOrder: string[]",
      'invoke("set_service_order", { serviceIds })',
      'invoke("set_workspace_order", { workspaceIds })',
    ):
      self.assertIn(marker, self.api)
    for marker in (
      'settings.insert("serviceOrder".into(), Value::Array(Vec::new()));',
      'settings.insert("workspaceOrder".into(), Value::Array(Vec::new()));',
      "fn set_service_order",
      "fn set_workspace_order",
      'persist_order_setting(&app, &state, "serviceOrder"',
      'persist_order_setting(&app, &state, "workspaceOrder"',
    ):
      self.assertIn(marker, self.main)
    handler = self.main.split("tauri::generate_handler![", 1)[1].split("]", 1)[0]
    self.assertIn("set_service_order", handler)
    self.assertIn("set_workspace_order", handler)

  def test_order_validation_rejects_blank_and_duplicate_ids(self) -> None:
    body = self.main.split("fn validate_order_ids", 1)[1].split("fn validate_app_settings_value", 1)[0]
    self.assertIn("let id = id.trim();", body)
    self.assertIn("if id.is_empty()", body)
    self.assertIn("seen.insert(id)", body)
    self.assertIn("duplicate id", body)

  def test_frontend_reconciles_stale_and_new_ids_after_data_changes(self) -> None:
    self.assertIn("async function reconcileSavedOrders()", self.app)
    self.assertIn("orderedBySavedIds(services, appSettings.serviceOrder)", self.app)
    self.assertIn("orderedBySavedIds(workspaces, appSettings.workspaceOrder)", self.app)
    self.assertIn("setAppSettings({ serviceOrder, workspaceOrder, workspaceLastUsed })", self.app)
    self.assertIn("workspaceIds.has(workspaceId)", self.app)
    self.assertGreaterEqual(self.app.count("await reconcileSavedOrders();"), 4)

  def test_drag_reorder_is_one_atomic_persistence_operation(self) -> None:
    block = self.app.split("// --- Service reordering", 1)[1].split("function onDragStart", 1)[0]
    self.assertIn("setServiceOrder(nextIds)", block)
    self.assertIn("Tauridium could not verify the saved service order", block)
    self.assertNotIn("updateService(", block)
    drop = self.app.split("async function onDrop", 1)[1].split("function row", 1)[0]
    self.assertIn("reorderVisibleSubsetAt", drop)
    self.assertIn("await persistServiceIds(nextIds, previousIds)", drop)

  def test_workspace_reorder_uses_same_verified_atomic_order_store(self) -> None:
    block = self.app.split("async function persistWorkspaceIds", 1)[1].split("async function handleCreateWorkspace", 1)[0]
    self.assertIn("setWorkspaceOrder(nextIds)", block)
    self.assertIn("Tauridium could not verify the saved workspace order", block)
    self.assertIn("await persistWorkspaceIds(nextIds, previousIds)", block)

  def test_filtered_drag_preserves_hidden_service_slots(self) -> None:
    self.assertIn("export function reorderVisibleSubset", self.ui)
    self.assertIn("visibleSet", self.ui)
    self.assertIn("reorders a filtered workspace subset without moving hidden service slots", self.ui_test)
    self.assertIn("supports explicit before/after sidebar drop placement without disturbing hidden slots", self.ui_test)
    self.assertIn("treats stale or duplicate drag-order input as a safe no-op", self.ui_test)

  def test_services_settings_is_dynamic_named_and_empty_safe(self) -> None:
    settings = self.app.split('{:else if settingsTab === "services"}', 1)[1].split('{:else if settingsTab === "appearance"}', 1)[0]
    self.assertIn("Configured services", settings)
    self.assertIn("{services.length}", settings)
    self.assertIn("{#each managedServiceRows as service, index (service.id)}", settings)
    self.assertIn("managedWorkspaceFilter", settings)
    self.assertIn("managedServiceQuery", settings)
    self.assertIn("MANAGED_SERVICE_PAGE_SIZE", settings)
    self.assertIn("{serviceLabel(service)}", settings)
    self.assertIn("No services configured", settings)
    self.assertIn("Service settings", settings)
    self.assertIn('return recipeId || "Unnamed service"', self.ui)

  def test_sidebar_reclaims_real_estate_and_scrolls_only_when_needed(self) -> None:
    sidebar = self.app.split('<aside class="sidebar">', 1)[1].split("</aside>", 1)[0]
    self.assertNotIn("+ Add a service", sidebar)
    self.assertNotIn("openAppSettings", sidebar)
    self.assertIn('class="svcarea"', sidebar)
    self.assertIn('class="count"', sidebar)
    self.assertIn("v{appVer}", sidebar)
    css = self.app.split(".svcarea {", 1)[1].split(".account {", 1)[0]
    self.assertIn("flex: 1", css)
    self.assertIn("min-height: 0", css)
    self.assertIn("overflow-y: auto", css)
    self.assertIn("overscroll-behavior: contain", css)
    self.assertIn("scrollbar-gutter: stable", css)

  def test_sidebar_has_no_workspace_strip_and_settings_tabs_wrap_without_horizontal_scroll(self) -> None:
    sidebar = self.app.split('<aside class="sidebar">', 1)[1].split("</aside>", 1)[0]
    self.assertNotIn('class="wspills"', sidebar)
    self.assertNotIn('class="pill"', sidebar)
    settings_css = self.app.split(".settings-tabs {", 1)[1].split(".setting-tab {", 1)[0]
    self.assertIn("border-radius", settings_css)
    self.assertIn("background", settings_css)
    self.assertIn("flex-wrap: wrap", settings_css)
    self.assertIn("overflow: visible", settings_css)
    self.assertNotIn("overflow-x: auto", settings_css)

  def test_native_tauridium_menu_owns_settings_and_add_service(self) -> None:
    builder = self.main.split("fn build_native_application_menu", 1)[1].split("#[derive(Clone, Copy)]", 1)[0]
    events = self.main.split("// Native application menu", 1)[1].split("// Request notification", 1)[0]
    self.assertIn('"open-settings"', builder)
    self.assertIn('"Settings"', builder)
    self.assertIn('"open-add-service"', builder)
    self.assertIn('"Add Service"', builder)
    self.assertIn('"open-add-workspace"', builder)
    self.assertIn('"Add Workspace"', builder)
    self.assertIn('app.emit("open-settings", ())', events)
    self.assertIn('app.emit("open-add-service", ())', events)
    self.assertIn('app.emit("open-add-workspace", ())', events)
    self.assertNotIn('"About Tauridium"', builder + events)
    self.assertNotIn("PredefinedMenuItem::about", builder + events)
    self.assertIn('listen("open-settings", openAppSettings)', self.app)
    self.assertIn('listen("open-add-service", openAdd)', self.app)
    self.assertIn('listen("open-add-workspace", openAddWorkspace)', self.app)


  def test_native_services_menu_tracks_actual_services_and_stable_ids(self) -> None:
    menu = self.main.split("fn build_native_application_menu", 1)[1].split("#[derive(Clone, Copy)]", 1)[0]
    self.assertIn("services: &[NativeServiceMenuEntry]", menu)
    self.assertIn('"No services configured"', menu)
    self.assertIn("for (index, service) in services.iter().enumerate()", menu)
    self.assertIn("native_service_menu_label(service)", menu)
    self.assertIn("service.enabled", menu)
    self.assertIn('(index < 9).then(|| format!("CmdOrCtrl+{}", index + 1))', menu)
    self.assertNotIn('format!("Service {i}")', menu)
    self.assertNotIn("for i in 1..=9u32", menu)
    self.assertIn("fn sync_services_menu", self.main)
    self.assertIn('format!("goto-service:{}", service.id)', menu)
    self.assertIn('id.strip_prefix("goto-service:")', self.main)
    self.assertIn('app.emit("select-service-id", service_id.to_string())', self.main)
    self.assertIn('invoke("sync_services_menu", { services })', self.api)
    self.assertIn('listen<string>("select-service-id"', self.app)
    self.assertIn("services.find((candidate) => candidate.id === e.payload)", self.app)
    self.assertIn("await refreshNativeServicesMenu();", self.app)

  def test_native_services_menu_escapes_names_and_has_no_phantom_slots(self) -> None:
    label = self.main.split("fn native_service_menu_label", 1)[1].split("fn build_native_application_menu", 1)[0]
    self.assertIn("service.name.trim()", label)
    self.assertIn("service.id.trim()", label)
    self.assertIn("chars().take(80)", label)
    self.assertIn('label.replace(\'&\', "&&")', label)
    startup = self.main.split("// Native application menu", 1)[1].split("// Request notification", 1)[0]
    self.assertIn("build_native_application_menu(app.handle(), &[])", startup)
    self.assertNotIn("goto-svc-", startup)
    self.assertNotIn("select-index", startup)

  def test_settings_menu_preserves_last_settings_tab(self) -> None:
    body = self.app.split("function openAppSettings()", 1)[1].split("function openAddWorkspace()", 1)[0]
    self.assertIn('view = "appSettings"', body)
    self.assertNotIn("settingsTab =", body)


if __name__ == "__main__":
  unittest.main()
