#!/usr/bin/env python3
"""Regression coverage for persistent Tauridium main-window geometry/state."""

from __future__ import annotations

import re
import shutil
import tempfile
import json
import window_state_policy
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WindowStateTests(unittest.TestCase):
  def setUp(self) -> None:
    self.main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    self.cargo = (ROOT / "src-tauri/Cargo.toml").read_text(encoding="utf-8")
    self.lock = (ROOT / "src-tauri/Cargo.lock").read_text(encoding="utf-8")

  def test_official_window_state_plugin_is_pinned_and_locked(self) -> None:
    self.assertIn('tauri-plugin-window-state = "=2.5.0"', self.cargo)
    import window_state_policy
    provenance = window_state_policy.validate(ROOT)
    self.assertEqual(provenance["upstream"]["sha256"], window_state_policy.UPSTREAM_SHA256)
    self.assertIn(".with_outer_size(cfg!(windows))", self.main)
    tauridium = re.search(
      r'\[\[package\]\]\nname = "tauridium"\n.*?(?=\n\[\[package\]\]|\Z)',
      self.lock,
      re.S,
    )
    self.assertIsNotNone(tauridium)
    self.assertIn('"tauri-plugin-window-state"', tauridium.group(0))


  def test_window_state_lockfile_preserves_valid_errno_resolution(self) -> None:
    self.assertRegex(
      self.lock,
      re.compile(
        r'\[\[package\]\]\nname = "errno"\nversion = "0\.3\.14"\n'
        r'source = "registry\+https://github\.com/rust-lang/crates\.io-index"\n'
        r'checksum = "39cab71617ae0d63f51a36d69f866391735b51691dbda63cf6f96d042b63efeb"',
      ),
    )
    self.assertNotRegex(
      self.lock,
      re.compile(
        r'name = "errno"\nversion = "0\.3\.13"\n.*?'
        r'checksum = "39cab71617ae0d63f51a36d69f866391735b51691dbda63cf6f96d042b63efeb"',
        re.S,
      ),
    )

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

  def test_tray_toggle_saves_before_hide_and_reveals_without_replaying_restore(self) -> None:
    body = self.main.split("fn toggle_main(app: &AppHandle)", 1)[1].split("\n}\n\n//", 1)[0]
    self.assertIn("save_main_window_state(app);", body)
    self.assertLess(body.index("save_main_window_state(app);"), body.index("let _ = w.hide();"))
    self.assertIn("show_main(app);", body)
    self.assertNotIn("restore_main_window_state", body)
    self.assertNotIn("restore_state(", body)

  def test_show_and_tray_quit_preserve_state_without_duplicate_restore(self) -> None:
    show_body = self.main.split("fn show_main(app: &AppHandle)", 1)[1].split(
      "\n}\n\nfn toggle_main", 1
    )[0]
    self.assertIn("let _ = w.show();", show_body)
    self.assertIn("let _ = w.set_focus();", show_body)
    self.assertNotIn("restore_main_window_state", show_body)
    self.assertNotIn("restore_state(", show_body)
    self.assertNotIn("fn restore_main_window_state", self.main)

    quit_body = self.main.split('"quit" => {', 1)[1].split("}", 1)[0]
    self.assertIn("save_main_window_state(app);", quit_body)
    self.assertLess(quit_body.index("save_main_window_state(app);"), quit_body.index("app.exit(0);"))


class WindowStateRepairIntegrityTests(unittest.TestCase):
  def fixture(self, temporary):
    directory = Path(temporary)
    for name in ("src-tauri/Cargo.toml", "src-tauri/Cargo.lock"):
      path = directory / name
      path.parent.mkdir(parents=True, exist_ok=True)
      shutil.copyfile(ROOT / name, path)
    shutil.copytree(ROOT / window_state_policy.RELATIVE, directory / window_state_policy.RELATIVE)
    return directory

  def test_changed_source_fails_without_a_reviewed_hash_update(self):
    with tempfile.TemporaryDirectory() as temporary:
      directory = self.fixture(temporary)
      source = directory / window_state_policy.RELATIVE / "src/lib.rs"
      source.write_text(source.read_text(encoding="utf-8") + "\n// changed source\n", encoding="utf-8")
      with self.assertRaisesRegex(ValueError, "integrity"):
        window_state_policy.validate(directory)

  def test_changing_the_upstream_identity_is_rejected(self):
    with tempfile.TemporaryDirectory() as temporary:
      directory = self.fixture(temporary)
      provenance = directory / window_state_policy.RELATIVE / "TAURIDIUM-PATCH.json"
      value = json.loads(provenance.read_text(encoding="utf-8"))
      value["upstream"]["sha256"] = "0" * 64
      provenance.write_text(json.dumps(value), encoding="utf-8")
      with self.assertRaisesRegex(ValueError, "upstream provenance"):
        window_state_policy.validate(directory)

  def test_replacing_the_reviewed_path_with_registry_source_is_rejected(self):
    with tempfile.TemporaryDirectory() as temporary:
      directory = self.fixture(temporary)
      lock = directory / "src-tauri/Cargo.lock"
      source = lock.read_text(encoding="utf-8").replace('version = "2.5.0+tauridium.1"', 'version = "2.5.0+tauridium.1"\nsource = "registry+https://github.com/rust-lang/crates.io-index"')
      lock.write_text(source, encoding="utf-8")
      with self.assertRaisesRegex(ValueError, "lock identity"):
        window_state_policy.validate(directory)


if __name__ == "__main__":
  unittest.main()
