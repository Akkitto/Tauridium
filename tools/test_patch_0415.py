"""Regression coverage for Tauridium 0.4.15 Rust settings defaults."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUST = (ROOT / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")
APP = (ROOT / "src" / "App.svelte").read_text(encoding="utf-8")


class Patch0415Tests(unittest.TestCase):
  def test_default_settings_avoid_large_recursive_json_macro(self) -> None:
    block = RUST.split("fn default_app_settings_value() -> Value {", 1)[1].split(
      "\nfn is_hex_color", 1
    )[0]
    self.assertIn("let mut settings = serde_json::Map::<String, Value>::new();", block)
    self.assertIn("Value::Object(settings)", block)
    self.assertNotIn("#![recursion_limit", RUST)
    self.assertNotIn("serde_json::json!", block)

  def test_default_settings_preserve_critical_0414_values(self) -> None:
    block = RUST.split("fn default_app_settings_value() -> Value {", 1)[1].split(
      "\nfn is_hex_color", 1
    )[0]
    for marker in (
      'settings.insert("autostart".into(), false.into());',
      'settings.insert("theme".into(), "system".into());',
      'settings.insert("accentColor".into(), "#ffc131".into());',
      'settings.insert("captureServiceShortcuts".into(), true.into());',
      'settings.insert("automaticBackupRetention".into(), 10.into());',
      'settings.insert("lastAutomaticBackupAt".into(), 0.into());',
    ):
      self.assertIn(marker, block)

  def test_stale_searchrow_css_is_removed(self) -> None:
    self.assertNotIn(".searchrow {", APP)
    self.assertNotIn(".searchrow input {", APP)


if __name__ == "__main__":
  unittest.main()
