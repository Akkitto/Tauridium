"""Source contracts follow feature ownership without reading unrelated data."""
from pathlib import Path
import tempfile
import unittest

from frontend_source import frontend_sources, read_frontend_file


class FrontendSourceTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    (self.root / "src/components").mkdir(parents=True)
    (self.root / "src/lib/controllers").mkdir(parents=True)

  def write(self, name, text):
    path = self.root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

  def test_follows_same_line_component_controller_and_default_imports(self):
    self.write("src/App.svelte", '<script>\nimport Panel from "./components/Panel.svelte"; import { create } from "./lib/controllers/feature.svelte"; import { defaults } from "./lib/appSettingsDefaults";</script>')
    self.write("src/components/Panel.svelte", "<p>Unicode: \u201cPanel\u201d</p>")
    self.write("src/lib/controllers/feature.svelte.ts", "export const create = () => 1;")
    self.write("src/lib/appSettingsDefaults.ts", "export const defaults = {};")
    self.assertEqual(set(frontend_sources(self.root)), {
      "src/App.svelte", "src/components/Panel.svelte",
      "src/lib/controllers/feature.svelte.ts", "src/lib/appSettingsDefaults.ts",
    })
    self.assertIn("\u201cPanel\u201d", read_frontend_file(self.root, "src/components/Panel.svelte"))

  def test_excludes_unreachable_features_and_rejects_direct_selection(self):
    self.write("src/App.svelte", "<p>App</p>")
    self.write("src/components/Unused.svelte", "<p>Unused</p>")
    self.assertEqual(list(frontend_sources(self.root)), ["src/App.svelte"])
    with self.assertRaises(KeyError):
      read_frontend_file(self.root, "src/components/Unused.svelte")

  def test_visits_cyclic_component_imports_once(self):
    self.write("src/App.svelte", 'import Panel from "./components/Panel.svelte";')
    self.write("src/components/Panel.svelte", 'import App from "../App.svelte";')
    self.assertEqual(len(frontend_sources(self.root)), 2)

  def test_excludes_outside_source_and_unrelated_library_imports(self):
    self.write("src/App.svelte", 'import outside from "../outside.svelte"; import api from "./lib/api";')
    (self.root / "outside.svelte").write_bytes(bytes([255]))
    (self.root / "src/lib/api.ts").write_bytes(bytes([255]))
    self.assertEqual(list(frontend_sources(self.root)), ["src/App.svelte"])
