"""Regression coverage for Tauridium 0.4.12 stale icon-request cleanup."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Patch0412Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    cls.api = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")

  def test_service_icon_request_contains_only_runtime_used_fields(self) -> None:
    block = self.main.split("struct ServiceIconRequest {", 1)[1].split("}\n\n#[tauri::command]", 1)[0]
    self.assertNotIn("is_local_recipe", block)
    for field in (
      "service_id: String",
      "recipe_id: String",
      "custom_url: Option<String>",
      "team: Option<String>",
      "prefer_website_icon: bool",
    ):
      self.assertIn(field, block)

  def test_frontend_does_not_send_removed_icon_request_field(self) -> None:
    block = self.api.split("export function getServiceIcon(", 1)[1].split("export function copyServiceIconCache", 1)[0]
    self.assertNotIn("isLocalRecipe", block)
    self.assertIn("preferWebsiteIcon", block)


if __name__ == "__main__":
  unittest.main()
