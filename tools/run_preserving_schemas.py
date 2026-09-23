#!/usr/bin/env python3
"""Run an alternate Cargo feature matrix without changing canonical Tauri schemas."""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = ROOT / "src-tauri/gen/schemas"


def snapshot_files(schema_root: Path) -> dict[Path, tuple[bytes, int]]:
  snapshot: dict[Path, tuple[bytes, int]] = {}
  for path in sorted(schema_root.rglob("*")):
    if path.is_symlink():
      raise RuntimeError(f"generated schema path must not be a symlink: {path}")
    if path.is_file():
      snapshot[path.relative_to(schema_root)] = (path.read_bytes(), path.stat().st_mode)
  return snapshot


def restore_files(schema_root: Path, snapshot: dict[Path, tuple[bytes, int]]) -> None:
  for path in sorted(schema_root.rglob("*"), reverse=True):
    relative = path.relative_to(schema_root)
    if path.is_file() and relative not in snapshot:
      path.unlink()
    elif path.is_dir() and not any(path.iterdir()):
      path.rmdir()

  for relative, (contents, mode) in snapshot.items():
    path = schema_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)
    os.chmod(path, mode)


def run_preserving_schemas(command: Sequence[str], schema_root: Path, cwd: Path) -> int:
  if not command or Path(command[0]).name != "cargo":
    raise ValueError("generated-schema guard requires a Cargo command")
  if not schema_root.is_dir():
    raise RuntimeError(f"generated schema directory is missing: {schema_root}")

  snapshot = snapshot_files(schema_root)
  print(f"+ {shlex.join(command)}", flush=True)
  try:
    result = subprocess.run(command, cwd=cwd, check=False)
  finally:
    restore_files(schema_root, snapshot)
  return result.returncode if result.returncode >= 0 else 128 - result.returncode


def main() -> int:
  return run_preserving_schemas(sys.argv[1:], SCHEMA_ROOT, ROOT)


if __name__ == "__main__":
  raise SystemExit(main())
