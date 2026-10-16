"""Exact public inventory and bounded, non-executing artifact validation."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import zipfile

TARGETS = {
  "x86_64-pc-windows-msvc": ("windows", "x64", "win-x64"),
  "aarch64-pc-windows-msvc": ("windows", "arm64", "win-arm64"),
  "x86_64-unknown-linux-gnu": ("linux", "x64", "linux-x64"),
  "aarch64-unknown-linux-gnu": ("linux", "arm64", "linux-arm64"),
}
MAX_FILE = 2 * 1024**3
MAX_TOTAL = 16 * 1024**3


def safe_name(name: str) -> None:
  normalized = name.rstrip("/")
  parts = PurePosixPath(normalized).parts
  if (not parts or normalized.startswith("/") or "\\" in name or ":" in name
      or any(part in (".", "..") or part.endswith((".", " ")) for part in parts)
      or any(ord(c) < 32 or ord(c) == 127 for c in name)
      or normalized != "/".join(parts)):
    raise SystemExit("error: unsafe artifact member path")


def regular(path: Path) -> os.stat_result:
  result = path.lstat()
  if not stat.S_ISREG(result.st_mode) or getattr(result, "st_file_attributes", 0) & 0x400:
    raise SystemExit("error: artifact must be a regular file, never a link/reparse point")
  if not 0 < result.st_size <= MAX_FILE:
    raise SystemExit("error: artifact is empty or exceeds the public size budget")
  return result


def digest(path: Path) -> str:
  result = hashlib.sha256()
  with path.open("rb") as stream:
    for block in iter(lambda: stream.read(1024 * 1024), b""):
      result.update(block)
  return result.hexdigest()


def target_names(version: str, target: str, signed: bool = False) -> set[str]:
  platform, arch, runtime = TARGETS[target]
  prefix = f"tauridium-{version}"
  names = {f"{prefix}-run-{runtime}.zip"}
  if platform == "windows":
    portable = f"{prefix}-windows-{arch}-portable.zip"
    names.update({portable, portable + ".sha256"})
    bundles = {f"{prefix}-windows-{arch}.msi", f"{prefix}-windows-{arch}-setup.exe"}
    names.update(bundles)
    if signed:
      names.update(name + ".sig" for name in bundles)
  else:
    names.update(f"{prefix}-linux-{arch}.{extension}" for extension in ("deb", "rpm", "AppImage"))
    if signed:
      names.add(f"{prefix}-linux-{arch}.AppImage.sig")
  return names


def handoff_names(version: str) -> set[str]:
  return {f"tauridium-{version}-{kind}.zip" for kind in ("src", "doc", "run-build-handoff")}


def public_names(version: str, *, signed: bool = True, metadata: bool = True) -> set[str]:
  names = handoff_names(version)
  for target in TARGETS:
    names.update(target_names(version, target, signed))
  if metadata:
    names.update({"SHA256SUMS", "ARTIFACTS.json", f"tauridium-{version}-scoop.json",
                  f"tauridium-{version}-build-inputs.cdx.json"})
    if signed:
      names.add("latest.json")
  return names


def inspect_file(path: Path) -> None:
  size = regular(path).st_size
  with path.open("rb") as stream:
    header = stream.read(128)
    suffix = path.suffix
    if suffix == ".zip":
      with zipfile.ZipFile(path) as archive:
        names = set()
        total = 0
        for entry in archive.infolist():
          safe_name(entry.filename)
          if entry.filename in names or entry.flag_bits & 1:
            raise SystemExit("error: duplicate or encrypted ZIP member")
          names.add(entry.filename)
          mode = entry.external_attr >> 16
          if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
            raise SystemExit("error: ZIP contains a link or special file")
          total += entry.file_size
          if entry.file_size > MAX_FILE or total > MAX_TOTAL or len(names) > 100_000:
            raise SystemExit("error: ZIP expansion exceeds the public size budget")
        if archive.testzip() is not None:
          raise SystemExit("error: ZIP integrity validation failed")
    elif suffix == ".exe":
      if header[:2] != b"MZ" or len(header) < 64:
        raise SystemExit("error: installer is not a PE executable")
      offset = struct.unpack_from("<I", header, 60)[0]
      if offset > size - 4:
        raise SystemExit("error: invalid PE header offset")
      stream.seek(offset)
      if stream.read(4) != b"PE\0\0":
        raise SystemExit("error: invalid PE signature")
    else:
      expected = {".AppImage": b"\x7fELF", ".msi": bytes.fromhex("d0cf11e0a1b11ae1"),
                  ".deb": b"!<arch>\n", ".rpm": bytes.fromhex("edabeedb")}.get(suffix)
      if expected and not header.startswith(expected):
        raise SystemExit("error: artifact format does not match its public filename")
      if suffix == ".AppImage" and header[8:11] not in (b"AI\x01", b"AI\x02"):
        raise SystemExit("error: ELF is not an AppImage")
      if suffix in (".json", ".sig", ".sha256") or path.name == "SHA256SUMS":
        if size > 16 * 1024**2:
          raise SystemExit("error: public metadata exceeds its size budget")
        if suffix == ".json":
          json.loads(path.read_text(encoding="utf-8"))


def validate_directory(directory: Path, expected: set[str], *, internal: set[str] | None = None,
                       inspect: bool = True) -> list[Path]:
  internal = internal or set()
  metadata = directory.lstat()
  if not stat.S_ISDIR(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x400:
    raise SystemExit("error: public artifact directory must not be a link/reparse point")
  actual = {path.name for path in directory.iterdir()}
  missing, extra = expected - actual, actual - expected - internal
  if missing or extra:
    # An unexpected filename itself can contain a credential. Public CI logs
    # may show approved missing names and counts, never attacker-supplied names.
    raise SystemExit(f"error: public artifact inventory differs: missing={sorted(missing)}, unexpectedFileCount={len(extra)}")
  total = 0
  for name in sorted(actual):
    safe_name(name)
    path = directory / name
    total += regular(path).st_size
    if total > MAX_TOTAL:
      raise SystemExit("error: public artifact set exceeds its size budget")
    if inspect:
      inspect_file(path)
  return [directory / name for name in sorted(expected)]


def write_inventory(directory: Path, version: str, commit: str) -> Path:
  if not re.fullmatch(r"[a-f0-9]{40}", commit):
    raise SystemExit("error: artifact inventory requires an immutable Git commit")
  names = public_names(version) - {"ARTIFACTS.json", "SHA256SUMS"}
  files = validate_directory(directory, names, internal={"release-notes.md"})
  inventory = {"schema": 1, "version": version, "commit": commit,
               "files": [{"name": path.name, "bytes": path.stat().st_size, "sha256": digest(path)} for path in files]}
  output = directory / "ARTIFACTS.json"
  output.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
  return output
