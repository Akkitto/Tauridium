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

    def test_local_backport_rejects_tampering_or_bypassed_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (".npmrc", "package.json", "package-lock.json"):
                shutil.copyfile(ROOT / name, root / name)
            shutil.copytree(ROOT / "vendor/deepmerge", root / "vendor/deepmerge")
            POLICY.validate(root)
            runtime = root / "vendor/deepmerge/dist/cjs.js"
            original = runtime.read_bytes()
            runtime.write_bytes(original + b"\n// synthetic tampering\n")
            with self.assertRaisesRegex(ValueError, "integrity mismatch"):
                POLICY.validate(root)
            runtime.write_bytes(original)
            manifest = root / "package.json"
            data = json.loads(manifest.read_text(encoding="utf-8"))
            del data["overrides"]["deepmerge"]
            manifest.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "override is required"):
                POLICY.validate(root)

    @unittest.skipUnless(shutil.which("git"), "Requires Git checkout conversion")
    def test_windows_checkout_preserves_integrity_bound_vendor_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copyfile(ROOT / ".gitattributes", root / ".gitattributes")
            shutil.copytree(ROOT / "vendor/deepmerge", root / "vendor/deepmerge")
            manifest = json.loads((root / "vendor/deepmerge/TAURIDIUM-PATCH.json").read_text(encoding="utf-8"))
            expected = {name: (root / "vendor/deepmerge" / name).read_bytes() for name in manifest["files"]}
            command = [shutil.which("git"), "-c", "core.autocrlf=true", "-c", "core.safecrlf=false"]
            for args in (["init", "--quiet"], ["add", "--force", ".gitattributes", "vendor/deepmerge"],
                         ["checkout-index", "--force", "--all"]):
                subprocess.run(command + args, cwd=root, check=True, capture_output=True, timeout=30)
            for name, content in expected.items():
                with self.subTest(name=name):
                    self.assertEqual((root / "vendor/deepmerge" / name).read_bytes(), content)

    def test_local_lock_rejects_other_links_and_second_registry_merger(self):
        original = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))["packages"]
        for path, entry in (
            ("node_modules/unknown", {"link": True, "resolved": "../outside"}),
            ("node_modules/plugin/node_modules/deepmerge", {"version": "4.3.1", "resolved": "https://registry.npmjs.org/deepmerge/-/deepmerge-4.3.1.tgz"}),
            ("node_modules/deepmerge", {"link": True, "resolved": "../vendor/deepmerge"}),
        ):
            with self.subTest(path=path):
                packages = original | {path: entry}
                with self.assertRaises(ValueError):
                    POLICY.validate_local_lock(packages)

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
class FrontendNativeProbeTests(unittest.TestCase):
    def run_probe(self, *, version="1.2.15", binding_version="1.2.15", failure=None, missing=None, extra_env=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools").mkdir()
            shutil.copyfile(ROOT / "tools/check_frontend.mjs", root / "tools/check_frontend.mjs")
            # The real merger security suite has its own integration tests.
            (root / "tools/check_deepmerge.mjs").write_text("export async function checkInstallation() {}", encoding="utf-8")
            versions = {"rolldown": "1.2.15", "lightningcss": "1.33.0"}
            for platform in ("linux-x64-gnu", "linux-x64-musl", "linux-arm64-gnu", "linux-arm64-musl",
                             "win32-x64-msvc", "win32-arm64-msvc", "darwin-x64", "darwin-arm64"):
                versions["@rolldown/binding-" + platform] = "1.2.15"
                versions["lightningcss-" + platform] = "1.33.0"
            (root / "package-lock.json").write_text(json.dumps({
                "packages": {"node_modules/" + name: {"version": value} for name, value in versions.items()},
            }), encoding="utf-8")
            for name, value in versions.items():
                if missing == name or missing == "native" and "binding-" in name:
                    continue
                package = root / "node_modules" / name
                package.mkdir(parents=True)
                actual_version = version if name == "rolldown" else binding_version if "binding-" in name else value
                (package / "package.json").write_text(json.dumps({
                    "name": name, "version": actual_version, "main": "index.js",
                }), encoding="utf-8")
                (package / "index.js").write_text("module.exports = {};", encoding="utf-8")
            if missing != "rolldown":
                dist = root / "node_modules/rolldown/dist"
                dist.mkdir()
                (dist / "index.mjs").write_text("export const VERSION = " + json.dumps(version) + ";", encoding="utf-8")
                transform = ("throw new Error('synthetic JavaScript transform failure');" if failure == "javascript" else
                             "if (options.lang !== 'ts' || !input.includes(': number')) throw new Error('wrong transform input'); "
                             "return {errors: [], code: 'const tauridiumCheck = 1 + 2;\\n'};")
                (dist / "utils-index.mjs").write_text(
                    "export function transformSync(filename, input, options) { " + transform + " }", encoding="utf-8")
            if missing != "lightningcss":
                transform = ("throw new Error('synthetic CSS transform failure');" if failure == "css" else
                             "if (!options.minify || !options.code.toString().includes('#ff0000')) throw new Error('wrong CSS input'); "
                             "return {code: Buffer.from('.tauridium-check{color:red}')};")
                (root / "node_modules/lightningcss/index.js").write_text(
                    "exports.transform = (options) => { " + transform + " };", encoding="utf-8")
            env = {key: value for key, value in os.environ.items() if not key.startswith("NAPI_RS_")}
            return subprocess.run([shutil.which("node"), str(root / "tools/check_frontend.mjs")],
                                  cwd=root, env=env | (extra_env or {}), capture_output=True, text=True, timeout=30)

    def test_probe_uses_local_native_apis_without_executable_shims(self):
        result = self.run_probe()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("native transforms validated", result.stdout)

    def test_probe_rejects_package_or_native_binding_version_mismatch(self):
        self.assertNotEqual(self.run_probe(version="0.0.0").returncode, 0)
        self.assertNotEqual(self.run_probe(binding_version="0.0.0").returncode, 0)

    def test_probe_propagates_javascript_and_css_native_transform_failures(self):
        for failure in ("javascript", "css"):
            with self.subTest(failure=failure):
                result = self.run_probe(failure=failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("synthetic", result.stderr)

    def test_probe_cannot_fall_back_to_global_or_registry_packages(self):
        for missing in ("rolldown", "lightningcss", "native"):
            with self.subTest(missing=missing):
                self.assertNotEqual(self.run_probe(missing=missing).returncode, 0)

    def test_probe_refuses_external_native_binding_and_wasm_overrides(self):
        for name in ("NAPI_RS_NATIVE_LIBRARY_PATH", "NAPI_RS_FORCE_WASI", "NAPI_RS_WASI_FLAVOR"):
            with self.subTest(name=name):
                self.assertNotEqual(self.run_probe(extra_env={name: "synthetic-control"}).returncode, 0)

    def test_runtime_check_rejects_unsupported_versions_before_loading_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            probe = Path(directory) / "check_frontend.mjs"
            shutil.copyfile(ROOT / "tools/check_frontend.mjs", probe)
            for version, supported in (("20.19.0", False), ("22.11.0", False), ("22.12.0", True),
                                       ("23.0.0", False), ("24.0.0", True), ("25.0.0", False), ("26.0.0", True)):
                with self.subTest(version=version):
                    source = ("Object.defineProperty(process.versions, 'node', {value: " + json.dumps(version) + "}); "
                              "process.argv.push('--runtime-only'); await import(" + json.dumps(probe.as_uri()) + ");")
                    result = subprocess.run([shutil.which("node"), "--input-type=module", "-e", source],
                                            capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode == 0, supported, result.stderr)
