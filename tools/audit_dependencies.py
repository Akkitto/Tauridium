"""Current whole-lock RustSec gate with explicit expiring scope/version assessments, never ignores."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import tauri_build
import audit_local_npm

ROOT = Path(__file__).resolve().parents[1]
LOCKS = ("src-tauri/Cargo.lock", "flatpak/tauri-cli.Cargo.lock")
DATABASE_URL = "https://github.com/RustSec/advisory-db.git"


def evaluate(lock: str, report: dict, policy: dict, today: date) -> list[dict]:
  settings = report.get("settings", {})
  if (settings.get("ignore") or settings.get("target_arch") or settings.get("target_os")
      or settings.get("severity") is not None
      or not {"unmaintained", "unsound", "notice"}.issubset(settings.get("informational_warnings", []))):
    raise SystemExit("error: RustSec gate refuses ignored advisories, severity filters or incomplete target/warning coverage")
  assessed = {(row["lock"], row["kind"], row["id"], row["package"], row["version"]): row
              for row in policy["assessments"]}
  findings = [("vulnerability", row) for row in report["vulnerabilities"]["list"]]
  findings.extend((kind, row) for kind, rows in report.get("warnings", {}).items() for row in rows)
  accepted = []
  for kind, finding in findings:
    advisory, package = finding.get("advisory") or {}, finding["package"]
    key = (lock, kind, advisory.get("id"), package["name"], package["version"])
    row = assessed.get(key)
    if row is None:
      raise SystemExit(f"error: unassessed RustSec finding: {key}; update/fix the dependency, never add a blanket ignore")
    if date.fromisoformat(row["expires"]) < today or not row.get("reason"):
      raise SystemExit(f"error: expired/incomplete dependency assessment: {row['id']} {row['package']}")
    accepted.append({"id": row["id"], "package": row["package"], "version": row["version"],
                     "kind": kind, "status": row["status"], "expires": row["expires"], "reason": row["reason"]})
  return accepted


def verify_controls(policy: dict) -> None:
  application = ROOT / LOCKS[0]
  if hashlib.sha256(application.read_bytes()).hexdigest() != policy.get("applicationLockSha256"):
    raise SystemExit("error: application advisory assessment is not valid for this exact dependency lock")
  sdk = ROOT / LOCKS[1]
  if hashlib.sha256(sdk.read_bytes()).hexdigest() != policy["builderLockSha256"]:
    raise SystemExit("error: builder advisory assessment is not valid for this CLI dependency lock")
  for name in ("TAURI_SIGNING_RPM_KEY", "TAURI_SIGNING_PRIVATE_KEY"):
    try:
      tauri_build.build_environment({name: "synthetic control, never a real key"})
    except SystemExit:
      continue
    raise SystemExit("error: builder advisory controls require signing-key rejection before build code")
  config = json.loads((ROOT / "src-tauri/tauri.no-updater.conf.json").read_text(encoding="utf-8"))
  if config != {"bundle": {"createUpdaterArtifacts": False}}:
    raise SystemExit("error: builder assessment requires key-free unsigned build configuration")


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--snapshot-db", type=Path, help="Explicit offline diagnostic snapshot; NOT the required current online gate")
  args = parser.parse_args()
  tool = shutil.which("cargo-audit")
  if not tool:
    raise SystemExit("error: cargo-audit is required; run just init or enter the updated nix develop environment")
  version = json.loads((ROOT / "data/build-toolchain.json").read_text(encoding="utf-8"))["cargoAudit"]
  probe = subprocess.run([tool, "audit", "--version"], capture_output=True, text=True, check=False, timeout=30)
  if probe.returncode or not re.fullmatch(r"cargo-audit(?:-audit)? " + re.escape(version), probe.stdout.strip()):
    raise SystemExit("error: dependency auditing requires the exact pinned cargo-audit version")
  policy = json.loads((ROOT / "data/security-advisory-policy.json").read_text(encoding="utf-8"))
  verify_controls(policy)
  now = datetime.now(timezone.utc)
  local_npm = (audit_local_npm.check(ROOT, today=now.date()) if args.snapshot_db is None else
               {"currentOnlineGate": False, "status": "Not run in an offline RustSec diagnostic"})
  with tempfile.TemporaryDirectory(prefix="tauridium-private-rustsec-") as temporary:
    root = Path(temporary)
    database = args.snapshot_db.resolve() if args.snapshot_db else root / "advisory-db"
    git_env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    git_env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
    if args.snapshot_db is None:
      subprocess.run(["git", "clone", "--quiet", "--depth=1", DATABASE_URL, str(database)],
                     cwd=root, env=git_env, capture_output=True, check=True, timeout=180)
    summaries = []
    for lock in LOCKS:
      command = [tool, "audit", "--file", str(ROOT / lock), "--db", str(database), "--url", DATABASE_URL, "--json"]
      if args.snapshot_db:
        command.append("--no-fetch")
      process = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False, timeout=300)
      if process.returncode not in (0, 1):
        raise SystemExit("error: dependency advisory scanner failed; private diagnostics withheld")
      report = json.loads(process.stdout)
      revision = subprocess.run(["git", "-C", str(database), "rev-parse", "HEAD"], cwd=root, env=git_env,
                                capture_output=True, text=True, check=True, timeout=30).stdout.strip()
      summaries.append({"lock": lock, "knownVulnerabilities": len(report["vulnerabilities"]["list"]),
                        "databaseCommit": revision,
                        "explicitAssessments": evaluate(lock, report, policy, now.date())})
    print(json.dumps({"passed": True, "databaseCommit": revision, "checkedAtUtc": now.isoformat(),
                      "currentOnlineGate": args.snapshot_db is None, "localNpmBackports": local_npm, "locks": summaries}, indent=2))
  return 0


if __name__ == "__main__":
  try:
    raise SystemExit(main())
  except (OSError, ValueError, KeyError, subprocess.SubprocessError):
    raise SystemExit("error: current dependency advisory gate could not complete; private scanner diagnostics withheld") from None
