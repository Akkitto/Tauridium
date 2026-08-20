"""Regression coverage for Tauridium 0.4.10 service settings and icon/shortcut fixes."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Patch0410Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
    cls.api = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
    cls.main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    cls.icons = (ROOT / "src-tauri/src/icons.rs").read_text(encoding="utf-8")

  def test_automatic_and_bulk_icon_fetching_respect_service_preference(self) -> None:
    hydrate = self.app.split("function hydrateServiceIcons", 1)[1].split("function markIconFailed", 1)[0]
    failed = self.app.split("function markIconFailed", 1)[1].split("function closeServiceContextMenu", 1)[0]
    bulk = self.app.split("async function refetchAllServiceIcons", 1)[1].split("async function handleDelete", 1)[0]
    self.assertIn("if (!appSettings.fetchMissingServiceIcons) return;", hydrate)
    self.assertIn("service.useFavicon === true", hydrate)
    self.assertIn("appSettings.fetchMissingServiceIcons && service.useFavicon === true", failed)
    self.assertIn("const preferred = services.filter((service) => service.useFavicon === true);", bulk)
    self.assertIn("for (const service of preferred)", bulk)
    self.assertNotIn("for (const service of services)", bulk)
    self.assertIn("if !should_fetch", self.icons)
    self.assertNotIn("request.prefer_website_icon ||", self.main)

  def test_custom_recipe_and_custom_website_default_to_website_icon_preference(self) -> None:
    create = self.main.split("async fn create_service", 1)[1].split("fn create_custom_website_service", 1)[0]
    custom = self.main.split("fn create_custom_website_service", 1)[1].split("// Delete a service", 1)[0]
    self.assertIn("local_recipe && !recipes::is_bundled_recipe(&recipe_id)", create)
    self.assertIn('serde_json::json!({ "useFavicon": true })', create)
    self.assertIn('"customUrl": url, "useFavicon": true', custom)
    self.assertIn('r.source === "custom" || !r.icons?.svg', self.app)

  def test_duplicate_preserves_assigned_icon_and_cached_website_icon_policy(self) -> None:
    duplicate = self.app.split("async function duplicateServiceFromUi", 1)[1].split("async function reloadServiceFromUi", 1)[0]
    self.assertIn("if (service.isLocalRecipe === true) patch.iconUrl = service.iconUrl ?? null", self.app)
    self.assertIn("if (service.useFavicon === true)", duplicate)
    self.assertIn("await copyServiceIconCache(service.id, newId)", duplicate)
    self.assertIn("await loadServiceIcon(duplicate, false, false, true)", duplicate)
    self.assertIn('invoke("copy_service_icon_cache"', self.api)
    self.assertIn("fn copy_service_icon_cache", self.main)
    self.assertIn("pub(crate) fn copy_cached", self.icons)

  def test_native_reload_routes_through_frontend_toast_path(self) -> None:
    menu = self.main.split('"reload-service" =>', 1)[1].split('"reload-app" =>', 1)[0]
    self.assertIn('app.emit("shortcut-action", "reloadService".to_string())', menu)
    reload_ui = self.app.split("async function reloadServiceFromUi", 1)[1].split("async function refetchAllServiceIcons", 1)[0]
    self.assertIn("appSettings.reloadToasts", reload_ui)
    self.assertIn("reloaded.", reload_ui)

  def test_devtools_shortcut_reaches_focused_service_webview_and_windows_opens(self) -> None:
    bridge = self.main.split("fn service_shortcut_bridge_js", 1)[1].split("const IPC_SHIM_JS", 1)[0]
    actions = self.main.split('const SHORTCUT_ACTIONS', 1)[1].split('fn effective_service_shortcut_capture', 1)[0]
    self.assertIn('"toggleDevtools"', actions)
    self.assertIn('for action in SHORTCUT_ACTIONS', bridge)
    self.assertIn("window.addEventListener('keydown'", bridge)
    self.assertIn("dispatch_service_shortcut", bridge)
    self.assertIn(".initialization_script(script)", self.main)
    toggle = self.main.split("fn toggle_devtools(app", 1)[1].split("fn reload_active_service", 1)[0]
    self.assertIn('#[cfg(target_os = "windows")]', toggle)
    self.assertIn("wv.open_devtools();", toggle)

  def test_keybinding_copy_explains_shift_and_recreates_service_webviews(self) -> None:
    self.assertIn("Shift is required only when <strong>Shift</strong> is explicitly present", self.app)
    save = self.app.split("async function saveAppSetting", 1)[1].split("async function moveManagedService", 1)[0]
    self.assertIn('if (key === "keybindings" || key === "captureServiceShortcuts")', save)
    self.assertIn("await closeServices();", save)
    self.assertIn("selectService(restore)", save)

  def test_service_name_is_immediately_dirty_and_unsaved_close_confirms(self) -> None:
    self.assertIn('value={settingsSvc.name} oninput={(e) => saveText("name", e.currentTarget.value)}', self.app)
    close = self.app.split("async function closeServiceSettings", 1)[1].split("async function persistService", 1)[0]
    self.assertIn("if (svcDirty || serviceTemplateDirty)", close)
    self.assertIn('confirmAsk("Discard unsaved service changes?")', close)
    self.assertIn("if (!discard) return;", close)

  def test_failed_service_save_keeps_dirty_state_and_does_not_optimistically_commit(self) -> None:
    persist = self.app.split("async function persistService", 1)[1].split("// Handlers modify ONLY local state", 1)[0]
    save = self.app.split("async function saveServiceSettings", 1)[1].split("async function setServiceEnabled", 1)[0]
    self.assertIn("async function persistService(reload = false): Promise<boolean>", self.app)
    self.assertIn("return false;", persist)
    self.assertLess(persist.index("await updateService"), persist.index("services = services.map"))
    self.assertIn("if (!saved) return;", save)
    self.assertIn("svcDirty = false;", save)
    self.assertLess(save.index("if (!saved) return;"), save.index("svcDirty = false;"))
    self.assertIn("Unable to save custom URL placeholders", save)

  def test_only_favorites_follows_indirect_message_badge(self) -> None:
    indirect = self.app.index('toggle("Indirect message badge"')
    favorites = self.app.index('toggle("Only favorites in unread count"')
    media = self.app.index('toggle("Media badge"')
    self.assertLess(indirect, favorites)
    self.assertLess(favorites, media)

  def test_service_settings_workspace_manager_is_searchable_scrollable_and_transactional(self) -> None:
    self.assertIn('placeholder="Search workspaces…"', self.app)
    self.assertIn('class="service-workspace-list"', self.app)
    self.assertIn("max-height: min(38vh, 420px); overflow-y: auto", self.app)
    self.assertIn("serviceWorkspaceRows", self.app)
    self.assertIn("serviceWorkspacePageCount", self.app)
    self.assertIn("MANAGED_SERVICE_PAGE_SIZE", self.app)
    create = self.app.split("async function createWorkspaceForCurrentService", 1)[1].split("async function renameWorkspace", 1)[0]
    self.assertIn("created = await createWorkspace(name)", create)
    self.assertIn("await updateWorkspace(created.id, created.name, [settingsSvc.id])", create)
    self.assertIn("if (created) await deleteWorkspace(created.id).catch", create)
    toggle = self.app.split("async function toggleServiceInWorkspace", 1)[1].split("async function toggleCurrentServiceWorkspace", 1)[0]
    self.assertIn("const previous = [...ws.services]", toggle)
    self.assertIn("services: previous", toggle)

  def test_accent_picker_uses_aligned_dedicated_control_row(self) -> None:
    self.assertIn('class="setting-card setting-card-stack accent-setting-card"', self.app)
    self.assertIn('class="accent-picker-control"', self.app)
    self.assertIn('class="secondary sm accent-custom-button"', self.app)
    self.assertIn(".accent-picker-control { display: flex; align-items: center; justify-content: space-between", self.app)


if __name__ == "__main__":
  unittest.main()
