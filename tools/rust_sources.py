"""Source-contract scope for the entrypoint and its extracted orchestration domains.

Historical contract checks cover code that used to live together in main.rs. Keep
that scope explicit while allowing Rust to organize it into modules. Runtime and
Rust unit tests remain responsible for behavior; this helper only reads source.
"""
from pathlib import Path


def read_orchestration_sources(root: Path) -> str:
    rust = root / "src-tauri" / "src"
    paths = [rust / "main.rs"]
    for domain in ("app_settings", "services"):
        paths.extend(sorted((rust / domain).rglob("*.rs")))
    return "\n\n".join(path.read_text(encoding="utf-8") for path in paths)
