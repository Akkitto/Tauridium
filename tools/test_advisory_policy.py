"""A contextual SDK assessment never suppresses an application or new-version finding."""
from datetime import date
import json
import unittest

import audit_dependencies as audit


class AdvisoryPolicyTests(unittest.TestCase):
  def setUp(self):
    self.policy = json.loads((audit.ROOT / "data/security-advisory-policy.json").read_text(encoding="utf-8"))
    self.report = {"settings": {"ignore": [], "target_arch": [], "target_os": [], "severity": None,
                                "informational_warnings": ["unmaintained", "unsound", "notice"]},
                   "vulnerabilities": {"list": [{"advisory": {"id": "RUSTSEC-2023-0071"}, "package": {"name": "rsa", "version": "0.9.10"}}]},
                   "warnings": {}}

  def test_exact_sdk_scope_and_version_are_required(self):
    accepted = audit.evaluate("flatpak/tauri-cli.Cargo.lock", self.report, self.policy, date(2026, 10, 15))
    self.assertEqual(accepted[0]["status"], "not-affected-under-enforced-controls")
    with self.assertRaisesRegex(SystemExit, "unassessed"):
      audit.evaluate("src-tauri/Cargo.lock", self.report, self.policy, date(2026, 10, 15))
    self.report["vulnerabilities"]["list"][0]["package"]["version"] = "0.9.11"
    with self.assertRaisesRegex(SystemExit, "unassessed"):
      audit.evaluate("flatpak/tauri-cli.Cargo.lock", self.report, self.policy, date(2026, 10, 15))

  def test_expiry_and_upstream_new_findings_fail_closed(self):
    with self.assertRaisesRegex(SystemExit, "expired"):
      audit.evaluate("flatpak/tauri-cli.Cargo.lock", self.report, self.policy, date(2026, 12, 1))
    self.report["vulnerabilities"]["list"][0]["advisory"]["id"] = "RUSTSEC-2099-9999"
    with self.assertRaisesRegex(SystemExit, "unassessed"):
      audit.evaluate("flatpak/tauri-cli.Cargo.lock", self.report, self.policy, date(2026, 10, 15))

  def test_manual_ignores_and_filters_are_never_accepted(self):
    self.report["settings"]["ignore"] = ["RUSTSEC-2023-0071"]
    with self.assertRaisesRegex(SystemExit, "refuses ignored"):
      audit.evaluate("flatpak/tauri-cli.Cargo.lock", self.report, self.policy, date(2026, 10, 15))

  def test_exact_published_lock_and_key_free_controls_hold(self):
    audit.verify_controls(self.policy)


if __name__ == "__main__":
  unittest.main()
