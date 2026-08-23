#!/usr/bin/env python3
"""Reject known Rust supply-chain indicators from the August 2026 incident."""

from __future__ import annotations

import argparse
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MALICIOUS_EXACT: dict[str, str] = {
  "append-only-vec": "0.1.9",
  "arrayref": "0.3.10",
  "internment": "0.8.7",
}

MALICIOUS_NAMES: frozenset[str] = frozenset(
  {
    "proc-macro1",
    "proc-macro-en",
    "aovine",
    "arone",
    "aronenao",
    "tinymember",
  }
)

DEPENDENCY_TABLES = {"dependencies", "dev-dependencies", "build-dependencies"}


@dataclass(frozen=True)
class Finding:
  path: Path
  package: str
  version: str | None
  reason: str


def blocked_reason(name: str, version: str | None) -> str | None:
  if name in MALICIOUS_NAMES:
    return "deleted malicious/typosquat crate name"
  if version is not None and MALICIOUS_EXACT.get(name) == version:
    return "deleted malicious crate release"
  return None


def version_mentions(version_spec: object, version: str) -> bool:
  if not isinstance(version_spec, str):
    return False
  return re.search(rf"(?<![0-9.]){re.escape(version)}(?![0-9.])", version_spec) is not None


def scan_lockfile(path: Path) -> list[Finding]:
  findings: list[Finding] = []
  data = tomllib.loads(path.read_text(encoding="utf-8"))
  for package in data.get("package", []):
    name = package.get("name")
    version = package.get("version")
    if not isinstance(name, str) or not isinstance(version, str):
      continue
    reason = blocked_reason(name, version)
    if reason:
      findings.append(Finding(path, name, version, reason))
    source = package.get("source")
    if isinstance(source, str) and source.startswith("registry+") and not package.get("checksum"):
      findings.append(Finding(path, name, version, "registry package is missing lockfile checksum"))
  return findings


def iter_manifest_dependencies(node: object):
  if not isinstance(node, dict):
    return
  for key, value in node.items():
    if key in DEPENDENCY_TABLES and isinstance(value, dict):
      for alias, spec in value.items():
        if isinstance(spec, dict):
          name = spec.get("package", alias)
          version = spec.get("version")
        else:
          name = alias
          version = spec
        if isinstance(name, str):
          yield name, version
    yield from iter_manifest_dependencies(value)


def scan_manifest(path: Path) -> list[Finding]:
  findings: list[Finding] = []
  data = tomllib.loads(path.read_text(encoding="utf-8"))
  package = data.get("package")
  if isinstance(package, dict):
    name = package.get("name")
    version = package.get("version")
    if isinstance(name, str):
      reason = blocked_reason(name, version if isinstance(version, str) else None)
      if reason:
        findings.append(
          Finding(path, name, version if isinstance(version, str) else None, reason)
        )

  for name, version_spec in iter_manifest_dependencies(data):
    if name in MALICIOUS_NAMES:
      findings.append(Finding(path, name, None, "deleted malicious/typosquat dependency"))
      continue
    malicious_version = MALICIOUS_EXACT.get(name)
    if malicious_version and version_mentions(version_spec, malicious_version):
      findings.append(
        Finding(path, name, malicious_version, "dependency specification names malicious release")
      )
  return findings


def crate_archive_identity(path: Path) -> tuple[str, str | None]:
  stem = path.name.removesuffix(".crate")
  for name in MALICIOUS_NAMES:
    if stem == name or stem.startswith(f"{name}-"):
      version = stem[len(name) + 1 :] if stem.startswith(f"{name}-") else None
      return name, version or None
  for name, version in MALICIOUS_EXACT.items():
    if stem == f"{name}-{version}":
      return name, version
  return "", None


def scan_crate_archives(root: Path) -> list[Finding]:
  findings: list[Finding] = []
  if not root.exists():
    return findings
  for path in root.rglob("*.crate"):
    name, version = crate_archive_identity(path)
    if not name:
      continue
    reason = blocked_reason(name, version) or "suspicious deleted crate archive"
    findings.append(Finding(path, name, version, reason))
  return findings


def scan_repository(root: Path = ROOT) -> list[Finding]:
  findings: list[Finding] = []
  for path in sorted(root.rglob("Cargo.lock")):
    if ".git" not in path.parts:
      findings.extend(scan_lockfile(path))
  for filename in ("Cargo.toml", "Cargo.toml.orig"):
    for path in sorted(root.rglob(filename)):
      if ".git" not in path.parts:
        findings.extend(scan_manifest(path))
  findings.extend(scan_crate_archives(root))
  return findings


def cargo_cache_root() -> Path:
  cargo_home = os.environ.get("CARGO_HOME")
  if cargo_home:
    return Path(cargo_home).expanduser() / "registry" / "cache"
  return Path.home() / ".cargo" / "registry" / "cache"


def print_findings(findings: list[Finding]) -> None:
  for finding in findings:
    version = f"@{finding.version}" if finding.version else ""
    print(
      f"error: {finding.package}{version}: {finding.reason}: {finding.path}",
      flush=True,
    )


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument(
    "--cache",
    action="store_true",
    help="also scan the local Cargo registry cache using the Rust Security Team IOC list",
  )
  args = parser.parse_args()

  findings = scan_repository(ROOT)
  cache_root = cargo_cache_root()
  if args.cache:
    findings.extend(scan_crate_archives(cache_root))

  if findings:
    print_findings(findings)
    return 1

  message = "Rust supply-chain check passed: repository contains no blocked August 2026 crates."
  if args.cache:
    if cache_root.exists():
      message += " Cargo registry cache is clean for the same indicators."
    else:
      message += " Cargo registry cache is not present."
  print(message)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
