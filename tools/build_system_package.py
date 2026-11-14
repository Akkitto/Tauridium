"""Build and export the key-free Linux package-manager payload."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import sys

from aur import ROOT, TARGETS, write_payload
from run_preserving_schemas import SCHEMA_ROOT, snapshot_files, restore_files


def build(target: str) -> Path:
  if sys.platform != "linux" or target not in TARGETS:
    raise ValueError("system packages require a supported Linux build target")
  if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
    raise ValueError("system-package builds require a clean worktree")
  target_dir = ROOT / "release/system-target"
  environment = dict(os.environ, CARGO_TARGET_DIR=str(target_dir))
  snapshot = snapshot_files(SCHEMA_ROOT)
  try:
    subprocess.run([sys.executable, "tools/tauri_build.py", "--no-bundle", "--ci", "--target", target,
                    "--no-default-features", "--features", "system-package"], cwd=ROOT, env=environment, check=True)
  finally:
    restore_files(SCHEMA_ROOT, snapshot)
  return write_payload(target_dir / target / "release/tauridium", target, ROOT / "release/system-packages")


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("target", choices=TARGETS)
  args = parser.parse_args()
  print(build(args.target))
