"""Regression coverage for Tauridium 0.4.14 shortcut capture and workspace UX."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
RUST = (ROOT / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")


class Patch0414Tests(unittest.TestCase):
  def test_service_shortcut_capture_defaults_on_and_is_portable(self) -> None:
    self.assertIn('captureServiceShortcuts: boolean;', API)
    self.assertIn('serviceShortcutCaptureOverrides: Record<string, boolean>;', API)
    self.assertIn('captureServiceShortcuts: true', APP)
    self.assertIn('serviceShortcutCaptureOverrides: {}', APP)
    self.assertIn('"captureServiceShortcuts": true', RUST)
    self.assertIn('"serviceShortcutCaptureOverrides": {}', RUST)
    self.assertIn('App setting serviceShortcutCaptureOverrides is invalid', RUST)

  def test_service_webview_bridge_captures_single_shortcuts_and_chords(self) -> None:
    bridge = RUST.split('fn service_shortcut_bridge_js', 1)[1].split('const IPC_SHIM_JS', 1)[0]
    self.assertIn('effective_service_shortcut_capture', RUST)
    actions = RUST.split('const SHORTCUT_ACTIONS', 1)[1].split('fn effective_service_shortcut_capture', 1)[0]
    self.assertIn('"quickWorkspaceSwitch"', actions)
    self.assertIn('"toggleDevtools"', actions)
    self.assertIn('for action in SHORTCUT_ACTIONS', bridge)
    self.assertIn("window.addEventListener('keydown'", bridge)
    self.assertIn('seq.length === 2', bridge)
    self.assertIn('e.preventDefault()', bridge)
    self.assertIn('e.stopImmediatePropagation()', bridge)
    self.assertIn("tauridium-shortcut://bridge/", bridge)
    self.assertIn("window.location.href", bridge)
    self.assertNotIn("__TAURI_INTERNALS__", bridge)
    self.assertIn("service_shortcut_action_from_url", RUST)
    self.assertIn(".on_navigation(move |url|", RUST)
    self.assertNotIn("fn dispatch_service_shortcut", RUST)

  def test_service_override_is_inheritance_aware_and_recreates_webview(self) -> None:
    self.assertIn('serviceShortcutCaptureMode(serviceId: string)', APP)
    self.assertIn('effectiveServiceShortcutCapture(serviceId: string)', APP)
    self.assertIn('value={serviceShortcutCaptureMode(settingsServiceId)}', APP)
    self.assertIn('<option value="inherit">Use global setting', APP)
    self.assertIn('<option value="tauridium">Tauridium shortcuts first</option>', APP)
    self.assertIn('<option value="website">Website shortcuts first</option>', APP)
    setter = APP.split('async function setServiceShortcutCaptureMode', 1)[1].split('async function toggleCurrentServiceWorkspace', 1)[0]
    self.assertIn('delete serviceShortcutCaptureOverrides[serviceId]', setter)
    self.assertIn('await closeService(serviceId)', setter)
    self.assertNotIn('!', setter.split('serviceShortcutCaptureOverrides', 1)[0])

  def test_global_toggle_recreates_open_service_webviews(self) -> None:
    self.assertIn('Capture Tauridium shortcuts inside services', APP)
    save = APP.split('async function saveAppSetting', 1)[1].split('async function moveManagedService', 1)[0]
    self.assertIn('key === "keybindings" || key === "captureServiceShortcuts"', save)
    self.assertIn('await closeServices();', save)
    self.assertIn('selectService(restore)', save)

  def test_shortcut_override_follows_duplicate_and_delete_lifecycle(self) -> None:
    duplicate = APP.split('async function duplicateServiceFromUi', 1)[1].split('async function reloadServiceFromUi', 1)[0]
    self.assertIn('serviceShortcutCaptureOverrides[newId] = serviceShortcutCaptureOverrides[service.id]', duplicate)
    delete = APP.split('async function handleDelete', 1)[1].split('async function handleClearCache', 1)[0]
    self.assertIn('delete serviceShortcutCaptureOverrides[s.id]', delete)

  def test_native_menu_wording_and_add_workspace_action(self) -> None:
    menu = RUST.split('fn build_native_application_menu', 1)[1].split('#[derive(Clone, Copy)]', 1)[0]
    self.assertIn('"Settings"', menu)
    self.assertIn('"Add Service"', menu)
    self.assertIn('"Add Workspace"', menu)
    self.assertNotIn('"Settings…"', menu)
    self.assertNotIn('"Add Service…"', menu)
    events = RUST.split('// Native application menu', 1)[1].split('// Request notification', 1)[0]
    self.assertIn('app.emit("open-add-workspace", ())', events)
    self.assertIn('listen("open-add-workspace", openAddWorkspace)', APP)
    self.assertIn('document.querySelector<HTMLInputElement>(".workspace-create-row input")?.focus()', APP)

  def test_service_workspace_manager_has_clear_membership_actions_and_pagination(self) -> None:
    block = APP.split('<div class="set-title">Workspaces</div>', 1)[1].split('<div class="set-title">Appearance</div>', 1)[0]
    self.assertIn('Workspace membership', block)
    self.assertIn('{serviceWorkspaceJoinedCount} of {workspaces.length} joined', block)
    self.assertIn('<option value="joined">Joined</option>', block)
    self.assertIn('<option value="available">Not joined</option>', block)
    self.assertIn('{#each serviceWorkspaceRows as workspace', block)
    self.assertIn('{joined ? "Remove" : "Add"}', block)
    self.assertIn('serviceWorkspacePageCount', block)
    self.assertIn('Create a workspace', block)
    self.assertNotIn('type="checkbox"', block)
    self.assertIn('max-height: min(38vh, 420px); overflow-y: auto', APP)


if __name__ == "__main__":
  unittest.main()
