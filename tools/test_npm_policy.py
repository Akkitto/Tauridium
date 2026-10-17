"""Real npm negative controls, including npm versions without allowScripts support."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("npm_policy", ROOT / "tools/npm_policy.py")
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


class NpmPolicyTests(unittest.TestCase):
    def test_all_build_paths_disable_lifecycle_hooks(self):
        POLICY.validate(ROOT)
        for name, marker in (
            ("tools/init.py", '["npm", "ci", "--ignore-scripts"]'),
            ("tools/init.ps1", "& npm.cmd ci --ignore-scripts"),
            ("flatpak/dev.brani.tauridium.yml", "npm ci --offline --ignore-scripts --cache="),
            ("packaging/nix/package.nix", 'env.npm_config_ignore_scripts = "true"'),
        ):
            self.assertIn(marker, (ROOT / name).read_text(encoding="utf-8"))

    def test_unexpected_install_hook_is_rejected_before_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (".npmrc", "package.json", "package-lock.json"):
                shutil.copyfile(ROOT / name, root / name)
            lock_path = root / "package-lock.json"
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            lock["packages"]["node_modules/unreviewed"] = {"version": "1.0.0", "hasInstallScript": True}
            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unexpected dependency"):
                POLICY.validate(root)

    @unittest.skipUnless(shutil.which("npm") and shutil.which("node"), "Requires real npm and Node; run inside nix develop or the initialized Windows environment")
    def test_real_npm_never_executes_dependency_installation_hooks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copyfile(ROOT / ".npmrc", root / ".npmrc")
            hook = 'node -e "require(\'fs\').writeFileSync(\'lifecycle-executed\', \'synthetic control\')"'
            package = {"name": "tauridium-lifecycle-control", "version": "1.0.0", "private": True,
                       "scripts": {name: hook for name in ("preinstall", "install", "postinstall", "prepare")}}
            (root / "package.json").write_text(json.dumps(package), encoding="utf-8")
            npm = shutil.which("npm")
            # .cmd cannot be executed directly by subprocess on Windows without a shell.
            prefix = ["cmd.exe", "/d", "/c", npm] if os.name == "nt" else [npm]
            flags = ["--offline", "--no-audit", "--no-fund", "--cache", str(root / "cache")]
            env = {key: value for key, value in os.environ.items() if key.lower() != "npm_config_ignore_scripts"}
            def run(args, extra_env=None):
                subprocess.run(prefix + args + flags, cwd=root, env=env | (extra_env or {}),
                               check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            run(["install", "--package-lock-only", "--ignore-scripts"])
            marker = root / "lifecycle-executed"
            # Positive control: this authored fixture really executes when hooks are enabled.
            run(["ci", "--ignore-scripts=false"])
            self.assertTrue(marker.exists())
            marker.unlink()
            run(["ci", "--ignore-scripts"], {"npm_config_ignore_scripts": "false"})
            self.assertFalse(marker.exists(), "The explicit bootstrap flag must beat an unsafe environment override")
            run(["ci"])
            self.assertFalse(marker.exists(), "The project default must protect ordinary manual npm ci")


@unittest.skipUnless(shutil.which("node"), "Requires Node from the initialized development environment")
class EsbuildProbeTests(unittest.TestCase):
    def run_probe(self, *, version="0.25.12", failure=False, missing=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools").mkdir()
            shutil.copyfile(ROOT / "tools/check_esbuild.mjs", root / "tools/check_esbuild.mjs")
            (root / "package-lock.json").write_text(json.dumps({
                "packages": {"node_modules/esbuild": {"version": "0.25.12"}},
            }), encoding="utf-8")
            if not missing:
                package = root / "node_modules/esbuild"
                package.mkdir(parents=True)
                # Deliberately no bin directory, npm shim or install script.
                body = "throw new Error('synthetic native transform failure')" if failure else (
                    "if (options.loader !== 'js') throw new Error('wrong loader'); return {code: input}"
                )
                (package / "index.js").write_text(
                    "exports.version = " + json.dumps(version) + ";\n"
                    "exports.transformSync = (input, options) => { " + body + " };\n",
                    encoding="utf-8",
                )
            return subprocess.run([shutil.which("node"), str(root / "tools/check_esbuild.mjs")],
                                  cwd=root, capture_output=True, text=True, timeout=30)

    def test_probe_uses_local_api_without_executable_shims(self):
        result = self.run_probe()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("native transform validated", result.stdout)

    def test_probe_rejects_package_version_mismatch(self):
        self.assertNotEqual(self.run_probe(version="0.0.0").returncode, 0)

    def test_probe_propagates_native_transform_failure(self):
        result = self.run_probe(failure=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("synthetic native transform failure", result.stderr)

    def test_probe_cannot_fall_back_to_global_or_registry_package(self):
        self.assertNotEqual(self.run_probe(missing=True).returncode, 0)
