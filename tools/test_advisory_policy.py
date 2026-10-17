"""A contextual SDK assessment never suppresses an application or new-version finding."""
from datetime import date
import copy
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

  def test_zbus_maintenance_assessment_is_exact_not_a_vulnerability_exemption(self):
    report = copy.deepcopy(self.report)
    finding = {"advisory": {"id": "RUSTSEC-2026-0371"}, "package": {"name": "zbus_names", "version": "4.3.2"}}
    report["vulnerabilities"]["list"] = []
    report["warnings"] = {"unmaintained": [finding]}
    accepted = audit.evaluate("src-tauri/Cargo.lock", report, self.policy, date(2026, 10, 17))
    self.assertEqual(accepted[0]["status"], "reviewed-maintenance-warning")
    self.assertEqual(accepted[0]["expires"], "2026-11-15")
    for advisory, package, version in (
      ("RUSTSEC-2026-0370", "zvariant", "5.12.0"),
      ("RUSTSEC-2026-0372", "zvariant_derive", "5.12.0"),
    ):
      with self.subTest(package=package):
        related = copy.deepcopy(report)
        related["warnings"]["unmaintained"] = [{"advisory": {"id": advisory},
          "package": {"name": package, "version": version}}]
        reviewed = audit.evaluate("src-tauri/Cargo.lock", related, self.policy, date(2026, 10, 17))
        self.assertEqual(reviewed[0]["status"], "reviewed-maintenance-warning")
        self.assertEqual(reviewed[0]["expires"], "2026-11-15")
        related["vulnerabilities"]["list"] = related["warnings"].pop("unmaintained")
        with self.assertRaisesRegex(SystemExit, "unassessed"):
          audit.evaluate("src-tauri/Cargo.lock", related, self.policy, date(2026, 10, 17))
    for lock, kind, version in (
      ("flatpak/tauri-cli.Cargo.lock", "unmaintained", "4.3.2"),
      ("src-tauri/Cargo.lock", "unmaintained", "4.3.3"),
      ("src-tauri/Cargo.lock", "vulnerability", "4.3.2"),
      ("src-tauri/Cargo.lock", "unsound", "4.3.2"),
    ):
      with self.subTest(lock=lock, kind=kind, version=version):
        changed = copy.deepcopy(report)
        changed_finding = copy.deepcopy(finding)
        changed_finding["package"]["version"] = version
        changed["warnings"] = {} if kind == "vulnerability" else {kind: [changed_finding]}
        changed["vulnerabilities"]["list"] = [changed_finding] if kind == "vulnerability" else []
        with self.assertRaisesRegex(SystemExit, "unassessed"):
          audit.evaluate(lock, changed, self.policy, date(2026, 10, 17))

  def test_zbus_maintenance_assessment_cannot_outlive_the_short_review_window(self):
    report = copy.deepcopy(self.report)
    report["vulnerabilities"]["list"] = []
    report["warnings"] = {"unmaintained": [{"advisory": {"id": "RUSTSEC-2026-0371"},
      "package": {"name": "zbus_names", "version": "4.3.2"}}]}
    with self.assertRaisesRegex(SystemExit, "expired"):
      audit.evaluate("src-tauri/Cargo.lock", report, self.policy, date(2026, 11, 16))

  def test_application_assessments_reject_changed_or_missing_exact_lock_binding(self):
    for value in (None, "0" * 64):
      with self.subTest(value=value):
        changed = copy.deepcopy(self.policy)
        changed["applicationLockSha256"] = value
        with self.assertRaisesRegex(SystemExit, "application advisory assessment.*exact dependency lock"):
          audit.verify_controls(changed)


if __name__ == "__main__":
  unittest.main()
