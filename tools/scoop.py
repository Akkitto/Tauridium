#!/usr/bin/env python3
"""Build and validate Tauridium's portable Windows and Scoop release assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from package_release import ZIP_TIME, add_file, inspect_runtime, version

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "Akkitto/Tauridium"
TEMPLATE = ROOT / "packaging" / "scoop" / "tauridium.json.template"
DESCRIPTION = "Lightweight Tauri-based web app service and workspace hub"
HOMEPAGE = f"https://github.com/{REPOSITORY}"
LICENSE = "MIT"
WEBVIEW2_NOTE = (
  "Requires Microsoft Edge WebView2 Runtime. Windows 10 (April 2018 or later) and "
  "Windows 11 normally provide it with the operating system."
)
WINDOWS_TARGETS = {
  "x86_64-pc-windows-msvc": ("x64", "64bit"),
  "aarch64-pc-windows-msvc": ("arm64", "arm64"),
}
ROOT_FIELD_ORDER = (
  "version",
  "description",
  "homepage",
  "license",
  "notes",
  "architecture",
  "shortcuts",
  "checkver",
  "autoupdate",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def release_url(release_version: str, filename: str) -> str:
  return (
    f"https://github.com/{REPOSITORY}/releases/download/v{release_version}/"
    f"{quote(filename, safe='{}')}"
  )


def portable_filename(release_version: str, target: str) -> str:
  try:
    arch, _scoop_arch = WINDOWS_TARGETS[target]
  except KeyError as error:
    raise SystemExit(f"error: unsupported Scoop Windows target: {target}") from error
  return f"tauridium-{release_version}-windows-{arch}-portable.zip"


def checksum_filename(release_version: str, target: str) -> str:
  return portable_filename(release_version, target) + ".sha256"


def write_checksum(path: Path) -> Path:
  output = path.with_name(path.name + ".sha256")
  output.write_text(f"{sha256(path)}  {path.name}\n", encoding="utf-8")
  return output


def read_checksum(path: Path) -> str:
  text = path.read_text(encoding="utf-8").strip()
  fields = text.split()
  if len(fields) != 2 or not SHA256_RE.fullmatch(fields[0]) or fields[1] != path.name.removesuffix(".sha256"):
    raise SystemExit(f"error: invalid portable checksum file: {path}")
  return fields[0]


def validate_portable_archive(path: Path) -> None:
  if not path.is_file():
    raise SystemExit(f"error: portable archive not found: {path}")
  try:
    with zipfile.ZipFile(path, "r") as archive:
      if archive.testzip() is not None:
        raise SystemExit(f"error: portable archive contains a corrupt member: {path}")
      entries = archive.infolist()
      if [entry.filename for entry in entries] != ["tauridium.exe"]:
        raise SystemExit(
          "error: Scoop portable archive must contain only tauridium.exe at the archive root"
        )
      executable = entries[0]
      if executable.date_time != ZIP_TIME:
        raise SystemExit("error: portable archive timestamp is not deterministic")
      if executable.compress_type != zipfile.ZIP_DEFLATED:
        raise SystemExit("error: portable executable is not stored with deterministic ZIP deflate")
      if executable.file_size <= 0:
        raise SystemExit("error: portable executable is empty")
  except zipfile.BadZipFile as error:
    raise SystemExit(f"error: invalid portable ZIP: {path}") from error


def verify_portable_runtime(path: Path, expected_target: str) -> None:
  validate_portable_archive(path)
  if os.name != "nt":
    return
  with tempfile.TemporaryDirectory(prefix="tauridium-scoop-portable-") as temp_dir:
    root = Path(temp_dir)
    with zipfile.ZipFile(path, "r") as archive:
      archive.extractall(root)
    runtime = root / "tauridium.exe"
    runtime_info = inspect_runtime(runtime, version())
    if runtime_info.target != expected_target:
      raise SystemExit(
        "error: portable runtime target mismatch; "
        f"expected {expected_target}, found {runtime_info.target}"
      )


def package_portable(runtime: Path, target: str, output_dir: Path) -> tuple[Path, Path]:
  if target not in WINDOWS_TARGETS:
    raise SystemExit(f"error: unsupported Scoop Windows target: {target}")
  release_version = version()
  runtime_info = inspect_runtime(runtime, release_version)
  if runtime_info.target != target:
    raise SystemExit(
      f"error: portable runtime target mismatch; expected {target}, found {runtime_info.target}"
    )
  output_dir.mkdir(parents=True, exist_ok=True)
  output = output_dir / portable_filename(release_version, target)
  with zipfile.ZipFile(output, "w") as archive:
    add_file(archive, runtime, "tauridium.exe", mode=0o755)
  validate_portable_archive(output)
  checksum = write_checksum(output)
  if read_checksum(checksum) != sha256(output):
    raise SystemExit("error: generated portable checksum does not match the archive")
  return output, checksum


def replace_placeholders(value: Any, replacements: dict[str, str]) -> Any:
  if isinstance(value, dict):
    return {key: replace_placeholders(item, replacements) for key, item in value.items()}
  if isinstance(value, list):
    return [replace_placeholders(item, replacements) for item in value]
  if isinstance(value, str):
    rendered = value
    for marker, replacement in replacements.items():
      rendered = rendered.replace(marker, replacement)
    return rendered
  return value


def load_template() -> dict[str, Any]:
  try:
    document = json.loads(TEMPLATE.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError) as error:
    raise SystemExit(f"error: invalid Scoop manifest template: {error}") from error
  if not isinstance(document, dict):
    raise SystemExit("error: Scoop manifest template root must be an object")
  return document


def validate_manifest_shape(document: dict[str, Any], *, template: bool) -> None:
  if tuple(document.keys()) != ROOT_FIELD_ORDER:
    raise SystemExit(
      "error: Scoop manifest fields are not in the official contribution-guide order; "
      f"found {tuple(document.keys())}"
    )
  expected_version = "{{version}}" if template else version()
  if document.get("version") != expected_version:
    raise SystemExit(
      f"error: Scoop manifest version mismatch; expected {expected_version!r}, "
      f"found {document.get('version')!r}"
    )
  for key, expected in (
    ("description", DESCRIPTION),
    ("homepage", HOMEPAGE),
    ("license", LICENSE),
    ("notes", WEBVIEW2_NOTE),
    ("checkver", "github"),
  ):
    if document.get(key) != expected:
      raise SystemExit(f"error: Scoop manifest {key} is not canonical")
  if "bin" in document:
    raise SystemExit("error: GUI-only Tauridium Scoop manifest must not create a CLI shim")
  if "persist" in document:
    raise SystemExit(
      "error: Tauridium state lives in standard OS user-data directories; Scoop persist must not duplicate it"
    )
  if document.get("shortcuts") != [["tauridium.exe", "Tauridium"]]:
    raise SystemExit("error: Scoop manifest must create only the Tauridium GUI shortcut")

  architecture = document.get("architecture")
  if not isinstance(architecture, dict) or tuple(architecture.keys()) != ("64bit", "arm64"):
    raise SystemExit("error: Scoop manifest must provide ordered 64bit and arm64 architectures")
  autoupdate = document.get("autoupdate")
  if not isinstance(autoupdate, dict) or tuple(autoupdate.keys()) != ("architecture",):
    raise SystemExit("error: Scoop autoupdate must contain only its architecture map")
  auto_arch = autoupdate.get("architecture")
  if not isinstance(auto_arch, dict) or tuple(auto_arch.keys()) != ("64bit", "arm64"):
    raise SystemExit("error: Scoop autoupdate must cover 64bit and arm64")

  release_version = "{{version}}" if template else version()
  for target, (asset_arch, scoop_arch) in WINDOWS_TARGETS.items():
    entry = architecture.get(scoop_arch)
    if not isinstance(entry, dict) or tuple(entry.keys()) != ("url", "hash"):
      raise SystemExit(f"error: Scoop architecture {scoop_arch} must contain ordered url/hash")
    expected_name = f"tauridium-{release_version}-windows-{asset_arch}-portable.zip"
    expected_url = release_url(release_version, expected_name)
    if entry.get("url") != expected_url:
      raise SystemExit(f"error: Scoop architecture {scoop_arch} URL is not canonical")
    hash_value = entry.get("hash")
    expected_hash = f"{{{{windows-{asset_arch}-sha256}}}}" if template else None
    if template:
      if hash_value != expected_hash:
        raise SystemExit(f"error: Scoop architecture {scoop_arch} hash placeholder is not canonical")
    elif not isinstance(hash_value, str) or not SHA256_RE.fullmatch(hash_value):
      raise SystemExit(f"error: Scoop architecture {scoop_arch} hash is not SHA-256")

    auto_entry = auto_arch.get(scoop_arch)
    if not isinstance(auto_entry, dict) or tuple(auto_entry.keys()) != ("url",):
      raise SystemExit(f"error: Scoop autoupdate {scoop_arch} must contain only url")
    expected_auto = (
      f"https://github.com/{REPOSITORY}/releases/download/v$version/"
      f"tauridium-$version-windows-{asset_arch}-portable.zip"
    )
    if auto_entry.get("url") != expected_auto:
      raise SystemExit(f"error: Scoop autoupdate {scoop_arch} URL is not canonical")


def validate_template() -> None:
  validate_manifest_shape(load_template(), template=True)


def portable_hash(assets_dir: Path, target: str) -> str:
  release_version = version()
  portable = assets_dir / portable_filename(release_version, target)
  validate_portable_archive(portable)
  actual = sha256(portable)
  sidecar = portable.with_name(portable.name + ".sha256")
  if not sidecar.is_file():
    raise SystemExit(f"error: portable checksum sidecar is missing: {sidecar}")
  recorded = read_checksum(sidecar)
  if recorded != actual:
    raise SystemExit(f"error: portable checksum mismatch: {portable.name}")
  return actual


def verify_collected_portable(assets_dir: Path, target: str) -> None:
  release_version = version()
  portable = assets_dir / portable_filename(release_version, target)
  portable_hash(assets_dir, target)
  verify_portable_runtime(portable, target)


def generate_release_manifest(assets_dir: Path, output: Path) -> dict[str, Any]:
  validate_template()
  replacements = {"{{version}}": version()}
  for target, (asset_arch, _scoop_arch) in WINDOWS_TARGETS.items():
    replacements[f"{{{{windows-{asset_arch}-sha256}}}}"] = portable_hash(assets_dir, target)
  document = replace_placeholders(load_template(), replacements)
  if not isinstance(document, dict):
    raise SystemExit("error: rendered Scoop manifest root must be an object")
  validate_manifest_shape(document, template=False)
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps(document, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
  return document


def validate_release_manifest(path: Path, assets_dir: Path | None = None) -> None:
  try:
    document = json.loads(path.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError) as error:
    raise SystemExit(f"error: invalid Scoop release manifest: {error}") from error
  if not isinstance(document, dict):
    raise SystemExit("error: Scoop release manifest root must be an object")
  validate_manifest_shape(document, template=False)
  if assets_dir is None:
    return
  architecture = document["architecture"]
  for target, (_asset_arch, scoop_arch) in WINDOWS_TARGETS.items():
    expected = portable_hash(assets_dir, target)
    if architecture[scoop_arch]["hash"] != expected:
      raise SystemExit(f"error: Scoop manifest hash mismatch for {scoop_arch}")


def generate_local_manifest(
  portable: Path,
  target: str,
  url: str,
  output: Path,
  *,
  checkver_url: str | None = None,
  autoupdate_url: str | None = None,
) -> None:
  if target not in WINDOWS_TARGETS:
    raise SystemExit(f"error: unsupported Scoop Windows target: {target}")
  if (checkver_url is None) != (autoupdate_url is None):
    raise SystemExit("error: local Scoop checkver and autoupdate URLs must be supplied together")
  validate_portable_archive(portable)
  _asset_arch, scoop_arch = WINDOWS_TARGETS[target]
  document: dict[str, Any] = {
    "version": version(),
    "description": DESCRIPTION,
    "homepage": HOMEPAGE,
    "license": LICENSE,
    "notes": WEBVIEW2_NOTE,
    "architecture": {
      scoop_arch: {
        "url": url,
        "hash": sha256(portable),
      }
    },
    "shortcuts": [["tauridium.exe", "Tauridium"]],
  }
  if checkver_url is not None and autoupdate_url is not None:
    document["checkver"] = {
      "url": checkver_url,
      "regex": r"([\d.]+)",
    }
    document["autoupdate"] = {
      "architecture": {
        scoop_arch: {
          "url": autoupdate_url,
        }
      }
    }
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps(document, indent=4) + "\n", encoding="utf-8")


def main() -> int:
  parser = argparse.ArgumentParser()
  subparsers = parser.add_subparsers(dest="command", required=True)

  package = subparsers.add_parser("package-portable")
  package.add_argument("--runtime", type=Path, required=True)
  package.add_argument("--target", required=True)
  package.add_argument("--output-dir", type=Path, default=ROOT / "release" / "native")

  verify = subparsers.add_parser("verify-portable")
  verify.add_argument("--portable", type=Path, required=True)
  verify.add_argument("--target", required=True)

  verify_collected = subparsers.add_parser("verify-collected")
  verify_collected.add_argument("--assets-dir", type=Path, required=True)
  verify_collected.add_argument("--target", required=True)

  template = subparsers.add_parser("validate-template")

  manifest = subparsers.add_parser("release-manifest")
  manifest.add_argument("--assets-dir", type=Path, required=True)
  manifest.add_argument("--output", type=Path)

  validate = subparsers.add_parser("validate-manifest")
  validate.add_argument("--manifest", type=Path, required=True)
  validate.add_argument("--assets-dir", type=Path)

  local = subparsers.add_parser("local-manifest")
  local.add_argument("--portable", type=Path, required=True)
  local.add_argument("--target", required=True)
  local.add_argument("--url", required=True)
  local.add_argument("--checkver-url")
  local.add_argument("--autoupdate-url")
  local.add_argument("--output", type=Path, required=True)

  args = parser.parse_args()
  if args.command == "package-portable":
    portable, checksum = package_portable(
      args.runtime.resolve(),
      args.target,
      args.output_dir.resolve(),
    )
    print(portable)
    print(checksum)
    return 0
  if args.command == "verify-portable":
    verify_portable_runtime(args.portable.resolve(), args.target)
    print(f"Portable archive verified: {args.portable}")
    return 0
  if args.command == "verify-collected":
    verify_collected_portable(args.assets_dir.resolve(), args.target)
    print(f"Collected portable archive verified for {args.target}")
    return 0
  if args.command == "validate-template":
    validate_template()
    print(f"Scoop manifest template validated: {TEMPLATE}")
    return 0
  if args.command == "release-manifest":
    assets_dir = args.assets_dir.resolve()
    output = (
      args.output.resolve()
      if args.output
      else assets_dir / f"tauridium-{version()}-scoop.json"
    )
    generate_release_manifest(assets_dir, output)
    print(output)
    return 0
  if args.command == "validate-manifest":
    validate_release_manifest(
      args.manifest.resolve(),
      args.assets_dir.resolve() if args.assets_dir else None,
    )
    print(f"Scoop release manifest validated: {args.manifest}")
    return 0
  if args.command == "local-manifest":
    generate_local_manifest(
      args.portable.resolve(),
      args.target,
      args.url,
      args.output.resolve(),
      checkver_url=args.checkver_url,
      autoupdate_url=args.autoupdate_url,
    )
    print(args.output)
    return 0
  raise AssertionError("unreachable")


if __name__ == "__main__":
  raise SystemExit(main())
