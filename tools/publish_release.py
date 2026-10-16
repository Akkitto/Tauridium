"""Minimal protected publisher: hash-only validation, draft upload, exact remote verification."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.append(str(Path(__file__).resolve().parent))
import release_policy as policy
import release_snapshot


def gh(*arguments: str) -> str:
  result = subprocess.run(["gh", *arguments], check=False, capture_output=True, text=True, timeout=600)
  if result.returncode:
    raise SystemExit("error: GitHub publication operation failed; any uploaded draft remains private for owner review")
  return result.stdout


def api(path: str) -> dict:
  return json.loads(gh("api", path))


def remote_release(repository: str, tag: str) -> dict:
  release = api(f"repos/{repository}/releases/tags/{tag}")
  pages = json.loads(gh("api", "--paginate", "--slurp",
                        f"repos/{repository}/releases/{release['id']}/assets?per_page=100"))
  release["assets"] = [asset for page in pages for asset in page]
  return release


def verify_remote_assets(release: dict, snapshot: dict) -> None:
  expected = {row["name"]: row for row in snapshot["files"] if row["name"] != "release-notes.md"}
  assets = release["assets"]
  if len(assets) != len(expected) or {asset["name"] for asset in assets} != set(expected):
    raise SystemExit("error: uploaded draft has a missing/duplicate/unexpected asset; refusing publication")
  for asset in assets:
    record = expected[asset["name"]]
    if asset.get("state") != "uploaded" or asset["size"] != record["bytes"] or asset.get("digest") != "sha256:" + record["sha256"]:
      raise SystemExit("error: remote asset size/digest differs from verified bytes; draft retained for owner review")


def publish(directory: Path, release_version: str, commit: str, expected: str, repository: str) -> None:
  if repository != "Akkitto/Tauridium":
    raise SystemExit("error: publisher is restricted to the reviewed upstream repository")
  snapshot = release_snapshot.verify(directory, release_version, commit, "final", expected)
  tag = "v" + release_version
  remote = api(f"repos/{repository}/git/ref/tags/{tag}")["object"]
  for _ in range(8):
    if remote["type"] != "tag":
      break
    remote = api(f"repos/{repository}/git/tags/{remote['sha']}")["object"]
  if remote.get("type") != "commit" or remote.get("sha") != commit:
    raise SystemExit("error: remote release tag does not resolve to the verified release commit")
  pages = json.loads(gh("api", "--paginate", "--slurp", f"repos/{repository}/releases?per_page=100"))
  if any(release["tag_name"] == tag for page in pages for release in page):
    raise SystemExit("error: a release/draft already exists; refusing to overwrite or replace any assets")
  files = [str(directory / name) for name in sorted(policy.public_names(release_version))]
  gh("release", "create", tag, *files, "--repo", repository, "--verify-tag", "--draft",
     "--title", f"Tauridium {release_version}", "--notes-file", str(directory / "release-notes.md"))
  staged = remote_release(repository, tag)
  if not staged["draft"] or staged["tag_name"] != tag:
    raise SystemExit("error: expected a private draft before promotion")
  verify_remote_assets(staged, snapshot)
  gh("release", "edit", tag, "--repo", repository, "--draft=false", "--latest")
  final = remote_release(repository, tag)
  verify_remote_assets(final, snapshot)
  if final["draft"]:
    raise SystemExit("error: draft promotion did not complete")
  print(f"Published verified Tauridium {release_version}; {len(files)} exact assets")


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("assets", type=Path)
  parser.add_argument("--commit", required=True)
  parser.add_argument("--input-sha256", required=True)
  args = parser.parse_args()
  version = json.loads((Path(__file__).resolve().parents[1] / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))["version"]
  try:
    publish(args.assets, version, args.commit, args.input_sha256, os.environ.get("GITHUB_REPOSITORY", ""))
  except (OSError, ValueError, KeyError, subprocess.SubprocessError):
    raise SystemExit("error: publisher could not complete; no automatic deletion/overwrite is attempted") from None
