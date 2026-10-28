#!/usr/bin/env python3
"""Verify the effective, build-only Flatpak Rust compiler and Cargo cohort."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess

VERSION = "1.97.1"
PREFIX = Path("/app/lib/tauridium-rust-toolchain")


def verify(prefix: Path = PREFIX, version: str = VERSION) -> None:
  for name in ("rustc", "cargo"):
    expected = prefix / "bin" / name
    selected = shutil.which(name)
    if selected != str(expected):
      raise SystemExit(f"error: Flatpak {name} must use the pinned build-only toolchain")
    if name == "rustc":
      for variable in ("RUSTC", "CARGO_BUILD_RUSTC"):
        if os.environ.get(variable, str(expected)) != str(expected):
          raise SystemExit("error: Flatpak Cargo must use the pinned Rust compiler")
    result = subprocess.run([str(expected), "--version"], capture_output=True, text=True,
                            check=False, timeout=30)
    if result.returncode or not re.fullmatch(re.escape(name + " " + version) + r" \([^\r\n]+\)", result.stdout.strip()):
      raise SystemExit(f"error: Flatpak {name} must be the reviewed {version} toolchain")
    print(result.stdout.strip())


if __name__ == "__main__":
  try:
    verify()
  except (OSError, subprocess.SubprocessError):
    raise SystemExit("error: Flatpak build-only toolchain verification failed") from None
