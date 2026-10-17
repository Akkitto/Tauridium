"""Exact public inventory and bounded, non-executing artifact validation."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import time
import zipfile
import zlib

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


def zip_layout(archive: zipfile.ZipFile) -> None:
  # Public ZIPs are ordinary archives, never self-extracting/concatenated data.
  # Account for all local records too: a directory can omit a compressed member
  # without breaking ZipFile.testzip(), leaving its contents silently uninspected.
  entries = sorted(archive.infolist(), key=lambda entry: entry.header_offset)
  if len(entries) > 100_000:
    raise SystemExit("error: ZIP member inventory exceeds the public size budget")
  if (entries[0].header_offset if entries else archive.start_dir) != 0:
    raise SystemExit("error: ZIP preambles or concatenated archive layouts are not permitted")
  failure = "error: ZIP contains unindexed, overlapping or trailing container data"
  stream = archive.fp
  if stream is None:
    raise SystemExit(failure)
  original_position = stream.tell()
  try:
    for index, entry in enumerate(entries):
      # ZipInfo may normalize backslashes on Windows and truncate NULs. Reject
      # the original central-directory name before trusting that transformed view.
      safe_name(entry.orig_filename)
      if entry.orig_filename != entry.filename:
        raise SystemExit("error: unsafe normalized ZIP member path")
      if entry.is_dir() and entry.file_size:
        raise SystemExit("error: ZIP directory entries must not contain file payloads")
      boundary = entries[index + 1].header_offset if index + 1 < len(entries) else archive.start_dir
      stream.seek(entry.header_offset)
      header = stream.read(30)
      if len(header) != 30 or header[:4] != b"PK\x03\x04":
        raise SystemExit(failure)
      _, _, flags, compression, _, _, crc, compressed, expanded, name_size, extra_size = struct.unpack("<4s5H3I2H", header)
      end = entry.header_offset + 30 + name_size + extra_size + entry.compress_size
      if flags != entry.flag_bits or compression != entry.compress_type or end > boundary:
        raise SystemExit(failure)
      if not flags & 8:
        if (end != boundary or crc != entry.CRC
            or compressed not in (entry.compress_size, 0xffffffff) or expanded not in (entry.file_size, 0xffffffff)):
          raise SystemExit(failure)
      else:
        # Streaming ZIPs legitimately use signed/unsigned 32-bit or ZIP64 data
        # descriptors. Permit exactly the descriptor bytes, never an arbitrary gap.
        wide = compressed == 0xffffffff or expanded == 0xffffffff
        size = 20 if wide else 12
        gap = boundary - end
        if gap not in (size, size + 4):
          raise SystemExit(failure)
        stream.seek(end)
        descriptor = stream.read(gap)
        if gap == size + 4:
          if descriptor[:4] != b"PK\x07\x08":
            raise SystemExit(failure)
          descriptor = descriptor[4:]
        if struct.unpack("<IQQ" if wide else "<III", descriptor) != (entry.CRC, entry.compress_size, entry.file_size):
          raise SystemExit(failure)
    stream.seek(0, os.SEEK_END)
    length = stream.tell()
    stream.seek(max(0, length - 65557))
    tail = stream.read(65557)
    marker = tail.rfind(b"PK\x05\x06")
    if marker < 0 or len(tail) - marker < 22:
      raise SystemExit(failure)
    _, disk, directory_disk, disk_count, count, directory_size, directory_offset, comment_size = struct.unpack_from("<4s4H2IH", tail, marker)
    end_record = length - len(tail) + marker
    if marker + 22 + comment_size != len(tail) or disk or directory_disk:
      raise SystemExit(failure)
    stream.seek(max(0, end_record - 20))
    locator = stream.read(20)
    if locator.startswith(b"PK\x06\x07"):
      _, locator_disk, position, disks = struct.unpack("<4sIQI", locator)
      if locator_disk or disks != 1 or position > end_record - 76:
        raise SystemExit(failure)
      stream.seek(position)
      record = stream.read(56)
      if len(record) != 56 or record[:4] != b"PK\x06\x06":
        raise SystemExit(failure)
      _, record_size, _, _, disk, directory_disk, disk_count, count, directory_size, directory_offset = struct.unpack("<4sQ2H2I4Q", record)
      if disk or directory_disk or record_size != 44 or position + 56 != end_record - 20:
        raise SystemExit(failure)
      end_record = position
    if (disk_count != count or count != len(entries) or directory_offset != archive.start_dir
        or directory_offset + directory_size != end_record):
      raise SystemExit(failure)
  finally:
    stream.seek(original_position)


def zip_payload(archive: zipfile.ZipFile, entry: zipfile.ZipInfo, *, limit: int) -> bytes:
  """Decode the complete physical stream, independently of ZipExtFile's size cap.

  Public producers use only stored/deflate. Reject other codecs rather than let
  a reader's truncated output or unused compressed suffix escape inspection.
  """
  failure = "error: ZIP codec consumption, size or full CRC validation failed"
  if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
    raise SystemExit("error: unsupported public ZIP compression method")
  if entry.flag_bits & 1 or entry.file_size > limit or limit < 0:
    raise SystemExit("error: ZIP expansion exceeds the actual byte budget")
  # This verifies the local filename, flags and overlap checks, but its payload
  # reader is deliberately not trusted to validate the underlying codec stream.
  with archive.open(entry):
    pass
  stream = archive.fp
  assert stream is not None
  stream.seek(entry.header_offset + 26)
  name_size, extra_size = struct.unpack("<HH", stream.read(4))
  stream.seek(entry.header_offset + 30 + name_size + extra_size)
  decoder = zlib.decompressobj(-15) if entry.compress_type == zipfile.ZIP_DEFLATED else None
  output = bytearray()
  crc, remaining = 0, entry.compress_size
  deadline = time.monotonic() + 180
  while remaining:
    if time.monotonic() > deadline:
      raise SystemExit("error: ZIP decoder exceeded its time budget")
    block = stream.read(min(65536, remaining))
    if not block:
      raise zipfile.BadZipFile(failure)
    remaining -= len(block)
    pending = block
    while True:
      if time.monotonic() > deadline:
        raise SystemExit("error: ZIP decoder exceeded its time budget")
      chunk = decoder.decompress(pending, min(65536, entry.file_size - len(output) + 1)) if decoder else pending
      output.extend(chunk)
      crc = zlib.crc32(chunk, crc)
      if len(output) > entry.file_size or len(output) > limit:
        raise SystemExit("error: ZIP expansion exceeds the actual byte budget")
      if decoder and (decoder.unused_data or decoder.eof and remaining):
        raise zipfile.BadZipFile(failure)
      pending = decoder.unconsumed_tail if decoder else b""
      # zlib can consume the last input byte yet retain output internally when
      # max_length is reached. Drain it with bounded empty-input calls too;
      # absence of unconsumed_tail alone does not mean all output was produced.
      if decoder is None or decoder.eof or not pending and not chunk:
        break
  if (decoder and not decoder.eof) or len(output) != entry.file_size or crc != entry.CRC:
    raise zipfile.BadZipFile(failure)
  return bytes(output)


def inspect_file(path: Path) -> None:
  size = regular(path).st_size
  with path.open("rb") as stream:
    header = stream.read(128)
    suffix = path.suffix
    if suffix == ".zip":
      with zipfile.ZipFile(path) as archive:
        zip_layout(archive)
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
          zip_payload(archive, entry, limit=min(MAX_FILE, MAX_TOTAL - total + entry.file_size))
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
