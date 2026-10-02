#!/usr/bin/env python3
"""Regression coverage for native HTML5 file drops in service webviews."""

from pathlib import Path
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")


class ServiceFileDropTests(unittest.TestCase):
  def test_every_service_builder_preserves_browser_file_drops(self) -> None:
    source = re.sub(r"//[^\n]*", "", MAIN)
    builders = re.findall(r"WebviewBuilder::new\([^\n]+\)(.*?);", source, re.S)
    self.assertTrue(builders, "Service webview creation must be covered")
    for builder in builders:
      self.assertIn(".disable_drag_drop_handler()", builder)
    create = MAIN.split("async fn create_service_webview", 1)[1].split(
      "struct ServiceViewRequest", 1
    )[0]
    self.assertNotIn("#[cfg", create.split(".disable_drag_drop_handler()", 1)[0])

  def test_active_and_preloaded_views_use_the_same_drop_policy(self) -> None:
    for name in ("show_service", "preload_service"):
      command = MAIN.split(f"async fn {name}(", 1)[1].split("#[tauri::command]", 1)[0]
      self.assertIn("create_service_webview(", command)
    config = json.loads((ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    main = next(window for window in config["app"]["windows"] if window["label"] == "main")
    self.assertIs(main["dragDropEnabled"], False)

  def test_native_drop_smoke_test_checks_real_files_and_trusted_events(self) -> None:
    smoke = (ROOT / "tools/service_file_drop_smoke.py").read_text(encoding="utf-8")
    fixture = (ROOT / "tools/fixtures/file-drop.html").read_text(encoding="utf-8")
    self.assertIn("text/uri-list", smoke)
    self.assertIn("mousedown", smoke)
    self.assertIn("sha256", smoke)
    self.assertIn("isTrusted", fixture)
    self.assertIn("event.dataTransfer.files", fixture)
    self.assertIn("file.arrayBuffer()", fixture)
    self.assertNotIn("new DragEvent", fixture)
    self.assertNotIn("new File(", fixture)


if __name__ == "__main__":
  unittest.main()
