"""Nix release regression coverage; executed package/VM gates live in the flake."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("nix_smoke", ROOT / "tools/nix_smoke.py")
assert SPEC and SPEC.loader
SMOKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SMOKE)


class NixTests(unittest.TestCase):
  def test_graphical_smoke_requires_rendered_frontend_not_just_native_title(self):
    self.assertFalse(SMOKE.sign_in_screen_rendered("Tauridium Edit View"))
    self.assertFalse(SMOKE.sign_in_screen_rendered("Tauridium Email Password"))
    self.assertTrue(SMOKE.sign_in_screen_rendered("Tauridium\nEmail\nPassword\nUse Tauridium without an account"))
  def test_locked_inputs_and_real_dependency_hashes(self):
    lock = json.loads((ROOT / "flake.lock").read_text())
    for name in ("nixpkgs", "rust-overlay"):
      self.assertEqual(len(lock["nodes"][name]["locked"]["rev"]), 40)
      self.assertTrue(lock["nodes"][name]["locked"]["narHash"].startswith("sha256-"))
    package = (ROOT / "packaging/nix/package.nix").read_text()
    self.assertNotIn("fakeHash", package)
    self.assertIn("wrapGAppsHook3", package)
    self.assertIn('buildNoDefaultFeatures = true;', package)
    self.assertIn('buildFeatures = [ "nix" ];', package)
    self.assertIn("../../vendor", package)
    self.assertNotIn("../../node_modules", package)
    self.assertNotIn("WEBKIT_DISABLE_SANDBOX", package)

  def test_nix_feature_does_not_enable_updater_or_native_autostart(self):
    cargo = (ROOT / "src-tauri/Cargo.toml").read_text()
    feature = cargo.split("\nnix = [", 1)[1].split("]", 1)[0]
    self.assertIn("notification", feature)
    self.assertNotIn("updater", feature)
    self.assertNotIn("autostart", feature)
    self.assertIn("rfd/gtk3", feature)

  def test_release_publication_requires_both_nix_architectures(self):
    release = (ROOT / ".github/workflows/release.yml").read_text()
    self.assertIn("needs: [handoff, build, scoop, nix]", release)
    workflow = (ROOT / ".github/workflows/nix.yml").read_text()
    for marker in ("aarch64-linux", "x86_64-linux", "flake check", ".#smoke", ".#nixos-test"):
      self.assertIn(marker, workflow)

  def test_smoke_rejects_native_and_flatpak_runtime_policies(self):
    for mode in ("native", "flatpak"):
      with self.assertRaises(RuntimeError):
        SMOKE.validate_build_info({"buildMode": "production", "distribution": {"mode": mode}})

  def test_smoke_checks_every_nix_policy_flag(self):
    distribution = {"mode": "nix", "updaterManagedExternally": True}
    flags = ("portalFileAccess", "portalNotifications", "portalAutostart", "downloadsRequireDestination", "automaticBackupsUsePrivateStorage")
    distribution.update({flag: False for flag in flags})
    info = {"buildMode": "production", "distribution": distribution}
    SMOKE.validate_build_info(info)
    for flag in flags:
      with self.subTest(flag=flag), self.assertRaises(RuntimeError):
        SMOKE.validate_build_info({**info, "distribution": {**distribution, flag: True}})
    with self.assertRaises(RuntimeError):
      SMOKE.validate_build_info({**info, "buildMode": "development"})


if __name__ == "__main__":
  unittest.main()
