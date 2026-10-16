"""Explicit reviewed runtime metadata contract, shared by producer and consumers."""
from __future__ import annotations

import configparser
from pathlib import Path

APP_ID = "dev.brani.tauridium"
RUNTIME_BRANCH = "51"
DEBUG_EXTENSION = f"Extension {APP_ID}.Debug"


def validate_permissions(path: Path) -> None:
  failure = "error: candidate permissions differ from the reviewed least-privilege contract"
  if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024:
    raise SystemExit(failure)
  metadata = configparser.ConfigParser(interpolation=None, empty_lines_in_values=False)
  metadata.optionxform = str
  try:
    with path.open(encoding="utf-8") as stream:
      metadata.read_file(stream)
  except (OSError, UnicodeError, configparser.Error):
    raise SystemExit(failure) from None
  required = {"Application", "Context", "Session Bus Policy"}
  optional = {"System Bus Policy", "Environment", DEBUG_EXTENSION, "Build"}
  sections = set(metadata.sections())
  if metadata.defaults() or required - sections or sections - required - optional:
    raise SystemExit(failure)
  application = dict(metadata["Application"])
  if (set(application) != {"name", "runtime", "sdk", "command"}
      or application["name"] != APP_ID or application["command"] != "tauridium"):
    raise SystemExit(failure)
  runtime, sdk = application["runtime"].split("/"), application["sdk"].split("/")
  if (len(runtime) != 3 or len(sdk) != 3 or runtime[0] != "org.gnome.Platform"
      or sdk[0] != "org.gnome.Sdk" or runtime[1:] != sdk[1:]
      or runtime[1] not in {"x86_64", "aarch64"} or runtime[2] != RUNTIME_BRANCH):
    raise SystemExit(failure)
  context = {key: set(filter(None, value.split(";"))) for key, value in metadata["Context"].items()}
  if context != {"shared": {"ipc", "network"}, "sockets": {"fallback-x11", "pulseaudio", "wayland"},
                 "devices": {"dri"}}:
    raise SystemExit(failure)
  if dict(metadata["Session Bus Policy"]) != {"org.kde.StatusNotifierWatcher": "talk", "org.freedesktop.secrets": "talk"}:
    raise SystemExit(failure)
  # These groups grant access/set runtime state even without a Context change.
  if any(section in metadata and dict(metadata[section]) for section in ("System Bus Policy", "Environment")):
    raise SystemExit(failure)
  if DEBUG_EXTENSION in metadata and dict(metadata[DEBUG_EXTENSION]) != {
      "directory": "lib/debug", "autodelete": "true", "no-autodownload": "true"}:
    raise SystemExit(failure)
  if "Build" in metadata and dict(metadata["Build"]) != {"built-extensions": f"{APP_ID}.Debug;"}:
    raise SystemExit(failure)
