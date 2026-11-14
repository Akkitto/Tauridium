"""Compile an Arch production ELF with the locked graph, without installer bundling."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
from tauri_build import build_environment

ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
  subprocess.run(["cargo", "build", "--manifest-path", "src-tauri/Cargo.toml", "--release",
                  "--offline", "--locked", "--no-default-features", "--features", "system-package,tauri/custom-protocol"],
                 cwd=ROOT, env=build_environment(dict(os.environ)), check=True)
