"""Exact source identity for the frame-aware window-state repair."""
import hashlib
import json
from pathlib import Path
import tomllib

NAME = "tauri-plugin-window-state"
VERSION = "2.5.0+tauridium.1"
UPSTREAM_SHA256 = "5d6815cab7b212f9cfe16a9d79d8d22f9e14159e4a9460f7dec1467167a008e3"
RELATIVE = "vendor/tauri-plugin-window-state"


def validate(root: Path) -> dict:
  manifest = tomllib.loads((root / "src-tauri/Cargo.toml").read_text(encoding="utf-8"))
  if (manifest["dependencies"].get(NAME) != "=2.5.0"
      or manifest.get("patch", {}).get("crates-io", {}).get(NAME) != {"path": "../" + RELATIVE}):
    raise ValueError("Window-state repair must use the exact reviewed local source")
  lock = tomllib.loads((root / "src-tauri/Cargo.lock").read_text(encoding="utf-8"))
  entries = [entry for entry in lock["package"] if entry["name"] == NAME]
  if len(entries) != 1 or entries[0]["version"] != VERSION or any(key in entries[0] for key in ("source", "checksum")):
    raise ValueError("Window-state repair has an unexpected lock identity")
  directory = root / RELATIVE
  if any(path.is_symlink() for path in (directory, directory.parent)):
    raise ValueError("Window-state repair must not use linked source directories")
  provenance = directory / "TAURIDIUM-PATCH.json"
  if provenance.is_symlink():
    raise ValueError("Window-state provenance must not be linked")
  patch = json.loads(provenance.read_text(encoding="utf-8"))
  if patch.get("upstream") != {
      "version": "2.5.0",
      "url": "https://crates.io/api/v1/crates/tauri-plugin-window-state/2.5.0/download",
      "sha256": UPSTREAM_SHA256,
  }:
    raise ValueError("Window-state repair must retain its exact upstream provenance")
  if set(patch.get("files", {})) != {"Cargo.toml", "src/lib.rs"}:
    raise ValueError("Window-state repair source hash inventory differs")
  for name, expected in patch["files"].items():
    path = directory / name
    if path.is_symlink() or path.parent.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
      raise ValueError("Window-state repair source integrity check failed: " + name)
  package = tomllib.loads((directory / "Cargo.toml").read_text(encoding="utf-8"))["package"]
  if package["name"] != NAME or package["version"] != VERSION:
    raise ValueError("Window-state repair package metadata differs")
  return patch
