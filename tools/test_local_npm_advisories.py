"""Fail-closed monitoring for advisories hidden by npm's local-link handling."""
from datetime import date
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("audit_local_npm", ROOT / "tools/audit_local_npm.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class Response(io.BytesIO):
    status = 200

    def geturl(self):
        return AUDIT.ENDPOINT


class LocalNpmAdvisoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "data").mkdir()
        (self.root / "tools").mkdir()
        for name in (".npmrc", "package.json", "package-lock.json"):
            shutil.copyfile(ROOT / name, self.root / name)
        shutil.copyfile(ROOT / "data/local-npm-advisory-policy.json", self.root / "data/local-npm-advisory-policy.json")
        shutil.copyfile(ROOT / "tools/check_deepmerge.mjs", self.root / "tools/check_deepmerge.mjs")
        shutil.copytree(ROOT / "vendor/deepmerge", self.root / "vendor/deepmerge")
        self.policy = json.loads((self.root / "data/local-npm-advisory-policy.json").read_text(encoding="utf-8"))
        self.payload = {"deepmerge": [self.policy["expectedAdvisory"]]}
        self.node = mock.patch.object(AUDIT.shutil, "which", return_value="synthetic-node").start()
        self.addCleanup(mock.patch.stopall)
        self.run = mock.patch.object(AUDIT.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")).start()

    def check(self, payload=None, today=date(2026, 10, 28)):
        with mock.patch.object(AUDIT, "_fetch_advisories", return_value=self.payload if payload is None else payload):
            return AUDIT.check(self.root, today=today)

    def test_exact_live_payload_is_bound_to_patch_and_actual_node_controls(self):
        result = self.check()
        self.assertTrue(result["passed"])
        self.assertTrue(result["currentOnlineGate"])
        self.assertEqual(result["findings"][0]["status"], "concretely-backported")
        self.assertEqual(result["findings"][0]["runtimeSha256"], AUDIT.LOCAL_RUNTIME_SHA256)
        self.run.assert_called_once_with(["synthetic-node", str(self.root / "tools/check_deepmerge.mjs")],
                                         cwd=self.root, capture_output=True, text=True, check=False, timeout=60)

    def test_new_advisory_is_never_hidden_by_the_known_backport(self):
        changed = json.loads(json.dumps(self.payload))
        changed["deepmerge"][0]["url"] = "https://github.com/advisories/GHSA-newx-newx-newx"
        with self.assertRaisesRegex(ValueError, "Unknown"):
            self.check(changed)
        changed["deepmerge"].append(self.policy["expectedAdvisory"])
        with self.assertRaisesRegex(ValueError, "Unknown or duplicate"):
            self.check(changed)

    def test_changed_range_severity_or_advisory_metadata_requires_review(self):
        for key, value in (("severity", "high"), ("vulnerable_versions", ">=4.0.0"),
                           ("id", 99), ("title", "Changed scope"),
                           ("cvss", {"score": 9.8, "vectorString": "changed"})):
            with self.subTest(key=key):
                changed = json.loads(json.dumps(self.payload))
                changed["deepmerge"][0][key] = value
                with self.assertRaisesRegex(ValueError, "details changed"):
                    self.check(changed)

    def test_assessment_expires_and_cannot_silently_extend_its_deadline(self):
        self.check(today=date(2026, 11, 15))
        with self.assertRaisesRegex(ValueError, "Expired"):
            self.check(today=date(2026, 11, 16))
        self.policy["expires"] = "2099-01-01"
        (self.root / "data/local-npm-advisory-policy.json").write_text(json.dumps(self.policy), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Expired or unreviewed"):
            self.check()

    def test_changed_patch_fails_even_if_its_own_manifest_is_rehashed(self):
        runtime = self.root / "vendor/deepmerge/dist/cjs.js"
        runtime.write_bytes(runtime.read_bytes() + b"\n// changed runtime\n")
        manifest_path = self.root / "vendor/deepmerge/TAURIDIUM-PATCH.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["dist/cjs.js"] = hashlib.sha256(runtime.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exact reviewed runtime patch"):
            self.check()

    def test_node_controls_cannot_be_skipped_or_fail_open(self):
        self.node.return_value = None
        with self.assertRaisesRegex(ValueError, "Node is required"):
            self.check()
        self.node.return_value = "synthetic-node"
        self.run.return_value = subprocess.CompletedProcess([], 1, "", "synthetic failure")
        with self.assertRaisesRegex(ValueError, "controls failed"):
            self.check()
        self.run.side_effect = subprocess.TimeoutExpired("node", 60)
        with self.assertRaises(subprocess.TimeoutExpired):
            self.check()

    def test_malformed_reports_and_unknown_packages_fail_closed(self):
        for report in ([], "bad", {"other": []}, {"deepmerge": None}, {"deepmerge": [None]}):
            with self.subTest(report=report), self.assertRaises(ValueError):
                self.check(report)

    def test_official_query_is_bounded_and_uses_the_original_registry_identity(self):
        encoded = json.dumps(self.payload).encode()
        with mock.patch.object(AUDIT.urllib.request, "urlopen", return_value=Response(encoded)) as request:
            self.assertEqual(AUDIT._fetch_advisories(), self.payload)
        args, kwargs = request.call_args
        self.assertEqual(args[0].full_url, AUDIT.ENDPOINT)
        self.assertEqual(args[0].get_method(), "POST")
        self.assertEqual(json.loads(args[0].data), {"deepmerge": ["4.3.1"]})
        self.assertEqual(kwargs["timeout"], 20)

    def test_network_malformed_oversized_or_redirected_response_fails_closed(self):
        with mock.patch.object(AUDIT.urllib.request, "urlopen", side_effect=urllib.error.URLError("synthetic")):
            with self.assertRaisesRegex(ValueError, "gate remains closed"):
                AUDIT._fetch_advisories()
        for raw in (b"not json", b"\xff", b"x" * (AUDIT.MAX_RESPONSE_BYTES + 1), b'{"deepmerge":[],"deepmerge":[]}'):
            with self.subTest(raw=raw[:20]), mock.patch.object(AUDIT.urllib.request, "urlopen", return_value=Response(raw)):
                with self.assertRaises(ValueError):
                    AUDIT._fetch_advisories()
        redirected = Response(b"{}")
        redirected.geturl = lambda: "https://unreviewed.invalid/advisories"
        with mock.patch.object(AUDIT.urllib.request, "urlopen", return_value=redirected):
            with self.assertRaisesRegex(ValueError, "redirect"):
                AUDIT._fetch_advisories()


if __name__ == "__main__":
    unittest.main()
