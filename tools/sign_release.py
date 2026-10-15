"""Key-custody-only step: no compilation, npm, cargo aliases, hooks or payload execution."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from package_release import version
from release_assets import expected_updater_artifact_names
import release_policy as policy
from updater_signature import verify

ROOT = Path(__file__).resolve().parents[1]


def signing_environment() -> tuple[dict[str, str], dict[str, str]]:
  # Remove key custody from the parent before invoking any helper/verifier.
  key = os.environ.pop("TAURI_SIGNING_PRIVATE_KEY", "")
  password = os.environ.pop("TAURI_SIGNING_PRIVATE_KEY_PASSWORD", "")
  for name in list(os.environ):
    if name.startswith(("TAURI_PRIVATE_KEY", "TAURI_SIGNING_PRIVATE_KEY")):
      del os.environ[name]
  if not key:
    raise SystemExit("error: protected release signing requires an updater private key")
  names = {"PATH", "HOME", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL"}
  base = {name: value for name, value in os.environ.items() if name in names}
  secret = {**base, "TAURI_SIGNING_PRIVATE_KEY": key, "TAURI_SIGNING_PRIVATE_KEY_PASSWORD": password}
  return base, secret


def sign(assets: Path, output: Path, release_version: str, *, executable: str | None = None) -> None:
  base_env, secret_env = signing_environment()
  executable = executable or shutil.which("cargo-tauri")
  if not executable:
    raise SystemExit("error: install the pinned cargo-tauri in a separate key-free step")
  executable = str(Path(executable).resolve())
  cli = json.loads((ROOT / "data/build-toolchain.json").read_text(encoding="utf-8"))["tauriCli"]
  if output.exists() or output.is_symlink():
    raise SystemExit("error: signing requires a fresh output directory")
  files = policy.validate_directory(assets, policy.public_names(release_version, signed=False, metadata=False),
                                    internal={"release-notes.md"})
  output.parent.mkdir(parents=True, exist_ok=True)
  with tempfile.TemporaryDirectory(prefix=".tauridium-signer-", dir=output.parent) as temporary:
    staged = Path(temporary)
    result = subprocess.run([executable, "--version"], cwd=staged, env=base_env, capture_output=True,
                            text=True, timeout=30, check=False)
    if result.returncode or result.stdout.strip() != f"tauri-cli {cli}":
      raise SystemExit("error: updater signing requires the exact pinned Tauri CLI")
    for source in files + [assets / "release-notes.md"]:
      policy.regular(source)
      shutil.copyfile(source, staged / source.name)
    try:
      for name in expected_updater_artifact_names(release_version):
        artifact = staged / name
        before = policy.digest(artifact)
        result = subprocess.run([executable, "signer", "sign", "--app-version", release_version, str(artifact.resolve())],
                                cwd=staged, env=secret_env, capture_output=True, timeout=120, check=False)
        if result.returncode:
          raise SystemExit("error: updater signing failed; signer output withheld to protect key material")
        if before != policy.digest(artifact):
          raise SystemExit("error: updater signing changed the artifact bytes")
        verify(artifact, artifact.with_name(name + ".sig"), release_version)
      policy.validate_directory(staged, policy.public_names(release_version, metadata=False),
                                internal={"release-notes.md"})
      os.rename(staged, output)
    finally:
      secret_env.clear()


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("assets", type=Path)
  parser.add_argument("output", type=Path)
  args = parser.parse_args()
  try:
    sign(args.assets, args.output, version())
  except (OSError, subprocess.SubprocessError):
    raise SystemExit("error: isolated updater signer could not complete; private process diagnostics withheld") from None
