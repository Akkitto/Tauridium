"""Canonical native builds are key-free; signing is a separate custody-only step."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SIGNING_PREFIXES = ("TAURI_SIGNING_", "TAURI_PRIVATE_KEY", "APPLE_CERTIFICATE", "APPLE_API_KEY",
                    "APPLE_API_ISSUER", "APPLE_ID", "APPLE_PASSWORD", "CSC_")


def build_environment(environment: dict[str, str]) -> dict[str, str]:
  present = [name for name, value in environment.items() if value and name.startswith(SIGNING_PREFIXES)]
  if present:
    raise SystemExit("error: native builds never accept signing credentials; unset the signing environment and use the separate isolated sign-artifacts step")
  result = {name: value for name, value in environment.items() if not name.startswith(SIGNING_PREFIXES)}
  # Preserve Cargo's existing flag semantics while avoiding whitespace-sensitive
  # path arguments on Windows. More specific mappings follow general home paths.
  encoded = result.get("CARGO_ENCODED_RUSTFLAGS")
  flags = encoded.split("\x1f") if encoded else result.get("RUSTFLAGS", "").split()
  flags.extend([f"--remap-path-prefix={Path.home()}=/build/home",
                f"--remap-path-prefix={ROOT}=/build/tauridium"])
  result.pop("RUSTFLAGS", None)
  result["CARGO_ENCODED_RUSTFLAGS"] = "\x1f".join(flags)
  return result


def build(arguments: list[str]) -> int:
  if "--" in arguments:
    raise SystemExit("error: canonical build options must be Tauri CLI options, not unreviewed trailing Cargo arguments")
  environment = build_environment(dict(os.environ))
  executable = shutil.which("cargo-tauri")
  if not executable:
    raise SystemExit("error: pinned Tauri CLI is missing; run just init")
  executable = str(Path(executable).resolve())
  policy = json.loads((ROOT / "data/build-toolchain.json").read_text(encoding="utf-8"))
  config = ROOT / "src-tauri/tauri.no-updater.conf.json"
  if json.loads(config.read_text(encoding="utf-8")) != {"bundle": {"createUpdaterArtifacts": False}}:
    raise SystemExit("error: key-free build configuration must disable updater signing")
  probe = subprocess.run([executable, "--version"], cwd=ROOT, env=environment,
                         capture_output=True, text=True, check=False, timeout=30)
  if probe.returncode or probe.stdout.strip() != "tauri-cli " + policy["tauriCli"]:
    raise SystemExit("error: native build requires the exact pinned Tauri CLI; run just init")
  # Invoke the binary directly: no Cargo alias or before-build script runs with a
  # signing credential. The final merge config always disables automatic signing.
  command = [executable, "build", *arguments, "--config", str(config)]
  return subprocess.run(command, cwd=ROOT, env=environment, check=False).returncode


if __name__ == "__main__":
  try:
    raise SystemExit(build(sys.argv[1:]))
  except (OSError, subprocess.SubprocessError):
    raise SystemExit("error: key-free native build could not start or complete") from None
