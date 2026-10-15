"""Pin all Tauri producers to identical verified upstream CLI inputs."""
import base64
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BuildToolchainTests(unittest.TestCase):
    def test_published_cli_lock_and_crate_identity_are_exact(self):
        policy = json.loads((ROOT / "data/build-toolchain.json").read_text(encoding="utf-8"))
        self.assertRegex(policy["tauriCli"], r"^2\.\d+\.\d+$")
        self.assertEqual(hashlib.sha256((ROOT / "flatpak/tauri-cli.Cargo.lock").read_bytes()).hexdigest(),
                         policy["tauriCliLockSha256"])
        flatpak = (ROOT / "flatpak/dev.brani.tauridium.yml").read_text(encoding="utf-8")
        self.assertIn(f'tauri-cli-{policy["tauriCli"]}.crate', flatpak)
        self.assertIn(policy["tauriCliCrateSha256"], flatpak)
        nix = (ROOT / "packaging/nix/tauri-cli.nix").read_text(encoding="utf-8")
        self.assertIn("sha256-" + base64.b64encode(bytes.fromhex(policy["tauriCliCrateSha256"])).decode("ascii"), nix)
        self.assertNotIn("fakeHash", nix)

    def test_distribution_and_developer_shell_use_the_same_cli_and_cleanup_builder(self):
        flake = (ROOT / "flake.nix").read_text(encoding="utf-8")
        self.assertEqual(flake.count('pkgs.callPackage ./packaging/nix/tauri-cli.nix'), 2)
        flatpak = (ROOT / "flatpak/dev.brani.tauridium.yml").read_text(encoding="utf-8")
        module = flatpak.split("  - name: tauri-cli", 1)[1].split("  - name: tauridium", 1)[0]
        self.assertIn("cleanup:\n      - /bin/cargo-tauri", module)
