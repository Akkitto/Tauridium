#!/usr/bin/env python3
"""Reject non-English project prose before a Tauridium release."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "node_modules", "target", "dist", "release", "__pycache__"}
BINARY_SUFFIXES = {".png", ".ico", ".icns", ".zip", ".exe", ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf"}

# Hex encoding keeps the checker itself English-only while still matching legacy text.
_HIGH_CONFIDENCE_HEX = (
  '696e74726f757661626c65',
  '696c6c697369626c65',
  '696e6a6f69676e61626c65',
  '7265636f6e6e6578696f6e',
  '7265676c616765',
  '7265676c61676573',
  '72656365747465',
  '7265636574746573',
  '73657276657572',
  '66656e65747265',
  '6e617669676174657572',
  '74656c656368617267656d656e74',
  '74656c656368617267656d656e7473',
  '7072656368617267656d656e74',
  '6465636f6e6e6578696f6e',
  '6964656e74696669616e74',
  '64656d617272616765',
  '6368617267656d656e74',
  '646f7373696572',
  '6563726974757265',
  '7375707072696d65',
  '7375707072696d6572',
  '7265706f736974696f6e6e65',
  '7265737461757265',
  '726574656e7465',
  '62617363756c65',
  '6d6173717565',
  '61666669636865',
  '656e7265676973747265',
  '646573616374697665',
  '68696265726e65',
  '66616e746f6d65',
  '636f72726f6d7075',
  '746972657473',
  '6f6374657473',
  '6175746f7269736174696f6e',
  '6c616e63656d656e74',
  '726561666669636865',
  '73656c656374696f6e6e65',
  '696e76616c696465',
  '66696e616c69736174696f6e',
  '70726f66696c',
  '7265706572746f697265',
  '646570656e64616e6365',
  '646570656e64616e636573',
  '7075626c6965',
  '7075626c696572',
  '706c617465666f726d65'
)
_STOPWORD_HEX = (
  '6c6573',
  '646573',
  '756e65',
  '6475',
  '64616e73',
  '706f7572',
  '61766563',
  '646570756973',
  '6c6f7273717565',
  '73696e6f6e',
  '617563756e',
  '617563756e65',
  '746f756a6f757273',
  '6a616d616973',
  '636861717565',
  '70756973',
  '616c6f7273',
  '61696e7369',
  '61696c6c65757273',
  '6a75737175'
)
HIGH_CONFIDENCE = {bytes.fromhex(item).decode("ascii") for item in _HIGH_CONFIDENCE_HEX}
STOPWORDS = {bytes.fromhex(item).decode("ascii") for item in _STOPWORD_HEX}
WORD_RE = re.compile(r"[A-Za-z\u00c0-\u024f]+")
# Accents strongly associated with the legacy prose being removed from Tauridium.
LEGACY_ACCENTS = set("\u00e0\u00e2\u00e7\u00e9\u00e8\u00ea\u00eb\u00ee\u00ef\u00f4\u00fb\u00f9\u00fc\u00ff\u0153\u00e6\u00c0\u00c2\u00c7\u00c9\u00c8\u00ca\u00cb\u00ce\u00cf\u00d4\u00db\u00d9\u00dc\u0178\u0152\u00c6")


def tracked_files(root: Path = ROOT) -> list[Path]:
  git = subprocess.run(
    ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=False
  )
  if git.returncode == 0:
    return [root / item.decode("utf-8") for item in git.stdout.split(b"\0") if item]
  files: list[Path] = []
  for path in root.rglob("*"):
    if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
      continue
    files.append(path)
  return files


def scan_text(text: str) -> list[str]:
  issues: list[str] = []
  if any(char in LEGACY_ACCENTS for char in text):
    issues.append("legacy accented prose")
  words = [word.lower() for word in WORD_RE.findall(text)]
  found = sorted(set(words).intersection(HIGH_CONFIDENCE))
  if found:
    issues.append("legacy language lexeme")
  stop_count = sum(word in STOPWORDS for word in words)
  if stop_count >= 2:
    issues.append("legacy language stop-word pattern")
  return issues


def scan_file(path: Path) -> list[tuple[int, str]]:
  if path.suffix.lower() in BINARY_SUFFIXES:
    return []
  try:
    raw = path.read_bytes()
  except OSError:
    return []
  if b"\0" in raw:
    return []
  try:
    text = raw.decode("utf-8")
  except UnicodeDecodeError:
    return []
  results: list[tuple[int, str]] = []
  for line_number, line in enumerate(text.splitlines(), 1):
    issues = scan_text(line)
    if issues:
      results.append((line_number, ", ".join(issues)))
  return results


def main() -> int:
  failures: list[str] = []
  for path in tracked_files():
    for line_number, issue in scan_file(path):
      failures.append(f"{path.relative_to(ROOT)}:{line_number}: {issue}")
  if failures:
    print("error: current tracked project tree contains non-English legacy prose:")
    for failure in failures:
      print(f"  {failure}")
    return 1
  print("Tauridium tracked project tree is English-only.")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
