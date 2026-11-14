"""Verify a trusted, locally built system-package executable without opening a GUI."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def validate(info: dict, version: str, target: str) -> None:
  if info.get("version") != version or info.get("target") != target or info.get("buildMode") != "production":
    raise ValueError("system package build identity/production mode differs")
  policy = info.get("distribution", {})
  if policy.get("mode") != "system-package" or policy.get("updaterManagedExternally") is not True:
    raise ValueError("system package must disable the native updater")
  for flag in ("portalFileAccess", "portalNotifications", "portalAutostart", "downloadsRequireDestination", "automaticBackupsUsePrivateStorage"):
    if policy.get(flag) is not False:
      raise ValueError("system package must preserve ordinary desktop capabilities")


def inspect(binary: Path, version: str, target: str) -> dict:
  # Call only an explicitly supplied trusted local build, never downloaded content.
  with tempfile.TemporaryDirectory(prefix="tauridium-build-info-") as temporary:
    output = Path(temporary) / "build-info.json"
    subprocess.run([str(binary.resolve(strict=True)), "--build-info-file", str(output)], check=True, timeout=30)
    info = json.loads(output.read_text(encoding="utf-8"))
  validate(info, version, target)
  return info


if __name__ == "__main__":
  inspect(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
  print("Production system-package identity and desktop policy verified.")
