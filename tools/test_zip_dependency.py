"""No withdrawn ZIP parser in the application or its Windows updater feature."""
from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ZipDependencyTests(unittest.TestCase):
  def test_runtime_and_windows_updater_use_the_exact_maintained_parser(self):
    lock = tomllib.loads((ROOT / "src-tauri/Cargo.lock").read_text(encoding="utf-8"))
    self.assertEqual([row["version"] for row in lock["package"] if row["name"] == "zip"], ["9.1.2"])
    plugin = tomllib.loads((ROOT / "vendor/tauri-plugin-updater/Cargo.toml").read_text(encoding="utf-8"))
    dependency = plugin["target"]['cfg(target_os = "windows")']["dependencies"]["zip"]
    self.assertEqual(dependency, {"version": "=9.1.2", "optional": True, "default-features": False})
    self.assertIn("TAURIDIUM-PATCH.md", [path.name for path in (ROOT / "vendor/tauri-plugin-updater").iterdir()])


if __name__ == "__main__":
  unittest.main()
