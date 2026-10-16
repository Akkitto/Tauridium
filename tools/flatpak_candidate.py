#!/usr/bin/env python3
"""Validate/run the exact current Flatpak candidate; never use the installed app."""
from __future__ import annotations

import argparse
import configparser
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import flatpak_build as build
import tauri_build

APP_ID = "dev.brani.tauridium"


def document(path: Path) -> dict:
  build.file_digest(path)
  if path.stat().st_size > 1024**2:
    raise SystemExit("error: Flatpak candidate metadata is oversized")
  value = json.loads(path.read_text(encoding="utf-8"))
  if not isinstance(value, dict):
    raise SystemExit("error: Flatpak candidate metadata must be an object")
  return value


def select(candidate: str = "") -> Path:
  if build.git("status", "--porcelain", "--untracked-files=all").strip():
    raise SystemExit("error: commit worktree edits and rebuild before validating a Flatpak candidate")
  head = build.git("rev-parse", "HEAD").decode().strip()
  pointer = None
  if not candidate:
    pointer_path = build.ROOT / "release/flatpak/latest.json"
    if not pointer_path.is_file():
      raise SystemExit("error: no successful current Flatpak candidate; run just flatpak-build first")
    pointer = document(pointer_path)
    candidate = pointer["candidate"]
  raw = Path(candidate).absolute()
  if raw.is_symlink() or not raw.is_dir():
    raise SystemExit("error: candidate must be a real successful build directory")
  output = raw.resolve()
  identity, result = document(output / "identity.json"), document(output / "result.json")
  if (identity.get("schemaVersion") != 1 or identity.get("configurationCommit") != head
      or identity.get("installed") is not False or result.get("passed") is not True
      or result.get("installed") is not False or result.get("runtimeExecutables") != ["tauridium"]):
    raise SystemExit("error: incomplete or stale Flatpak candidate; rebuild the current committed HEAD")
  revision = identity.get("commit")
  if identity.get("publicationPinVerified") is False:
    if revision != head:
      raise SystemExit("error: local Flatpak candidate does not match current HEAD")
  elif identity.get("publicationPinVerified") is True:
    text = build.git("show", head + ":" + build.MANIFEST).decode("utf-8")
    match = build.PIN.search(text)
    if match is None or revision != match["commit"] or build.git("rev-parse", match["tag"] + "^{commit}").decode().strip() != revision:
      raise SystemExit("error: publication candidate does not match its exact reviewed tag/pin")
  else:
    raise SystemExit("error: candidate source mode is invalid")
  if pointer and pointer.get("resultSha256") != build.file_digest(output / "result.json"):
    raise SystemExit("error: latest candidate result differs from its successful build seal")
  checks = ((build.file_digest(output / "identity.json"), result.get("identitySha256")),
            (build.file_digest(output / "source.tar"), identity.get("sourceSha256")),
            (build.tree_digest(output / "configuration"), identity.get("configurationSha256")),
            (build.tree_digest(output / "build/files"), result.get("runtimeSha256")),
            (build.file_digest(output / "build/metadata"), result.get("metadataSha256")),
            (build.tree_digest(output / "repo"), result.get("repoSha256")))
  if any(actual != expected for actual, expected in checks):
    raise SystemExit("error: candidate bytes changed after its successful build; rebuild instead of testing mixed outputs")
  return output


def flatpak() -> str:
  command = shutil.which("flatpak")
  if command is None:
    raise SystemExit("error: flatpak is required; enter nix develop or install Flatpak")
  return command


