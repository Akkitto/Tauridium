#!/usr/bin/env python3
"""Create deterministic Tauridium source, runtime, and documentation release ZIPs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ZIP_TIME = (2026, 1, 1, 0, 0, 0)
SOURCE_MANIFEST_NAME = ".tauridium-source-manifest.json"
SOURCE_MANIFEST_SCHEMA = 1
BUILD_INFO_ARGUMENT = "--build-info-file"


@dataclass(frozen=True)
class SourceEntry:
  path: Path
  archive_path: str
  sha256: str
  mode: int


@dataclass(frozen=True)
class SourceContext:
  entries: tuple[SourceEntry, ...]
  manifest: dict[str, Any]
  manifest_bytes: bytes


@dataclass(frozen=True)
class RuntimeArtifact:
  path: Path
  target: str
  suffix: str


def version() -> str:
  return json.loads((ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))["version"]


def require_pinned_rustfmt_clean() -> None:
  toolchain = (ROOT / "rust-toolchain.toml").read_text(encoding="utf-8")
  if 'channel = "1.97.1"' not in toolchain or '"rustfmt"' not in toolchain:
    raise SystemExit("error: release packaging requires the pinned Rust 1.97.1 rustfmt toolchain")
  try:
    result = subprocess.run(
      [
        "cargo",
        "fmt",
        "--manifest-path",
        "src-tauri/Cargo.toml",
        "--all",
        "--",
        "--check",
      ],
      cwd=ROOT,
      text=True,
      capture_output=True,
      check=False,
    )
  except FileNotFoundError as error:
    raise SystemExit(
      "error: release packaging requires cargo/rustfmt from the pinned Rust 1.97.1 toolchain"
    ) from error
  if result.returncode != 0:
    details = (result.stdout + result.stderr).strip()
    raise SystemExit(
      "error: release packaging refused because pinned rustfmt reports source drift"
      + (f"\n{details}" if details else "")
    )


def git_repository_root() -> Path | None:
  result = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"],
    cwd=ROOT,
    text=True,
    capture_output=True,
    check=False,
  )
  if result.returncode != 0:
    return None
  try:
    repository_root = Path(result.stdout.strip()).resolve()
  except (OSError, RuntimeError):
    return None
  return repository_root if repository_root == ROOT.resolve() else None


def git_output(*args: str) -> str:
  return subprocess.check_output(
    ["git", *args],
    cwd=ROOT,
    text=True,
    stderr=subprocess.PIPE,
  ).strip()


def sha256(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def file_mode(path: Path) -> int:
  return 0o755 if path.stat().st_mode & 0o111 else 0o644


def add_file(
  zf: zipfile.ZipFile,
  source: Path,
  archive_name: str,
  mode: int | None = None,
) -> None:
  info = zipfile.ZipInfo(archive_name, ZIP_TIME)
  info.compress_type = zipfile.ZIP_DEFLATED
  info.external_attr = (mode if mode is not None else file_mode(source)) << 16
  zf.writestr(info, source.read_bytes())


def add_bytes(zf: zipfile.ZipFile, data: bytes, archive_name: str, executable: bool = False) -> None:
  info = zipfile.ZipInfo(archive_name, ZIP_TIME)
  info.compress_type = zipfile.ZIP_DEFLATED
  info.external_attr = (0o755 if executable else 0o644) << 16
  zf.writestr(info, data)


def add_directory(zf: zipfile.ZipFile, archive_name: str) -> None:
  directory_name = archive_name.rstrip("/") + "/"
  info = zipfile.ZipInfo(directory_name, ZIP_TIME)
  info.compress_type = zipfile.ZIP_STORED
  info.external_attr = (0o40755 << 16) | 0x10
  zf.writestr(info, b"")


def safe_manifest_path(value: str) -> str:
  path = PurePosixPath(value)
  if path.is_absolute() or not value or ".." in path.parts or path.as_posix() != value:
    raise SystemExit(f"error: invalid source-manifest path: {value!r}")
  if value == SOURCE_MANIFEST_NAME:
    raise SystemExit(f"error: source manifest must not list itself: {value}")
  return value


def manifest_bytes(manifest: dict[str, Any]) -> bytes:
  return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()


def tracked_entries() -> tuple[SourceEntry, ...]:
  """Return tracked files using Git-index modes for cross-platform determinism.

  Windows does not expose Unix executable bits through ``Path.stat()`` the same
  way Unix does. Reading the index mode makes source ZIP permissions identical
  whether a release is packaged on Linux, macOS, or Windows.
  """
  raw = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=ROOT)
  entries: list[SourceEntry] = []
  for item in raw.split(b"\0"):
    if not item:
      continue
    metadata, raw_path = item.split(b"\t", 1)
    git_mode = metadata.split(b" ", 1)[0]
    if git_mode == b"100755":
      mode = 0o755
    elif git_mode == b"100644":
      mode = 0o644
    else:
      archive_path = raw_path.decode()
      raise SystemExit(
        f"error: unsupported Git index mode {git_mode.decode()} for {archive_path}"
      )
    archive_path = raw_path.decode()
    source = ROOT / archive_path
    entries.append(
      SourceEntry(
        path=source,
        archive_path=archive_path,
        sha256=sha256(source),
        mode=mode,
      )
    )
  return tuple(sorted(entries, key=lambda entry: entry.archive_path))


def exact_release_tag(release_version: str) -> str | None:
  expected = f"v{release_version}"
  tags = git_output("tag", "--points-at", "HEAD").splitlines()
  return expected if expected in tags else None


def git_source_context(release_version: str) -> SourceContext:
  expected_tag = f"v{release_version}"
  if exact_release_tag(release_version) != expected_tag:
    raise SystemExit(
      f"error: release packaging requires HEAD to carry exact tag {expected_tag}"
    )
  dirty = git_output("status", "--porcelain", "--untracked-files=all")
  if dirty:
    details = "\n".join(f"  {line}" for line in dirty.splitlines())
    raise SystemExit(
      "error: release packaging requires a clean Git worktree; changed paths:\n"
      + details
    )

  entries = tracked_entries()
  manifest: dict[str, Any] = {
    "schema": SOURCE_MANIFEST_SCHEMA,
    "project": "Tauridium",
    "version": release_version,
    "git": {
      "commit": git_output("rev-parse", "HEAD"),
      "tree": git_output("rev-parse", "HEAD^{tree}"),
      "tag": exact_release_tag(release_version),
      "log": git_output("log", "--oneline", "--decorate", "-20"),
    },
    "files": [
      {
        "path": entry.archive_path,
        "sha256": entry.sha256,
        "mode": entry.mode,
      }
      for entry in entries
    ],
  }
  return SourceContext(entries=entries, manifest=manifest, manifest_bytes=manifest_bytes(manifest))


def load_source_manifest(release_version: str) -> SourceContext:
  path = ROOT / SOURCE_MANIFEST_NAME
  if not path.is_file():
    raise SystemExit(
      "error: release packaging requires either a Git checkout or "
      f"{SOURCE_MANIFEST_NAME} from a Tauridium source ZIP"
    )

  try:
    manifest = json.loads(path.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError) as error:
    raise SystemExit(f"error: invalid {SOURCE_MANIFEST_NAME}: {error}") from error

  if manifest.get("schema") != SOURCE_MANIFEST_SCHEMA:
    raise SystemExit(f"error: unsupported source-manifest schema: {manifest.get('schema')!r}")
  if manifest.get("project") != "Tauridium":
    raise SystemExit("error: source manifest belongs to a different project")
  if manifest.get("version") != release_version:
    raise SystemExit(
      "error: source manifest version differs from this source tree; "
      "extract the matching release into a new empty directory"
    )
  git = manifest.get("git")
  if not isinstance(git, dict) or git.get("tag") != f"v{release_version}":
    raise SystemExit(
      f"error: source manifest is not anchored to exact release tag v{release_version}"
    )

  raw_entries = manifest.get("files")
  if not isinstance(raw_entries, list) or not raw_entries:
    raise SystemExit("error: source manifest contains no packaged files")

  entries: list[SourceEntry] = []
  seen: set[str] = set()
  for raw_entry in raw_entries:
    if not isinstance(raw_entry, dict):
      raise SystemExit("error: source manifest contains an invalid file entry")
    archive_path = safe_manifest_path(str(raw_entry.get("path", "")))
    if archive_path in seen:
      raise SystemExit(f"error: source manifest contains duplicate path: {archive_path}")
    seen.add(archive_path)

    expected_sha = raw_entry.get("sha256")
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
      raise SystemExit(f"error: invalid source-manifest SHA-256 for {archive_path}")
    mode = raw_entry.get("mode")
    if mode not in (0o644, 0o755):
      raise SystemExit(f"error: invalid source-manifest mode for {archive_path}: {mode!r}")

    source = ROOT / archive_path
    if not source.is_file():
      raise SystemExit(
        f"error: source-manifest file is missing: {archive_path}; "
        "extract the release into a new empty directory"
      )
    actual_sha = sha256(source)
    if actual_sha != expected_sha:
      raise SystemExit(
        f"error: source-manifest checksum mismatch: {archive_path}; "
        "use a clean Git checkout or freshly extracted source ZIP"
      )
    entries.append(
      SourceEntry(
        path=source,
        archive_path=archive_path,
        sha256=expected_sha,
        mode=mode,
      )
    )

  return SourceContext(
    entries=tuple(sorted(entries, key=lambda entry: entry.archive_path)),
    manifest=manifest,
    manifest_bytes=manifest_bytes(manifest),
  )


def source_context(release_version: str) -> SourceContext:
  if git_repository_root() is not None:
    return git_source_context(release_version)
  return load_source_manifest(release_version)


def git_metadata_directories() -> tuple[Path, ...]:
  repository_root = git_repository_root()
  if repository_root is None:
    raise SystemExit(
      "error: source ZIP packaging requires a real Git checkout so the complete .git "
      "history can be included"
    )
  git_dir = repository_root / ".git"
  if not git_dir.is_dir():
    raise SystemExit("error: source ZIP packaging requires a .git directory")
  return tuple(
    sorted(
      (path for path in git_dir.rglob("*") if path.is_dir()),
      key=lambda path: path.as_posix(),
    )
  )


def git_metadata_files() -> tuple[Path, ...]:
  repository_root = git_repository_root()
  if repository_root is None:
    raise SystemExit(
      "error: source ZIP packaging requires a real Git checkout so the complete .git "
      "history can be included"
    )
  git_dir = repository_root / ".git"
  if not git_dir.is_dir():
    raise SystemExit("error: source ZIP packaging requires a .git directory")
  files = tuple(
    sorted(
      (path for path in git_dir.rglob("*") if path.is_file()),
      key=lambda path: path.as_posix(),
    )
  )
  if not files:
    raise SystemExit("error: .git directory contains no files")
  return files


def build_source(output: Path, release_version: str, context: SourceContext) -> None:
  prefix = f"tauridium-{release_version}/"
  git_dir = ROOT / ".git"
  with zipfile.ZipFile(output, "w") as zf:
    for entry in context.entries:
      add_file(zf, entry.path, prefix + entry.archive_path, mode=entry.mode)
    add_bytes(zf, context.manifest_bytes, prefix + SOURCE_MANIFEST_NAME)
    add_directory(zf, prefix + ".git/")
    for directory in git_metadata_directories():
      archive_path = directory.relative_to(git_dir).as_posix()
      add_directory(zf, prefix + ".git/" + archive_path)
    for source in git_metadata_files():
      archive_path = source.relative_to(git_dir).as_posix()
      if archive_path == "config":
        config = source.read_text(encoding="utf-8")
        config = re.sub(
          r"(?m)^(\s*filemode\s*=\s*).*$",
          r"\g<1>false",
          config,
        )
        add_bytes(zf, config.encode(), prefix + ".git/" + archive_path)
      else:
        add_file(zf, source, prefix + ".git/" + archive_path, mode=0o644)


def default_runtimes() -> list[Path]:
  binary = "tauridium.exe" if os.name == "nt" else "tauridium"
  runtime = ROOT / "src-tauri" / "target" / "release" / binary
  if not runtime.is_file():
    raise SystemExit(
      f"error: default runtime artifact not found: {runtime}\n"
      "Run `just build` first or pass one or more --runtime paths explicitly."
    )
  return [runtime]


def runtime_zip_name(release_version: str, suffix: str) -> str:
  return f"tauridium-{release_version}-run-{suffix}.zip"


def target_suffix(target: str) -> str:
  """Return a short filesystem-safe suffix for a Rust compilation target."""
  common = {
    "x86_64-pc-windows-msvc": "win-x64",
    "aarch64-pc-windows-msvc": "win-arm64",
    "i686-pc-windows-msvc": "win-x86",
    "x86_64-pc-windows-gnu": "win-x64-gnu",
    "aarch64-pc-windows-gnullvm": "win-arm64-gnullvm",
    "x86_64-unknown-linux-gnu": "linux-x64",
    "aarch64-unknown-linux-gnu": "linux-arm64",
    "i686-unknown-linux-gnu": "linux-x86",
    "armv7-unknown-linux-gnueabihf": "linux-armv7-gnueabihf",
    "x86_64-unknown-linux-musl": "linux-x64-musl",
    "aarch64-unknown-linux-musl": "linux-arm64-musl",
    "x86_64-apple-darwin": "macos-x64",
    "aarch64-apple-darwin": "macos-arm64",
  }
  if target in common:
    return common[target]
  if not re.fullmatch(r"[A-Za-z0-9_.+-]+(?:-[A-Za-z0-9_.+-]+)+", target):
    raise SystemExit(f"error: runtime reported invalid Rust target triple: {target!r}")
  return target.replace("_", "-").lower()


def validate_build_info(info: object, release_version: str) -> tuple[str, str]:
  if not isinstance(info, dict):
    raise SystemExit("error: runtime build-information probe returned invalid JSON")
  if info.get("name") != "Tauridium":
    raise SystemExit("error: runtime build-information probe belongs to a different application")
  if info.get("version") != release_version:
    raise SystemExit(
      "error: runtime version differs from the release source; "
      f"expected {release_version}, found {info.get('version')!r}"
    )
  if info.get("buildMode") != "production":
    raise SystemExit(
      "error: runtime was not compiled in Tauri production mode; "
      f"buildMode={info.get('buildMode')!r}"
    )
  target = info.get("target")
  if not isinstance(target, str) or not target:
    raise SystemExit("error: runtime build-information probe returned no Rust target triple")
  return target, target_suffix(target)


def inspect_runtime(runtime: Path, release_version: str) -> RuntimeArtifact:
  # Do not infer the target from the packaging host. The executable reports the
  # Rust target it was actually compiled for, which keeps native and multi-target
  # release artifacts distinct even when they share one output directory.
  with tempfile.TemporaryDirectory(prefix="tauridium-build-info-") as temp:
    output = Path(temp) / "build-info.json"
    try:
      result = subprocess.run(
        [str(runtime), BUILD_INFO_ARGUMENT, str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
      )
    except (OSError, subprocess.TimeoutExpired) as error:
      raise SystemExit(f"error: unable to probe runtime build information: {error}") from error

    if result.returncode != 0:
      details = (result.stderr or result.stdout).strip()
      suffix = f": {details}" if details else ""
      raise SystemExit(
        f"error: runtime build-information probe failed with exit code {result.returncode}{suffix}"
      )
    if not output.is_file():
      raise SystemExit("error: runtime build-information probe produced no output file")
    try:
      info = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
      raise SystemExit(f"error: invalid runtime build-information output: {error}") from error
    target, suffix = validate_build_info(info, release_version)
    return RuntimeArtifact(path=runtime, target=target, suffix=suffix)


def group_runtimes_by_target(
  runtimes: list[RuntimeArtifact],
) -> dict[str, list[RuntimeArtifact]]:
  groups: dict[str, list[RuntimeArtifact]] = {}
  targets_by_suffix: dict[str, str] = {}
  for runtime in runtimes:
    previous = targets_by_suffix.setdefault(runtime.suffix, runtime.target)
    if previous != runtime.target:
      raise SystemExit(
        "error: runtime target suffix collision: "
        f"{previous!r} and {runtime.target!r} both map to {runtime.suffix!r}"
      )
    groups.setdefault(runtime.suffix, []).append(runtime)
  return groups


def build_runtime(
  output: Path,
  release_version: str,
  runtimes: list[RuntimeArtifact],
) -> None:
  names: set[str] = set()
  with zipfile.ZipFile(output, "w") as zf:
    for runtime in sorted(runtimes, key=lambda item: item.path.name.lower()):
      if not runtime.path.is_file():
        raise SystemExit(f"error: runtime artifact not found: {runtime.path}")
      if runtime.path.name.lower() in names:
        raise SystemExit(f"error: duplicate runtime filename for {runtime.target}: {runtime.path.name}")
      names.add(runtime.path.name.lower())
      add_file(zf, runtime.path, f"tauridium-{release_version}/{runtime.path.name}", mode=0o755)
    targets = ", ".join(sorted({runtime.target for runtime in runtimes}))
    readme = (
      f"Tauridium {release_version}\n\n"
      f"Rust target: {targets}\n"
      "Native runtime artifacts produced from the matching release source.\n"
      "Install or execute the artifact appropriate for its platform/package format.\n"
    ).encode()
    add_bytes(zf, readme, f"tauridium-{release_version}/README.txt")
    add_file(zf, ROOT / "LICENSE", f"tauridium-{release_version}/LICENSE")


def build_runtime_handoff(
  output: Path,
  release_version: str,
  context: SourceContext,
) -> None:
  """Package a source-only runtime build handoff without claiming a native executable."""
  prefix = f"tauridium-{release_version}/"
  handoff = (
    f"Tauridium {release_version} native runtime build handoff\n\n"
    "This archive contains the exact release source without Git metadata.\n"
    "It is not a fabricated or cross-platform executable, and no native runtime is claimed.\n\n"
    "Build and validate the native runtime on the target platform with:\n"
    "  just init ; just check ; just test ; just build ; just package\n\n"
    "On Windows 11, the same workflow is supported natively through PowerShell/pwsh; "
    "Bash, Nushell, WSL, and Git Bash are not required.\n\n"
    "Runtime ZIPs are target-qualified from the executable's reported Rust target, for example:\n"
    f"  tauridium-{release_version}-run-win-x64.zip\n"
    f"  tauridium-{release_version}-run-linux-x64.zip\n\n"
    "Rust formatting is pinned by rust-toolchain.toml to 1.97.1 and release packaging "
    "refuses to proceed unless cargo fmt -- --check succeeds.\n"
  ).encode()
  with zipfile.ZipFile(output, "w") as zf:
    for entry in context.entries:
      add_file(zf, entry.path, prefix + entry.archive_path, mode=entry.mode)
    add_bytes(zf, context.manifest_bytes, prefix + SOURCE_MANIFEST_NAME)
    add_bytes(zf, handoff, prefix + "RUNTIME-HANDOFF.txt")


def manifest_git_log(context: SourceContext) -> str:
  git = context.manifest.get("git")
  if isinstance(git, dict):
    log = git.get("log")
    if isinstance(log, str) and log:
      return log
  return "Git history unavailable; source integrity is anchored by the packaged source manifest."


def build_docs(
  output: Path,
  release_version: str,
  source_zip: Path,
  run_zips: list[Path],
  context: SourceContext,
) -> None:
  prefix = f"tauridium-{release_version}-doc/"
  evidence = ROOT / "release" / "evidence"
  checksum_lines = [f"{sha256(source_zip)}  {source_zip.name}"]
  checksum_lines.extend(f"{sha256(run_zip)}  {run_zip.name}" for run_zip in run_zips)
  checksums = ("\n".join(checksum_lines) + "\n").encode()
  with zipfile.ZipFile(output, "w") as zf:
    for name in ("README.md", "CHANGELOG.md", "LICENSE"):
      add_file(zf, ROOT / name, prefix + name)
    add_bytes(zf, checksums, prefix + "SHA256SUMS")
    add_bytes(zf, (manifest_git_log(context) + "\n").encode(), prefix + "GIT-LOG.txt")
    add_bytes(zf, context.manifest_bytes, prefix + SOURCE_MANIFEST_NAME)
    if evidence.is_dir():
      for source in sorted(evidence.rglob("*")):
        if source.is_file():
          add_file(zf, source, prefix + "evidence/" + source.relative_to(evidence).as_posix())


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("--runtime", type=Path, action="append")
  parser.add_argument(
    "--build-handoff",
    action="store_true",
    help="package an explicitly source-only run-build-handoff instead of a native runtime",
  )
  parser.add_argument("--output-dir", type=Path, default=ROOT / "release")
  args = parser.parse_args()

  require_pinned_rustfmt_clean()
  release_version = version()
  context = source_context(release_version)
  output_dir = args.output_dir.resolve()
  output_dir.mkdir(parents=True, exist_ok=True)
  src = output_dir / f"tauridium-{release_version}-src.zip"
  doc = output_dir / f"tauridium-{release_version}-doc.zip"
  build_source(src, release_version, context)
  if args.build_handoff and args.runtime:
    raise SystemExit("error: --build-handoff cannot be combined with --runtime")
  run_zips: list[Path] = []
  if args.build_handoff:
    handoff = output_dir / f"tauridium-{release_version}-run-build-handoff.zip"
    build_runtime_handoff(handoff, release_version, context)
    run_zips.append(handoff)
  else:
    runtime_paths = [path.resolve() for path in args.runtime] if args.runtime else default_runtimes()
    runtime_artifacts = [inspect_runtime(path, release_version) for path in runtime_paths]
    grouped_runtimes = group_runtimes_by_target(runtime_artifacts)
    for suffix, target_runtimes in sorted(grouped_runtimes.items()):
      run = output_dir / runtime_zip_name(release_version, suffix)
      build_runtime(run, release_version, target_runtimes)
      run_zips.append(run)
  build_docs(doc, release_version, src, run_zips, context)
  print(src)
  for run in run_zips:
    print(run)
  print(doc)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
