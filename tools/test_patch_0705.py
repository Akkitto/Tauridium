#!/usr/bin/env python3
"""Regression coverage for Tauridium Proton Tauri-marker compatibility."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARGO = (ROOT / "src-tauri/Cargo.toml").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
PROTON = (ROOT / "src-tauri/src/proton_compat.rs").read_text(encoding="utf-8")
TAURI_WEBVIEW = (ROOT / "vendor/tauri/src/manager/webview.rs").read_text(encoding="utf-8")
PATCH_DOC = (ROOT / "vendor/tauri/TAURIDIUM-PATCH.md").read_text(encoding="utf-8")
COMPAT_DOC = (ROOT / "docs/compatibility.md").read_text(encoding="utf-8")


class Patch0705Tests(unittest.TestCase):
  def test_workaround_targets_all_current_native_identity_web_clients(self) -> None:
    for host in (
      "account.proton.me",
      "mail.proton.me",
      "calendar.proton.me",
      "pass.proton.me",
      "authenticator.proton.me",
      "meet.proton.me",
    ):
      self.assertIn(f'"{host}"', PROTON)
    production = PROTON.split("#[cfg(test)]", 1)[0]
    for host in (
      "drive.proton.me",
      "wallet.proton.me",
      "docs.proton.me",
      "sheets.proton.me",
      "lumo.proton.me",
      "contacts.proton.me",
    ):
      self.assertNotIn(f'"{host}"', production)

  def test_workaround_is_conditionally_injected_at_service_boundary(self) -> None:
    conditional = "if proton_compat::requires_tauri_marker_workaround(&host)"
    self.assertEqual(MAIN.count(conditional), 1)
    self.assertIn(
      "builder = builder.initialization_script(proton_compat::TAURI_MARKER_WORKAROUND_JS);",
      MAIN,
    )
    self.assertNotIn("TAURI_MARKER_WORKAROUND_JS);\n    if let Some", PROTON)

  def test_workaround_removes_only_generic_marker(self) -> None:
    script = re.search(
      r'TAURI_MARKER_WORKAROUND_JS: &str = r#"(.*?)"#;',
      PROTON,
      re.DOTALL,
    )
    self.assertIsNotNone(script)
    body = script.group(1)
    self.assertIn("delete window.isTauri", body)
    self.assertNotIn("window.isTauri = false", body)
    self.assertNotIn("__TAURI_INTERNALS__", body)
    self.assertNotRegex(body, re.compile(r"web-mail|web-calendar|windows-mail"))

  def test_vendored_tauri_patch_changes_only_marker_configurability(self) -> None:
    marker = re.search(
      r"Object\.defineProperty\(window, 'isTauri', \{(?P<body>.*?)\}\);",
      TAURI_WEBVIEW,
      re.DOTALL,
    )
    self.assertIsNotNone(marker)
    body = marker.group("body")
    self.assertIn("value: true", body)
    self.assertIn("configurable: true", body)
    internals = re.search(
      r"Object\.defineProperty\(window, '__TAURI_INTERNALS__', \{(?P<body>.*?)\}\)",
      TAURI_WEBVIEW,
      re.DOTALL,
    )
    self.assertIsNotNone(internals)
    self.assertNotIn("configurable: true", internals.group("body"))

  def test_tauri_patch_is_exactly_pinned_and_documented_as_temporary(self) -> None:
    self.assertIn('tauri = { version = "=2.11.3"', CARGO)
    self.assertIn('tauri = { path = "../vendor/tauri" }', CARGO)
    self.assertIn("TEMPORARY patched Tauri 2.11.3", CARGO)
    self.assertIn("Temporary patch", PATCH_DOC)
    self.assertIn("## Removal", PATCH_DOC)
    self.assertIn("Do not expand this patch into a general hosted-site compatibility layer.", PATCH_DOC)

  def test_user_facing_compatibility_document_has_removal_boundary(self) -> None:
    for marker in (
      "Temporary Proton web-client workaround",
      "`mail.proton.me`",
      "`calendar.proton.me`",
      "`pass.proton.me`",
      "`authenticator.proton.me`",
      "`meet.proton.me`",
      "does **not** rewrite",
      "### Removal",
      "Keep this host list aligned",
    ):
      self.assertIn(marker, COMPAT_DOC)


if __name__ == "__main__":
  unittest.main()
