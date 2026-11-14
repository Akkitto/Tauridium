"""Make namcap errors fatal; namcap itself can return success for error findings."""
from pathlib import Path
import subprocess


def check(paths: list[str], cwd: Path | None = None) -> None:
  result = subprocess.run(["namcap", *paths], cwd=cwd, capture_output=True, text=True, check=True)
  print(result.stdout, end="")
  print(result.stderr, end="")
  if any(" E: " in line for line in (result.stdout + result.stderr).splitlines()):
    raise RuntimeError("namcap reported packaging errors")


if __name__ == "__main__":
  import sys
  check(sys.argv[1:])
