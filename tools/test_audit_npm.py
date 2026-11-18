"""Older npm must not exempt new findings while recognizing verified local patches."""
import copy
import unittest

import audit_npm as audit
import audit_picomatch


class CompleteNpmAuditTests(unittest.TestCase):
    def setUp(self):
        self.expected = {"picomatch": copy.deepcopy(audit_picomatch.EXPECTED)}
        expected = self.expected["picomatch"]
        direct = {"source": expected["id"], "name": "picomatch", "dependency": "picomatch",
                  "title": expected["title"], "url": expected["url"], "severity": expected["severity"],
                  "range": expected["vulnerable_versions"], "cwe": expected["cwe"], "cvss": expected["cvss"]}
        self.packages = {"node_modules/picomatch": {}, "vendor/picomatch": {}, "node_modules/fdir": {}}
        self.report = {"auditReportVersion": 2, "metadata": {"vulnerabilities": {"total": 2}},
                       "vulnerabilities": {
                           "picomatch": {"name": "picomatch", "via": [direct],
                                         "nodes": ["node_modules/picomatch", "vendor/picomatch"]},
                           "fdir": {"name": "fdir", "via": ["picomatch"], "nodes": ["node_modules/fdir"]}}}

    def test_old_npm_direct_and_transitive_backport_reports_are_exactly_assessed(self):
        self.assertEqual(audit.evaluate(self.report, self.expected, self.packages), ["fdir", "picomatch"])

    def test_new_npm_empty_local_link_report_is_accepted_only_as_complete_inventory(self):
        report = {"auditReportVersion": 2, "metadata": {"vulnerabilities": {"total": 0}}, "vulnerabilities": {}}
        self.assertEqual(audit.evaluate(report, self.expected, self.packages), [])

    def test_new_or_changed_direct_advisory_fails_even_on_known_package(self):
        for field, value in (("source", 999999), ("severity", "critical"), ("range", "*")):
            changed = copy.deepcopy(self.report)
            changed["vulnerabilities"]["picomatch"]["via"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                audit.evaluate(changed, self.expected, self.packages)

    def test_unrelated_or_mixed_direct_findings_are_not_hidden_by_transitive_edges(self):
        changed = copy.deepcopy(self.report)
        changed["vulnerabilities"]["fdir"]["via"].append(copy.deepcopy(changed["vulnerabilities"]["picomatch"]["via"][0]))
        with self.assertRaises(ValueError):
            audit.evaluate(changed, self.expected, self.packages)

    def test_cycles_missing_nodes_and_unknown_installed_copies_fail(self):
        for mutate in (
            lambda r: r["vulnerabilities"]["picomatch"].update(via=["fdir"]),
            lambda r: r["vulnerabilities"]["fdir"].update(via=["unknown"]),
            lambda r: r["vulnerabilities"]["picomatch"].update(nodes=["node_modules/fdir/node_modules/picomatch"]),
            lambda r: r["vulnerabilities"]["fdir"].update(nodes=[]),
        ):
            changed = copy.deepcopy(self.report)
            mutate(changed)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                audit.evaluate(changed, self.expected, self.packages)

    def test_failed_partial_and_malformed_reports_fail_closed(self):
        for report in ([], {}, {"error": {"code": "unavailable"}},
                       self.report | {"metadata": {"vulnerabilities": {"total": 0}}},
                       self.report | {"auditReportVersion": 1}, self.report | {"metadata": []}):
            with self.subTest(report=report), self.assertRaises(ValueError):
                audit.evaluate(report, self.expected, self.packages)
