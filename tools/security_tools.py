"""Install pinned scanners and native Minisign verifiers, never artifact payloads."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import stat
import struct
import subprocess
import tarfile
import tempfile
import zipfile
from urllib.parse import urlparse
from urllib.request import build_opener, HTTPRedirectHandler, Request

ROOT = Path(__file__).resolve().parents[1]


def minisign_entry(machine: str | None = None, system: str | None = None) -> dict:
  entry = dict(json.loads((ROOT / "data/security-tools.json").read_text(encoding="utf-8"))["minisign"])
  architecture = (machine or platform.machine()).lower()
  architecture = {"amd64": "x86_64", "arm64": "aarch64"}.get(architecture, architecture)
  operating_system = system or platform.system()
  if architecture not in ("x86_64", "aarch64") or operating_system not in ("Linux", "Windows"):
    raise SystemExit("error: pinned Minisign bootstrap supports Linux/Windows x64 and ARM64 only")
  if operating_system == "Windows":
    windows = entry["windows"]
    entry.update({key: value for key, value in windows.items() if key != "architectures"})
    entry.update(windows["architectures"][architecture])
  elif architecture == "aarch64":
    entry.update(entry["architectures"]["aarch64"])
  return entry


def minisign_cache() -> Path:
  entry = minisign_entry()
  architecture = "aarch64" if platform.machine().lower() in ("aarch64", "arm64") else "x86_64"
  system = "windows-" if platform.system() == "Windows" else ""
  return ROOT / "release/tools" / f"minisign-{entry['version']}-{system}{architecture}"


def unsafe_link(path: Path) -> bool:
  try:
    metadata = path.lstat()
  except FileNotFoundError:
    return False
  return stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, "st_file_attributes", 0) & 0x400)


def verify_binary(binary: bytes, entry: dict) -> bool:
  if hashlib.sha256(binary).hexdigest() != entry.get("binarySha256"):
    return False
  if "peMachine" in entry:
    if len(binary) < 64 or binary[:2] != b"MZ":
      return False
    offset = struct.unpack_from("<I", binary, 0x3c)[0]
    if offset > len(binary) - 6 or binary[offset:offset + 4] != b"PE\0\0":
      return False
    if struct.unpack_from("<H", binary, offset + 4)[0] != entry["peMachine"]:
      return False
  return True


def cached_minisign() -> str | None:
  if platform.system() not in ("Linux", "Windows") or platform.machine().lower() not in ("x86_64", "amd64", "aarch64", "arm64"):
    return None
  name = "minisign.exe" if platform.system() == "Windows" else "minisign"
  path = minisign_cache() / name
  try:
    if any(unsafe_link(parent) for parent in (path, *path.parents)):
      return None
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size < 64 * 1024**2:
      return None
    if not verify_binary(path.read_bytes(), minisign_entry()):
      return None
  except OSError:
    return None
  return str(path)


def ensure_minisign(*, download: bool = True) -> str:
  """Validate a private tool cache; never overwrite an existing damaged cache."""
  destination = minisign_cache()
  executable = cached_minisign()
  if executable is None:
    if destination.exists() or unsafe_link(destination):
      raise SystemExit("error: cached Minisign failed integrity checks; preserve/remove that cache explicitly before retrying")
    if not download:
      raise SystemExit("error: verified Minisign is missing and downloads are disabled")
    install(destination, "minisign")
    executable = cached_minisign()
  if executable is None:
    raise SystemExit("error: Minisign bootstrap did not provide a verified executable")
  allowed = {"PATH", "SystemRoot", "SYSTEMROOT", "WINDIR", "HOME", "USERPROFILE", "TMP", "TEMP", "TMPDIR", "LANG", "LC_ALL"}
  environment = {name: value for name, value in os.environ.items() if name in allowed}
  try:
    result = subprocess.run([executable, "-v"], env=environment, capture_output=True, timeout=30, check=False)
  except (OSError, subprocess.SubprocessError):
    raise SystemExit("error: verified Minisign could not execute") from None
  expected = ("minisign " + minisign_entry()["version"]).encode("ascii")
  if result.returncode or result.stdout.strip() != expected:
    raise SystemExit("error: verified Minisign returned an unexpected version")
  return executable


class HttpsOnlyRedirect(HTTPRedirectHandler):
  def redirect_request(self, request, fp, code, message, headers, newurl):
    if urlparse(newurl).scheme != "https":
      raise ValueError("Scanner download must not downgrade HTTPS")
    return super().redirect_request(request, fp, code, message, headers, newurl)


def install(output: Path, only: str | None = None) -> None:
  machine = platform.machine().lower()
  system = platform.system()
  native_minisign = only == "minisign" and system in ("Linux", "Windows") and machine in ("x86_64", "amd64", "aarch64", "arm64")
  if not native_minisign and (system != "Linux" or machine not in ("x86_64", "amd64")):
    raise SystemExit("error: isolated public artifact scanning runs on Linux x64")
  if output.exists() or output.is_symlink():
    raise SystemExit("error: scanner installation requires a fresh directory")
  if any(unsafe_link(parent) for parent in output.parents):
    raise SystemExit("error: scanner installation rejects linked/reparse-point directories")
  output.parent.mkdir(parents=True, exist_ok=True)
  policy = json.loads((ROOT / "data/security-tools.json").read_text(encoding="utf-8"))
  if only is not None:
    if only not in policy:
      raise SystemExit("error: unknown security tool")
    policy = {only: policy[only]}
  if "minisign" in policy:
    policy["minisign"] = minisign_entry(machine)
  opener = build_opener(HttpsOnlyRedirect())
  with tempfile.TemporaryDirectory(prefix=".tauridium-scanners-", dir=output.parent) as temporary:
    staged = Path(temporary)
    for name, entry in policy.items():
      if not entry["url"].startswith("https://github.com/"):
        raise SystemExit("error: unapproved scanner origin")
      with opener.open(Request(entry["url"], headers={"User-Agent": "Tauridium-security-tools"}), timeout=60) as response:
        data = response.read(64 * 1024**2 + 1)
      if len(data) > 64 * 1024**2 or hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise SystemExit("error: scanner archive checksum/size verification failed")
      if name == "minisign" and system == "Windows":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
          matches = [member for member in archive.infolist() if member.filename == entry["member"]]
          if (len(matches) != 1 or matches[0].is_dir() or matches[0].orig_filename != entry["member"]
              or stat.S_IFMT(matches[0].external_attr >> 16) not in (0, stat.S_IFREG)
              or matches[0].external_attr & 0x400 or not 0 < matches[0].file_size < 64 * 1024**2):
            raise SystemExit("error: scanner archive has no unique regular executable")
          with archive.open(matches[0]) as stream:
            binary = stream.read(64 * 1024**2 + 1)
      else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
          matches = [member for member in archive.getmembers() if member.name == entry["member"]]
          if len(matches) != 1 or not matches[0].isfile() or not 0 < matches[0].size < 64 * 1024**2:
            raise SystemExit("error: scanner archive has no unique regular executable")
          stream = archive.extractfile(matches[0])
          if stream is None:
            raise SystemExit("error: scanner archive executable cannot be read")
          binary = stream.read(64 * 1024**2 + 1)
      if len(binary) > 64 * 1024**2 or entry.get("binarySha256") and not verify_binary(binary, entry):
        raise SystemExit("error: security executable checksum/architecture verification failed")
      destination_name = name + ".exe" if name == "minisign" and system == "Windows" else name
      (staged / destination_name).write_bytes(binary)
      (staged / destination_name).chmod(0o755)
    os.rename(staged, output)
  print(f"Verified scanner tools installed: {output}")


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("output", nargs="?", type=Path)
  parser.add_argument("--only", choices=("minisign", "gitleaks", "7zz"))
  parser.add_argument("--ensure-minisign", action="store_true")
  parser.add_argument("--no-download", action="store_true")
  args = parser.parse_args()
  if args.ensure_minisign:
    if args.output is not None or args.only is not None:
      parser.error("--ensure-minisign does not accept an output directory or --only")
    print("Verified Minisign: " + ensure_minisign(download=not args.no_download))
  else:
    if args.output is None or args.no_download:
      parser.error("an output directory is required; --no-download requires --ensure-minisign")
    install(args.output, args.only)
