"""Decode public artifacts as data, scan Git objects and binary string views, fail closed.

No installer, application, archive script, DLL, hook or extracted payload is run.
All scan material and diagnostics stay in an automatically removed private directory.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import io
import json
import lzma
import os
from pathlib import Path
import re
import selectors
import shutil
import struct
import subprocess
import tempfile
import time
import zipfile
import zlib

import release_policy as policy

ROOT = Path(__file__).resolve().parents[1]
MAX_PAYLOAD = 512 * 1024**2
MAX_EXPANDED = 16 * 1024**3


class ArtifactRejection(RuntimeError):
  """Only static messages or reviewed rule/hash metadata may use this public channel."""


def public_failure(error: BaseException) -> str:
  if isinstance(error, ArtifactRejection):
    return str(error)
  if isinstance(error, zipfile.BadZipFile):
    return "ZIP structure or integrity validation failed; member names withheld"
  if isinstance(error, (DecoderFailure, subprocess.SubprocessError)):
    return "Artifact decoder/scanner failed; private process diagnostics withheld"
  if isinstance(error, OSError):
    return "Artifact/tool filesystem access failed; private paths withheld"
  if isinstance(error, (ValueError, KeyError, lzma.LZMAError, zlib.error)):
    return "Artifact data or metadata is invalid; private parser diagnostics withheld"
  return "Artifact validation failed; private diagnostics withheld"
PEM = re.compile(rb"-----BEGIN ([A-Z0-9 ]*PRIVATE KEY)-----.*?-----END \1-----", re.S)


class DecoderFailure(RuntimeError):
  def __init__(self, code: int, output: bytes, has_diagnostics: bool):
    super().__init__("Artifact decoder failed; private diagnostics withheld")
    self.code, self.output, self.has_diagnostics = code, output, has_diagnostics


def bounded_command(arguments: list[str], *, env=None, limit=MAX_PAYLOAD, timeout=180) -> bytes:
  """Bound both time and actual stdout bytes; never echo potentially private diagnostics."""
  with tempfile.TemporaryDirectory(prefix="tauridium-decoder-cwd-") as work, tempfile.TemporaryFile() as diagnostics:
    process = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=diagnostics, env=env, cwd=work)
    assert process.stdout is not None
    result = bytearray()
    deadline = time.monotonic() + timeout
    try:
      with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while True:
          if time.monotonic() >= deadline:
            raise ArtifactRejection("Artifact decoder exceeded its time budget")
          events = selector.select(min(1, max(0, deadline - time.monotonic())))
          if not events:
            continue
          block = os.read(process.stdout.fileno(), 64 * 1024)
          if not block:
            break
          result.extend(block)
          if len(result) > limit:
            raise ArtifactRejection("Artifact decoder exceeded its actual byte budget")
      code = process.wait(timeout=max(0.1, deadline - time.monotonic()))
      if code:
        raise DecoderFailure(code, bytes(result), bool(diagnostics.seek(0, os.SEEK_END)))
      if any(Path(work).iterdir()):
        raise ArtifactRejection("Read-only decoder unexpectedly wrote auxiliary files")
      return bytes(result)
    finally:
      if process.poll() is None:
        process.kill()
        process.wait()
      process.stdout.close()


def nsis_solid_stream(data: bytes) -> tuple[bytes, int]:
  """Independent bounded reader for the stock Tauri solid-LZMA NSIS format.

  See upstream 7-Zip NsisDecode.cpp: five LZMA properties, a header-size-prefixed
  solid stream, then per-file little-endian lengths. No installer stub is run.
  """
  signature = b"\xef\xbe\xad\xdeNullsoftInst"
  positions = [match.start() - 4 for match in re.finditer(re.escape(signature), data)
               if match.start() >= 516 and (match.start() - 4) % 512 == 0]
  if len(positions) != 1:
    raise ArtifactRejection("Unsupported or ambiguous NSIS first header")
  start = positions[0]
  flags, header_size, following_size = struct.unpack_from("<I16xII", data, start)
  if flags & 4 or following_size < 37 or not 0 < header_size <= 8 * 1024**2 or start + following_size > len(data):
    raise ArtifactRejection("Unsupported NSIS size/CRC policy")
  begin, end = start + 28, start + following_size - 4
  if zlib.crc32(data[512:end]) != struct.unpack_from("<I", data, end)[0]:
    raise ArtifactRejection("NSIS complete-container CRC validation failed")
  properties, dictionary = data[begin], struct.unpack_from("<I", data, begin + 1)[0]
  if properties >= 225 or not 4096 <= dictionary <= 64 * 1024**2:
    raise ArtifactRejection("Unsupported NSIS LZMA properties")
  lc, remainder = properties % 9, properties // 9
  decoder = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[{
      "id": lzma.FILTER_LZMA1, "dict_size": dictionary, "lc": lc,
      "lp": remainder % 5, "pb": remainder // 5}])
  decoded = decoder.decompress(data[begin + 5:end], max_length=MAX_PAYLOAD + 1)
  if len(decoded) > MAX_PAYLOAD or (not decoder.eof and not decoder.needs_input):
    raise ArtifactRejection("NSIS solid expansion exceeded its budget")
  if decoder.unused_data:
    raise ArtifactRejection("NSIS compressor has unexpected trailing data")
  if len(decoded) < header_size + 4 or struct.unpack_from("<I", decoded)[0] != header_size:
    raise ArtifactRejection("NSIS solid header length mismatch")
  return decoded, header_size + 4


def normalized_pem(value: bytes) -> bytes:
  return re.sub(rb"\s+", b"", value.replace(b"\\n", b"\n").replace(b"\\r", b"\r"))


def nsis_uninstaller(data: bytes, solid: bytes, offset: int) -> bytes:
  """Independently apply the bounded stub-patch records used by WriteUninstaller.

  Mirrors the documented data layout in upstream NsisHandler.cpp UninstallerPatch,
  not executable installer instructions. The second record is appended as data.
  """
  stub_end = data.index(b"\xef\xbe\xad\xdeNullsoftInst") - 4
  stub = bytearray(data[:stub_end])
  size = struct.unpack_from("<I", solid, offset)[0]
  patch = solid[offset + 4:offset + 4 + size]
  cursor = 0
  while cursor + 4 <= len(patch):
    length = struct.unpack_from("<I", patch, cursor)[0]
    if not length:
      if cursor + 4 != len(patch):
        raise ArtifactRejection("NSIS uninstaller patch has trailing records")
      break
    if cursor + 8 > len(patch):
      raise ArtifactRejection("Truncated NSIS uninstaller patch header")
    target = struct.unpack_from("<I", patch, cursor + 4)[0]
    cursor += 8
    if cursor + length > len(patch) or target + length > len(stub):
      raise ArtifactRejection("NSIS uninstaller patch escapes its stub")
    stub[target:target + length] = patch[cursor:cursor + length]
    cursor += length
  else:
    raise ArtifactRejection("NSIS uninstaller patch has no terminator")
  following = offset + 4 + size
  if following + 4 > len(solid):
    raise ArtifactRejection("NSIS uninstaller data record is missing")
  length = struct.unpack_from("<I", solid, following)[0]
  if following + 4 + length > len(solid):
    raise ArtifactRejection("Truncated NSIS uninstaller data record")
  return bytes(stub) + solid[following + 4:following + 4 + length]


def public_selftests(data: bytes, name: str, approved: set[str]) -> tuple[bytes, int]:
  # Do not allow arbitrary paths, arbitrary keys, or a broad Gitleaks private-key ignore.
  if not re.search(r"(?:^|/)(?:libgnutls[^/]*|crypto-selftests-pk\.c)$", name):
    return data, 0
  count = 0
  def replace(match):
    nonlocal count
    digest = hashlib.sha256(normalized_pem(match.group(0))).hexdigest()
    if digest not in approved:
      return match.group(0)
    count += 1
    return ("[Public upstream GnuTLS self-test vector SHA256:" + digest + "]").encode("ascii")
  return PEM.sub(replace, data), count


def container(data: bytes) -> bool:
  return (data.startswith((b"PK\x03\x04", b"\x1f\x8b", b"\xfd7zXZ\0", b"BZh", b"MSCF",
                           b"7z\xbc\xaf\x27\x1c", b"070701", b"070702", b"\x28\xb5\x2f\xfd", b"hsqs"))
          or len(data) > 262 and data[257:262] == b"ustar")


class Scanner:
  def __init__(self, root: Path, tools: Path):
    self.root, self.tools = root, tools
    self.corpus = root / "corpus"
    self.corpus.mkdir(mode=0o700)
    self.sources: dict[str, Path] = {}
    self.seen: set[str] = set()
    self.expanded = 0
    self.records = 0
    self.public_vectors = 0
    self.nsis_records_verified = 0
    self.decoded = Counter()
    self.approved = set(json.loads((ROOT / "data/public-crypto-selftests.json").read_text(encoding="utf-8"))["normalizedSha256"])

  def save(self, data: bytes, name: str, *, depth=0, decode=True) -> None:
    self.records += 1
    self.expanded += len(data)
    if len(data) > MAX_PAYLOAD or self.expanded > MAX_EXPANDED or self.records > 100_000 or depth > 8:
      raise ArtifactRejection("Artifact expansion exceeded its depth/file/byte budget")
    original_digest = hashlib.sha256(data).hexdigest()
    if original_digest in self.seen:
      return
    self.seen.add(original_digest)
    sanitized, count = public_selftests(data, name, self.approved)
    self.public_vectors += count
    path = self.corpus / (original_digest + ".payload")
    path.write_bytes(sanitized)
    path.chmod(0o600)
    self.sources[path.name] = path
    if "/evidence/" in name and Path(name).suffix.lower() == ".png":
      ocr = shutil.which("tesseract")
      if not ocr:
        raise ArtifactRejection("Reviewed public PNG evidence requires the OCR secret-scan gate")
      self.save(bounded_command([ocr, str(path.resolve()), "stdout"], limit=8 * 1024**2, timeout=60),
                name + "/OCR-TEXT", depth=depth + 1, decode=False)
    # Scan original byte strings in both UTF-16 byte orders too; no lossy decoding.
    for label, expression, encoding in (
        ("ascii", rb"[\x20-\x7e\t]{8,}", "ascii"),
        ("utf16le", rb"(?:[\x20-\x7e]\x00){8,}", "utf-16-le"),
        ("utf16be", rb"(?:\x00[\x20-\x7e]){8,}", "utf-16-be")):
      strings = [match.group(0).decode(encoding).encode("utf-8") for match in re.finditer(expression, sanitized)]
      view = self.corpus / (original_digest + "." + label)
      view.write_bytes(b"\n".join(strings))
      view.chmod(0o600)
      self.sources[view.name] = path
    if decode and (container(data) or data.startswith(b"MZ") and b"\xef\xbe\xad\xdeNullsoftInst" in data):
      self.decode(path, name, depth)

  def decode(self, path: Path, name: str, depth: int, *, installer=False) -> None:
    data = path.read_bytes()
    if data.startswith(b"PK\x03\x04"):
      self.zip(data, name, depth)
      return
    seven = str(self.tools / "7zz")
    listing = bounded_command([seven, "l", "-slt", "--", str(path.resolve())], limit=16 * 1024**2)
    self.save(listing, name + "/STATIC-LISTING", depth=depth, decode=False)
    header, separator, body = listing.decode("utf-8").partition("----------\n")
    if not separator:
      raise ArtifactRejection("Artifact decoder returned no member inventory")
    nsis = b"Type = Nsis" in listing
    if installer and not nsis:
      raise ArtifactRejection("Windows setup artifact is not an NSIS installer")
    solid, offset_base = nsis_solid_stream(data) if nsis else (None, 0)
    if solid is not None:
      self.save(solid, name + "/COMPLETE-NSIS-SOLID-STREAM", depth=depth + 1, decode=False)
    self.decoded["nsis" if nsis else "container"] += 1
    paths = set()
    for block in body.split("\n\n"):
      entry = dict(line.split(" = ", 1) for line in block.splitlines() if " = " in line)
      member = entry.get("Path")
      if not member:
        continue
      while member.startswith("./"):
        member = member[2:]
      if member in ("", "."):
        continue
      policy.safe_name(member)
      if member in paths or entry.get("Encrypted") == "+":
        raise ArtifactRejection("Duplicate/encrypted artifact member")
      paths.add(member)
      if entry.get("Folder") == "+" or entry.get("Mode", "").startswith("d") or entry.get("Attributes", "").startswith("D"):
        continue
      if entry.get("Mode", "").startswith("l") or "Symbolic Link" in entry or "Hard Link" in entry:
        target = entry.get("Symbolic Link", entry.get("Hard Link", ""))
        self.save(target.encode("utf-8"), name + "/" + member + "/LINK-TARGET", depth=depth + 1, decode=False)
        continue
      size_text = entry.get("Size", "")
      declared = int(size_text) if size_text.isdigit() else None
      if declared is not None and declared > MAX_PAYLOAD:
        raise ArtifactRejection("Declared artifact member exceeds the byte budget")
      payload = bounded_command([seven, "x", "-so", "-bd", "-spd", "--", str(path.resolve()), entry["Path"]])
      if solid is not None:
        offset = offset_base + int(entry["Offset"])
        if offset + 4 > len(solid):
          raise ArtifactRejection("NSIS file offset escapes the solid stream")
        length = struct.unpack_from("<I", solid, offset)[0]
        reconstructed = solid[offset + 4:offset + 4 + length]
        if entry["Path"].lower() == "uninstall.exe":
          reconstructed = nsis_uninstaller(data, solid, offset)
        if reconstructed != payload:
          raise ArtifactRejection("NSIS independent file reconstruction differs from decoder output")
        self.nsis_records_verified += 1
      elif declared is not None and len(payload) != declared:
        raise ArtifactRejection("Artifact member size differs from decoder inventory")
      self.save(payload, name + "/" + member, depth=depth + 1)

  def zip(self, data: bytes, name: str, depth: int) -> None:
    self.decoded["zip"] += 1
    git_files = {}
    manifest = None
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
      paths = set()
      for member in archive.infolist():
        policy.safe_name(member.filename)
        if member.filename in paths or member.flag_bits & 1:
          raise ArtifactRejection("Duplicate/encrypted ZIP member")
        paths.add(member.filename)
        if member.file_size > MAX_PAYLOAD or (member.external_attr >> 16) & 0o170000 not in (0, 0o100000, 0o040000):
          raise ArtifactRejection("ZIP member is too large or is not a regular file/directory")
        if member.is_dir():
          continue
        payload = archive.read(member)
        parts = member.filename.split("/")
        if any(part.lower() in {".aws", ".ssh", ".gnupg", ".env", "session.json", "app_settings.json"} for part in parts):
          raise ArtifactRejection("Public archive contains private configuration material")
        if ".git" in parts:
          relative = "/".join(parts[parts.index(".git") + 1:])
          git_files[relative] = payload
        if parts[-1] == ".tauridium-source-manifest.json":
          manifest = json.loads(payload)
        self.save(payload, name + "/" + member.filename, depth=depth + 1)
      if archive.testzip() is not None:
        raise ArtifactRejection("ZIP CRC verification failed")
    if git_files:
      self.git_objects(git_files, manifest, depth=depth + 1)

  def git_objects(self, files: dict[str, bytes], manifest: dict | None, *, depth=0) -> None:
    if not manifest or not isinstance(manifest.get("gitFiles"), list):
      raise ArtifactRejection("Source Git history has no approved-file hash inventory")
    version = manifest["version"]
    allowed = re.compile(r"(?:HEAD|config|index|info/exclude|refs/heads/master|refs/tags/v" + re.escape(version)
                         + r"|objects/[0-9a-f]{2}/[0-9a-f]{38}|objects/pack/pack-[0-9a-f]{40}\.(?:pack|idx))")
    expected = {record["path"].removeprefix(".git/"): record["sha256"] for record in manifest["gitFiles"]}
    if set(files) != set(expected) or any(not allowed.fullmatch(name) for name in files):
      raise ArtifactRejection("Source Git contains unapproved local state/refs/hooks/configuration")
    if files.get("config") != b"[core]\n\trepositoryformatversion = 0\n\tfilemode = false\n\tbare = false\n\tlogallrefupdates = false\n":
      raise ArtifactRejection("Source Git configuration is not the fixed inert public configuration")
    with tempfile.TemporaryDirectory(prefix="git-objects-", dir=self.root) as temporary:
      git_dir = Path(temporary) / "source.git"
      for name, data in files.items():
        if hashlib.sha256(data).hexdigest() != expected[name]:
          raise ArtifactRejection("Source Git file hash differs from its inventory")
        path = git_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
      env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
      env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_NO_REPLACE_OBJECTS="1")
      command = ["git", "--git-dir=" + str(git_dir), "-c", "core.hooksPath=" + os.devnull]
      bounded_command(command + ["fsck", "--full", "--strict", "--no-reflogs"], env=env, limit=16 * 1024**2)
      refs = bounded_command(command + ["for-each-ref", "--format=%(refname)"], env=env).decode().splitlines()
      if set(refs) != {"refs/heads/master", "refs/tags/v" + version}:
        raise ArtifactRejection("Source Git refs differ from the exact approved release ancestry")
      commit = manifest.get("git", {}).get("commit")
      if not isinstance(commit, str) or not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ArtifactRejection("Source manifest has no immutable release commit")
      for ref in ("refs/heads/master", "refs/tags/v" + version):
        actual = bounded_command(command + ["rev-parse", "--verify", ref + "^{commit}"], env=env).decode().strip()
        if actual != commit:
          raise ArtifactRejection("Source Git ref does not resolve to the approved release commit")
      listing = bounded_command(command + ["cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype) %(objectsize)"], env=env)
      reachable = {line.split()[0] for line in bounded_command(command + ["rev-list", "--objects", "--all"], env=env).decode().splitlines()}
      reachable.update(bounded_command(command + ["for-each-ref", "--format=%(objectname)"], env=env).decode().splitlines())
      if any(line.split()[0] not in reachable for line in listing.decode().splitlines()):
        raise ArtifactRejection("Source Git contains unreachable producer objects")
      for line in listing.decode("ascii").splitlines():
        oid, kind, size = line.split()
        if not re.fullmatch(r"[0-9a-f]{40}", oid) or kind not in ("blob", "tree", "commit", "tag") or int(size) > MAX_PAYLOAD:
          raise ArtifactRejection("Invalid or oversized source Git object")
        payload = bounded_command(command + ["cat-file", kind, oid], env=env)
        # Approved history can retain deleted compressed files. Inspect them just
        # like current-tree assets, without resetting the enclosing depth budget.
        self.save(payload, "GIT-OBJECT/" + oid, depth=depth + 1)
        self.decoded["git-" + kind] += 1

  def add(self, path: Path) -> None:
    policy.regular(path)
    data = path.read_bytes()
    self.save(data, path.name, decode=not path.name.endswith("-setup.exe"))
    if path.name.endswith("-setup.exe") or path.suffix in (".AppImage", ".deb", ".rpm", ".msi"):
      digest = hashlib.sha256(data).hexdigest()
      self.decode(self.corpus / (digest + ".payload"), path.name, 0, installer=path.name.endswith("-setup.exe"))
    if path.suffix == ".msi":
      tool = shutil.which("msiinfo")
      if not tool:
        raise ArtifactRejection("MSI table/stream scanner requires msitools (msiinfo)")
      for kind, operation in (("tables", "export"), ("streams", "extract")):
        names = bounded_command([tool, kind, str(path.resolve())], limit=1024**2).decode("utf-8").splitlines()
        for name in names:
          # Default IDT export writes Binary/Icon files. SQL export is read-only
          # (libmsi query/fetch/printf); object bytes are scanned via `extract`.
          if operation == "export":
            payload = self.msi_table(tool, path, name)
          else:
            payload = bounded_command([tool, operation, str(path.resolve()), name])
          self.save(payload, path.name + "/MSI-" + kind + "/" + name)

  @staticmethod
  def msi_table(tool: str, path: Path, name: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
      raise ArtifactRejection("Unsafe MSI table identifier")
    if name == "_SummaryInformation":
      return bounded_command([tool, "suminfo", str(path.resolve())])
    if name == "_ForceCodepage":
      # Reserved virtual table, handled specially by libmsi; no object columns.
      return bounded_command([tool, "export", str(path.resolve()), name])
    try:
      return bounded_command([tool, "export", "-s", str(path.resolve()), name])
    except DecoderFailure as error:
      # msitools 0.106 initializes export_sql.success to FALSE and never sets it
      # for an empty table. Independently re-export only a proven non-object
      # schema through IDT, so this fallback cannot create Binary/Icon files.
      schema = error.output
      if (error.code != 1 or error.has_diagnostics or schema.count(b"\n") != 1
          or not schema.startswith((f"CREATE TABLE `{name}` (").encode())
          or not schema.endswith(b")\n") or b"OBJECT" in schema):
        raise
      return bounded_command([tool, "export", str(path.resolve()), name])

  def scan(self) -> dict:
    executable = str(self.tools / "gitleaks")
    report = self.root / "findings.json"
    config = self.root / "gitleaks.toml"
    config.write_text("[extend]\nuseDefault = true\n", encoding="utf-8")
    result = subprocess.run([executable, "dir", str(self.corpus), "--config", str(config),
                             "--ignore-gitleaks-allow", "--gitleaks-ignore-path", str(self.root / "no-ignores"),
                             "--max-target-megabytes", "0", "--max-decode-depth", "10", "--no-banner",
                             "--no-color", "--report-format", "json", "--report-path", str(report)],
                            capture_output=True, timeout=600, check=False)
    if result.returncode not in (0, 1) or not report.is_file():
      raise ArtifactRejection("Secret scanner failed; private diagnostics withheld")
    findings = json.loads(report.read_text(encoding="utf-8"))
    rejected = []
    noncontiguous = 0
    for finding in findings:
      name = Path(finding["File"]).name
      secret = finding.get("Secret", "")
      original_path = self.sources.get(name)
      original = original_path.read_bytes() if original_path else b""
      encoded = any("decode" in str(tag).lower() for tag in finding.get("Tags", []))
      contiguous = any(secret.encode(encoding) in original for encoding in ("utf-8", "utf-16-le", "utf-16-be"))
      if not name.endswith(".payload") and not encoded and not contiguous:
        # `strings` must not invent a credential by joining unrelated byte ranges.
        # The raw original is independently scanned, and decoded secrets still fail.
        noncontiguous += 1
        continue
      rejected.append({"rule": finding["RuleID"], "payloadSha256": name.split(".", 1)[0]})
    summary = {"passed": not rejected, "payloads": len(self.seen), "expandedBytes": self.expanded,
               "decoded": dict(self.decoded), "independentNsisRecordsVerified": self.nsis_records_verified,
               "exactPublicGnuTlsVectors": self.public_vectors, "noncontiguousStringArtifacts": noncontiguous,
               "findings": rejected, "payloadsExecuted": False, "privateReportsPublished": False}
    # Raw scanner reports contain possible secrets: never return/print/upload them.
    if rejected:
      raise ArtifactRejection("Public artifact secret scan rejected payloads; only rule/hash metadata: " + json.dumps(rejected))
    return summary


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("assets", type=Path)
  parser.add_argument("--tools", required=True, type=Path)
  args = parser.parse_args()
  if os.name != "posix":
    parser.error("full public container scanning requires the isolated Linux release scanner")
  versions = json.loads((ROOT / "data/security-tools.json").read_text(encoding="utf-8"))
  if bounded_command([str(args.tools / "gitleaks"), "version"], limit=4096).decode().strip() != versions["gitleaks"]["version"]:
    parser.error("Gitleaks does not match the pinned scanner version")
  if ("7-Zip (z) " + versions["7zz"]["version"]).encode() not in bounded_command([str(args.tools / "7zz"), "i"], limit=64 * 1024):
    parser.error("7-Zip does not match the pinned decoder version")
  with tempfile.TemporaryDirectory(prefix="tauridium-private-artifact-scan-") as temporary:
    root = Path(temporary)
    root.chmod(0o700)
    scanner = Scanner(root, args.tools)
    for path in sorted(args.assets.iterdir()):
      scanner.add(path)
    print(json.dumps(scanner.scan(), sort_keys=True))
  return 0


if __name__ == "__main__":
  try:
    raise SystemExit(main())
  except Exception as error:
    # Parser/OS exceptions may embed credentials in member names, paths or argv.
    # Fail closed, but never print arbitrary exception text in public CI logs.
    raise SystemExit("error: public artifact security gate failed: " + public_failure(error)) from None
