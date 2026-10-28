"""Keep a local npm backport visible to current upstream advisory monitoring."""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

import npm_policy

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://registry.npmjs.org/-/npm/v1/security/advisories/bulk"
MAX_RESPONSE_BYTES = 65536
NETWORK_TIMEOUT = 20
KNOWN_ADVISORY = "https://github.com/advisories/GHSA-gcqx-w48m-w2h4"
LOCAL_RUNTIME_SHA256 = "f52c1deed5fef6181e217aa466fb2ec6936c2b9c22060a8c0cfa9c0f015df992"
REVIEW_DEADLINE = date(2026, 11, 15)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate keys in local npm advisory data")
        result[key] = value
    return result


def _fetch_advisories() -> dict:
    request = urllib.request.Request(
        ENDPOINT, data=b'{"deepmerge":["4.3.1"]}', method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=NETWORK_TIMEOUT) as response:
            if response.status != 200 or response.geturl() != ENDPOINT:
                raise ValueError("Unexpected npm advisory response or redirect")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("Oversized npm advisory response")
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Current local npm advisory query failed; the security gate remains closed") from error


def _load_policy(root: Path, today: date) -> dict:
    policy = json.loads((root / "data/local-npm-advisory-policy.json").read_text(encoding="utf-8"),
                        object_pairs_hook=_unique_object)
    if (policy.get("schemaVersion") != 1 or policy.get("upstream") != {"name": "deepmerge", "version": "4.3.1"}
            or policy.get("localVersion") != "4.3.1+tauridium.1"
            or policy.get("runtimeSha256") != LOCAL_RUNTIME_SHA256 or not policy.get("reason")):
        raise ValueError("Local npm advisory policy does not match the reviewed security backport")
    if date.fromisoformat(policy["expires"]) != REVIEW_DEADLINE or today > REVIEW_DEADLINE:
        raise ValueError("Expired or unreviewed local npm advisory assessment; reassess by 15 November 2026")
    advisory = policy.get("expectedAdvisory", {})
    if (advisory.get("url") != KNOWN_ADVISORY or advisory.get("id") != 1243505
            or advisory.get("severity") != "low" or advisory.get("vulnerable_versions") != ">=4.2.0 <=4.3.1"
            or set(advisory) != {"id", "url", "title", "severity", "vulnerable_versions", "cwe", "cvss"}):
        raise ValueError("Local npm policy may assess only the exact known upstream advisory")
    return policy


def _verify_backport(root: Path) -> None:
    npm_policy.validate(root)
    runtime = root / "vendor/deepmerge/dist/cjs.js"
    if hashlib.sha256(runtime.read_bytes()).hexdigest() != LOCAL_RUNTIME_SHA256:
        raise ValueError("Local npm assessment requires the exact reviewed runtime patch")
    node = shutil.which("node")
    if not node:
        raise ValueError("Node is required to execute the local npm backport security controls")
    result = subprocess.run([node, str(root / "tools/check_deepmerge.mjs")], cwd=root,
                            capture_output=True, text=True, check=False, timeout=60)
    if result.returncode:
        raise ValueError("Actual local npm backport security controls failed")


def _evaluate(report: dict, policy: dict) -> list[dict]:
    if not isinstance(report, dict) or not set(report).issubset({"deepmerge"}):
        raise ValueError("Malformed or unexpected package in npm advisory response")
    rows = report.get("deepmerge", [])
    if not isinstance(rows, list) or len(rows) > 1:
        raise ValueError("Unknown or duplicate npm advisories require review")
    findings = []
    for row in rows:
        if not isinstance(row, dict) or row.get("url") != KNOWN_ADVISORY:
            raise ValueError("Unknown local npm advisory; update or review the dependency")
        if row != policy["expectedAdvisory"]:
            raise ValueError("Known local npm advisory details changed; reassessment is required")
        findings.append({"id": "GHSA-gcqx-w48m-w2h4", "upstreamVersion": "4.3.1",
                         "severity": row["severity"], "status": "concretely-backported",
                         "localVersion": policy["localVersion"], "runtimeSha256": LOCAL_RUNTIME_SHA256,
                         "expires": policy["expires"], "reason": policy["reason"]})
    return findings


def check(root: Path = ROOT, today: date | None = None) -> dict:
    root = Path(root)
    now = datetime.now(timezone.utc)
    policy = _load_policy(root, today if today is not None else now.date())
    _verify_backport(root)
    findings = _evaluate(_fetch_advisories(), policy)
    return {"passed": True, "currentOnlineGate": True, "checkedAtUtc": now.isoformat(),
            "source": ENDPOINT, "upstream": policy["upstream"], "localVersion": policy["localVersion"],
            "runtimeSha256": LOCAL_RUNTIME_SHA256, "reviewDeadline": policy["expires"],
            "findings": findings}


def main() -> int:
    try:
        print(json.dumps(check(), indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print("error: current local npm advisory and backport controls failed; new findings, changed patch or expired review require action", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
