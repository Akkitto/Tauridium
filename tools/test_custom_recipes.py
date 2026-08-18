from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CustomRecipeReleaseTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    cls.recipes = (ROOT / "src-tauri/src/recipes.rs").read_text(encoding="utf-8")
    cls.profile = (ROOT / "src-tauri/src/local_profile.rs").read_text(encoding="utf-8")
    cls.app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
    cls.api = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")

  def test_bundled_recipe_endpoints_are_present(self) -> None:
    for recipe_id, url in {
      "nanogpt": "https://nano-gpt.com/chat",
      "chutes": "https://chutes.ai/chat",
      "opencode": "http://127.0.0.1:4096",
      "custom-website": "https://example.com",
    }.items():
      self.assertIn(f'"{recipe_id}"', self.recipes)
      self.assertIn(f'"{url}"', self.recipes)

  def test_bundled_ids_win_over_manual_custom_folders(self) -> None:
    body = self.recipes.split("pub(crate) fn local_recipe_config", 1)[1].split(
      "pub(crate) fn local_webview_js", 1
    )[0]
    self.assertLess(body.index("bundled_recipe(recipe_id)"), body.index("custom_recipe_package"))
    self.assertIn("if is_bundled_recipe(recipe_id)", self.recipes)

  def test_remote_catalog_id_is_owned_before_recipe_move(self) -> None:
    body = self.recipes.split("pub(crate) fn merge_catalog", 1)[1].split(
      "fn write_optional_file", 1
    )[0]
    self.assertIn(".map(str::to_owned)", body)
    self.assertIn("validate_recipe_id(&id)", body)
    self.assertIn("merged.insert(id, recipe)", body)
    self.assertNotIn("merged.insert(id.to_string(), recipe)", body)

  def test_recipe_files_use_configuration_directory(self) -> None:
    self.assertIn("app_config_dir()", self.recipes)
    self.assertIn('const CUSTOM_RECIPE_DIR: &str = "recipes"', self.recipes)
    self.assertIn('const PACKAGE_FILE: &str = "package.json"', self.recipes)

  def test_recipe_writes_use_package_as_last_discovery_marker(self) -> None:
    body = self.recipes.split("fn save_recipe_files", 1)[1].split(
      "pub(crate) fn save_custom_recipe", 1
    )[0]
    self.assertLess(body.index("write_optional_file(&dir.join(ICON_FILE)"), body.index("write_atomic(&dir.join(PACKAGE_FILE)"))
    self.assertLess(body.index("write_optional_file(&dir.join(WEBVIEW_FILE)"), body.index("write_atomic(&dir.join(PACKAGE_FILE)"))

  def test_imports_are_canonicalized_and_reserved_ids_rejected(self) -> None:
    self.assertIn('package["id"] = Value::String(id.clone())', self.recipes)
    self.assertIn("Recipe id is reserved by Tauridium", self.recipes)

  def test_custom_website_is_created_locally_with_url_in_one_command(self) -> None:
    command = self.main.split("fn create_custom_website_service", 1)[1].split(
      "// Delete a service", 1
    )[0]
    self.assertIn('"custom-website".into()', command)
    self.assertIn('serde_json::json!({ "customUrl": url })', command)
    self.assertIn("save_local_profile", command)
    self.assertIn('invoke("create_custom_website_service"', self.api)

  def test_signed_in_local_recipes_do_not_depend_on_server_recipe_ids(self) -> None:
    create = self.main.split("async fn create_service", 1)[1].split(
      "fn create_custom_website_service", 1
    )[0]
    self.assertIn("local_recipe_config", create)
    self.assertIn("is_local_mode(&state) || local_recipe", create)
    self.assertIn("has_local_recipe_service", self.main)
    self.assertIn("local_recipe_services_value", self.profile)

  def test_no_match_ui_has_both_direct_and_reusable_paths(self) -> None:
    self.assertIn("No preset recipe matches.", self.app)
    self.assertIn("Add a custom website", self.app)
    self.assertIn("Create a recipe", self.app)

  def test_gui_exposes_folder_and_package_import(self) -> None:
    self.assertIn("Import folder…", self.app)
    self.assertIn("Import package.json…", self.app)
    self.assertIn('invoke("import_custom_recipe"', self.api)

  def test_recipe_creator_warns_about_webview_script_trust(self) -> None:
    self.assertIn("A recipe webview.js runs inside the loaded website", self.app)
    self.assertIn("Only import or write scripts you trust.", self.app)

  def test_release_versions_are_consistent(self) -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    tauri = json.loads((ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    self.assertEqual(package["version"], "0.3.14")
    self.assertEqual(tauri["version"], "0.3.14")
    cargo = (ROOT / "src-tauri/Cargo.toml").read_text(encoding="utf-8")
    self.assertRegex(cargo, r'(?m)^version = "0\.3\.14"$')


if __name__ == "__main__":
  unittest.main()
