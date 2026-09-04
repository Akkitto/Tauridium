#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.7.7 workspace creation, About routing, and service icons."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
API_TEST = (ROOT / "src/lib/api.test.ts").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
ICONS = (ROOT / "src-tauri/src/icons.rs").read_text(encoding="utf-8")


class Patch0707Tests(unittest.TestCase):
  def test_new_services_join_the_current_workspace_before_activation(self) -> None:
    activate = APP.split("async function activateCreated", 1)[1].split(
      "function openCustomWebsite", 1
    )[0]
    self.assertIn("if (created && activeWorkspace)", activate)
    self.assertIn(
      "const workspace = workspaces.find((candidate) => candidate.id === activeWorkspace);",
      activate,
    )
    self.assertIn("const members = [...workspace.services, created.id];", activate)
    self.assertIn("await updateWorkspace(workspace.id, workspace.name, members);", activate)
    self.assertLess(
      activate.index("await updateWorkspace(workspace.id, workspace.name, members);"),
      activate.index("selectService(created);"),
    )

  def test_about_menu_starts_with_about_and_routes_to_settings_about_tab(self) -> None:
    menu = MAIN.split("let about_item", 1)[1].split("Menu::with_items(", 1)[0]
    self.assertIn('"open-about"', menu)
    self.assertIn('"About"', menu)
    self.assertLess(menu.index("&about_item"), menu.index("&project_homepage"))
    self.assertIn('"open-about" => {', MAIN)
    self.assertIn('let _ = app.emit("open-about", ());', MAIN)
    self.assertIn('listen("open-about", openAbout)', APP)
    open_about = APP.split("function openAbout()", 1)[1].split(
      "async function openProjectLink", 1
    )[0]
    self.assertIn('settingsTab = "about";', open_about)
    self.assertIn('view = "appSettings";', open_about)

  def test_service_settings_accept_website_or_direct_icon_source_urls(self) -> None:
    for marker in (
      "Custom icon source URL",
      'placeholder="example.com or https://example.com/path/icon.svg"',
      "void assignServiceIconFromUrl();",
      "Use icon",
      "ordinary website URL",
      "direct HTTP(S) image URL",
    ):
      self.assertIn(marker, APP)

    self.assertIn(
      'return invoke("fetch_service_icon_url", { serviceId, url });',
      API,
    )
    self.assertIn(
      'expect(mocks.invoke).toHaveBeenCalledWith("fetch_service_icon_url"',
      API_TEST,
    )
    self.assertIn("async fn fetch_service_icon_url(", MAIN)
    self.assertIn('fetch_icon_url(client, raw_url, "service icon source").await', ICONS)

  def test_custom_icon_failure_is_audited_and_restores_default_icon(self) -> None:
    command = MAIN.split("async fn fetch_service_icon_url", 1)[1].split(
      "fn hide_service_webviews", 1
    )[0]
    self.assertIn('"service-icon"', command)
    self.assertIn('"custom-source"', command)
    self.assertIn('"failure"', command)
    self.assertIn(
      '"Custom service icon source failed; default icon fallback selected"',
      command,
    )

    fetch = ICONS.split("pub(crate) async fn fetch_service_icon_url", 1)[1].split(
      "async fn discover_icon", 1
    )[0]
    self.assertIn("let _ = fs::remove_file(&path);", fetch)

    action = APP.split("async function assignServiceIconFromUrl", 1)[1].split(
      "function hydrateServiceIcons", 1
    )[0]
    self.assertIn("serviceIcons = remainingIcons;", action)
    self.assertIn("await updateService(serviceId, { useFavicon: false });", action)
    self.assertIn("The service is using its default icon.", action)

  def test_incompatible_image_payloads_are_rejected_before_caching(self) -> None:
    self.assertIn("fn image_bytes_look_compatible(", ICONS)
    self.assertIn(
      'Website icon uses incompatible or invalid image data ({mime})',
      ICONS,
    )
    self.assertIn(
      "icon_payload_validation_rejects_declared_images_with_incompatible_bytes",
      ICONS,
    )


if __name__ == "__main__":
  unittest.main()
