#!/usr/bin/env python3
"""Fail when the Tauridium release checkout has tracked or untracked changes."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
  result = subprocess.run(
    ["git", "status", "--porcelain", "--untracked-files=all"],
    cwd=ROOT,
    text=True,
    capture_output=True,
    check=False,
  )
  if result.returncode != 0:
    detail = result.stderr.strip() or "git status failed"
    raise SystemExit(f"error: unable to verify clean Git worktree: {detail}")

  dirty = [line for line in result.stdout.splitlines() if line.strip()]
  if dirty:
    details = "\n".join(f"  {line}" for line in dirty)
    raise SystemExit(
      "error: release requires a clean Git worktree; changed paths:\n" + details
    )

  print("Tauridium release Git worktree is clean.")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
