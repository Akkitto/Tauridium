#!/usr/bin/env python3
"""Collect native bundles and create deterministic Tauridium release metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from package_release import RuntimeArtifact, build_runtime, inspect_runtime, runtime_zip_name, version

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "Akkitto/Tauridium"

TARGETS = {
  "x86_64-pc-windows-msvc": ("windows", "x64", "x86_64"),
  "aarch64-pc-windows-msvc": ("windows", "arm64", "aarch64"),
  "x86_64-unknown-linux-gnu": ("linux", "x64", "x86_64"),
  "aarch64-unknown-linux-gnu": ("linux", "arm64", "aarch64"),
  "x86_64-apple-darwin": ("macos", "x64", "x86_64"),
  "aarch64-apple-darwin": ("macos", "arm64", "aarch64"),
}

BUNDLE_SPECS = {
  "windows": (
    ("msi", ".msi", "windows-{arch}.msi", True),
    ("nsis", ".exe", "windows-{arch}-setup.exe", True),
  ),
  "linux": (
    ("appimage", ".AppImage", "linux-{arch}.AppImage", True),
    ("deb", ".deb", "linux-{arch}.deb", False),
    ("rpm", ".rpm", "linux-{arch}.rpm", False),
  ),
  "macos": (
    ("dmg", ".dmg", "macos-{arch}.dmg", False),
    ("macos", ".app.tar.gz", "macos-{arch}.app.tar.gz", True),
  ),
}


def sha256(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def target_release_dir(target: str) -> Path:
  explicit = ROOT / "src-tauri" / "target" / target / "release"
  if explicit.is_dir():
    return explicit
  native = ROOT / "src-tauri" / "target" / "release"
  if native.is_dir():
    return native
  raise SystemExit(f"error: no Tauri release output found for target {target}")


def exactly_one(directory: Path, suffix: str) -> Path:
  matches = sorted(
    path for path in directory.iterdir() if path.is_file() and path.name.endswith(suffix)
  ) if directory.is_dir() else []
  if len(matches) != 1:
    raise SystemExit(
      f"error: expected exactly one {suffix} artifact in {directory}, found {len(matches)}"
    )
  return matches[0]


def copy_with_signature(
  source: Path,
  destination: Path,
  require_signature: bool,
) -> list[Path]:
  destination.parent.mkdir(parents=True, exist_ok=True)
  shutil.copy2(source, destination)
  written = [destination]
  signature = source.with_name(source.name + ".sig")
  if signature.is_file():
    signature_destination = destination.with_name(destination.name + ".sig")
    shutil.copy2(signature, signature_destination)
    written.append(signature_destination)
  elif require_signature:
    raise SystemExit(f"error: updater signature is missing for {source}")
  return written


def collect_native(target: str, output_dir: Path, require_signatures: bool) -> list[Path]:
  if target not in TARGETS:
    raise SystemExit(f"error: unsupported release target: {target}")
  platform, arch, _ = TARGETS[target]
  release_version = version()
  release_dir = target_release_dir(target)
  binary_name = "tauridium.exe" if platform == "windows" else "tauridium"
  runtime_path = release_dir / binary_name
  if not runtime_path.is_file():
    raise SystemExit(f"error: native runtime is missing: {runtime_path}")

  runtime = inspect_runtime(runtime_path, release_version)
  if runtime.target != target:
    raise SystemExit(
      f"error: runtime target mismatch; requested {target}, binary reports {runtime.target}"
    )

  output_dir.mkdir(parents=True, exist_ok=True)
  written: list[Path] = []
  run_zip = output_dir / runtime_zip_name(release_version, runtime.suffix)
  build_runtime(run_zip, release_version, [RuntimeArtifact(runtime_path, target, runtime.suffix)])
  written.append(run_zip)

  bundle_root = release_dir / "bundle"
  for bundle_dir, source_suffix, name_template, updater_artifact in BUNDLE_SPECS[platform]:
    source = exactly_one(bundle_root / bundle_dir, source_suffix)
    destination = output_dir / f"tauridium-{release_version}-{name_template.format(arch=arch)}"
    written.extend(
      copy_with_signature(
        source,
        destination,
        require_signature=require_signatures and updater_artifact,
      )
    )

  return written


def changelog_notes(release_version: str) -> str:
  lines = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").splitlines()
  marker = f"## [{release_version}]"
  try:
    start = next(index for index, line in enumerate(lines) if line.startswith(marker))
  except StopIteration as error:
    raise SystemExit(f"error: CHANGELOG.md has no release section for {release_version}") from error
  end = next(
    (index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")),
    len(lines),
  )
  notes = "\n".join(lines[start + 1 : end]).strip()
  if not notes:
    raise SystemExit(f"error: CHANGELOG.md release section for {release_version} is empty")
  return notes


def release_timestamp() -> str:
  result = subprocess.run(
    ["git", "show", "-s", "--format=%cI", "HEAD"],
    cwd=ROOT,
    text=True,
    capture_output=True,
    check=False,
  )
  if result.returncode != 0 or not result.stdout.strip():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
  value = datetime.fromisoformat(result.stdout.strip()).astimezone(timezone.utc)
  return value.isoformat().replace("+00:00", "Z")


def release_url(release_version: str, filename: str) -> str:
  return (
    f"https://github.com/{REPOSITORY}/releases/download/v{release_version}/"
    f"{quote(filename)}"
  )


def signed_entry(assets_dir: Path, filename: str, release_version: str) -> dict[str, str] | None:
  artifact = assets_dir / filename
  signature = assets_dir / f"{filename}.sig"
  if not artifact.is_file() or not signature.is_file():
    return None
  value = signature.read_text(encoding="utf-8").strip()
  if not value:
    raise SystemExit(f"error: updater signature is empty: {signature}")
  return {
    "signature": value,
    "url": release_url(release_version, filename),
  }


def expected_updater_artifact_names(release_version: str) -> tuple[str, ...]:
  return tuple(
    filename
    for arch_name in ("x64", "arm64")
    for filename in (
      f"tauridium-{release_version}-windows-{arch_name}-setup.exe",
      f"tauridium-{release_version}-windows-{arch_name}.msi",
      f"tauridium-{release_version}-linux-{arch_name}.AppImage",
    )
  )


def signed_updater_state(assets_dir: Path, release_version: str) -> str:
  expected = expected_updater_artifact_names(release_version)
  present_signatures = [name for name in expected if (assets_dir / f"{name}.sig").is_file()]
  if not present_signatures:
    return "unsigned"

  missing = [
    name
    for name in expected
    if not (assets_dir / name).is_file() or not (assets_dir / f"{name}.sig").is_file()
  ]
  if missing:
    raise SystemExit(
      "error: signed updater release is incomplete; missing artifact/signature pairs: "
      + ", ".join(missing)
    )
  return "signed"


def generate_updater_manifest(assets_dir: Path, output: Path, require_all: bool) -> dict[str, object]:
  release_version = version()
  platforms: dict[str, dict[str, str]] = {}

  for arch_name, updater_arch in (("x64", "x86_64"), ("arm64", "aarch64")):
    nsis_name = f"tauridium-{release_version}-windows-{arch_name}-setup.exe"
    msi_name = f"tauridium-{release_version}-windows-{arch_name}.msi"
    appimage_name = f"tauridium-{release_version}-linux-{arch_name}.AppImage"

    nsis = signed_entry(assets_dir, nsis_name, release_version)
    msi = signed_entry(assets_dir, msi_name, release_version)
    appimage = signed_entry(assets_dir, appimage_name, release_version)

    if nsis is not None:
      platforms[f"windows-{updater_arch}"] = nsis
      platforms[f"windows-{updater_arch}-nsis"] = nsis
    if msi is not None:
      platforms[f"windows-{updater_arch}-msi"] = msi
      platforms.setdefault(f"windows-{updater_arch}", msi)
    if appimage is not None:
      platforms[f"linux-{updater_arch}"] = appimage
      platforms[f"linux-{updater_arch}-appimage"] = appimage

  required = {
    "windows-x86_64",
    "windows-aarch64",
    "linux-x86_64",
    "linux-aarch64",
  }
  missing = sorted(required - set(platforms))
  if require_all and missing:
    raise SystemExit(f"error: updater manifest is missing required platforms: {', '.join(missing)}")
  if not platforms:
    raise SystemExit("error: updater manifest would contain no signed native artifacts")

  manifest: dict[str, object] = {
    "version": release_version,
    "notes": changelog_notes(release_version),
    "pub_date": release_timestamp(),
    "platforms": dict(sorted(platforms.items())),
  }
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
  return manifest


def write_release_notes(output: Path) -> None:
  release_version = version()
  body = (
    f"# Tauridium {release_version}\n\n"
    f"{changelog_notes(release_version)}\n\n"
    "Download the package matching your platform and architecture below.\n"
  )
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(body, encoding="utf-8")


def write_checksums(assets_dir: Path, output: Path) -> None:
  excluded = {output.resolve()}
  files = sorted(
    path for path in assets_dir.iterdir()
    if path.is_file() and path.resolve() not in excluded and path.name != "latest.json"
  )
  if not files:
    raise SystemExit(f"error: no release assets found in {assets_dir}")
  lines = [f"{sha256(path)}  {path.name}" for path in files]
  output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
  parser = argparse.ArgumentParser()
  subparsers = parser.add_subparsers(dest="command", required=True)

  collect = subparsers.add_parser("collect-native")
  collect.add_argument("--target", required=True)
  collect.add_argument("--output-dir", type=Path, default=ROOT / "release" / "native")
  collect.add_argument("--require-signatures", action="store_true")

  notes = subparsers.add_parser("release-notes")
  notes.add_argument("--output", type=Path, default=ROOT / "release" / "release-notes.md")

  updater = subparsers.add_parser("updater-manifest")
  updater.add_argument("--assets-dir", type=Path, required=True)
  updater.add_argument("--output", type=Path)
  updater.add_argument("--require-all", action="store_true")
  updater.add_argument("--if-signed", action="store_true")

  checksums = subparsers.add_parser("checksums")
  checksums.add_argument("--assets-dir", type=Path, required=True)
  checksums.add_argument("--output", type=Path)

  args = parser.parse_args()
  if args.command == "collect-native":
    for path in collect_native(args.target, args.output_dir.resolve(), args.require_signatures):
      print(path)
    return 0
  if args.command == "release-notes":
    write_release_notes(args.output.resolve())
    print(args.output.resolve())
    return 0
  if args.command == "updater-manifest":
    assets_dir = args.assets_dir.resolve()
    output = args.output.resolve() if args.output else assets_dir / "latest.json"
    if args.if_signed and signed_updater_state(assets_dir, version()) == "unsigned":
      output.unlink(missing_ok=True)
      print("updater metadata skipped: no updater signatures were published")
      return 0
    generate_updater_manifest(assets_dir, output, args.require_all)
    print(output)
    return 0
  if args.command == "checksums":
    assets_dir = args.assets_dir.resolve()
    output = args.output.resolve() if args.output else assets_dir / "SHA256SUMS"
    write_checksums(assets_dir, output)
    print(output)
    return 0
  raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
  raise SystemExit(main())
