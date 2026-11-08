"""Immutable executable upstream recipes, bounded discovery and cache isolation."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RecipeSourceTests(unittest.TestCase):
    def test_runtime_recipe_source_is_one_full_commit_not_a_mutable_branch(self):
        source = json.loads((ROOT / "data/recipe-source.json").read_text(encoding="utf-8"))
        self.assertEqual(source["repository"], "ferdium/ferdium-recipes")
        self.assertRegex(source["revision"], r"^[0-9a-f]{40}$")
        for name in ("src-tauri/src/main.rs", "src-tauri/src/local_profile.rs", "src/lib/ui.ts"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("ferdium-recipes/main/", text)
            self.assertNotIn("contents/recipes?ref=main", text)
        native = (ROOT / "src-tauri/src/recipe_source.rs").read_text(encoding="utf-8")
        self.assertIn('include_str!("../../data/recipe-source.json")', native)
        self.assertIn('cache_root.join("remote-recipes").join(revision())', native)
        main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
        cache = main.split("fn recipe_cache_directory", 1)[1].split("fn recipe_catalog_cache_path", 1)[0]
        self.assertIn(".app_cache_dir()", cache)
        self.assertNotIn(".app_data_dir()", cache)
        self.assertEqual(main.count("recipe_source::read_cache_with_legacy("), 3)

    def test_response_consumers_do_not_bypass_the_shared_stream_budget(self):
        for file in (ROOT / "src-tauri/src").glob("*.rs"):
            source = file.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"\.(?:bytes|text|json(?:::[^()]+)?)\(\)\s*\.await", source), file.name)
