#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.5.4 shortcuts, preloading, and hibernation."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
UI = (ROOT / "src/lib/ui.ts").read_text(encoding="utf-8")
UI_TEST = (ROOT / "src/lib/ui.test.ts").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")


class ShortcutPreloadHibernationPatchTests(unittest.TestCase):
  def test_all_default_keybindings_share_layout_stable_matching(self) -> None:
    defaults = {
      "quickWorkspaceSwitch": "Ctrl+D",
      "quickServiceSwitch": "Ctrl+S",
      "openSettings": "Ctrl+,",
      "addService": "Ctrl+N",
      "addWorkspace": "Ctrl+Shift+N",
      "nextService": "Ctrl+Tab",
      "previousService": "Ctrl+Shift+Tab",
      "nextWorkspace": "Ctrl+Alt+ArrowDown",
      "previousWorkspace": "Ctrl+Alt+ArrowUp",
      "reloadService": "Ctrl+R",
      "reloadApp": "Ctrl+Shift+R",
      "toggleDevtools": "Ctrl+Alt+I",
    }
    for action, binding in defaults.items():
      self.assertIn(f'{action}: "{binding}"', UI)
      self.assertIn(f'keybindings.insert("{action}".into(), "{binding}".into())', MAIN)
    self.assertIn('if (/^Key[A-Z]$/.test(event.code)) return event.code.slice(3);', UI)
    self.assertIn('Comma: ","', UI)
    self.assertIn('var code = String(e.code || \'\');', MAIN)
    self.assertIn('Comma:\',\'', MAIN)
    self.assertIn('"," => "Comma"', MAIN)
    self.assertIn('expect(strokes).toEqual(Object.values(DEFAULT_KEYBINDINGS));', UI_TEST)

  def test_preload_keeps_webviews_alive_offscreen_until_first_use(self) -> None:
    preload = MAIN.split("async fn preload_service", 1)[1].split("struct ServiceIconRequest", 1)[0]
    create = MAIN.split("async fn create_service_webview", 1)[1].split("async fn show_service", 1)[0]
    show = MAIN.split("async fn show_service", 1)[1].split("async fn preload_service", 1)[0]
    self.assertIn('state.preloading.lock().unwrap().insert(service_id.clone());', preload)
    self.assertIn('let offscreen = LogicalPosition::new(-30000.0, 0.0);', preload)
    self.assertNotIn('wv.hide()', preload)
    self.assertIn('.focused(false)', create)
    self.assertIn('.preloading', create)
    activate = MAIN.split('fn activate_service_webview', 1)[1].split('#[tauri::command]\nasync fn show_service', 1)[0]
    self.assertIn('let _ = wv.set_position(offscreen);', activate)
    self.assertIn('let _ = wv.show();', activate)
    self.assertIn('let _ = wv.set_focus();', activate)
    self.assertNotIn('let _ = wv.hide();', activate)
    self.assertIn('state.desired_active.lock().unwrap().as_deref() == Some(service_id.as_str())', preload)
    self.assertIn('activate_service_webview(&app, &state, &service_id, pos, size)', preload)

  def test_hidden_panels_do_not_suspend_background_preloads(self) -> None:
    hide = MAIN.split("fn hide_service_webviews", 1)[1].split("fn hide_all_services", 1)[0]
    self.assertIn('if active.as_deref() == Some(sid.as_str())', hide)
    self.assertIn('let _ = wv.hide();', hide)
    self.assertIn('let _ = wv.set_position(offscreen);', hide)
    self.assertIn('let _ = wv.show();', hide)

  def test_hibernation_is_off_by_default_and_only_explicit_timers_close_services(self) -> None:
    self.assertIn('hibernationTimer: 0,', APP)
    self.assertIn('settings.insert("hibernationTimer".into(), 0.into())', MAIN)
    reconcile = APP.split("function reconcileHibernationTimers", 1)[1].split("function selectService", 1)[0]
    self.assertIn('for (const id of [...hibTimers.keys()]) clearHibTimer(id);', reconcile)
    self.assertIn('if (!(appSettings.hibernationTimer > 0))', reconcile)
    self.assertIn('if (appSettings.preloadServices) preloadRest(activeId ?? undefined);', reconcile)
    schedule = APP.split("function scheduleHibernation", 1)[1].split("function reconcileHibernationTimers", 1)[0]
    self.assertIn('svc?.isHibernationEnabled !== true', schedule)
    self.assertIn('closeService(sid)', schedule)
    self.assertIn('if (key === "hibernationTimer") reconcileHibernationTimers();', APP)

  def test_preload_toggle_applies_immediately_and_stale_chains_cannot_resume(self) -> None:
    self.assertIn('let preloadGeneration = 0;', APP)
    self.assertIn('function cancelPreloading()', APP)
    self.assertIn('const generation = ++preloadGeneration;', APP)
    self.assertIn('if (generation !== preloadGeneration) return;', APP)
    self.assertIn('if (key === "preloadServices")', APP)
    self.assertIn('if (value === true) preloadRest(activeId ?? undefined);', APP)
    self.assertIn('else cancelPreloading();', APP)


if __name__ == "__main__":
  unittest.main()
