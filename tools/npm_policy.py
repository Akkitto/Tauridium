#!/usr/bin/env python3
"""Validate the script-free npm installation contract shared by both bootstraps."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE_HOOKS = {"preinstall", "install", "postinstall", "prepare", "prepublish", "prepublishOnly"}
EXPECTED_HOOK_METADATA = {"node_modules/esbuild": "0.25.12", "node_modules/fsevents": "2.3.3"}


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
    # esbuild's locked optional platform package supplies the native executable.
    # Its optimization/download postinstall hook is deliberately not executed.


def main() -> int:
    try:
        validate()
    except (OSError, ValueError, TypeError, KeyError):
        print("error: npm lifecycle policy validation failed; inspect .npmrc, root hooks and locked dependency hook metadata", file=sys.stderr)
        return 1
    print("npm lifecycle policy validated: all implicit dependency hooks are disabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
