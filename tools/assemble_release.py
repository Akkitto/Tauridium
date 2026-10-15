"""Assemble only the exact same-run unsigned target sets, without merged downloads."""
import argparse
import os
from pathlib import Path
import shutil
import tempfile

from package_release import version
import release_policy as policy


def assemble(staging: Path, output: Path, release_version: str) -> None:
  if output.exists() or output.is_symlink():
    raise SystemExit("error: release assembly requires a fresh output directory")
  expected_directories = {"release-handoff"} | {"native-" + target for target in policy.TARGETS}
  if {path.name for path in staging.iterdir()} != expected_directories:
    raise SystemExit("error: same-run staging contains unexpected/missing workflow artifacts")
  inputs = []
  for name in sorted(expected_directories):
    expected = (policy.handoff_names(release_version) | {"release-notes.md"}
                if name == "release-handoff" else policy.target_names(release_version, name[len("native-"):]))
    inputs.extend(policy.validate_directory(staging / name, expected))
  output.parent.mkdir(parents=True, exist_ok=True)
  with tempfile.TemporaryDirectory(prefix=".tauridium-assembly-", dir=output.parent) as temporary:
    staged = Path(temporary)
    for source in inputs:
      if (staged / source.name).exists():
        raise SystemExit("error: duplicate public artifact across target downloads")
      shutil.copyfile(source, staged / source.name)
    policy.validate_directory(staged, policy.public_names(release_version, signed=False, metadata=False),
                              internal={"release-notes.md"})
    os.rename(staged, output)


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("staging", type=Path)
  parser.add_argument("output", type=Path)
  args = parser.parse_args()
  assemble(args.staging, args.output, version())
