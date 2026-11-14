"""The service context menu is a native overlay so service webviews cannot cover it."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
  return (ROOT / path).read_text(encoding="utf-8")


class ServiceMenuOverlayTests(unittest.TestCase):
  def test_overlay_renderer_is_isolated_and_has_only_its_own_commands(self):
    capability = json.loads(read("src-tauri/capabilities/service-menu.json"))
    self.assertEqual(capability["webviews"], ["service-menu"])
    self.assertNotIn("windows", capability)
    self.assertEqual(
      set(capability["permissions"]),
      {"core:event:allow-listen", "core:event:allow-unlisten", "service-menu"},
    )
    ipc = read("src-tauri/src/ipc_security.rs")
    self.assertIn('"service-menu" => SERVICE_MENU_COMMANDS.contains(&command)', ipc)
    self.assertIn("!SERVICE_MENU_COMMANDS.contains(&command)", ipc)

  def test_choices_are_bound_to_the_menu_rust_opened(self):
    source = read("src-tauri/src/service_menu.rs")
    self.assertEqual(source.count("require_overlay(&webview)?;"), 3)
    action = source.split("pub(crate) fn service_menu_action", 1)[1].split("#[cfg(test)]", 1)[0]
    # The target service comes from Rust state, never from a renderer-supplied id.
    self.assertNotIn("service_id:", action.split("let menu", 1)[0])
    self.assertIn(".filter(|menu| menu.id == id)", action)
    self.assertIn("menu.permits(action)", action)

  def test_every_platform_restacks_the_overlay_above_services(self):
    source = read("src-tauri/src/service_menu.rs")
    raise_fn = source.split("fn raise(", 1)[1].split("fn create(", 1)[0]
    self.assertIn("reorder_overlay(&view, -1)", raise_fn)
    self.assertIn("SetWindowPos", raise_fn)
    self.assertIn("HWND_TOP", raise_fn)
    self.assertIn(".reparent(&window)", raise_fn)
    main = read("src-tauri/src/main.rs")
    self.assertGreaterEqual(len(re.findall(r"service_menu::restack\(", main)), 2)
    for event in ("Resized", "ScaleFactorChanged"):
      self.assertRegex(main, event + r"[^\n]*\n?[^\n]*service_menu::close")
    # Focus loss closes the menu only when another process owns the foreground window; the
    # Windows overlay is a child window, so focusing it must not dismiss the menu.
    self.assertRegex(main, r"Focused\(false\)[^\n]*\n?[^\n]*service_menu::window_focus_lost")

  def test_shell_renders_the_overlay_and_keeps_the_in_window_menu_as_fallback(self):
    app = read("src/App.svelte")
    self.assertIn("openStyledServiceContextMenu(service, event.clientX, event.clientY", app)
    self.assertIn('listen<ServiceMenuActionEvent>("service-menu-action"', app)
    fallback = app.split("function openStyledServiceContextMenu", 1)[1].split("function dismissServiceMenuOverlay", 1)[0]
    self.assertIn("serviceContextMenu = { serviceId: service.id, ...fallback }", fallback)
    self.assertIn("window.__TAURIDIUM_SERVICE_MENU__ ? ServiceMenu", read("src/main.ts"))

  def test_overlay_height_matches_the_fixed_renderer_layout(self):
    rust = read("src-tauri/src/service_menu.rs")
    self.assertIn("const MENU_HEIGHT: f64 = 2.0 * 6.0 + 7.0 * 34.0 + 3.0 * 9.0;", rust)
    svelte = read("src/ServiceMenu.svelte")
    self.assertIn("height: 34px", svelte)
    self.assertIn("margin: 4px 3px", svelte)
    self.assertIn("padding: 5px", svelte)


if __name__ == "__main__":
  unittest.main()
