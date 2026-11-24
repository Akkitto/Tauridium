"""Read the application feature graph for source-contract regressions."""
from __future__ import annotations

from pathlib import Path
import re

IMPORT = re.compile(r"(?:^|(?<=;))\s*import\s+[^;]*?\bfrom\s*[\"']([^\"']+)[\"']", re.MULTILINE)


def frontend_sources(repository: Path) -> dict[str, str]:
  """Follow only application-owned views, rune controllers and shared UI types."""
  root = repository.resolve()
  source_root = (root / "src").resolve()
  result: dict[str, str] = {}

  def allowed(path: Path) -> bool:
    try:
      relative = path.relative_to(source_root)
    except ValueError:
      return False
    return (
      bool(relative.parts) and (
      relative.as_posix() in {"App.svelte", "lib/navigation", "lib/navigation.ts", "lib/appSettingsDefaults", "lib/appSettingsDefaults.ts"}
      or relative.parts[0] == "components" and path.suffix == ".svelte"
      or relative.parts[:2] == ("lib", "controllers") and path.name.endswith((".svelte", ".svelte.ts"))
      )
    )

  def visit(path: Path) -> None:
    path = path.resolve()
    if not allowed(path):
      return
    if not path.is_file() and (path.name.endswith(".svelte") or not path.suffix):
      path = Path(str(path) + ".ts").resolve()
    if not allowed(path):
      return
    key = path.relative_to(root).as_posix()
    if key in result:
      return
    text = path.read_text(encoding="utf-8")
    result[key] = text
    for match in IMPORT.finditer(text):
      if match[1].startswith("."):
        visit(path.parent / match[1])

  visit(source_root / "App.svelte")
  return result


def read_frontend_source(repository: Path) -> str:
  """Keep historic cross-feature assertions attached to reachable source, not filenames."""
  return "\n".join(frontend_sources(repository).values())


def read_frontend_file(repository: Path, relative: str) -> str:
  """Select a specific feature owner, requiring it to be reachable from App."""
  return frontend_sources(repository)[relative]
