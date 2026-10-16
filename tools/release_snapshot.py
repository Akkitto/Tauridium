"""Small hash-only custody boundary: bind exact files to a trusted job-output digest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

sys.path.append(str(Path(__file__).resolve().parent))
import release_policy as policy

TRANSFER = "TRANSFER.json"


def names(version: str, stage: str) -> set[str]:
  if stage not in ("unsigned", "signed", "final"):
    raise SystemExit("error: unknown release custody stage")
  return policy.public_names(version, signed=stage != "unsigned", metadata=stage == "final") | {"release-notes.md"}


def document(directory: Path, version: str, commit: str, stage: str) -> dict:
  if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) or not re.fullmatch(r"[a-f0-9]{40}", commit):
    raise SystemExit("error: custody requires an immutable version/commit")
  files = policy.validate_directory(directory, names(version, stage), internal={TRANSFER}, inspect=False)
  return {"schema": 1, "version": version, "commit": commit, "stage": stage,
          "files": [{"name": path.name, "bytes": path.stat().st_size, "sha256": policy.digest(path)} for path in files]}


def seal(directory: Path, version: str, commit: str, stage: str) -> str:
  output = directory / TRANSFER
  if output.exists() or output.is_symlink():
    raise SystemExit("error: custody seals are immutable; refuse to replace an existing seal")
  result = document(directory, version, commit, stage)
  with output.open("x", encoding="utf-8") as stream:
    stream.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
  return policy.digest(output)


def verify(directory: Path, version: str, commit: str, stage: str, expected: str) -> dict:
  manifest = directory / TRANSFER
  policy.regular(manifest)
  if (not re.fullmatch(r"[a-f0-9]{64}", expected) or manifest.stat().st_size > 64 * 1024
      or policy.digest(manifest) != expected):
    raise SystemExit("error: custody seal differs from the trusted preceding job output")
  supplied = json.loads(manifest.read_text(encoding="utf-8"))
  actual = document(directory, version, commit, stage)
  if supplied != actual:
    raise SystemExit("error: artifact names, bytes or release identity changed across the custody boundary")
  return actual


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("command", choices=("seal", "verify"))
  parser.add_argument("assets", type=Path)
  parser.add_argument("--stage", choices=("unsigned", "signed", "final"), required=True)
  parser.add_argument("--commit", required=True)
  parser.add_argument("--expected")
  args = parser.parse_args()
  version = json.loads((Path(__file__).resolve().parents[1] / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))["version"]
  if args.command == "seal":
    print(seal(args.assets, version, args.commit, args.stage))
  else:
    verify(args.assets, version, args.commit, args.stage, args.expected or "")
