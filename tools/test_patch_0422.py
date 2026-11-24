#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.4.22 configured-service icon resolution."""

from __future__ import annotations

from frontend_source import read_frontend_file, read_frontend_source

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0422Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.app = read_frontend_source(ROOT)

  def test_resolved_service_icon_honours_per_service_website_icon_preference(self) -> None:
    helper = self.app.split("function preferredWebsiteIcon", 1)[1].split("async function loadServiceIcon", 1)[0]
    self.assertIn("if (service.useFavicon !== true) return null;", helper)
    self.assertIn("return ownValue(serviceIcons, service.id) ?? null;", helper)
    self.assertIn("return preferredWebsiteIcon(service) ?? iconSrc(service);", helper)

  def test_configured_services_use_same_resolved_icon_path_as_sidebar(self) -> None:
    managed = self.app.split('aria-label="Configured services"', 1)[1].split("managed-empty", 1)[0]
    sidebar = read_frontend_file(ROOT, "src/components/ServiceRow.svelte")
    self.assertIn("src={displayedServiceIcon(service)}", managed)
    self.assertNotIn("src={iconSrc(service)}", managed)
    self.assertIn("src={displayedServiceIcon(service)}", sidebar)
    self.assertIn("serviceIconFailed(service)", managed)
    self.assertIn("serviceIconFailed(service)", sidebar)

  def test_enabling_website_icon_preference_hydrates_icon_without_restart(self) -> None:
    persist = read_frontend_file(ROOT, "src/lib/controllers/serviceEditor.svelte.ts").split("async function persistService(", 1)[1].split("// Handlers modify ONLY local state", 1)[0]
    self.assertIn("previous?.useFavicon !== true || !host.preferredWebsiteIcon(s)", persist)
    self.assertIn("appSettings.fetchMissingServiceIcons", persist)
    self.assertIn("void host.loadServiceIcon(s);", persist)

  def test_stale_cached_website_icon_is_ignored_when_preference_is_disabled(self) -> None:
    helper = self.app.split("function preferredWebsiteIcon", 1)[1].split("function displayedServiceIcon", 1)[0]
    self.assertLess(
      helper.index("service.useFavicon !== true"),
      helper.index("ownValue(serviceIcons, service.id)"),
    )


if __name__ == "__main__":
  unittest.main()
