#!/usr/bin/env python3
"""Prepare the same checksum-verified, explicitly patched CLI on every platform.

Upstream CLI 2.12.3 and bundler 2.10.3 still require vulnerable ZIP 8. Only
their normalized ZIP dependencies, unused RPM signing stack, reviewed compression
lock and the CLI build identity are changed. No patch is made in Cargo's shared registry.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


class HttpsOnlyRedirect(HTTPRedirectHandler):
  def redirect_request(self, request, fp, code, message, headers, newurl):
    if urlparse(newurl).scheme != "https":
      raise SystemExit("error: builder download must not downgrade HTTPS")
    return super().redirect_request(request, fp, code, message, headers, newurl)


def download(name: str, version: str) -> bytes:
  request = Request(f"https://static.crates.io/crates/{name}/{name}-{version}.crate",
                    headers={"User-Agent": "Tauridium-verified-builder"})
  with build_opener(HttpsOnlyRedirect()).open(request, timeout=60) as response:
    return response.read(32 * 1024**2 + 1)


def unpack(data: bytes, output: Path, prefix: str, digest: str) -> None:
  if len(data) > 32 * 1024**2 or hashlib.sha256(data).hexdigest() != digest:
    raise SystemExit("error: upstream builder crate checksum or size differs")
  if output.exists() or output.is_symlink():
    raise SystemExit("error: builder preparation requires fresh output directories")
  with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
    members, seen, total = [], set(), 0
    for member in archive:
      path = PurePosixPath(member.name)
      total += member.size
      if (len(path.parts) < 2 or path.parts[0] != prefix or path.is_absolute()
          or member.name.rstrip("/") != "/".join(path.parts)
          or any(part in (".", "..") for part in path.parts) or "\\" in member.name or ":" in member.name
          or member.name in seen or not (member.isfile() or member.isdir())
          or total > 128 * 1024**2 or len(seen) >= 20000):
        raise SystemExit("error: upstream builder crate has an unsafe or oversized inventory")
      seen.add(member.name)
      members.append(member)
    output.mkdir(parents=True)
    for member in members:
      path = output.joinpath(*PurePosixPath(member.name).parts[1:])
      if member.isdir():
        path.mkdir(parents=True, exist_ok=True)
      else:
        path.parent.mkdir(parents=True, exist_ok=True)
        source = archive.extractfile(member)
        if source is None:
          raise SystemExit("error: incomplete builder crate")
        path.write_bytes(source.read())
        path.chmod(0o755 if member.mode & 0o111 else 0o644)


def replace_once(path: Path, old: str, new: str) -> None:
  text = path.read_text(encoding="utf-8")
  if text.count(old) != 1:
    raise SystemExit("error: reviewed builder dependency patch no longer matches upstream")
  path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


def prepare(output: Path, cli: bytes, bundler: bytes, policy: dict, lock: bytes) -> None:
  if hashlib.sha256(lock).hexdigest() != policy["tauriCliLockSha256"]:
    raise SystemExit("error: patched builder lock differs from its reviewed identity")
  unpack(cli, output, "tauri-cli-" + policy["tauriCli"], policy["tauriCliCrateSha256"])
  bundled = output / "tauridium-bundler"
  unpack(bundler, bundled, "tauri-bundler-" + policy["tauriBundler"], policy["tauriBundlerCrateSha256"])
  manifest = output / "Cargo.toml"
  replace_once(manifest, 'version = "' + policy["tauriCli"] + '"\n', 'version = "' + policy["tauriCliBuild"] + '"\n')
  replace_once(manifest, '[dependencies.tauri-bundler]\n', '[dependencies.tauri-bundler]\npath = "tauridium-bundler"\n')
  for path in (manifest, bundled / "Cargo.toml"):
    replace_once(path, '[dependencies.zip]\nversion = "8"\n', '[dependencies.zip]\nversion = "=9.0.4"\n')
  replace_once(bundled / "Cargo.toml",
               '[target.\'cfg(target_os = "linux")\'.dependencies.rpm]\nversion = "0.30"\nfeatures = ["bzip2-compression"]\n',
               '[target.\'cfg(target_os = "linux")\'.dependencies.rpm]\nversion = "0.30"\ndefault-features = false\n'
               'features = ["payload", "bzip2-compression", "gzip-compression", "zstd-compression", "xz-compression"]\n')
  rpm = bundled / "src/bundle/linux/rpm.rs"
  replace_once(rpm, 'use rpm::{self, Dependency, FileOptions, signature::pgp};', 'use rpm::{self, Dependency, FileOptions};')
  replace_once(rpm, '''  let pkg = if let Ok(raw_secret_key) = env::var("TAURI_SIGNING_RPM_KEY") {
    let mut signer = pgp::Signer::from_asc(&raw_secret_key)?;
    if let Ok(passphrase) = env::var("TAURI_SIGNING_RPM_KEY_PASSPHRASE") {
      signer = signer.with_key_passphrase(passphrase);
    }
    builder.build_and_sign(signer)?
  } else {
    builder.build()?
  };''', '''  if env::var_os("TAURI_SIGNING_RPM_KEY").is_some()
    || env::var_os("TAURI_SIGNING_RPM_KEY_PASSPHRASE").is_some()
  {
    return Err(crate::Error::GenericError(
      "Tauridium builds never accept RPM signing credentials".into(),
    ));
  }
  let pkg = builder.build()?;''')
  (output / "Cargo.lock").write_bytes(lock)


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--cli", type=Path)
  parser.add_argument("--bundler", type=Path)
  parser.add_argument("--policy", type=Path, default=ROOT / "data/build-toolchain.json")
  parser.add_argument("--lock", type=Path, default=ROOT / "flatpak/tauri-cli.Cargo.lock")
  parser.add_argument("--output", type=Path)
  parser.add_argument("--install", action="store_true")
  args = parser.parse_args()
  policy = json.loads(args.policy.read_text(encoding="utf-8"))
  cli = args.cli.read_bytes() if args.cli else download("tauri-cli", policy["tauriCli"])
  bundler = args.bundler.read_bytes() if args.bundler else download("tauri-bundler", policy["tauriBundler"])
  lock = args.lock.read_bytes()
  with tempfile.TemporaryDirectory(prefix="tauridium-verified-cli-") as temporary:
    output = args.output or Path(temporary) / "source"
    prepare(output, cli, bundler, policy, lock)
    if args.install:
      # Do not pass signing credentials to this build or any dependency script.
      import sys
      sys.path.insert(0, str(ROOT / "tools"))
      from tauri_build import build_environment
      return subprocess.run(["cargo", "install", "--path", str(output), "--locked", "--force"],
                            env=build_environment(dict(os.environ)), check=False).returncode
  return 0


if __name__ == "__main__":
  try:
    raise SystemExit(main())
  except (OSError, ValueError, KeyError, tarfile.TarError, subprocess.SubprocessError):
    raise SystemExit("error: verified patched CLI preparation or installation failed") from None
