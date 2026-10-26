"""Pin all Tauri producers to identical verified upstream CLI inputs."""
import base64
import hashlib
import json
from pathlib import Path
import unittest
import tomllib

ROOT = Path(__file__).resolve().parents[1]


class BuildToolchainTests(unittest.TestCase):
    def test_published_cli_lock_and_crate_identity_are_exact(self):
        policy = json.loads((ROOT / "data/build-toolchain.json").read_text(encoding="utf-8"))
        self.assertRegex(policy["tauriCli"], r"^2\.\d+\.\d+$")
        self.assertRegex(policy["tauriCliBuild"], r"^2\.\d+\.\d+\+tauridium\.\d+$")
        lock = tomllib.loads((ROOT / "flatpak/tauri-cli.Cargo.lock").read_text(encoding="utf-8"))
        self.assertEqual([p["version"] for p in lock["package"] if p["name"] == "zip"], ["9.0.4"])
        self.assertFalse({"pgp", "ml-dsa"} & {p["name"] for p in lock["package"]})
        self.assertEqual([p["version"] for p in lock["package"] if p["name"] == "tauri-cli"], [policy["tauriCliBuild"]])
        self.assertEqual(hashlib.sha256((ROOT / "flatpak/tauri-cli.Cargo.lock").read_bytes()).hexdigest(),
                         policy["tauriCliLockSha256"])
        flatpak = (ROOT / "flatpak/dev.brani.tauridium.yml").read_text(encoding="utf-8")
        self.assertIn(f'tauri-cli-{policy["tauriCli"]}.crate', flatpak)
        self.assertIn(policy["tauriCliCrateSha256"], flatpak)
        self.assertIn(policy["tauriBundlerCrateSha256"], flatpak)
        for producer in ("tools/init.py", "tools/init.ps1", "packaging/nix/tauri-cli.nix", "flatpak/dev.brani.tauridium.yml"):
            self.assertIn("prepare-tauri-cli.py", (ROOT / producer).read_text(encoding="utf-8"))
        nix = (ROOT / "packaging/nix/tauri-cli.nix").read_text(encoding="utf-8")
        self.assertIn("sha256-" + base64.b64encode(bytes.fromhex(policy["tauriCliCrateSha256"])).decode("ascii"), nix)
        self.assertNotIn("fakeHash", nix)

    def test_builder_compression_stack_has_all_reviewed_security_fixes(self):
        lock = tomllib.loads((ROOT / "flatpak/tauri-cli.Cargo.lock").read_text(encoding="utf-8"))
        minimums = {"zstd": (0, 14, 3), "zstd-safe": (8, 2, 0), "zstd-sys": (2, 1, 2)}
        packages = [package for package in lock["package"] if package["name"] in minimums]
        self.assertEqual({package["name"] for package in packages}, set(minimums))
        for package in packages:
            with self.subTest(package=package["name"], version=package["version"]):
                version = tuple(int(part) for part in package["version"].split("+", 1)[0].split("."))
                self.assertGreaterEqual(version, minimums[package["name"]])

    def test_distribution_and_developer_shell_use_the_same_cli_and_cleanup_builder(self):
        flake = (ROOT / "flake.nix").read_text(encoding="utf-8")
        self.assertEqual(flake.count('pkgs.callPackage ./packaging/nix/tauri-cli.nix'), 2)
        flatpak = (ROOT / "flatpak/dev.brani.tauridium.yml").read_text(encoding="utf-8")
        module = flatpak.split("  - name: tauri-cli", 1)[1].split("  - name: tauridium", 1)[0]
        self.assertIn("cleanup:\n      - /bin/cargo-tauri", module)
