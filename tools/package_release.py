#!/usr/bin/env python3
"""Create deterministic Tauridium source, runtime, and documentation release ZIPs."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
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
  data: bytes | None = None


@dataclass(frozen=True)
class SourceContext:
  entries: tuple[SourceEntry, ...]
  manifest: dict[str, Any]
  manifest_bytes: bytes
  git_files: tuple[tuple[str, bytes], ...] = ()


@dataclass(frozen=True)
class RuntimeArtifact:
  path: Path
  target: str
  suffix: str


def version() -> str:
  return json.loads((ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))["version"]


def git_command(*args: str, platform_name: str | None = None) -> list[str]:
  """Build a Git command without Unix file-mode false positives on Windows."""
  platform = os.name if platform_name is None else platform_name
  command = ["git"]
  if platform == "nt":
    command.extend(["-c", "core.filemode=false"])
  command.extend(args)
  return command


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


def require_rust_supply_chain_clean() -> None:
  result = subprocess.run(
    [sys.executable, "tools/check_rust_supply_chain.py"],
    cwd=ROOT,
    text=True,
    capture_output=True,
    check=False,
  )
  if result.returncode != 0:
    details = (result.stdout + result.stderr).strip()
    raise SystemExit(
      "error: release packaging refused because the Rust supply-chain guard failed"
      + (f"\n{details}" if details else "")
    )


def git_repository_root() -> Path | None:
  result = subprocess.run(
    git_command("rev-parse", "--show-toplevel"),
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
    git_command(*args),
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
  reject_link(source)
  info = zipfile.ZipInfo(archive_name, ZIP_TIME)
  info.compress_type = zipfile.ZIP_DEFLATED
  info.external_attr = (mode if mode is not None else file_mode(source)) << 16
  zf.writestr(info, source.read_bytes())


def reject_link(path: Path) -> None:
  metadata = path.lstat()
  if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x400:
    raise SystemExit("error: public artifact input must not be a symlink or reparse point: " + str(path))


@contextmanager
def release_zip(output: Path):
  """Never replace an existing artifact until a complete new ZIP validates."""
  with tempfile.NamedTemporaryFile(prefix="." + output.name + "-", suffix=".tmp", dir=output.parent, delete=False) as handle:
    temporary = Path(handle.name)
  try:
    with zipfile.ZipFile(temporary, "w") as archive:
      yield archive
    with zipfile.ZipFile(temporary) as archive:
      if archive.testzip() is not None:
        raise SystemExit("error: generated ZIP failed its integrity check")
      names = archive.namelist()
      if len(set(names)) != len(names):
        raise SystemExit("error: generated ZIP contains duplicate members")
      for name in names:
        path = PurePosixPath(name.rstrip("/"))
        if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or path.as_posix() != name.rstrip("/"):
          raise SystemExit("error: generated ZIP contains an unsafe member")
    os.replace(temporary, output)
  finally:
    temporary.unlink(missing_ok=True)


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
  if (
    path.is_absolute() or not value or not path.parts or ".." in path.parts
    or path.as_posix() != value or "\\" in value or ":" in value
    or any(part.rstrip(" .") != part or part.casefold() == ".git" for part in path.parts)
  ):
    raise SystemExit(f"error: invalid source-manifest path: {value!r}")
  if value == SOURCE_MANIFEST_NAME:
    raise SystemExit(f"error: source manifest must not list itself: {value}")
  return value


def manifest_bytes(manifest: dict[str, Any]) -> bytes:
  return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()


def tracked_entries(tree: str | None = None) -> tuple[SourceEntry, ...]:
  """Return tracked files using Git-index modes for cross-platform determinism.

  Windows does not expose Unix executable bits through ``Path.stat()`` the same
  way Unix does. Reading the index mode makes source ZIP permissions identical
  whether a release is packaged on Linux, macOS, or Windows.
  """
  command = git_command("ls-tree", "-r", "-z", tree) if tree else git_command("ls-files", "--stage", "-z")
  raw = subprocess.check_output(command, cwd=ROOT)
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
    safe_manifest_path(archive_path)
    source = ROOT / archive_path
    # Index objects are immutable and preserve Git's canonical line endings;
    # never dereference a tracked working-tree path when exporting source.
    blob = metadata.split()[2 if tree else 1].decode("ascii")
    data = subprocess.check_output(git_command("cat-file", "blob", blob), cwd=ROOT)
    entries.append(
      SourceEntry(
        path=source,
        archive_path=archive_path,
        sha256=hashlib.sha256(data).hexdigest(),
        mode=mode,
        data=data,
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
  flags = subprocess.check_output(git_command("ls-files", "-v", "-z"), cwd=ROOT)
  if any(item and not item.startswith(b"H ") for item in flags.split(b"\0")):
    raise SystemExit("error: release rejects assume-unchanged, skip-worktree or other hidden index flags")

  git_files = sanitized_git_files(release_version)
  commit = dict(git_files)["refs/heads/master"].decode("ascii").strip()
  entries = tracked_entries(commit)
  manifest: dict[str, Any] = {
    "schema": SOURCE_MANIFEST_SCHEMA,
    "project": "Tauridium",
    "version": release_version,
    "git": {
      "commit": commit,
      "tree": git_output("rev-parse", commit + "^{tree}"),
      "tag": exact_release_tag(release_version),
      "log": git_output("log", "--oneline", "--no-decorate", "-20", commit),
    },
    "files": [
      {
        "path": entry.archive_path,
        "sha256": entry.sha256,
        "mode": entry.mode,
      }
      for entry in entries
    ],
    "gitFiles": [
      {"path": ".git/" + name, "sha256": hashlib.sha256(data).hexdigest()}
      for name, data in git_files
    ],
  }
  return SourceContext(entries=entries, manifest=manifest, manifest_bytes=manifest_bytes(manifest), git_files=git_files)


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
    reject_link(source)
    data = source.read_bytes()
    actual_sha = hashlib.sha256(data).hexdigest()
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
        data=data,
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


def should_package_release(if_tagged: bool, release_version: str) -> bool:
  """Return whether a conditional packaging invocation should create artifacts.

  Extracted release sources are anchored by their source manifest rather than a
  live Git tag, so they must continue into the normal manifest validation path.
  Direct packaging remains strict because only ``--if-tagged`` enables the
  branch-friendly skip used by the top-level ``just release`` workflow.
  """
  if not if_tagged or git_repository_root() is None:
    return True
  expected_tag = f"v{release_version}"
  if exact_release_tag(release_version) == expected_tag:
    return True
  print(
    "Release artifact packaging skipped: "
    f"HEAD is not the exact version tag {expected_tag}. "
    "Validation and the production build completed successfully; "
    "tag the release commit before creating immutable release ZIPs."
  )
  return False


def tree_entries(root: Path) -> tuple[tuple[tuple[Path, str], ...], tuple[tuple[Path, str], ...]]:
  """Return directory/file entries with traversal-owned relative archive paths.

  Archive paths are carried while walking instead of being reconstructed with
  lexical parent-path reconstruction. On Windows, the same directory can be
  exposed through both its long name and an 8.3 short-name alias, making lexical
  parent comparisons unreliable even when both paths identify the same directory.
  """
  directories: list[tuple[Path, str]] = []
  reject_link(root)
  files: list[tuple[Path, str]] = []
  pending: list[tuple[Path, str]] = [(root, "")]
  while pending:
    current, relative_root = pending.pop()
    child_directories: list[tuple[Path, str]] = []
    for child in sorted(current.iterdir(), key=lambda path: path.name):
      reject_link(child)
      archive_path = f"{relative_root}/{child.name}" if relative_root else child.name
      if child.is_dir():
        directories.append((child, archive_path))
        child_directories.append((child, archive_path))
      elif child.is_file():
        files.append((child, archive_path))
    pending.extend(reversed(child_directories))
  return (
    tuple(sorted(directories, key=lambda entry: entry[1])),
    tuple(sorted(files, key=lambda entry: entry[1])),
  )




def sanitized_git_files(release_version: str) -> tuple[tuple[str, bytes], ...]:
  """Export approved tag ancestry into a NEW repository, never local Git state.

  Preserve private full-Git recovery checkpoints separately. Fetching one
  immutable tag object transfers its reachable history, not dangling objects,
  local refs, config, hooks, reflogs, helpers or a producer's index.
  """
  if git_repository_root() is None:
    raise SystemExit("error: source ZIP requires a real Git checkout")
  tag = f"v{release_version}"
  tag_object = git_output("rev-parse", f"refs/tags/{tag}")
  commit = git_output("rev-parse", f"refs/tags/{tag}^{{commit}}")
  if commit != git_output("rev-parse", "HEAD"):
    raise SystemExit("error: source export tag and HEAD disagree")
  env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
             GIT_TERMINAL_PROMPT="0", GIT_CONFIG_COUNT="0")
  # Caller-injected Git routing/config variables cannot redirect the clean
  # export. Identity and real publisher credentials are neither read nor copied.
  for key in tuple(env):
    if key.startswith("GIT_") and key not in {"GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_TERMINAL_PROMPT", "GIT_CONFIG_COUNT"}:
      env.pop(key)
  with tempfile.TemporaryDirectory(prefix="tauridium-public-git-") as temporary:
    clean = Path(temporary) / "repo"
    template = Path(temporary) / "empty-template"
    template.mkdir()
    def run(*args: str) -> None:
      subprocess.run(["git", "-c", "core.hooksPath=" + str(template),
                      "-c", "core.fsmonitor=false", "-c", "fetch.writeCommitGraph=false",
                      *args], cwd=clean if clean.exists() else temporary,
                     env=env, check=True, capture_output=True)
    run("init", "--quiet", "--template=" + str(template), str(clean))
    run("config", "core.logAllRefUpdates", "false")
    run("-c", "protocol.file.allow=always", "fetch", "--quiet", "--no-tags",
        "--no-write-fetch-head", str(ROOT), f"{tag_object}:refs/tags/{tag}")
    run("update-ref", "refs/heads/master", commit)
    run("symbolic-ref", "HEAD", "refs/heads/master")
    run("read-tree", commit)
    git_dir = clean / ".git"
    # Fixed, inert public configuration; never copy producer configuration.
    (git_dir / "config").write_text(
      "[core]\n\trepositoryformatversion = 0\n\tfilemode = false\n\tbare = false\n\tlogallrefupdates = false\n",
      encoding="utf-8",
    )
    (git_dir / "info").mkdir(exist_ok=True)
    (git_dir / "info" / "exclude").write_text(SOURCE_MANIFEST_NAME + "\n", encoding="utf-8")
    allowed = re.compile(r"(?:HEAD|config|index|info/exclude|refs/heads/master|refs/tags/" + re.escape(tag) + r"|objects/[0-9a-f]{2}/[0-9a-f]{38}|objects/pack/pack-[0-9a-f]{40}\.(?:pack|idx))")
    _directories, files = tree_entries(git_dir)
    return tuple((name, source.read_bytes()) for source, name in files if allowed.fullmatch(name))


def add_source_entry(zf: zipfile.ZipFile, entry: SourceEntry, prefix: str) -> None:
  if entry.data is not None:
    add_bytes(zf, entry.data, prefix + entry.archive_path, executable=entry.mode == 0o755)
  else:
    add_file(zf, entry.path, prefix + entry.archive_path, mode=entry.mode)


def build_source(output: Path, release_version: str, context: SourceContext) -> None:
  if not context.git_files:
    raise SystemExit("error: source ZIP requires a real Git checkout and sanitized approved history")
  prefix = f"tauridium-{release_version}/"
  with release_zip(output) as zf:
    for entry in context.entries:
      add_source_entry(zf, entry, prefix)
    add_bytes(zf, context.manifest_bytes, prefix + SOURCE_MANIFEST_NAME)
    add_directory(zf, prefix + ".git/")
    directories = {"objects", "objects/info", "objects/pack", "refs", "refs/heads", "refs/tags"}
    for archive_path, _data in context.git_files:
      directories.update(str(parent) for parent in PurePosixPath(archive_path).parents if str(parent) != ".")
    for archive_path in sorted(directories):
      add_directory(zf, prefix + ".git/" + archive_path)
    for archive_path, data in context.git_files:
      add_bytes(zf, data, prefix + ".git/" + archive_path)


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
  with release_zip(output) as zf:
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
      + (
        "\nLinux executables are dynamically linked and require the build's compatible GTK/WebKit libraries.\n"
        "A runtime built in the locked Nix development shell also requires its Nix store dependencies;\n"
        "this ZIP is not a standalone Nix closure or a portable AppImage.\n"
        "From the paired full-Git source archive, use the locked environment to launch that runtime:\n"
        "  nix --extra-experimental-features 'nix-command flakes' develop --command /path/to/tauridium\n"
        "For Nix/NixOS installation, prefer the wrapped source-built package described in docs/NIX.md:\n"
        "  nix --extra-experimental-features 'nix-command flakes' run .#tauridium\n"
        if any("linux" in runtime.target for runtime in runtimes) else ""
      )
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
    "Do not run the release workflow directly from this Git-free archive.\n"
    f"Extract the paired tauridium-{release_version}-src.zip into a new empty directory; "
    "it contains the complete Git history and exact release tag required by the workflow.\n"
    "From that extracted full-Git source directory, build and validate the native runtime with:\n"
    "  just init\n"
    "  just release\n\n"
    "On Windows 11, the same workflow is supported natively through PowerShell/pwsh; "
    "Bash, Nushell, WSL, and Git Bash are not required.\n\n"
    "For file-drop validation, use the fixture and native-service checklist in docs/file-drops.md.\n\n"
    "Runtime ZIPs are target-qualified from the executable's reported Rust target, for example:\n"
    f"  tauridium-{release_version}-run-win-x64.zip\n"
    f"  tauridium-{release_version}-run-linux-x64.zip\n\n"
    "Rust formatting is pinned by rust-toolchain.toml to 1.97.1 and release packaging "
    "refuses to proceed unless cargo fmt -- --check succeeds.\n"
  ).encode()
  with release_zip(output) as zf:
    for entry in context.entries:
      add_source_entry(zf, entry, prefix)
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
  *,
  public_evidence: bool = False,
) -> None:
  prefix = f"tauridium-{release_version}-doc/"
  entries = {entry.archive_path: entry for entry in context.entries}
  checksum_lines = [f"{sha256(source_zip)}  {source_zip.name}"]
  checksum_lines.extend(f"{sha256(run_zip)}  {run_zip.name}" for run_zip in run_zips)
  checksums = ("\n".join(checksum_lines) + "\n").encode()
  with release_zip(output) as zf:
    for name in ("README.md", "CHANGELOG.md", "AGENTS.md", "LICENSE"):
      add_source_entry(zf, entries[name], prefix)
    for source, archive_path in (
      (ROOT / "docs" / "installation.md", "docs/installation.md"),
      (ROOT / "docs" / "NIX.md", "docs/NIX.md"),
      (ROOT / "docs" / "file-drops.md", "docs/file-drops.md"),
      (ROOT / "docs" / "download-notifications.md", "docs/download-notifications.md"),
      (ROOT / "docs" / "releases" / f"{release_version}-validation.md", f"docs/releases/{release_version}-validation.md"),
      (ROOT / "tools" / "fixtures" / "file-drop.html", "tools/fixtures/file-drop.html"),
      (ROOT / "docs" / "github-language-statistics.md", "docs/github-language-statistics.md"),
      (ROOT / "packaging" / "scoop" / "README.md", "docs/scoop-packaging.md"),
    ):
      source_name = source.as_posix().removeprefix(ROOT.as_posix() + "/")
      if source_name in entries:
        entry = entries[source_name]
        add_bytes(zf, entry.data if entry.data is not None else entry.path.read_bytes(), prefix + archive_path)
    add_bytes(zf, checksums, prefix + "SHA256SUMS")
    add_bytes(zf, (manifest_git_log(context) + "\n").encode(), prefix + "GIT-LOG.txt")
    add_bytes(zf, context.manifest_bytes, prefix + SOURCE_MANIFEST_NAME)
    for name, entry in entries.items():
      if name.startswith("docs/examples/nix/"):
        add_source_entry(zf, entry, prefix)
    if public_evidence:
      for archive_path, data in public_evidence_files(release_version):
        add_bytes(zf, data, prefix + "evidence/" + archive_path)


def public_evidence_files(release_version: str) -> tuple[tuple[str, bytes], ...]:
  """Explicit reviewed staging only; never recursively publish raw evidence."""
  manifest_path = ROOT / "release" / "public-evidence.json"
  try:
    reject_link(manifest_path)
    if manifest_path.stat().st_size > 1024 * 1024:
      raise SystemExit("error: public evidence manifest exceeds 1 MiB")
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
  except (OSError, ValueError) as error:
    raise SystemExit(f"error: unable to load public evidence manifest: {error}") from error
  if not isinstance(document, dict) or document.get("schema") != 1 or document.get("version") != release_version:
    raise SystemExit("error: public evidence manifest is not for this release")
  records = document.get("files")
  if not isinstance(records, list) or len(records) > 100:
    raise SystemExit("error: public evidence must have at most 100 approved files")
  stage = ROOT / "release" / "public-evidence"
  if not stage.is_dir():
    raise SystemExit("error: public evidence staging directory is missing")
  _directories, actual_files = tree_entries(stage)
  actual = {name for _path, name in actual_files}
  approved: dict[str, str] = {}
  for record in records:
    if not isinstance(record, dict) or not isinstance(record.get("path"), str) or not isinstance(record.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
      raise SystemExit("error: malformed public evidence entry or SHA-256")
    name = safe_manifest_path(record["path"])
    if name in approved or Path(name).suffix.lower() not in {".png", ".json", ".md", ".txt", ".log"} or any(part.startswith(".") for part in PurePosixPath(name).parts):
      raise SystemExit("error: unexpected or duplicate public evidence member")
    approved[name] = record["sha256"]
  if actual != set(approved):
    raise SystemExit("error: public evidence staging differs from its approved manifest")
  result = []
  total = 0
  for path, name in actual_files:
    if path.stat().st_size > 10 * 1024 * 1024:
      raise SystemExit("error: public evidence file exceeds 10 MiB")
    data = path.read_bytes()
    total += len(data)
    if total > 50 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != approved[name]:
      raise SystemExit("error: public evidence size or checksum validation failed")
    result.append((name, data))
  return tuple(result)


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("--runtime", type=Path, action="append")
  parser.add_argument(
    "--build-handoff",
    action="store_true",
    help="package an explicitly source-only run-build-handoff instead of a native runtime",
  )
  parser.add_argument(
    "--if-tagged",
    action="store_true",
    help="skip artifact packaging successfully when a Git checkout is not at its exact version tag",
  )
  parser.add_argument("--output-dir", type=Path, default=ROOT / "release")
  parser.add_argument("--public-evidence", action="store_true", help="include only independently reviewed release/public-evidence.json staged files; raw release/evidence is never public")
  args = parser.parse_args()

  require_pinned_rustfmt_clean()
  require_rust_supply_chain_clean()
  release_version = version()
  if not should_package_release(args.if_tagged, release_version):
    return 0
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
  build_docs(doc, release_version, src, run_zips, context, public_evidence=args.public_evidence)
  print(src)
  for run in run_zips:
    print(run)
  print(doc)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
