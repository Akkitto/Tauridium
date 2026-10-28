"""Exercise the installed backport and an independent vulnerable positive control."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
GUARD = ROOT / "tools/check_deepmerge.mjs"


@unittest.skipUnless(NODE, "Requires Node from the initialized development environment")
class DeepmergeSecurityTests(unittest.TestCase):
    def run_module(self, source):
        return subprocess.run([NODE, "--input-type=module", "-e", source], cwd=ROOT,
                              capture_output=True, text=True, timeout=60)

    @unittest.skipUnless((ROOT / "node_modules/@sveltejs/vite-plugin-svelte/package.json").exists(),
                         "Requires installed locked frontend dependencies")
    def test_actual_svelte_dependency_is_patched_and_compatible(self):
        result = subprocess.run([NODE, str(GUARD)], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("actual Svelte resolution", result.stdout)

    def test_security_controls_detect_returned_object_prototype_poisoning(self):
        # This independent vulnerable operation demonstrates the same returned-object
        # boundary: Object.prototype stays intact while the merged object inherits data.
        source = "import { checkPrototypeSafety } from " + json.dumps(GUARD.as_uri()) + ";\n" + r"""
const vulnerable = (target, source) => Object.assign({}, target, source);
const body = JSON.parse('{"__proto__":{"tauridiumPrototypePoison":true}}');
const result = vulnerable(null, body);
if (result.tauridiumPrototypePoison !== true || Object.hasOwn(result, 'tauridiumPrototypePoison')
    || ({}).tauridiumPrototypePoison !== undefined) throw new Error('Invalid vulnerable control');
checkPrototypeSafety(vulnerable);
"""
        result = self.run_module(source)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("returned prototype changed", result.stderr)

    def test_nested_registry_copy_cannot_replace_the_reviewed_backport(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools").mkdir()
            shutil.copyfile(GUARD, root / "tools/check_deepmerge.mjs")
            shutil.copytree(ROOT / "vendor/deepmerge", root / "vendor/deepmerge")
            (root / "package.json").write_text('{"name":"tauridium-resolution-control","private":true}', encoding="utf-8")
            plugin = root / "node_modules/@sveltejs/vite-plugin-svelte"
            plugin.mkdir(parents=True)
            (plugin / "package.json").write_text('{"name":"@sveltejs/vite-plugin-svelte","main":"index.js"}', encoding="utf-8")
            (plugin / "index.js").write_text("module.exports = {};", encoding="utf-8")
            nested = plugin / "node_modules/deepmerge"
            nested.mkdir(parents=True)
            (nested / "package.json").write_text('{"name":"deepmerge","version":"4.3.1","main":"index.js"}', encoding="utf-8")
            (nested / "index.js").write_text("throw new Error('Unreviewed dependency must never execute');", encoding="utf-8")
            result = subprocess.run([NODE, str(root / "tools/check_deepmerge.mjs")], cwd=root,
                                    capture_output=True, text=True, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Svelte must resolve the explicit patched dependency", result.stderr)
            self.assertNotIn("Error: Unreviewed dependency must never execute", result.stderr)

    def test_symbol_keys_are_not_confused_with_reserved_string_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "symbols.cjs"
            fixture.write_text("module.exports = require(" + json.dumps(str(ROOT / "vendor/deepmerge/dist/cjs.js")) + ");",
                               encoding="utf-8")
            source = "import { createRequire } from 'node:module';\n" + \
                     "import { checkCompatibility } from " + json.dumps(GUARD.as_uri()) + ";\n" + \
                     "checkCompatibility(createRequire(import.meta.url)(" + json.dumps(str(fixture)) + "));"
            result = self.run_module(source)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
