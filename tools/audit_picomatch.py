"""Current advisory monitoring for the exact local picomatch ReDoS backport."""
from datetime import date, datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request

import npm_policy
from audit_local_npm import AssessmentExpired, _unique_object

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://registry.npmjs.org/-/npm/v1/security/advisories/bulk"
REVIEWED = date(2026, 11, 18)
DEADLINE = date(2026, 11, 30)
EXPECTED = {
    "id": 1247710,
    "url": "https://github.com/advisories/GHSA-fc5q-39xc-vjpf",
    "title": "picomatch vulnerable to ReDoS through single-branch repeated extglobs",
    "severity": "high", "vulnerable_versions": "<=4.0.7",
    "cwe": ["CWE-1333"],
    "cvss": {"score": 7.5, "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H"},
}


def evaluate(report, today):
    if not REVIEWED <= today <= DEADLINE:
        raise AssessmentExpired("Picomatch security backport requires fresh review")
    if not isinstance(report, dict) or not set(report).issubset({"picomatch"}):
        raise ValueError("Unexpected package in current picomatch advisory response")
    rows = report.get("picomatch", [])
    if not isinstance(rows, list) or len(rows) > 1 or any(row != EXPECTED for row in rows):
        raise ValueError("Unknown or changed picomatch advisory requires review")
    return [{"id": "GHSA-fc5q-39xc-vjpf", "severity": "high", "upstreamVersion": "4.0.7",
             "localVersion": npm_policy.PICOMATCH_VERSION, "status": "concretely-backported",
             "parserSha256": npm_policy.PICOMATCH_PARSER_SHA256, "expires": DEADLINE.isoformat()}
            for _row in rows]


def check(root=ROOT, today=None):
    root = Path(root)
    now = datetime.now(timezone.utc)
    current = today or now.date()
    # Fail before network access on expiry, source drift or bypassed resolution.
    evaluate({}, current)
    npm_policy.validate(root)
    node = shutil.which("node")
    if not node:
        raise ValueError("Node is required for actual glob-backport controls")
    result = subprocess.run([node, str(root / "tools/check_picomatch.mjs")], cwd=root,
                            capture_output=True, text=True, timeout=60, check=False)
    if result.returncode:
        raise ValueError("Actual picomatch backport security controls failed")
    request = urllib.request.Request(ENDPOINT, data=b'{"picomatch":["4.0.7"]}', method="POST",
                                    headers={"Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200 or response.geturl() != ENDPOINT:
            raise ValueError("Unexpected picomatch advisory response or redirect")
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError("Oversized picomatch advisory response")
    report = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    return {"passed": True, "currentOnlineGate": True, "source": ENDPOINT,
            "checkedAtUtc": now.isoformat(), "findings": evaluate(report, current)}
