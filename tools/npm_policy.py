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
    validate_picomatch_lock(packages)
    if packages.get("node_modules/deepmerge") != {"resolved": LOCAL_PATH, "link": True}:
        raise ValueError("The Svelte merger must resolve to the reviewed local security backport")
    if packages.get(LOCAL_PATH, {}).get("version") != LOCAL_VERSION:
        raise ValueError("Unexpected local deepmerge version")
    for path, entry in packages.items():
        if path in ("node_modules/deepmerge", "node_modules/picomatch"):
            continue
        if entry.get("link") or (entry.get("resolved") is not None and
                                 not entry["resolved"].startswith("https://registry.npmjs.org/")):
            raise ValueError("Unreviewed local or non-registry npm source")
        if path.endswith("/picomatch") and path != "vendor/picomatch":
            raise ValueError("A second picomatch copy could bypass the security backport")
        if path.endswith("/deepmerge") and path != LOCAL_PATH:
            raise ValueError("A second deepmerge copy could bypass the security backport")


PICOMATCH_MANIFEST_SHA256 = "0bbade1d0862d8b971e15f90a97920231b145737398e3ee6f2fd20c000668101"
PICOMATCH_VERSION = "4.0.7+tauridium.1"
PICOMATCH_INTEGRITY = "sha512-qcJu88Q2IWqJsDD529JKMdwGm/dvInW4HvQnRwiH9JtihJvzGOscDtHE3x1pBKeUOTysQ8kVmLnJ2kJu7yhcGA=="
PICOMATCH_PARSER_SHA256 = "10e08261453bc5e1579afe463d2855940c89b35b821df7cc7483a1f93e42c2e1"


def validate_picomatch_lock(packages: dict) -> None:
    if (packages.get("node_modules/picomatch") != {"resolved": "vendor/picomatch", "link": True}
            or packages.get("vendor/picomatch", {}).get("version") != PICOMATCH_VERSION):
        raise ValueError("The glob matcher must resolve to the exact reviewed local security backport")


def validate_picomatch_source(root: Path, package: dict) -> None:
    if (package.get("devDependencies", {}).get("picomatch") != "file:vendor/picomatch"
            or package.get("overrides", {}).get("picomatch") != "$picomatch"):
        raise ValueError("The explicit picomatch security override is required")
    vendor = root / "vendor/picomatch"
    if vendor.is_symlink():
        raise ValueError("The local glob security backport must be in the source tree")
    raw = (vendor / "TAURIDIUM-PATCH.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != PICOMATCH_MANIFEST_SHA256:
        raise ValueError("Picomatch security-patch manifest integrity mismatch")
    provenance = json.loads(raw.decode("utf-8"))
    if (provenance.get("version") != PICOMATCH_VERSION or provenance.get("upstream") != {
            "name": "picomatch", "version": "4.0.7",
            "url": "https://registry.npmjs.org/picomatch/-/picomatch-4.0.7.tgz",
            "sha512": PICOMATCH_INTEGRITY}):
        raise ValueError("Unexpected picomatch security-patch provenance")
    files = provenance.get("files", {})
    expected = {"index.js", "posix.js", "lib/constants.js", "lib/parse.js", "lib/picomatch.js",
                "lib/scan.js", "lib/utils.js", "LICENSE", "package.json"}
    if set(files) != expected or files.get("lib/parse.js") != PICOMATCH_PARSER_SHA256:
        raise ValueError("Incomplete or unreviewed picomatch security-patch manifest")
    for name, digest in files.items():
        path = vendor / name
        if (path.is_symlink() or not path.resolve().is_relative_to(vendor.resolve())
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
            raise ValueError("Local picomatch security-patch integrity mismatch")
    metadata = json.loads((vendor / "package.json").read_text(encoding="utf-8"))
    if (metadata.get("name") != "picomatch" or metadata.get("version") != PICOMATCH_VERSION
            or metadata.get("main") != "index.js" or metadata.get("scripts") or metadata.get("dependencies")):
        raise ValueError("The reviewed local matcher may not acquire hooks or dependencies")


def validate_local_sources(root: Path, package: dict, packages: dict) -> None:
    validate_local_lock(packages)
    validate_picomatch_source(root, package)
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
