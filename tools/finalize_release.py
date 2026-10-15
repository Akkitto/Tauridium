"""Generate/recheck a complete immutable public snapshot; print only its exact file list."""
import argparse
import json
from pathlib import Path
import tempfile

import build_input_sbom
from package_release import git_output, version
import release_assets
import release_policy as policy
import scoop


def finalize(directory: Path) -> None:
  release_version = version()
  policy.validate_directory(directory, policy.public_names(release_version, metadata=False),
                            internal={"release-notes.md"})
  release_assets.generate_updater_manifest(directory, directory / "latest.json", True)
  scoop.generate_release_manifest(directory, directory / f"tauridium-{release_version}-scoop.json")
  document = build_input_sbom.generate(build_input_sbom.ROOT, release_version, git_output("rev-parse", "HEAD"))
  (directory / f"tauridium-{release_version}-build-inputs.cdx.json").write_text(
      json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
  policy.write_inventory(directory, release_version, git_output("rev-parse", "HEAD"))
  release_assets.write_checksums(directory, directory / "SHA256SUMS")
  verify(directory)


def verify(directory: Path) -> list[Path]:
  release_version = version()
  files = policy.validate_directory(directory, policy.public_names(release_version),
                                    internal={"release-notes.md"})
  manifest = json.loads((directory / "ARTIFACTS.json").read_text(encoding="utf-8"))
  if (manifest.get("schema") != 1 or manifest.get("version") != release_version
      or manifest.get("commit") != git_output("rev-parse", "HEAD")):
    raise SystemExit("error: public inventory is not bound to this release commit/version")
  records = manifest.get("files", [])
  expected = {path.name for path in files} - {"ARTIFACTS.json", "SHA256SUMS"}
  if len(records) != len(expected) or {record["name"] for record in records} != expected:
    raise SystemExit("error: artifact inventory does not cover exactly the published payloads")
  for record in records:
    path = directory / record["name"]
    if record["bytes"] != path.stat().st_size or record["sha256"] != policy.digest(path):
      raise SystemExit("error: staged public payload changed after inventory creation")
  checksum_lines = (directory / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
  expected_lines = [f"{policy.digest(path)}  {path.name}" for path in files if path.name != "SHA256SUMS"]
  if checksum_lines != sorted(expected_lines, key=lambda value: value.split("  ", 1)[1]):
    raise SystemExit("error: checksums differ from the exact published snapshot")
  with tempfile.TemporaryDirectory(prefix="tauridium-public-metadata-") as temporary:
    expected_updater = release_assets.generate_updater_manifest(directory, Path(temporary) / "latest.json", True)
    if json.loads((directory / "latest.json").read_text(encoding="utf-8")) != expected_updater:
      raise SystemExit("error: updater metadata differs from the verified canonical artifact signatures")
  scoop.validate_release_manifest(directory / f"tauridium-{release_version}-scoop.json", directory)
  return files


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("command", choices=("generate", "verify", "list"))
  parser.add_argument("assets", type=Path)
  args = parser.parse_args()
  if args.command == "generate":
    finalize(args.assets)
  else:
    paths = verify(args.assets)
    if args.command == "list":
      print("\n".join(str(path) for path in paths))
