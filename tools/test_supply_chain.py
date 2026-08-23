#!/usr/bin/env python3
"""Regression coverage for Tauridium's Rust supply-chain guard."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
  sys.path.insert(0, str(TOOLS))

import check_rust_supply_chain as guard



class RustSupplyChainTests(unittest.TestCase):
  def test_official_august_2026_indicator_set_is_complete(self) -> None:
    self.assertEqual(
      guard.MALICIOUS_EXACT,
      {
        "append-only-vec": "0.1.9",
        "arrayref": "0.3.10",
        "internment": "0.8.7",
      },
    )
    self.assertEqual(
      guard.MALICIOUS_NAMES,
      frozenset({"proc-macro1", "proc-macro-en", "aovine", "arone", "aronenao", "tinymember"}),
    )

  def test_current_repository_has_no_blocked_crates(self) -> None:
    self.assertEqual(guard.scan_repository(), [])

  def test_malicious_lockfile_versions_are_rejected(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      lock = Path(temp_dir) / "Cargo.lock"
      lock.write_text(
        'version = 4\n\n[[package]]\nname = "arrayref"\nversion = "0.3.10"\n',
        encoding="utf-8",
      )
      findings = guard.scan_lockfile(lock)
      self.assertEqual([(item.package, item.version) for item in findings], [("arrayref", "0.3.10")])

  def test_registry_package_without_checksum_is_rejected(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      lock = Path(temp_dir) / "Cargo.lock"
      lock.write_text(
        'version = 4\n\n[[package]]\nname = "demo"\nversion = "1.0.0"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n',
        encoding="utf-8",
      )
      findings = guard.scan_lockfile(lock)
      self.assertEqual(len(findings), 1)
      self.assertIn("missing lockfile checksum", findings[0].reason)

  def test_deleted_typosquat_is_rejected_at_any_version(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      lock = Path(temp_dir) / "Cargo.lock"
      lock.write_text(
        'version = 4\n\n[[package]]\nname = "proc-macro1"\nversion = "1.0.106"\n',
        encoding="utf-8",
      )
      findings = guard.scan_lockfile(lock)
      self.assertEqual(len(findings), 1)
      self.assertEqual(findings[0].package, "proc-macro1")

  def test_manifest_dependency_on_blocked_release_is_rejected(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      manifest = Path(temp_dir) / "Cargo.toml"
      manifest.write_text(
        '[package]\nname = "demo"\nversion = "0.1.0"\n\n[dependencies]\ninternment = "0.8.7"\n',
        encoding="utf-8",
      )
      findings = guard.scan_manifest(manifest)
      self.assertEqual([(item.package, item.version) for item in findings], [("internment", "0.8.7")])

  def test_cache_archive_indicators_are_rejected(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      cache = Path(temp_dir)
      (cache / "proc-macro-en-9.9.9.crate").write_bytes(b"")
      (cache / "append-only-vec-0.1.9.crate").write_bytes(b"")
      findings = guard.scan_crate_archives(cache)
      self.assertEqual({item.package for item in findings}, {"proc-macro-en", "append-only-vec"})


if __name__ == "__main__":
  unittest.main()
