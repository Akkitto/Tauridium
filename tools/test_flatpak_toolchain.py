"""The Flatpak producer uses the reviewed compiler without shipping build tools."""
from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest
from unittest import mock

import flatpak_build as build

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("flatpak_rust_toolchain", ROOT / "flatpak/check-rust-toolchain.py")
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class FlatpakRustToolchainTests(unittest.TestCase):
  def test_exact_official_component_cohort_matches_canonical_rust(self):
    version = tomllib.loads((ROOT / "rust-toolchain.toml").read_text(encoding="utf-8"))["toolchain"]["channel"]
    self.assertEqual(PROBE.VERSION, version)
    module = json.loads((ROOT / "flatpak/rust-toolchain.json").read_text(encoding="utf-8"))
    expected = {
      ("rustc", "x86_64"): "9819d0a32d56bd339585319c80260e332779f5541fd66838ab7e016d6c814819",
      ("rustc", "aarch64"): "b344b81f0cd4c2246c7da8b197fe7a339d7dd02bb15cb69b2524115d9c75224c",
      ("cargo", "x86_64"): "e1be5f5ff7f7f80ca506fb65770b759edbdc6d303781ed71c5de8ec8a8394779",
      ("cargo", "aarch64"): "8f70bcaccea5ba4db187c3fd4d64e24592b4e16af513497201f5909d61691dbe",
      ("rust-std", "x86_64"): "1c1e704ae80126b7de34f72ea2825f7fd01736dec20732faed47374b95282fba",
      ("rust-std", "aarch64"): "46aed8e63186350004d8ec6afca798811e6530b514352e5a8a26f3dc4939b3be",
    }
    archives = [entry for entry in module["sources"] if entry["type"] == "archive"]
    self.assertEqual(len(archives), len(expected))
    self.assertEqual({(entry["dest"], tuple(entry["only-arches"])) for entry in archives},
                     {(component, (arch,)) for component, arch in expected})
    for entry in archives:
      component, arch = entry["dest"], entry["only-arches"][0]
      self.assertEqual(entry["url"], f"https://static.rust-lang.org/dist/2026-07-16/{component}-{version}-{arch}-unknown-linux-gnu.tar.xz")
      self.assertEqual(entry["sha256"], expected[component, arch])
    self.assertEqual(module["cleanup"], ["*"])
    self.assertFalse(any("rustup" in command or "curl" in command for command in module["build-commands"]))

  def test_private_compiler_path_and_checks_cover_both_producers_before_compilation(self):
    manifest = (ROOT / "flatpak/dev.brani.tauridium.yml").read_text(encoding="utf-8")
    self.assertNotIn("org.freedesktop.Sdk.Extension.rust-stable", manifest)
    self.assertIn("org.freedesktop.Sdk.Extension.node24", manifest)
    self.assertIn("runtime-version: '51'", manifest)
    self.assertIn("prepend-path: /app/lib/tauridium-rust-toolchain/bin", manifest)
    self.assertIn("RUSTC: /app/lib/tauridium-rust-toolchain/bin/rustc", manifest)
    self.assertIn("cleanup-commands:\n  - rm -rf /app/lib/tauridium-rust-toolchain", manifest)
    self.assertLess(manifest.index("  - rust-toolchain.json"), manifest.index("  - name: tauri-cli"))
    for name in ("tauri-cli", "tauridium"):
      module = manifest.split("  - name: " + name + "\n", 1)[1].split("\n  - name:", 1)[0]
      commands = module.split("    build-commands:\n", 1)[1]
      self.assertTrue(commands.startswith("      - python3 /app/lib/tauridium-rust-toolchain/check-rust-toolchain.py\n"))
    self.assertIn("rust-toolchain.toml", build.LOCKS)

  def run_probe(self, *, versions=None, shadow=False, override=False, failed=False):
    prefix = Path("/synthetic-build-toolchain")
    versions = versions or {"rustc": PROBE.VERSION, "cargo": PROBE.VERSION}
    def which(name):
      return "/synthetic-sdk/bin/" + name if shadow else str(prefix / "bin" / name)
    def run(command, **_kwargs):
      name = Path(command[0]).name
      return subprocess.CompletedProcess(command, int(failed), f"{name} {versions[name]} (synthetic-cohort)\n", "")
    variables = {"RUSTC": str(prefix / "bin/rustc"), "CARGO_BUILD_RUSTC": str(prefix / "bin/rustc")}
    if override:
      variables["CARGO_BUILD_RUSTC"] = "/synthetic-sdk/bin/rustc"
    with (mock.patch.dict(os.environ, variables), mock.patch.object(PROBE.shutil, "which", side_effect=which),
          mock.patch.object(PROBE.subprocess, "run", side_effect=run), redirect_stdout(io.StringIO())):
      PROBE.verify(prefix)

  def test_reviewed_compiler_and_cargo_cohort_passes(self):
    self.run_probe()

  def test_sdk_path_shadow_and_effective_compiler_overrides_are_rejected(self):
    for options in ({"shadow": True}, {"override": True}):
      with self.subTest(options=options), self.assertRaisesRegex(SystemExit, "pinned"):
        self.run_probe(**options)

  def test_known_regression_versions_and_mismatched_cargo_are_rejected(self):
    for versions in ({"rustc": "1.98.0", "cargo": PROBE.VERSION},
                     {"rustc": "1.99.0", "cargo": PROBE.VERSION},
                     {"rustc": PROBE.VERSION, "cargo": "1.99.0"}):
      with self.subTest(versions=versions), self.assertRaisesRegex(SystemExit, "reviewed"):
        self.run_probe(versions=versions)
    with self.assertRaisesRegex(SystemExit, "reviewed"):
      self.run_probe(failed=True)

  def test_retained_build_toolchain_is_rejected_before_candidate_sealing(self):
    with tempfile.TemporaryDirectory() as temporary:
      output = Path(temporary)
      toolchain = output / "build/files/lib/tauridium-rust-toolchain"
      toolchain.mkdir(parents=True)
      (toolchain / "synthetic-rustc").write_text("synthetic-build-tool", encoding="utf-8")
      with self.assertRaisesRegex(SystemExit, "build-only Rust toolchain"):
        build.validate_runtime_layout(output)
