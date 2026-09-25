#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.8.5 per-service page zoom."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
UI = (ROOT / "src/lib/ui.ts").read_text(encoding="utf-8")
UI_TEST = (ROOT / "src/lib/ui.test.ts").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


class ServiceZoomPatchTests(unittest.TestCase):
  def test_zoom_uses_bounded_browser_style_levels_and_shortcuts(self) -> None:
    self.assertIn(
      "SERVICE_ZOOM_LEVELS = [50, 67, 80, 90, 100, 110, 125, 150, 175, 200]",
      UI,
    )
    for action, binding in {
      "zoomIn": "Ctrl+Shift+=",
      "zoomOut": "Ctrl+-",
      "resetZoom": "Ctrl+0",
    }.items():
      self.assertIn(f'{action}: "{binding}"', UI)
      self.assertIn(f'keybindings.insert("{action}".into(), "{binding}".into())', MAIN)
    self.assertIn("steps service zoom through bounded browser-style levels", UI_TEST)

  def test_backend_applies_saved_zoom_without_exposing_remote_ipc(self) -> None:
    create = MAIN.split("async fn create_service_webview", 1)[1].split(
      "struct ServiceViewRequest", 1
    )[0]
    command = MAIN.split("fn set_service_zoom", 1)[1].split(
      "fn get_distribution_info", 1
    )[0]
    self.assertIn("effective_service_zoom_percent", create)
    self.assertIn("webview.set_zoom", create)
    self.assertIn("persist_app_settings", command)
    self.assertIn("previous_percent", command)
    self.assertIn("additionally unable to restore", command)
    self.assertNotIn("core:webview:allow-set-webview-zoom", (ROOT / "src-tauri/capabilities/default.json").read_text(encoding="utf-8"))

  def test_zoom_is_persisted_as_validated_tauridium_local_metadata(self) -> None:
    self.assertIn("serviceZoomLevels: Record<string, number>", API)
    self.assertIn('"serviceZoomLevels".into()', MAIN)
    self.assertIn("validate_service_zoom_levels", MAIN)
    self.assertIn("SERVICE_ZOOM_MIN_PERCENT: u16 = 50", MAIN)
    self.assertIn("SERVICE_ZOOM_MAX_PERCENT: u16 = 200", MAIN)
    self.assertIn("patch_0805_service_zoom_defaults_persist_and_validate_safely", MAIN)

  def test_zoom_is_reachable_and_lifecycle_safe(self) -> None:
    self.assertIn('case "zoomIn": if (activeService)', APP)
    self.assertIn('case "zoomOut": if (activeService)', APP)
    self.assertIn('case "resetZoom": if (activeService)', APP)
    self.assertIn('text: "Reset zoom (100%)"', APP)
    self.assertIn('<div class="set-title">Page zoom</div>', APP)
    self.assertIn("serviceZoomOperations", APP)
    self.assertIn("serviceZoomLevels[newId]", APP)
    self.assertIn("delete serviceZoomLevels[s.id]", APP)
    self.assertIn("page zoom, notifications", README)


if __name__ == "__main__":
  unittest.main()
