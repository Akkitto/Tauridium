"""Scan the complete npm graph and verify exact local backports on every npm version."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import audit_local_npm
import audit_picomatch
import npm_policy

ROOT = Path(__file__).resolve().parents[1]


def evaluate(report: dict, expected: dict, packages: dict) -> list[str]:
    """Accept only facts already covered by executed, exact backport controls.

    npm 10 reports local patched links as their upstream versions; npm 11 omits
    them. Neither representation replaces our independent current upstream query.
    Metavulnerabilities are accepted only when every path ends in a verified
    backport. Unknown direct findings, malformed graphs and cycles fail closed.
    """
    if not isinstance(report, dict) or report.get("auditReportVersion") != 2 or report.get("error"):
        raise ValueError("Malformed or failed complete npm audit")
    findings = report.get("vulnerabilities")
    metadata = report.get("metadata")
    if not isinstance(metadata, dict) or not isinstance(metadata.get("vulnerabilities"), dict):
        raise ValueError("Missing complete npm vulnerability counts")
    total = metadata["vulnerabilities"].get("total")
    if not isinstance(findings, dict) or type(total) is not int or total != len(findings):
        raise ValueError("Incomplete npm advisory inventory")
    resolved, visiting = set(), set()

    def verify(name):
        if name in resolved:
            return
        if name in visiting or name not in findings:
            raise ValueError("Cyclic or incomplete npm advisory graph")
        visiting.add(name)
        entry = findings[name]
        if not isinstance(entry, dict) or entry.get("name") != name:
            raise ValueError("Malformed npm advisory package")
        nodes, via = entry.get("nodes"), entry.get("via")
        if (not isinstance(nodes, list) or not nodes or any(node not in packages for node in nodes)
                or not isinstance(via, list) or not via):
            raise ValueError("Missing npm advisory paths or provenance")
        direct = [row for row in via if isinstance(row, dict)]
        if direct:
            if name not in expected or len(via) != 1:
                raise ValueError("Unassessed direct npm vulnerability")
            row = direct[0]
            keys = {"source", "name", "dependency", "title", "url", "severity", "range", "cwe", "cvss"}
            if set(row) != keys or row["name"] != name or row["dependency"] != name:
                raise ValueError("Unrecognized npm advisory metadata")
            normalized = {"id": row["source"], "url": row["url"], "title": row["title"],
                          "severity": row["severity"], "vulnerable_versions": row["range"],
                          "cwe": row["cwe"], "cvss": row["cvss"]}
            allowed = {f"node_modules/{name}", f"vendor/{name}"}
            if normalized != expected[name] or not set(nodes).issubset(allowed):
                raise ValueError("Unassessed npm advisory or unpatched package copy")
        else:
            for parent in via:
                if not isinstance(parent, str):
                    raise ValueError("Malformed npm advisory dependency")
                verify(parent)
        visiting.remove(name)
        resolved.add(name)

    for name in findings:
        verify(name)
    return sorted(resolved)


def check(root: Path = ROOT) -> dict:
    root = Path(root)
    now = datetime.now(timezone.utc)
    npm_policy.validate(root)
    # Execute integrity, actual-resolution and exploit controls, and query the
    # original registry identities even when npm itself skips local links.
    merge = audit_local_npm.check(root, today=now.date())
    glob = audit_picomatch.check(root, today=now.date())
    expected = {"deepmerge": audit_local_npm._load_policy(root, now.date())["expectedAdvisory"],
                "picomatch": audit_picomatch.EXPECTED}
    npm = shutil.which("npm")
    if not npm:
        raise ValueError("npm is required for the complete dependency audit")
    prefix = ["cmd.exe", "/d", "/c", npm] if os.name == "nt" else [npm]
    arguments = ["audit", "--json", "--audit-level=low", "--include=dev", "--include=optional",
                 "--include=peer", "--registry=https://registry.npmjs.org"]
    result = subprocess.run(prefix + arguments, cwd=root, capture_output=True, text=True,
                            encoding="utf-8", check=False, timeout=120)
    if result.returncode not in (0, 1):
        raise ValueError("Complete npm advisory scanner failed")
    report = json.loads(result.stdout, object_pairs_hook=audit_local_npm._unique_object)
    packages = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))["packages"]
    assessed = evaluate(report, expected, packages)
    if result.returncode and not assessed:
        raise ValueError("npm failed without a complete assessed finding inventory")
    return {"passed": True, "currentOnlineGate": True, "checkedAtUtc": now.isoformat(),
            "npmExitCode": result.returncode, "verifiedBackportGraphFindings": assessed,
            "localBackportControls": {"deepmerge": merge, "picomatch": glob}}


if __name__ == "__main__":
    try:
        print(json.dumps(check(), indent=2))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print("error: complete npm audit or exact backport controls failed; unknown findings, changed source, expiry and scanner errors require action", file=sys.stderr)
        raise SystemExit(1) from None
