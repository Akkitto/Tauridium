from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SettingsUiReleaseTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
    cls.api = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
    cls.main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")

  def test_all_settings_tabs_remain_available(self) -> None:
    for tab in ("general", "services", "appearance", "privacy", "advanced", "updates", "about"):
      self.assertIn(f'settingsTab === "{tab}"', self.app)

  def test_settings_use_consistent_card_layout(self) -> None:
    self.assertIn('class="panel settings-panel"', self.app)
    self.assertIn('class="settings-content"', self.app)
    self.assertGreaterEqual(self.app.count('class="settings-section"'), 8)
    self.assertGreaterEqual(self.app.count('class="setting-card'), 12)
    self.assertIn("grid-template-columns: minmax(0, 1fr) auto", self.app)
    self.assertIn(".setting-copy", self.app)
    self.assertIn(".setting-description", self.app)

  def test_settings_have_responsive_control_alignment(self) -> None:
    self.assertIn(".setting-control { min-width: 176px", self.app)
    self.assertIn(".setting-card { grid-template-columns: 1fr", self.app)
    self.assertIn(".setting-card-toggle { grid-template-columns: minmax(0, 1fr) auto", self.app)

  def test_every_application_setting_remains_exposed(self) -> None:
    settings_body = self.app.split('{:else if view === "appSettings"}', 1)[1].split('{#snippet row', 1)[0]
    for key in (
      "autostart",
      "startMinimized",
      "theme",
      "accentColor",
      "closeToSystemTray",
      "privateNotifications",
      "showDisabledServices",
      "showServiceName",
      "showMessageBadgeWhenMuted",
      "userAgentPref",
      "sidebarWidth",
      "iconSize",
      "grayscaleServices",
      "grayscaleDim",
      "sidebarServicesLocation",
      "hibernationTimer",
      "preloadServices",
    ):
      self.assertIn(key, settings_body)

  def test_settings_typography_uses_one_desktop_ui_system(self) -> None:
    self.assertIn('system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', self.app)
    self.assertIn('button, input, select, textarea { font-family: inherit; }', self.app)
    self.assertIn('.setting-label {', self.app)
    self.assertIn('.setting-description {', self.app)
    self.assertIn('.section-heading h3 {', self.app)

  def test_about_has_standard_open_source_identity_content(self) -> None:
    for marker in (
      'class="about-logo"',
      'class="about-version"',
      "Source code ↗",
      "Releases ↗",
      "Report an issue ↗",
      "Repository",
      "Issues and feature requests",
      "MIT License",
      "Copyright © 2026 Mathieu Vedie",
      "Maintainer",
      "Contributors ↗",
      "Tauri v2",
      "Ferdium",
    ):
      self.assertIn(marker, self.app)
    self.assertNotIn('<div class="row-toggle"><span>Version</span>', self.app)

  def test_about_uses_native_external_browser_path(self) -> None:
    self.assertIn('invoke("open_external_url", { url })', self.api)
    self.assertIn("fn open_external_url(url: String) -> Result<(), String>", self.main)
    self.assertIn('matches!(parsed.scheme(), "http" | "https")', self.main)
    self.assertIn("open_external(parsed.as_str())", self.main)
    self.assertIn("openExternalUrl(url)", self.app)

  def test_about_link_handlers_are_complete_svelte_expressions(self) -> None:
    about = self.app.split('{:else if settingsTab === "about"}', 1)[1].split('{/if}', 1)[0]
    handlers = [line.strip() for line in about.splitlines() if 'onclick={() => openProjectLink(' in line]
    self.assertEqual(len(handlers), 9)
    for handler in handlers:
      self.assertRegex(
        handler,
        r'onclick=\{\(\) => openProjectLink\("https://[^"]+"\)\s*\}',
        msg=f"Malformed About onclick expression: {handler}",
      )

  def test_about_icon_is_bundled_with_frontend(self) -> None:
    icon = ROOT / "src/assets/tauridium.svg"
    self.assertTrue(icon.is_file())
    self.assertIn('import tauridiumLogo from "./assets/tauridium.svg";', self.app)


if __name__ == "__main__":
  unittest.main()
