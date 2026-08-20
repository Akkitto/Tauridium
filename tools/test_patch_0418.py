"""Regression coverage for Tauridium 0.4.18 integrations."""
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
UI = (ROOT / "src" / "lib" / "ui.ts").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")
RECIPES = (ROOT / "src-tauri" / "src" / "recipes.rs").read_text(encoding="utf-8")
TAURI = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))


class Patch0418Tests(unittest.TestCase):
  def test_add_workspace_has_default_shortcut_everywhere(self) -> None:
    self.assertIn('addWorkspace: "Ctrl+Shift+N"', UI)
    self.assertIn('keybindings.insert("addWorkspace".into(), "Ctrl+Shift+N".into());', MAIN)
    self.assertIn('shortcut("addWorkspace")', MAIN)
    self.assertIn('"addWorkspace",', MAIN.split('const SHORTCUT_ACTIONS', 1)[1].split('fn effective_service_shortcut_capture', 1)[0])
    self.assertIn('case "addWorkspace": openAddWorkspace(); break;', APP)
    self.assertIn('["addWorkspace", "Add workspace", "Create a new workspace."]', APP)

  def test_keybinding_merge_adds_new_defaults_without_resetting_existing_bindings(self) -> None:
    merge = MAIN.split('fn merge_app_settings_value', 1)[1].split('fn read_app_settings_value', 1)[0]
    self.assertIn('if key == "keybindings"', merge)
    self.assertIn('let default_bindings = base', merge)
    self.assertIn('default_bindings.insert(action.clone(), binding.clone());', merge)
    self.assertIn('app_settings_merge_preserves_existing_keybindings_and_adds_new_defaults', MAIN)

  def test_reload_toast_waits_for_replacement_webview_ready_and_uses_overlay(self) -> None:
    reload_body = APP.split('async function reloadServiceFromUi', 1)[1].split('async function refetchAllServiceIcons', 1)[0]
    status_listener = APP.split('listen<{ id: string; status: "loading" | "ready" }>("svc-status"', 1)[1].split('// Native Services menu events', 1)[0]
    self.assertIn('pendingReloadToasts.set(service.id', reload_body)
    self.assertNotIn('showToast(`${serviceLabel(service)} reloaded.`)', reload_body)
    self.assertIn('pendingReloadToasts.get(e.payload.id)', status_listener)
    self.assertIn('showToast(reloadToast)', status_listener)
    self.assertIn('showServiceToastOverlay(activeId, message)', APP)
    self.assertIn('invoke("show_service_toast_overlay", { serviceId, message })', API)
    self.assertIn('fn service_toast_overlay_script(', MAIN)
    production_main = MAIN.split('#[cfg(test)]', 1)[0]
    self.assertNotIn('window.__tauridiumShowToast', production_main)
    self.assertIn('fn show_service_toast_overlay(', MAIN)

  def test_requested_bundled_recipes_have_expected_service_urls(self) -> None:
    expected = {
      "woodpecker": "http://localhost:8000/",
      "codeberg": "https://codeberg.org/",
      "sourcehut": "https://sr.ht/",
      "fritzbox": "http://192.168.178.1/",
      "artifacts-mmo": "https://artifactsmmo.com/",
      "lumo": "https://lumo.proton.me/",
      "suno": "https://suno.com/create",
      "midjourney": "https://www.midjourney.com/imagine",
      "sora": "https://sora.chatgpt.com/sunset",
      "grafana": "http://localhost:3000/",
      "graylog": "http://localhost:9000/",
      "kibana": "http://localhost:5601/",
      "anytype": "https://anytype.io/",
    }
    for recipe_id, url in expected.items():
      with self.subTest(recipe_id=recipe_id):
        self.assertIn(f'"{recipe_id}",', RECIPES)
        self.assertIn(f'"{url}",', RECIPES)
    for recipe_id in ("woodpecker", "fritzbox", "grafana", "graylog", "kibana"):
      block = RECIPES.split(f'"{recipe_id}",', 1)[1].split('),', 1)[0]
      self.assertIn('true,', block)

  def test_codeberg_and_sourcehut_support_workspace_namespace_routes(self) -> None:
    self.assertIn('"codeberg" => Some("https://codeberg.org/{teamId}")', RECIPES)
    self.assertIn('"sourcehut" => Some("https://sr.ht/~{teamId}/")', RECIPES)
    self.assertIn('"hasTeamId": team_url.is_some()', RECIPES)

  def test_main_window_starts_hidden_until_restored_state_is_applied(self) -> None:
    main_window = TAURI["app"]["windows"][0]
    self.assertIs(main_window["visible"], False)
    reveal = MAIN.split('fn reveal_main_window_after_startup_restore', 1)[1].split('fn show_main', 1)[0]
    self.assertLess(reveal.index('restore_main_window_state(&window);'), reveal.index('window.show();'))
    self.assertIn('if !start_minimized', reveal)
    setup = MAIN.split('.setup(|app|', 1)[1].split('start_badge_poller', 1)[0]
    self.assertIn('reveal_main_window_after_startup_restore(app.handle(), start_minimized);', setup)


if __name__ == "__main__":
  unittest.main()
