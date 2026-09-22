#!/usr/bin/env python3
"""Regenerate deterministic Flatpak Cargo/npm offline source manifests.

This intentionally implements only the lockfile formats used by Tauridium:
Cargo.lock v4 registry packages and npm package-lock.json v3 packages with
registry tarball URLs plus sha512 integrity values. It mirrors the source
layout consumed by Cargo and npm inside flatpak-builder.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FLATPAK_DIR = ROOT / "flatpak"
CARGO_LOCK = ROOT / "src-tauri" / "Cargo.lock"
NODE_LOCK = ROOT / "package-lock.json"
CARGO_OUTPUT = FLATPAK_DIR / "cargo-sources.json"
NODE_OUTPUT = FLATPAK_DIR / "node-sources.json"
TAURI_CLI_OUTPUT = FLATPAK_DIR / "tauri-cli-cargo-sources.json"

CARGO_CONFIG = (
  '[source.vendored-sources]\n'
  'directory = "vendor"\n\n'
  '[source.crates-io]\n'
  'replace-with = "vendored-sources"\n\n'
  '[net]\n'
  'offline = true\n'
)


def _compact_json(value: Any) -> str:
  return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _pretty_json(value: Any) -> str:
  return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def generate_cargo_sources(lock_path: Path) -> list[dict[str, Any]]:
  lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
  packages = lock.get("package")
  if not isinstance(packages, list):
    raise ValueError(f"{lock_path}: missing [[package]] entries")

  sources: list[dict[str, Any]] = []
  for package in packages:
    source = package.get("source", "")
    if not source.startswith("registry+"):
      # Local/path-patched crates are already in the immutable upstream source.
      continue

    name = package.get("name")
    version = package.get("version")
    checksum = package.get("checksum")
    if not all(isinstance(value, str) and value for value in (name, version, checksum)):
      raise ValueError(f"{lock_path}: registry package lacks name/version/checksum: {package!r}")

    destination = f"cargo/vendor/{name}-{version}"
    sources.append(
      {
        "type": "archive",
        "archive-type": "tar-gzip",
        "url": f"https://static.crates.io/crates/{name}/{name}-{version}.crate",
        "sha256": checksum,
        "dest": destination,
      }
    )
    sources.append(
      {
        "type": "inline",
        "contents": _compact_json({"package": checksum, "files": {}}),
        "dest": destination,
        "dest-filename": ".cargo-checksum.json",
      }
    )

  sources.append(
    {
      "type": "inline",
      "contents": CARGO_CONFIG,
      "dest": "cargo",
      "dest-filename": "config.toml",
    }
  )
  return sources


def _decode_sha512_integrity(integrity: str) -> tuple[str, str]:
  if not integrity.startswith("sha512-"):
    raise ValueError(f"Unsupported npm integrity algorithm: {integrity}")
  payload = integrity.removeprefix("sha512-")
  try:
    digest = base64.b64decode(payload, validate=True)
  except ValueError as error:
    raise ValueError(f"Invalid npm sha512 integrity: {integrity}") from error
  if len(digest) != hashlib.sha512().digest_size:
    raise ValueError(f"Invalid npm sha512 digest length: {integrity}")
  return payload, digest.hex()


def generate_node_sources(lock_path: Path) -> list[dict[str, Any]]:
  lock = json.loads(lock_path.read_text(encoding="utf-8"))
  if lock.get("lockfileVersion") != 3:
    raise ValueError(f"{lock_path}: expected package-lock v3")
  packages = lock.get("packages")
  if not isinstance(packages, dict):
    raise ValueError(f"{lock_path}: missing packages map")

  sources: list[dict[str, Any]] = []
  for package_path, package in packages.items():
    if not isinstance(package, dict):
      continue
    url = package.get("resolved")
    integrity = package.get("integrity")
    if url is None and integrity is None:
      continue
    if not isinstance(url, str) or not isinstance(integrity, str):
      raise ValueError(f"{lock_path}: incomplete resolved package {package_path}")
    if not url.startswith("https://registry.npmjs.org/"):
      raise ValueError(f"{lock_path}: unsupported non-registry package URL: {url}")

    _, content_hash = _decode_sha512_integrity(integrity)
    cache_key = f"make-fetch-happen:request-cache:{url}"
    cache_key_hash = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    cache_entry = {
      "key": cache_key,
      "integrity": integrity,
      "time": 0,
      "metadata": {"url": url, "reqHeaders": {}, "resHeaders": {}},
    }
    cache_entry_json = _compact_json(cache_entry)
    cache_entry_hash = hashlib.sha1(cache_entry_json.encode("utf-8")).hexdigest()

    sources.append(
      {
        "type": "file",
        "url": url,
        "sha512": content_hash,
        "dest": (
          "flatpak-node/npm-cache/_cacache/content-v2/sha512/"
          f"{content_hash[:2]}/{content_hash[2:4]}"
        ),
        "dest-filename": content_hash[4:],
      }
    )
    sources.append(
      {
        "type": "inline",
        "contents": f"{cache_entry_hash}\t{cache_entry_json}",
        "dest": (
          "flatpak-node/npm-cache/_cacache/index-v5/"
          f"{cache_key_hash[:2]}/{cache_key_hash[2:4]}"
        ),
        "dest-filename": cache_key_hash[4:],
      }
    )

  return sources


def _check_file(path: Path, generated: list[dict[str, Any]]) -> bool:
  expected = _pretty_json(generated)
  actual = path.read_text(encoding="utf-8") if path.exists() else ""
  if actual == expected:
    print(f"OK: {path.relative_to(ROOT)}")
    return True
  print(f"OUTDATED: {path.relative_to(ROOT)}", file=sys.stderr)
  return False


def _validate_tauri_cli_sources() -> bool:
  if not TAURI_CLI_OUTPUT.exists():
    print(f"MISSING: {TAURI_CLI_OUTPUT.relative_to(ROOT)}", file=sys.stderr)
    return False
  try:
    sources = json.loads(TAURI_CLI_OUTPUT.read_text(encoding="utf-8"))
  except json.JSONDecodeError as error:
    print(f"INVALID: {TAURI_CLI_OUTPUT.relative_to(ROOT)}: {error}", file=sys.stderr)
    return False
  if not isinstance(sources, list) or len(sources) < 500:
    print(f"INVALID: {TAURI_CLI_OUTPUT.relative_to(ROOT)} has too few sources", file=sys.stderr)
    return False
  final = sources[-1] if sources else {}
  expected_final = {
    "type": "inline",
    "contents": CARGO_CONFIG,
    "dest": "cargo",
    "dest-filename": "config.toml",
  }
  if final != expected_final:
    print(f"INVALID: {TAURI_CLI_OUTPUT.relative_to(ROOT)} lacks Cargo offline config", file=sys.stderr)
    return False
  print(f"OK: {TAURI_CLI_OUTPUT.relative_to(ROOT)} (pinned tauri-cli 2.11.3 source set)")
  return True


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
    "--check",
    action="store_true",
    help="fail when generated application Cargo/npm manifests differ from committed files",
  )
  args = parser.parse_args()

  cargo_sources = generate_cargo_sources(CARGO_LOCK)
  node_sources = generate_node_sources(NODE_LOCK)

  if args.check:
    ok = _check_file(CARGO_OUTPUT, cargo_sources)
    ok = _check_file(NODE_OUTPUT, node_sources) and ok
    ok = _validate_tauri_cli_sources() and ok
    return 0 if ok else 1

  FLATPAK_DIR.mkdir(parents=True, exist_ok=True)
  CARGO_OUTPUT.write_text(_pretty_json(cargo_sources), encoding="utf-8", newline="\n")
  NODE_OUTPUT.write_text(_pretty_json(node_sources), encoding="utf-8", newline="\n")
  if not _validate_tauri_cli_sources():
    return 1
  print(f"Wrote {CARGO_OUTPUT.relative_to(ROOT)} ({len(cargo_sources)} sources)")
  print(f"Wrote {NODE_OUTPUT.relative_to(ROOT)} ({len(node_sources)} sources)")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
