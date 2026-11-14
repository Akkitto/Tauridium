#!/usr/bin/env python3
"""Prepare local Arch packages. No installs, registry writes or credential access."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import tarfile
import tempfile
import zipfile

import release_policy
from arch_check import inspect, validate as validate_build

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {"x86_64-unknown-linux-gnu": ("x64", 62), "aarch64-unknown-linux-gnu": ("arm64", 183)}
PAYLOAD = {
  "usr/bin/tauridium": None,
  "usr/share/applications/dev.brani.tauridium.desktop": "data/dev.brani.tauridium.desktop",
  "usr/share/metainfo/dev.brani.tauridium.metainfo.xml": "data/dev.brani.tauridium.metainfo.xml",
  "usr/share/icons/hicolor/512x512/apps/dev.brani.tauridium.png": "src-tauri/icons/icon.png",
  "usr/share/icons/hicolor/scalable/apps/dev.brani.tauridium.svg": "data/dev.brani.tauridium.svg",
  "usr/share/licenses/tauridium/LICENSE": "LICENSE",
}
SOURCE_ROOTS = ("src/", "vendor/", "data/", "src-tauri/src/", "src-tauri/assets/", "src-tauri/icons/", "src-tauri/capabilities/", "src-tauri/permissions/", "src-tauri/bundled-recipes/")
SOURCE_FILES = {"package.json", "package-lock.json", ".npmrc", "index.html", "vite.config.ts", "svelte.config.js", "tsconfig.json", "LICENSE", "src-tauri/Cargo.toml", "src-tauri/Cargo.lock", "src-tauri/build.rs", "src-tauri/tauri.conf.json", "tools/check_deepmerge.mjs", "tools/check_rust_supply_chain.py", "tools/arch_check.py", "tools/arch_build.py", "tools/tauri_build.py"}


def git(*args: str, root: Path = ROOT) -> str:
  return subprocess.check_output(["git", *args], cwd=root, text=True, encoding="utf-8").strip()


def version(root: Path = ROOT) -> str:
  value = json.loads((root / "package.json").read_text(encoding="utf-8"))["version"]
  if not re.fullmatch(r"\d+\.\d+\.\d+", value):
    raise ValueError("Arch packaging requires a stable three-part application version")
  return value


def payload_name(value: str, target: str) -> str:
  return f"tauridium-{value}-linux-{TARGETS[target][0]}-system.zip"


def check_elf(data: bytes, target: str) -> None:
  if len(data) < 64 or data[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", data, 18)[0] != TARGETS[target][1]:
    raise ValueError("system-package payload is not the expected 64-bit Linux ELF")


def validate_payload(path: Path, value: str, target: str) -> dict:
  release_policy.inspect_file(path)
  with zipfile.ZipFile(path) as archive:
    if set(archive.namelist()) != set(PAYLOAD) | {"BUILD-INFO.json"}:
      raise ValueError("system-package ZIP has missing or unexpected files")
    record = json.loads(archive.read("BUILD-INFO.json"))
    if record.get("schema") != 1 or not re.fullmatch(r"[a-f0-9]{40}", record.get("commit", "")):
      raise ValueError("system-package provenance record is malformed")
    validate_build(record["build"], value, target)
    binary = archive.read("usr/bin/tauridium")
    check_elf(binary, target)
    if record.get("binarySha256") != hashlib.sha256(binary).hexdigest():
      raise ValueError("system-package binary differs from the build record")
    for member in archive.infolist():
      expected = 0o755 if member.filename == "usr/bin/tauridium" else 0o644
      if stat.S_IMODE(member.external_attr >> 16) != expected:
        raise ValueError("system-package payload permissions differ")
  return record


def write_payload(binary: Path, target: str, output: Path, root: Path = ROOT) -> Path:
  value = version(root)
  release_policy.regular(binary)
  info = inspect(binary, value, target)
  contents = binary.read_bytes()
  check_elf(contents, target)
  record = {"schema": 1, "commit": git("rev-parse", "HEAD", root=root), "build": info,
            "binarySha256": hashlib.sha256(contents).hexdigest()}
  if git("status", "--porcelain", "--untracked-files=normal", root=root):
    raise ValueError("system-package release payload requires a clean Git worktree")
  output.mkdir(parents=True, exist_ok=True)
  destination = output / payload_name(value, target)
  if destination.exists() or destination.is_symlink():
    raise ValueError("system-package payload already exists; preserve it and choose a fresh output")
  with tempfile.TemporaryDirectory(prefix=".system-package-", dir=output) as temporary:
    staged = Path(temporary) / destination.name
    with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
      files = {name: contents if source is None else (root / source).read_bytes() for name, source in PAYLOAD.items()}
      files["BUILD-INFO.json"] = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode()
      for name, data in sorted(files.items()):
        entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
        entry.create_system = 3
        entry.external_attr = (stat.S_IFREG | (0o755 if name == "usr/bin/tauridium" else 0o644)) << 16
        entry.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(entry, data)
    validate_payload(staged, value, target)
    os.rename(staged, destination)
  return destination


def render(template: str, values: dict[str, str]) -> str:
  for key, value in values.items():
    if not re.fullmatch(r"[A-Za-z0-9._:/+\-=]+", value):
      raise ValueError("unsafe Arch recipe substitution")
    template = template.replace("@" + key + "@", value)
  if re.search(r"@[A-Z0-9_]+@", template):
    raise ValueError("unresolved Arch recipe field")
  return template


def write_recipe(directory: Path, kind: str, values: dict[str, str], root: Path = ROOT) -> None:
  template = (root / "packaging/aur" / f"PKGBUILD.{kind}.in").read_text(encoding="utf-8")
  (directory / "PKGBUILD").write_text(render(template, values), encoding="utf-8")
  # .SRCINFO is always generated by real makepkg via validate, never approximated.


def prepare_source(output: Path | None = None, root: Path = ROOT) -> Path:
  if git("status", "--porcelain", "--untracked-files=normal", root=root):
    raise ValueError("commit changes before preparing a reproducible Arch source snapshot")
  commit, value = git("rev-parse", "HEAD", root=root), version(root)
  destination = output or root / "release/aur" / commit[:12] / "tauridium"
  if destination.exists() or destination.is_symlink():
    raise ValueError("Arch preparation requires a fresh output directory")
  destination.parent.mkdir(parents=True, exist_ok=True)
  with tempfile.TemporaryDirectory(prefix=".aur-source-", dir=destination.parent) as temporary:
    staged = Path(temporary)
    source = f"tauridium-{value}-{commit[:12]}.tar.gz"
    # Export only tracked build inputs from HEAD. No .git, credentials, caches or evidence.
    tracked = git("ls-files", root=root).splitlines()
    selected = sorted(x for x in tracked if x in SOURCE_FILES or x.startswith(SOURCE_ROOTS))
    if not SOURCE_FILES.issubset(selected):
      raise ValueError("Arch source snapshot is missing required build inputs")
    timestamp = int(git("show", "-s", "--format=%ct", "HEAD", root=root))
    with (staged / source).open("wb") as stream, gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0) as compressed, tarfile.open(fileobj=compressed, mode="w|") as archive:
      for name in selected:
        release_policy.safe_name(name)
        mode = git("ls-files", "-s", "--", name, root=root).split()[0]
        if mode not in ("100644", "100755"):
          raise ValueError("Arch source inputs must be regular tracked files")
        data = subprocess.check_output(["git", "show", f"HEAD:{name}"], cwd=root)
        entry = tarfile.TarInfo("tauridium/" + name)
        entry.mode, entry.size, entry.mtime = int(mode, 8) & 0o777, len(data), timestamp
        archive.addfile(entry, io.BytesIO(data))
    tagged = git("tag", "--points-at", "HEAD", root=root).splitlines()
    values = {"VERSION": value, "COMMIT": commit, "PKGREL": "1" if "v" + value in tagged else "0.1", "SOURCE": source, "SHA256": release_policy.digest(staged / source)}
    write_recipe(staged, "source", values, root)
    (staged / "SOURCE.json").write_text(json.dumps({"commit": commit, "version": value, "sha256": values["SHA256"], "source": source}, indent=2) + "\n", encoding="utf-8")
    os.rename(staged, destination)
  return destination


def prepare_binary(path: Path, output: Path | None = None, root: Path = ROOT) -> Path:
  value = version(root)
  target = "x86_64-unknown-linux-gnu"  # ARM64 is not advertised until tested on Arch Linux ARM.
  if path.name != payload_name(value, target):
    raise ValueError("binary recipe requires the matching x86_64 system-package asset")
  record = validate_payload(path, value, target)
  destination = output or root / "release/aur" / record["commit"][:12] / "tauridium-bin"
  if destination.exists() or destination.is_symlink():
    raise ValueError("Arch binary preparation requires a fresh output directory")
  destination.parent.mkdir(parents=True, exist_ok=True)
  with tempfile.TemporaryDirectory(prefix=".aur-binary-", dir=destination.parent) as temporary:
    staged = Path(temporary)
    shutil.copyfile(path, staged / path.name)
    # Local sources remain fully usable from a checkout without any registry account.
    write_recipe(staged, "binary", {"VERSION": value, "PKGREL": "1", "SOURCE": path.name, "SHA256": release_policy.digest(path)}, root)
    os.rename(staged, destination)
  return destination


def validate_recipe(directory: Path) -> None:
  if not shutil.which("makepkg"):
    raise ValueError("Arch makepkg is required; run this command on Arch Linux as an ordinary user")
  if os.geteuid() == 0:
    raise ValueError("makepkg must run as an ordinary user")
  subprocess.run(["makepkg", "--verifysource"], cwd=directory, check=True)
  info = subprocess.check_output(["makepkg", "--printsrcinfo"], cwd=directory)
  destination = directory / ".SRCINFO"
  if destination.is_symlink():
    raise ValueError("refusing a symlinked .SRCINFO")
  if destination.exists() and destination.read_bytes() != info:
    raise ValueError(".SRCINFO differs; review changes before replacing it")
  destination.write_bytes(info)
  subprocess.run(["namcap", "PKGBUILD"], cwd=directory, check=True)


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  commands = parser.add_subparsers(dest="command", required=True)
  source = commands.add_parser("prepare")
  source.add_argument("--output", type=Path)
  binary = commands.add_parser("prepare-bin")
  binary.add_argument("archive", type=Path)
  binary.add_argument("--output", type=Path)
  check = commands.add_parser("validate")
  check.add_argument("directory", type=Path)
  payload = commands.add_parser("payload")
  payload.add_argument("--binary", type=Path, required=True)
  payload.add_argument("--target", choices=TARGETS, required=True)
  payload.add_argument("--output", type=Path, default=ROOT / "release/system-packages")
  args = parser.parse_args()
  if args.command == "prepare":
    print(prepare_source(args.output))
  elif args.command == "prepare-bin":
    print(prepare_binary(args.archive, args.output))
  elif args.command == "validate":
    validate_recipe(args.directory.resolve(strict=True))
  else:
    print(write_payload(args.binary, args.target, args.output))


if __name__ == "__main__":
  try:
    main()
  except (ValueError, OSError, subprocess.SubprocessError, zipfile.BadZipFile, KeyError) as error:
    raise SystemExit(f"error: {error}") from None