def runtime_command(output: Path, profile: Path) -> list[str]:
  arguments = [flatpak(), "build", "--runtime", "--readonly", "--die-with-parent",
               "--nofilesystem=host", "--nofilesystem=home", f"--filesystem={profile}",
               "--no-talk-name=org.freedesktop.secrets"]
  for key, child in (("XDG_DATA_HOME", "data"), ("XDG_CONFIG_HOME", "config"),
                     ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state")):
    (profile / child).mkdir(mode=0o700)
    arguments.append(f"--env={key}={profile / child}")
  # Xvfb can use abstract X11 sockets; expose only its actual auth file, not home.
  authority = os.environ.get("XAUTHORITY")
  if authority and Path(authority).is_file():
    arguments.extend([f"--filesystem={Path(authority).resolve()}:ro", f"--env=XAUTHORITY={Path(authority).resolve()}"])
  for key in ("GDK_BACKEND", "LIBGL_ALWAYS_SOFTWARE", "WEBKIT_DISABLE_DMABUF_RENDERER"):
    if os.environ.get(key):
      arguments.append(f"--env={key}={os.environ[key]}")
  if os.environ.get("GDK_BACKEND") == "x11":
    arguments.extend(["--nosocket=wayland", "--socket=x11"])
  return [*arguments, str(output / "build"), "/app/bin/tauridium"]


def validate_permissions(path: Path) -> None:
  metadata = configparser.ConfigParser(interpolation=None)
  metadata.optionxform = str
  metadata.read(path, encoding="utf-8")
  application = metadata["Application"]
  if (application.get("name") != APP_ID or application.get("command") != "tauridium"
      or not application.get("runtime", "").startswith("org.gnome.Platform/")
      or not application.get("sdk", "").startswith("org.gnome.Sdk/")):
    raise SystemExit("error: candidate runtime identity is invalid")
  context = {key: set(filter(None, value.split(";"))) for key, value in metadata["Context"].items()}
  expected = {"shared": {"ipc", "network"}, "sockets": {"fallback-x11", "pulseaudio", "wayland"}, "devices": {"dri"}}
  if context != expected or dict(metadata["Session Bus Policy"]) != {
      "org.kde.StatusNotifierWatcher": "talk", "org.freedesktop.secrets": "talk"}:
    raise SystemExit("error: candidate permissions differ from the reviewed least-privilege contract")


def lint(output: Path, environment: dict[str, str], *, online=False) -> None:
  manifest = output / "configuration" / build.MANIFEST
  validate_permissions(output / "build/metadata")
  command = build.builder_command(environment)
  expanded = subprocess.run([*command, "--show-manifest", str(manifest)], env=environment,
                            cwd=build.ROOT, capture_output=True, check=True, timeout=60)
  definition = json.loads(expanded.stdout)
  source = definition["modules"][-1]["sources"][-1]
  if (definition.get("app-id") != APP_ID or source.get("type") != "archive"
      or Path(source.get("path", "")).resolve() != (output / "source.tar").resolve()
      or source.get("sha256") != build.file_digest(output / "source.tar")):
    raise SystemExit("error: candidate manifest does not describe its sealed source")
  subprocess.run([flatpak(), "repo", "--info", str(output / "repo")], env=environment, check=True, timeout=30)
  # These offline checks inspect the candidate's installed metadata, not HEAD or
  # the owner's installed application. No network-only Flathub policy is hidden.
  subprocess.run([flatpak(), "build", "--readonly", "--unshare=network", "--nofilesystem=host",
                  "--nofilesystem=home", str(output / "build"), "sh", "-ec",
                  "appstreamcli validate --no-net /app/share/metainfo/dev.brani.tauridium.metainfo.xml; "
                  "desktop-file-validate /app/share/applications/dev.brani.tauridium.desktop"],
                 env=environment, check=True, timeout=60)
  if online:
    tool = shutil.which("flatpak-builder-lint")
    prefix = [tool] if tool else [flatpak(), "run", "--command=flatpak-builder-lint", "org.flatpak.Builder"]
    for kind, path in (("manifest", manifest), ("appstream", output / "build/files/share/metainfo/dev.brani.tauridium.metainfo.xml"),
                       ("repo", output / "repo")):
      subprocess.run([*prefix, kind, str(path)], env=environment, check=True, timeout=180)


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("action", choices=("test", "run", "lint", "flathub-lint"))
  parser.add_argument("--candidate", default="", help="Successful candidate directory; default is latest successful current-HEAD build")
  args = parser.parse_args()
  environment = tauri_build.build_environment(dict(os.environ))
  output = select(args.candidate)
  print(f"Verified current Flatpak candidate: {output}", flush=True)
  if args.action in ("lint", "flathub-lint"):
    lint(output, environment, online=args.action == "flathub-lint")
  else:
    with tempfile.TemporaryDirectory(prefix="tauridium-flatpak-qa-") as temporary:
      profile = Path(temporary)
      command = runtime_command(output, profile)
      if args.action == "test":
        info_path = profile / "build-info.json"
        subprocess.run([*command, "--build-info-file", str(info_path)], env=environment, check=True, timeout=30)
        info = document(info_path)
        if info.get("buildMode") != "production" or info.get("distribution", {}).get("mode") != "flatpak":
          raise SystemExit("error: candidate is not a production Flatpak executable")
      else:
        subprocess.run(command, env=environment, check=True)
  print("Flatpak candidate validation passed; no application installed or owner profile used", flush=True)
  return 0


if __name__ == "__main__":
  try:
    raise SystemExit(main())
  except (OSError, ValueError, KeyError, configparser.Error, subprocess.SubprocessError):
    raise SystemExit("error: candidate validation failed; inspect private command output; online Flathub checks also require network/ownership verification") from None
