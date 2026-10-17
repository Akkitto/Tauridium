#!/usr/bin/env python3
"""Build a clean immutable local snapshot without installing over the user's Flatpak."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
import stat

import generate_flatpak_sources as sources
from flatpak_policy import validate_permissions
import tauri_build

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "flatpak/dev.brani.tauridium.yml"
LOCKS = ("src-tauri/Cargo.lock", "package-lock.json", "flatpak/tauri-cli.Cargo.lock",
         "data/build-toolchain.json")
GENERATED = ("flatpak/cargo-sources.json", "flatpak/node-sources.json", "flatpak/tauri-cli-cargo-sources.json",
             "flatpak/tauri-cli-policy.json")
PIN = re.compile(r"(?m)^      - type: git\r?\n        url: https://github.com/Akkitto/Tauridium.git\r?\n"
                 r"        tag: (?P<tag>v[0-9]+\.[0-9]+\.[0-9]+)\r?\n"
                 r"        commit: (?P<commit>\S+)\r?\n        dest: source\r?\n"
                 r"        x-checker-data:\r?\n          type: git\r?\n          tag-pattern: [^\r\n]+\r?\n")


def file_digest(path: Path) -> str:
  if not path.is_file() or path.is_symlink():
    raise SystemExit("error: Flatpak candidate requires regular files, not links")
  digest = hashlib.sha256()
  with path.open("rb") as stream:
    for block in iter(lambda: stream.read(1024**2), b""):
      digest.update(block)
  return digest.hexdigest()


def tree_digest(root: Path) -> str:
  if not root.is_dir() or root.is_symlink():
    raise SystemExit("error: Flatpak candidate tree must be a real directory")
  records = []
  for path in sorted(root.rglob("*")):
    name = path.relative_to(root).as_posix()
    if path.is_symlink():
      if not path.resolve().is_relative_to(root.resolve()):
        raise SystemExit("error: Flatpak candidate contains an escaping link")
      records.append([name, "link", os.readlink(path)])
    elif path.is_file():
      records.append([name, stat.S_IMODE(path.stat().st_mode), file_digest(path)])
    elif not path.is_dir():
      raise SystemExit("error: Flatpak candidate contains a special file")
  return hashlib.sha256(json.dumps(records, separators=(",", ":")).encode()).hexdigest()


def atomic_json(path: Path, value: dict) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with tempfile.NamedTemporaryFile(prefix=".tauridium-candidate-", dir=path.parent, delete=False) as stream:
    temporary = Path(stream.name)
    try:
      stream.write((json.dumps(value, indent=2) + "\n").encode("utf-8"))
      stream.flush()
      os.fsync(stream.fileno())
      stream.close()
      os.replace(temporary, path)
    finally:
      temporary.unlink(missing_ok=True)


def validate_runtime_layout(output: Path) -> None:
  # flatpak build prefers build/usr over the runtime named in metadata, even
  # with --runtime. No custom SDK/runtime tree is supported by this producer.
  if os.path.lexists(output / "build/usr"):
    raise SystemExit("error: Flatpak candidate contains an unreviewed custom runtime")


def seal_candidate(output: Path) -> None:
  # A successful pointer is a custody transition, not merely a byte hash. Refuse
  # unreviewed runtime permissions before writing either success document.
  validate_runtime_layout(output)
  validate_permissions(output / "build/metadata")
  result = {"passed": True, "installed": False, "runtimeExecutables": ["tauridium"],
            "identitySha256": file_digest(output / "identity.json"),
            "runtimeSha256": tree_digest(output / "build/files"),
            "metadataSha256": file_digest(output / "build/metadata"),
            "repoSha256": tree_digest(output / "repo")}
  atomic_json(output / "result.json", result)
  # Publish the pointer only after every build/export and inventory check passes.
  atomic_json(ROOT / "release/flatpak/latest.json", {"candidate": str(output.resolve()),
              "resultSha256": file_digest(output / "result.json")})


def git(*arguments: str) -> bytes:
  environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
  environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_NO_REPLACE_OBJECTS="1")
  return subprocess.run(["git", "-c", "core.fsmonitor=false", *arguments], cwd=ROOT, env=environment,
                        check=True, capture_output=True, timeout=90).stdout


def builder_command(environment: dict[str, str]) -> list[str]:
  native = shutil.which("flatpak-builder")
  if native:
    return [native]
  flatpak = shutil.which("flatpak")
  if flatpak:
    result = subprocess.run([flatpak, "info", "org.flatpak.Builder"], env=environment, capture_output=True, timeout=30)
    if result.returncode == 0:
      return [flatpak, "run", "--command=flatpak-builder", "org.flatpak.Builder"]
  raise SystemExit("error: install flatpak-builder or org.flatpak.Builder; nix develop supplies the native builder")


def verify_inputs(generated: dict[str, bytes], source: dict[str, bytes]) -> None:
  with tempfile.TemporaryDirectory(prefix="tauridium-flatpak-locks-") as temporary:
    root = Path(temporary)
    for index, name in enumerate(LOCKS[:3]):
      (root / str(index)).write_bytes(source[name])
    expected = (sources.generate_cargo_sources(root / "0"), sources.generate_node_sources(root / "1"),
                sources.generate_cargo_sources(root / "2"), json.loads(source["data/build-toolchain.json"]))
    for name, value in zip(GENERATED, expected):
      if json.loads(generated[name]) != value:
        raise SystemExit("error: Flatpak offline inputs do not match selected source; use the local build or synchronize publication inputs with its immutable source")
  policy = json.loads(source["data/build-toolchain.json"])
  if hashlib.sha256(source["flatpak/tauri-cli.Cargo.lock"]).hexdigest() != policy["tauriCliLockSha256"]:
    raise SystemExit("error: selected Flatpak builder lock differs from its reviewed toolchain policy")


def exact_tree_archive(revision: str) -> bytes:
  """Export Git tree/blob bytes, never producer/tracked export attributes or filters."""
  stream = io.BytesIO()
  directories = set()
  total = 0
  with tarfile.open(fileobj=stream, mode="w", format=tarfile.PAX_FORMAT) as archive:
    for row in git("ls-tree", "-r", "-z", "--full-tree", revision).split(b"\0"):
      if not row:
        continue
      metadata, raw_path = row.split(b"\t", 1)
      mode, kind, oid = metadata.split()
      name = raw_path.decode("utf-8")
      parts = PurePosixPath(name).parts
      if (kind != b"blob" or mode not in (b"100644", b"100755")
          or not re.fullmatch(rb"[0-9a-f]{40}", oid) or not parts or name != "/".join(parts)
          or name.startswith("/") or "\\" in name or ":" in name
          or any(part in (".", "..", ".git") for part in parts)):
        raise SystemExit("error: exact Flatpak source requires safe regular Git tree entries")
      data = git("cat-file", "blob", oid.decode("ascii"))
      actual = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data, usedforsecurity=False).hexdigest()
      if actual != oid.decode("ascii"):
        raise SystemExit("error: Flatpak source object does not match its Git identity")
      total += len(data)
      if total > 512 * 1024**2:
        raise SystemExit("error: Flatpak source snapshot exceeds its byte budget")
      for index in range(1, len(parts)):
        parent = "/".join(parts[:index])
        if parent not in directories:
          entry = tarfile.TarInfo(parent)
          entry.type, entry.mode = tarfile.DIRTYPE, 0o755
          archive.addfile(entry)
          directories.add(parent)
      entry = tarfile.TarInfo(name)
      entry.mode, entry.size = (0o755 if mode == b"100755" else 0o644), len(data)
      archive.addfile(entry, io.BytesIO(data))
  return stream.getvalue()


def snapshot_flatpak(archive: bytes, destination: Path) -> None:
  # Keep the original relative module/include/patch paths. Never relocate by a
  # basename search, copy ignored files, or extract archive links/special entries.
  with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as source:
    for member in source.getmembers():
      path = PurePosixPath(member.name)
      if not path.parts or path.parts[0] != "flatpak":
        continue
      if path.is_absolute() or ".." in path.parts or not (member.isdir() or member.isfile()):
        raise SystemExit("error: Flatpak configuration snapshot contains an unsafe path or non-regular entry")
      target = destination.joinpath(*path.parts)
      if member.isdir():
        target.mkdir(parents=True, exist_ok=True)
      else:
        target.parent.mkdir(parents=True, exist_ok=True)
        stream = source.extractfile(member)
        if stream is None:
          raise SystemExit("error: Flatpak configuration snapshot is incomplete")
        target.write_bytes(stream.read())
        target.chmod(member.mode & 0o777)


def local_manifest(text: str, archive: Path, digest: str) -> str:
  replacement = ("      - type: archive\n        archive-type: tar\n"
                 f"        path: {json.dumps(str(archive))}\n        sha256: {digest}\n"
                 "        strip-components: 0\n        dest: source\n")
  result, count = PIN.subn(lambda _match: replacement, text)
  if count != 1:
    raise SystemExit("error: expected one exact immutable Tauridium source pin in the Flatpak reference")
  return result


def prepare(publication: bool, parent: Path) -> tuple[Path, Path]:
  if git("status", "--porcelain", "--untracked-files=all").strip():
    raise SystemExit("error: Flatpak snapshot requires a clean committed worktree; commit edits first")
  if any(row and not row.startswith(b"H ") for row in git("ls-files", "-v", "-z").split(b"\0")):
    raise SystemExit("error: Flatpak snapshot rejects hidden Git index flags")
  head = git("rev-parse", "HEAD").decode().strip()
  text = git("show", head + ":" + MANIFEST).decode("utf-8")
  matches = list(PIN.finditer(text))
  if len(matches) != 1:
    raise SystemExit("error: Flatpak reference has no unique source pin")
  revision = head
  if publication:
    revision = matches[0]["commit"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
      raise SystemExit("error: materialize the immutable Flatpak publication source pin first")
    if git("rev-parse", matches[0]["tag"] + "^{commit}").decode().strip() != revision:
      raise SystemExit("error: Flatpak publication tag and source commit differ")
  try:
    selected = {name: git("show", revision + ":" + name) for name in LOCKS}
  except subprocess.CalledProcessError:
    raise SystemExit("error: selected Flatpak source predates required reviewed build metadata; use just flatpak-build for local HEAD, then synchronize the publication pin after an authorized release") from None
  current = {name: git("show", head + ":" + name) for name in (*GENERATED, "data/build-toolchain.json")}
  verify_inputs(current, selected)
  if current["data/build-toolchain.json"] != selected["data/build-toolchain.json"]:
    raise SystemExit("error: Flatpak publication builder policy differs from selected source")
  parent.mkdir(parents=True, exist_ok=True)
  output = Path(tempfile.mkdtemp(prefix=revision[:12] + "-", dir=parent))
  archive = exact_tree_archive(revision)
  source = output / "source.tar"
  source.write_bytes(archive)
  digest = hashlib.sha256(archive).hexdigest()
  # Build configuration comes from reviewed HEAD; application source is explicit.
  snapshot_flatpak(archive if revision == head else exact_tree_archive(head), output / "configuration")
  manifest = output / "configuration" / MANIFEST
  manifest.write_text(local_manifest(text, source, digest), encoding="utf-8", newline="\n")
  (output / "identity.json").write_text(json.dumps({
      "schemaVersion": 1,
      "commit": revision, "configurationCommit": head, "sourceSha256": digest,
      "configurationSha256": tree_digest(output / "configuration"),
      "publicationPinVerified": publication, "installed": False}, indent=2) + "\n", encoding="utf-8")
  return output, manifest


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--publication", action="store_true", help="Verify the reference tag/pin and its exact offline inputs before building")
  parser.add_argument("--prepare-only", action="store_true", help="Validate and materialize the immutable snapshot without building")
  parser.add_argument("--output-parent", type=Path, default=ROOT / "release/flatpak")
  args = parser.parse_args()
  environment = tauri_build.build_environment(dict(os.environ))
  output, manifest = prepare(args.publication, args.output_parent.resolve())
  print(f"Verified immutable Flatpak snapshot: {output}", flush=True)
  if args.prepare_only:
    return 0
  command = builder_command(environment)
  subprocess.run([*command, "--sandbox", "--user", "--disable-rofiles-fuse", "--keep-build-dirs",
                  "--state-dir=" + str(ROOT / ".flatpak-builder"), "--repo=" + str(output / "repo"),
                  str(output / "build"), str(manifest)], cwd=ROOT, env=environment, check=True)
  executables = {entry.name for entry in (output / "build/files/bin").iterdir()}
  if executables != {"tauridium"}:
    raise SystemExit("error: final Flatpak runtime executable inventory differs; builder tools must not ship")
  seal_candidate(output)
  print(f"Flatpak build/export passed, no application installed: {output}", flush=True)
  return 0


if __name__ == "__main__":
  try:
    raise SystemExit(main())
  except (OSError, ValueError, KeyError, subprocess.SubprocessError, tarfile.TarError):
    raise SystemExit("error: Flatpak snapshot/build failed; inspect the private local build output") from None

