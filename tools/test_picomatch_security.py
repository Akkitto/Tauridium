"""Fail closed on bypassed, changed or expired local glob security controls."""
from datetime import date
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import audit_picomatch as audit
import npm_policy

ROOT = Path(__file__).resolve().parents[1]


class PicomatchSecurityTests(unittest.TestCase):
    def test_only_exact_current_advisory_is_assessed(self):
        report = {"picomatch": [copy.deepcopy(audit.EXPECTED)]}
        accepted = audit.evaluate(report, date(2026, 11, 18))
        self.assertEqual(accepted[0]["status"], "concretely-backported")
        self.assertEqual(accepted[0]["expires"], "2026-11-30")
        for field, value in (("id", 0), ("severity", "critical"), ("vulnerable_versions", "*")):
            changed = copy.deepcopy(report)
            changed["picomatch"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                audit.evaluate(changed, date(2026, 11, 18))

    def test_new_duplicate_or_other_package_findings_fail(self):
        for report in ({"other": []}, {"picomatch": [{"id": 9999}]},
                       {"picomatch": [audit.EXPECTED, audit.EXPECTED]}, {"picomatch": None}):
            with self.subTest(report=report), self.assertRaises(ValueError):
                audit.evaluate(report, date(2026, 11, 18))

    def test_review_does_not_apply_before_or_after_its_exact_window(self):
        for day in (date(2026, 11, 17), date(2026, 12, 1)):
            with self.subTest(day=day), self.assertRaises(audit.AssessmentExpired):
                audit.evaluate({}, day)

    def test_second_registry_copy_or_bypassed_link_fails(self):
        original = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))["packages"]
        for name, entry in (("node_modules/picomatch", {"version": "4.0.7"}),
                            ("node_modules/vite/node_modules/picomatch", {"version": "4.0.7"})):
            with self.subTest(name=name), self.assertRaises(ValueError):
                npm_policy.validate_local_lock(original | {name: entry})

    def test_patch_tampering_and_override_bypass_fail(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / "vendor/picomatch", root / "vendor/picomatch")
            npm_policy.validate_picomatch_source(root, package)
            parser = root / "vendor/picomatch/lib/parse.js"
            parser.write_bytes(parser.read_bytes() + b"\n// synthetic tampering\n")
            with self.assertRaisesRegex(ValueError, "integrity mismatch"):
                npm_policy.validate_picomatch_source(root, package)
            manifest_path = root / "vendor/picomatch/TAURIDIUM-PATCH.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"]["lib/parse.js"] = hashlib.sha256(parser.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "manifest integrity mismatch"):
                npm_policy.validate_picomatch_source(root, package)
            changed = copy.deepcopy(package)
            del changed["overrides"]["picomatch"]
            with self.assertRaisesRegex(ValueError, "override is required"):
                npm_policy.validate_picomatch_source(root, changed)

    @unittest.skipUnless(shutil.which("node"), "Requires the initialized Node environment")
    def test_real_dependency_resolution_matching_and_bounded_exploit_controls(self):
        subprocess.run([shutil.which("node"), str(ROOT / "tools/check_picomatch.mjs")],
                       cwd=ROOT, check=True, capture_output=True, timeout=60)

    @unittest.skipUnless(shutil.which("git"), "Requires Git checkout conversion")
    def test_windows_checkout_preserves_manifest_bound_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copyfile(ROOT / ".gitattributes", root / ".gitattributes")
            shutil.copytree(ROOT / "vendor/picomatch", root / "vendor/picomatch")
            package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
            command = [shutil.which("git"), "-c", "core.autocrlf=true", "-c", "core.safecrlf=false"]
            for args in (["init", "--quiet"], ["add", "--force", ".gitattributes", "vendor/picomatch"],
                         ["checkout-index", "--force", "--all"]):
                subprocess.run(command + args, cwd=root, check=True, capture_output=True, timeout=30)
            npm_policy.validate_picomatch_source(root, package)
