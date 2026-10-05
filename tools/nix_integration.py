"""Evaluate the documented consumers with real, locked NixOS/Home Manager modules.

No build, activation, profile installation or modification of host configuration.
Home Manager is a test-only dependency, not a Tauridium package/flake dependency.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEMS = ("x86_64-linux", "aarch64-linux")
FAILURES = ("homeMissingArgument", "nixosMissingArgument", "integratedMissingArgument")
HOME_CASES = {"direct", "overlay", "inputs", "closure"}
NIXOS_CASES = {"direct", "overlay", "closure", "integrated", "integratedOverlay"}


def validate_report(report):
  if report.get("directAlias") is not True:
    raise RuntimeError("Default and named package aliases must match")
  for group, expected in (("homeChecks", HOME_CASES), ("nixosChecks", NIXOS_CASES)):
    cases = report.get(group, {})
    if set(cases) != expected:
      raise RuntimeError(f"Incomplete {group}: expected {sorted(expected)}")
    for name, values in cases.items():
      key = "activation" if group == "homeChecks" or name.startswith("integrated") else "package"
      value = values.get(key, "")
      if not value.startswith("/nix/store/") or not value.endswith(".drv"):
        raise RuntimeError(f"No evaluated derivation for {group}/{name}")


def missing_argument(result):
  return result.returncode != 0 and re.search(r"attribute ['\"]tauridium['\"] missing", result.stderr) is not None


def evaluate(attribute):
  return subprocess.run(
    ["nix", "--extra-experimental-features", "nix-command flakes", "eval",
     "--json", "--no-write-lock-file", "--no-update-lock-file", f"./tests/nix-integration#{attribute}"],
    cwd=ROOT, text=True, capture_output=True, check=False, timeout=300,
  )


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--system", choices=SYSTEMS, action="append")
  parser.add_argument("--output", type=Path)
  args = parser.parse_args()
  evidence = {}
  for system in args.system or SYSTEMS:
    result = evaluate(f"reports.{system}")
    if result.returncode:
      raise RuntimeError(f"Consumer evaluation failed ({system}):\n{result.stderr}")
    report = json.loads(result.stdout)
    validate_report(report)
    report["missingArgumentRegressions"] = {}
    for failure in FAILURES:
      result = evaluate(f"failures.{system}.{failure}")
      if not missing_argument(result):
        raise RuntimeError(f"Expected missing Tauridium argument ({system}/{failure}):\n{result.stdout}\n{result.stderr}")
      report["missingArgumentRegressions"][failure] = {"expectedFailure": True, "diagnostic": result.stderr}
    evidence[system] = report
    print(f"{system}: 10 consumption checks and 3 missing-argument regressions passed")
  if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
  main()
