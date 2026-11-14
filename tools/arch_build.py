"""Compile an Arch production ELF with the locked graph, without installer bundling."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
from tauri_build import build_environment

ROOT = Path(__file__).resolve().parents[1]


def build(target: str | None = None, environment: dict[str, str] | None = None) -> None:
  command = ["cargo", "build", "--manifest-path", "src-tauri/Cargo.toml", "--release",
                  "--offline", "--locked", "--no-default-features", "--features", "system-package,tauri/custom-protocol"]
  if target:
    command.extend(["--target", target])
  subprocess.run(command, cwd=ROOT, env=build_environment(dict(os.environ) if environment is None else environment), check=True)


if __name__ == "__main__":
  build()
