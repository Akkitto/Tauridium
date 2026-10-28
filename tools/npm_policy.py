#!/usr/bin/env python3
"""Validate the script-free npm installation contract shared by both bootstraps."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE_HOOKS = {"preinstall", "install", "postinstall", "prepare", "prepublish", "prepublishOnly"}
EXPECTED_HOOK_METADATA = {"node_modules/fsevents": "2.3.3"}


LOCAL_PATH = "vendor/deepmerge"
LOCAL_VERSION = "4.3.1+tauridium.1"
UPSTREAM_INTEGRITY = "sha512-3sUqbMEc77XqpdNO7FRyRog+eW3ph+GYCbj+rK+uYyRMuwsVy0rMiVtPn+QJlKFvWP/1PYpapqYn0Me2knFn+A=="


def validate_local_lock(packages: dict) -> None:
    """Only the reviewed in-tree security backport may use a local npm link."""
    if packages.get("node_modules/deepmerge") != {"resolved": LOCAL_PATH, "link": True}:
        raise ValueError("The Svelte merger must resolve to the reviewed local security backport")
    if packages.get(LOCAL_PATH, {}).get("version") != LOCAL_VERSION:
        raise ValueError("Unexpected local deepmerge version")
    for path, entry in packages.items():
        if path == "node_modules/deepmerge":
            continue
        if entry.get("link") or (entry.get("resolved") is not None and
                                 not entry["resolved"].startswith("https://registry.npmjs.org/")):
            raise ValueError("Unreviewed local or non-registry npm source")
        if path.endswith("/deepmerge") and path != LOCAL_PATH:
            raise ValueError("A second deepmerge copy could bypass the security backport")


def validate_local_sources(root: Path, package: dict, packages: dict) -> None:
    validate_local_lock(packages)
    if package.get("devDependencies", {}).get("deepmerge") != "file:" + LOCAL_PATH or package.get("overrides", {}).get("deepmerge") != "$deepmerge":
        raise ValueError("The explicit root deepmerge security override is required")
    vendor = root / LOCAL_PATH
    if vendor.is_symlink():
        raise ValueError("The local security backport must be in the source tree")
    provenance = json.loads((vendor / "TAURIDIUM-PATCH.json").read_text(encoding="utf-8"))
    upstream = provenance.get("upstream", {})
    if provenance.get("version") != LOCAL_VERSION or upstream != {
        "name": "deepmerge", "version": "4.3.1",
        "url": "https://registry.npmjs.org/deepmerge/-/deepmerge-4.3.1.tgz",
        "sha512": UPSTREAM_INTEGRITY,
    }:
        raise ValueError("Unexpected deepmerge security-patch provenance")
    files = provenance.get("files", {})
    if set(files) != {"dist/cjs.js", "package.json", "LICENSE", "index.d.ts"}:
        raise ValueError("Incomplete deepmerge security-patch manifest")
    for name, digest in files.items():
        path = vendor / name
        if path.is_symlink() or not path.resolve().is_relative_to(vendor.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Local deepmerge security-patch integrity mismatch")
    metadata = json.loads((vendor / "package.json").read_text(encoding="utf-8"))
    if metadata.get("name") != "deepmerge" or metadata.get("version") != LOCAL_VERSION or metadata.get("main") != "dist/cjs.js" or metadata.get("scripts") or metadata.get("dependencies"):
        raise ValueError("The reviewed local merger may not acquire hooks or dependencies")


def validate(root: Path = ROOT) -> None:
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))
    config = [line.strip() for line in (root / ".npmrc").read_text(encoding="utf-8").splitlines()
              if line.strip() and not line.lstrip().startswith(("#", ";"))]
    if config != ["ignore-scripts=true"]:
        raise ValueError("Project .npmrc must disable implicit lifecycle scripts")
    if "allowScripts" in package:
        raise ValueError("Remove unsupported allowScripts metadata; it is not a lifecycle security control")
    if set(package.get("scripts", {})) & LIFECYCLE_HOOKS:
        raise ValueError("Root installation lifecycle hooks are prohibited")
    packages = lock.get("packages", {})
    hooks = {path for path, entry in packages.items() if entry.get("hasInstallScript")}
    if hooks != set(EXPECTED_HOOK_METADATA) or any(packages[path].get("version") != version for path, version in EXPECTED_HOOK_METADATA.items()):
        raise ValueError("Unexpected dependency lifecycle-hook metadata; review the lockfile before installation")
    validate_local_sources(root, package, packages)
    # Vite 8's Rolldown and Lightning CSS use locked native platform packages.
    # The optional macOS fsevents installation hook remains deliberately disabled.


def main() -> int:
    try:
        validate()
    except (OSError, ValueError, TypeError, KeyError):
        print("error: npm lifecycle policy validation failed; inspect .npmrc, hooks, locked sources and the local security backport", file=sys.stderr)
        return 1
    print("npm lifecycle policy validated: all implicit dependency hooks are disabled; local security backport verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
