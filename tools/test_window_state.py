#!/usr/bin/env python3
"""Regression coverage for persistent Tauridium main-window geometry/state."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WindowStateTests(unittest.TestCase):
  def setUp(self) -> None:
    self.main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    self.cargo = (ROOT / "src-tauri/Cargo.toml").read_text(encoding="utf-8")
    self.lock = (ROOT / "src-tauri/Cargo.lock").read_text(encoding="utf-8")

  def test_official_window_state_plugin_is_pinned_and_locked(self) -> None:
    self.assertIn('tauri-plugin-window-state = "=2.4.1"', self.cargo)
    self.assertRegex(
      self.lock,
      re.compile(
        r'\[\[package\]\]\nname = "tauri-plugin-window-state"\nversion = "2\.4\.1"'
        r'.*?checksum = "73736611e14142408d15353e21e3cca2f12a3cfb523ad0ce85999b6d2ef1a704"',
        re.S,
      ),
    )
    tauridium = re.search(
      r'\[\[package\]\]\nname = "tauridium"\n.*?(?=\n\[\[package\]\]|\Z)',
      self.lock,
      re.S,
    )
    self.assertIsNotNone(tauridium)
    self.assertIn('"tauri-plugin-window-state"', tauridium.group(0))

  def test_persistence_tracks_geometry_and_window_mode_but_not_visibility(self) -> None:
    body = self.main.split("fn persisted_window_state_flags()", 1)[1].split("\n}", 1)[0]
    for flag in ("SIZE", "POSITION", "MAXIMIZED", "FULLSCREEN"):
      self.assertIn(f"StateFlags::{flag}", body)
    self.assertNotIn("StateFlags::VISIBLE", body)
    self.assertNotIn("StateFlags::DECORATIONS", body)
    self.assertIn("persisted_window_state_tracks_geometry_without_visibility", self.main)

  def test_plugin_is_scoped_to_main_window_and_stable_state_file(self) -> None:
    self.assertIn("tauri_plugin_window_state::Builder::new()", self.main)
    self.assertIn(".with_state_flags(persisted_window_state_flags())", self.main)
    self.assertIn('.with_filter(|label| label == "main")', self.main)
    self.assertIn('.with_filename("window-state.json")', self.main)

  def test_close_to_tray_saves_before_hiding(self) -> None:
    event_body = self.main.split("WindowEvent::CloseRequested { api, .. } => {", 1)[1].split(
      "WindowEvent::", 1
    )[0]
    self.assertIn("save_main_window_state(&handle);", event_body)
    self.assertIn("api.prevent_close();", event_body)
    self.assertIn("let _ = w.hide();", event_body)
    self.assertLess(
      event_body.index("save_main_window_state(&handle);"),
      event_body.index("let _ = w.hide();"),
    )

  def test_tray_toggle_saves_before_hide_and_restores_before_show(self) -> None:
    body = self.main.split("fn toggle_main(app: &AppHandle)", 1)[1].split("\n}\n\n//", 1)[0]
    self.assertIn("save_main_window_state(app);", body)
    self.assertIn("restore_main_window_state(&w);", body)
    self.assertLess(body.index("save_main_window_state(app);"), body.index("let _ = w.hide();"))
    restore = body.index("restore_main_window_state(&w);")
    show = body.index("let _ = w.show();", restore)
    self.assertLess(restore, show)

  def test_show_and_tray_quit_preserve_state(self) -> None:
    show_body = self.main.split("fn show_main(app: &AppHandle)", 1)[1].split(
      "\n}\n\nfn toggle_main", 1
    )[0]
    self.assertIn("if !w.is_visible().unwrap_or(false)", show_body)
    self.assertIn("restore_main_window_state(&w);", show_body)

    quit_body = self.main.split('"quit" => {', 1)[1].split("}", 1)[0]
    self.assertIn("save_main_window_state(app);", quit_body)
    self.assertLess(quit_body.index("save_main_window_state(app);"), quit_body.index("app.exit(0);"))


if __name__ == "__main__":
  unittest.main()
