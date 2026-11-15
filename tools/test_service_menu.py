"""Preserve the service menu's presentation and native authority boundaries."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ServiceMenuBoundaryTests(unittest.TestCase):
  def test_the_styled_menu_is_not_left_behind_the_native_service_in_the_shell(self):
    app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
    renderer = (ROOT / "src/ServiceMenu.svelte").read_text(encoding="utf-8")
    self.assertNotIn('class="service-context-menu"', app)
    self.assertIn('class="service-context-menu"', renderer)
    self.assertIn('width: 226px', renderer)
    for action in ('settings', 'reload', 'zoom-in', 'zoom-out', 'zoom-reset', 'duplicate', 'toggle'):
      self.assertIn(f'choose("{action}")', renderer)
    self.assertIn('prettyServiceContextMenu', app)
    self.assertIn('popupNativeServiceContextMenu', app)

  def test_the_popup_has_an_exact_local_capability(self):
    value = json.loads((ROOT / "src-tauri/capabilities/service-menu.json").read_text(encoding="utf-8"))
    self.assertEqual(value['webviews'], ['service-menu'])
    self.assertEqual(set(value['permissions']), {'core:event:allow-listen', 'core:event:allow-unlisten', 'service-menu'})
    self.assertNotIn('remote', value)
    self.assertNotIn('windows', value)


if __name__ == '__main__':
  unittest.main()
