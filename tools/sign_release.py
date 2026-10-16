"""Linux-only minimal key custody: pinned Minisign, hash-only inputs, no build tools."""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

# Protected workflows invoke Python with -I; never load user/PYTHONPATH code.
sys.path.append(str(Path(__file__).resolve().parent))
import release_policy as policy
from updater_signature import verify
import release_snapshot

ROOT = Path(__file__).resolve().parents[1]


def signing_environment() -> tuple[dict[str, str], dict[str, str]]:
  # Remove key custody from the parent before invoking any helper/verifier.
  key = os.environ.pop("TAURI_SIGNING_PRIVATE_KEY", "")
  password = os.environ.pop("TAURI_SIGNING_PRIVATE_KEY_PASSWORD", "")
  for name in list(os.environ):
    if name.startswith(("TAURI_PRIVATE_KEY", "TAURI_SIGNING_")):
      del os.environ[name]
  if not key:
    raise SystemExit("error: protected release signing requires an updater private key")
  names = {"PATH", "HOME", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL"}
  base = {name: value for name, value in os.environ.items() if name in names}
  secret = {"TAURI_SIGNING_PRIVATE_KEY": key, "TAURI_SIGNING_PRIVATE_KEY_PASSWORD": password}
  return base, secret


def pinned_signer(executable: str) -> str:
  path = Path(executable).resolve(strict=True)
  policy.regular(path)
  entry = json.loads((ROOT / "data/security-tools.json").read_text(encoding="utf-8"))["minisign"]
  if policy.digest(path) != entry["binarySha256"]:
    raise SystemExit("error: signer is not the checksum-pinned official Minisign executable")
  return str(path)


def sign(assets: Path, output: Path, release_version: str, *, executable: str) -> None:
  base_env, secret = signing_environment()
  try:
    if sys.platform != "linux" or not Path("/dev/shm").is_dir():
      raise SystemExit("error: isolated key custody requires Linux shared-memory staging")
    executable = pinned_signer(executable)
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", release_version):
      raise SystemExit("error: invalid signing release version")
    if output.exists() or output.is_symlink():
      raise SystemExit("error: signing requires a fresh output directory")
    # No ZIP, PE, MSI or other complex artifact parsers under key custody.
    files = policy.validate_directory(assets, policy.public_names(release_version, signed=False, metadata=False),
                                      internal={"release-notes.md", release_snapshot.TRANSFER}, inspect=False)
    password = secret["TAURI_SIGNING_PRIVATE_KEY_PASSWORD"].encode("utf-8")
    if any(value in password for value in (b"\0", b"\r", b"\n")) or len(password) > 1022:
      raise SystemExit("error: Minisign passphrase must be a single line of at most 1022 UTF-8 bytes")
    if len(secret["TAURI_SIGNING_PRIVATE_KEY"]) > 16 * 1024:
      raise SystemExit("error: invalid updater private-key envelope")
    try:
      key_bytes = base64.b64decode(secret["TAURI_SIGNING_PRIVATE_KEY"].strip(), validate=True)
    except (ValueError, binascii.Error):
      raise SystemExit("error: invalid updater private-key envelope") from None
    secret.clear()
    output.parent.mkdir(parents=True, exist_ok=True)
    with (tempfile.TemporaryDirectory(prefix="tauridium-key-", dir="/dev/shm") as custody,
          tempfile.TemporaryDirectory(prefix=".tauridium-signer-", dir=output.parent) as temporary):
      key = Path(custody) / "updater.key"
      descriptor = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
      with os.fdopen(descriptor, "wb") as stream:
        stream.write(key_bytes)
      del key_bytes
      staged = Path(temporary)
      for source in files + [assets / "release-notes.md"]:
        policy.regular(source)
        shutil.copyfile(source, staged / source.name)
      unsigned = policy.public_names(release_version, signed=False, metadata=False)
      signatures = policy.public_names(release_version, metadata=False) - unsigned
      for signature_name in sorted(signatures):
        name = signature_name[:-4]
        artifact = staged / name
        before = policy.digest(artifact)
        raw = Path(custody) / "signature.minisig"
        comment = f"timestamp:{int(time.time())}\tfile:{name}\tversion:{release_version}"
        process = subprocess.run([executable, "-S", "-s", str(key), "-m", str(artifact.resolve()),
                                  "-x", str(raw), "-t", comment], cwd=custody, env=base_env,
                                 input=password + b"\n", capture_output=True, timeout=120, check=False)
        if process.returncode:
          raise SystemExit("error: updater signing failed; signer output withheld to protect key material")
        if before != policy.digest(artifact):
          raise SystemExit("error: updater signing changed the artifact bytes")
        signature = staged / signature_name
        signature.write_bytes(base64.b64encode(raw.read_bytes()))
        verify(artifact, signature, release_version, executable=executable)
      policy.validate_directory(staged, policy.public_names(release_version, metadata=False),
                                internal={"release-notes.md"}, inspect=False)
      os.rename(staged, output)
  finally:
    secret.clear()


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("assets", type=Path)
  parser.add_argument("output", type=Path)
  parser.add_argument("--minisign", required=True)
  parser.add_argument("--input-sha256", required=True)
  parser.add_argument("--commit", required=True)
  args = parser.parse_args()
  try:
    release_version = json.loads((ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))["version"]
    release_snapshot.verify(args.assets, release_version, args.commit, "unsigned", args.input_sha256)
    sign(args.assets, args.output, release_version, executable=args.minisign)
    print(release_snapshot.seal(args.output, release_version, args.commit, "signed"))
  except (OSError, ValueError, subprocess.SubprocessError):
    raise SystemExit("error: isolated updater signer could not complete; private process diagnostics withheld") from None
