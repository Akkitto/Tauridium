#!/usr/bin/env python3
"""Fail when the Tauridium release checkout has tracked or untracked changes."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git_status_command(platform_name: str | None = None) -> list[str]:
  """Build a clean-tree query that respects each platform's file capabilities."""
  platform = os.name if platform_name is None else platform_name
  command = ["git"]
  if platform == "nt":
    # Full-Git checkpoints created on Unix can carry core.filemode=true into
    # Git for Windows, whose working tree cannot represent Unix execute bits.
    command.extend(["-c", "core.filemode=false"])
  command.extend(["status", "--porcelain", "--untracked-files=all"])
  return command


def main() -> int:
  result = subprocess.run(
    git_status_command(),
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
