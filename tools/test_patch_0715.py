#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.7.15 service catalog/export UX fixes."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "App.svelte").read_text(encoding="utf-8")
UI = (ROOT / "src" / "lib" / "ui.ts").read_text(encoding="utf-8")
API = (ROOT / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
RECIPES = (ROOT / "src-tauri" / "src" / "recipes.rs").read_text(encoding="utf-8")
EXPORT = (ROOT / "src-tauri" / "src" / "service_export.rs").read_text(encoding="utf-8")


class Patch0715Tests(unittest.TestCase):
  def test_public_services_are_bundled_with_stable_endpoints_and_icons(self) -> None:
    expected = {
      "arli-ai": "https://www.arliai.com/account?lang=en",
      "porkbun": "https://porkbun.com/",
      "deluxhost": "https://dash.deluxhost.net/en/dashboard",
    }
    for recipe_id, url in expected.items():
      self.assertIn(f'"{recipe_id}"', RECIPES)
      self.assertIn(f'"{url}"', RECIPES)
      self.assertIn(
        f'include_str!("../bundled-recipes/{recipe_id}/icon.svg")',
        RECIPES,
      )
      icon = ROOT / "src-tauri" / "bundled-recipes" / recipe_id / "icon.svg"
      self.assertTrue(icon.is_file(), recipe_id)
      self.assertIn("<svg", icon.read_text(encoding="utf-8"))

  def test_service_export_schema_uses_portable_and_personal_recipe_terms(self) -> None:
    for marker in (
      "const EXPORT_SCHEMA: u32 = 2;",
      "include_all_personal_recipes",
      "portable_recipe_path",
      "portable_recipes",
      "portable_recipe_count",
      "Ferdium recipes",
      "Tauridium built-in recipes",
      "Personal recipes",
      "Custom websites",
    ):
      self.assertIn(marker, EXPORT)
    for obsolete in (
      "include_all_local_recipes",
      "local_recipe_path",
      "local_recipes:",
      "custom_recipe_count",
    ):
      self.assertNotIn(obsolete, EXPORT)
    self.assertIn('"hasCustomUrl": false', EXPORT)

  def test_services_settings_list_is_bounded_scrollable_and_paginated(self) -> None:
    for marker in (
      'class="managed-list service-managed-list"',
      "max-height: min(58vh, 680px);",
      "overflow-y: auto;",
      "overscroll-behavior: contain;",
      "scrollbar-gutter: stable;",
      'aria-label="Configured services pages"',
      "managedServicePageCount",
    ):
      self.assertIn(marker, APP)

  def test_recipe_origin_terminology_is_consistent_and_user_facing(self) -> None:
    for marker in (
      'return "Ferdium recipe";',
      'return "Tauridium built-in";',
      'return "Personal recipe";',
      'if (service.recipeId === "custom-website") return "Custom website";',
      "Include all personal recipes & custom websites",
      "Personal recipe folder:",
      "Personal recipe creator",
      "{recipeSourceLabel(r.source)}",
    ):
      self.assertIn(marker, APP + UI)
    self.assertIn("includeAllPersonalRecipes", API)
    self.assertIn("portableRecipeCount", API)

  def test_service_export_selection_uses_the_whole_noninteractive_row(self) -> None:
    for marker in (
      'class="managed-row service-export-row"',
      '<label class="managed-identity service-export-identity service-export-toggle">',
      'onchange={(event) => setServiceExportSelected(service.id, event.currentTarget.checked)}',
      '.service-export-toggle {',
    ):
      self.assertIn(marker, APP)
    self.assertNotIn("toggleServiceExportFromRow", APP)



if __name__ == "__main__":
  unittest.main()
