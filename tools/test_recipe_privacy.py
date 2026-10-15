"""Explicit executable-content trust and accurate export privacy boundaries."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RecipePrivacyTests(unittest.TestCase):
    def test_native_script_export_requires_explicit_request_and_has_negative_test(self):
        source = (ROOT / "src-tauri/src/service_export.rs").read_text(encoding="utf-8")
        for marker in ("pub include_sensitive_recipe_scripts: bool",
                       "if include_scripts && !recipe.webview_js.trim().is_empty()",
                       "personal_executable_code_is_excluded_by_default_and_requires_explicit_opt_in",
                       '"personalRecipeScriptsOptIn": request.include_sensitive_recipe_scripts',
                       '"requiresPrivacyReview": true', 'object.retain('):
            self.assertIn(marker, source)
        self.assertNotIn('"secretsRedacted": true', source)

    def test_ui_requires_explicit_import_and_export_trust_and_warns_about_backups(self):
        source = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
        main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
        for marker in ("let serviceExportIncludeSensitiveRecipeScripts = $state(false)",
                       "Import this recipe only if you trust",
                       "This backup contains private service configuration",
                       "This portable export contains private service configuration",
                       "Include personal executable recipe scripts?"):
            self.assertIn(marker, source)
        body = main.split("fn import_custom_recipe(", 1)[1].split("// --- Workspaces", 1)[0]
        self.assertLess(body.index("trusted_code != Some(true)"),
                        body.index("recipes::import_custom_recipe"))
