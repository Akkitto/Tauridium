#!/usr/bin/env python3
"""Bootstrap Tauridium development dependencies reproducibly.

`just init` delegates here so a fresh checkout can prepare its JavaScript
dependencies and, on supported Linux distributions, install the native Tauri
development packages that Cargo discovers through pkg-config.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
OS_RELEASE = Path("/etc/os-release")
SYSTEM_DEPS_ENV = "TAURIDIUM_INIT_SYSTEM_DEPS"
INIT_VERSION = "0.4.4"

# Modules that Tauridium's Linux Tauri/WebKitGTK dependency graph needs at build
# time. Checking modules instead of package names keeps init idempotent across
# distro package naming differences.
LINUX_PKG_CONFIG_MODULES = (
  "atk",
  "cairo",
  "gdk-3.0",
  "gdk-pixbuf-2.0",
  "gtk+-3.0",
  "javascriptcoregtk-4.1",
  "librsvg-2.0",
  "libsoup-3.0",
  "openssl",
  "pango",
  "webkit2gtk-4.1",
)
LINUX_PKG_CONFIG_ALTERNATIVES = (
  ("ayatana-appindicator3-0.1", "appindicator3-0.1"),
)
LINUX_REQUIRED_TOOLS = (
  "cc",
  "curl",
  "file",
  "make",
  "wget",
)
APT_NETWORK_OPTIONS = (
  "-o",
  "Acquire::Retries=3",
  "-o",
  "Acquire::http::Timeout=20",
  "-o",
  "Acquire::https::Timeout=20",
)

# Tauri v2 Linux prerequisites, with pkg-config/pkgconf made explicit because
# the Rust -sys crates use it to locate the native libraries.
APT_PACKAGES = (
  "pkg-config",
  "libwebkit2gtk-4.1-dev",
  "build-essential",
  "curl",
  "wget",
  "file",
  "libxdo-dev",
  "libssl-dev",
  "libayatana-appindicator3-dev",
  "librsvg2-dev",
)
DNF_PACKAGES = (
  "pkgconf-pkg-config",
  "webkit2gtk4.1-devel",
  "openssl-devel",
  "curl",
  "wget",
  "file",
  "libappindicator-gtk3-devel",
  "librsvg2-devel",
  "libxdo-devel",
)
PACMAN_PACKAGES = (
  "pkgconf",
  "webkit2gtk-4.1",
  "base-devel",
  "curl",
  "wget",
  "file",
  "openssl",
  "appmenu-gtk-module",
  "libappindicator-gtk3",
  "librsvg",
  "xdotool",
)
APK_PACKAGES = (
  "pkgconf",
  "build-base",
  "webkit2gtk-4.1-dev",
  "curl",
  "wget",
  "file",
  "openssl",
  "libayatana-appindicator-dev",
  "librsvg",
)
ZYPPER_PACKAGES = (
  "pkg-config",
  "webkit2gtk3-devel",
  "libopenssl-devel",
  "curl",
  "wget",
  "file",
  "libappindicator3-1",
  "librsvg-devel",
)


class InitError(RuntimeError):
  """Expected bootstrap failure with an actionable user-facing message."""


def parse_os_release(text: str) -> dict[str, str]:
  """Parse the small KEY=VALUE format used by /etc/os-release."""
  values: dict[str, str] = {}
  for raw_line in text.splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
      continue
    key, value = line.split("=", 1)
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
      value = value[1:-1]
    values[key] = value
  return values


def os_release() -> dict[str, str]:
  if not OS_RELEASE.is_file():
    return {}
  return parse_os_release(OS_RELEASE.read_text(encoding="utf-8"))


def distro_tokens(release: dict[str, str]) -> set[str]:
  """Return normalized distro-family tokens used for package-manager choice."""
  tokens = {release.get("ID", "").lower()}
  tokens.update(part.lower() for part in release.get("ID_LIKE", "").split())
  return {token for token in tokens if token}


def privilege_prefix() -> list[str]:
  """Use sudo for system package installation only when not already root."""
  geteuid = getattr(os, "geteuid", None)
  if callable(geteuid) and geteuid() == 0:
    return []
  if shutil.which("sudo"):
    return ["sudo"]
  raise InitError(
    "native Linux prerequisites are missing and root privileges are required; "
    "install sudo or run `just init` from an account that can install system packages"
  )


def package_manager_commands(
  release: dict[str, str],
  *,
  root: bool,
  available: set[str] | None = None,
) -> list[list[str]]:
  """Return idempotent package installation commands for a supported distro."""
  if available is None:
    available = {
      name
      for name in ("apt-get", "dnf", "pacman", "apk", "zypper")
      if shutil.which(name)
    }
  prefix = [] if root else ["sudo"]
  tokens = distro_tokens(release)

  if "apt-get" in available and tokens & {"debian", "ubuntu", "linuxmint", "pop"}:
    return [
      [*prefix, "apt-get", *APT_NETWORK_OPTIONS, "update"],
      [*prefix, "apt-get", *APT_NETWORK_OPTIONS, "install", "-y", *APT_PACKAGES],
    ]

  if "dnf" in available and tokens & {"fedora", "rhel", "centos"}:
    return [
      [*prefix, "dnf", "install", "-y", *DNF_PACKAGES],
      [*prefix, "dnf", "group", "install", "-y", "c-development"],
    ]

  if "pacman" in available and tokens & {"arch", "manjaro"}:
    return [
      [*prefix, "pacman", "-Syu", "--needed", "--noconfirm", *PACMAN_PACKAGES],
    ]

  if "apk" in available and "alpine" in tokens:
    return [
      [*prefix, "apk", "add", "--no-cache", *APK_PACKAGES],
    ]

  if "zypper" in available and tokens & {"opensuse", "suse"}:
    return [
      [*prefix, "zypper", "--non-interactive", "refresh"],
      [*prefix, "zypper", "--non-interactive", "install", *ZYPPER_PACKAGES],
      [*prefix, "zypper", "--non-interactive", "install", "-t", "pattern", "devel_basis"],
    ]

  distro = release.get("PRETTY_NAME") or release.get("ID") or "unknown Linux distribution"
  raise InitError(
    f"automatic native dependency installation is not supported on {distro}; "
    "install the Tauri v2 Linux prerequisites for this distribution, then rerun `just init`"
  )


def pkg_config_exists(module: str) -> bool:
  """Return whether one pkg-config module is discoverable."""
  if not shutil.which("pkg-config"):
    return False
  result = subprocess.run(
    ["pkg-config", "--exists", module],
    cwd=ROOT,
    check=False,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
  )
  return result.returncode == 0


def pkg_config_missing(modules: Sequence[str] = LINUX_PKG_CONFIG_MODULES) -> list[str]:
  """Return exact missing pkg-config modules."""
  if not shutil.which("pkg-config"):
    return list(modules)
  return [module for module in modules if not pkg_config_exists(module)]


def libxdo_development_available() -> bool:
  """Probe libxdo by compiling/linking instead of assuming an xdo.pc file.

  Debian's libxdo-dev intentionally ships xdo.h and libxdo.so without pkg-config
  metadata, so `pkg-config --exists xdo` is a false negative there. A tiny
  compile/link probe validates exactly what Tauridium needs from the development
  package and works across distributions regardless of pkg-config packaging.
  """
  compiler = shutil.which("cc")
  if not compiler:
    return False

  source = (
    "#include <stddef.h>\n"
    "#include <xdo.h>\n"
    "int main(void) { xdo_t *x = xdo_new(NULL); return x == NULL; }\n"
  )
  with tempfile.TemporaryDirectory(prefix="tauridium-xdo-") as directory:
    output = Path(directory) / "xdo-probe"
    result = subprocess.run(
      [compiler, "-x", "c", "-", "-lxdo", "-o", str(output)],
      cwd=ROOT,
      input=source,
      text=True,
      check=False,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
    )
  return result.returncode == 0


def native_prerequisites_missing() -> list[str]:
  """Return all missing native module/tool requirements in readable form."""
  missing = pkg_config_missing()
  for alternatives in LINUX_PKG_CONFIG_ALTERNATIVES:
    if not any(pkg_config_exists(module) for module in alternatives):
      missing.append("|".join(alternatives))
  for tool in LINUX_REQUIRED_TOOLS:
    if not shutil.which(tool):
      missing.append(f"tool:{tool}")
  if shutil.which("cc") and not libxdo_development_available():
    missing.append("libxdo-dev")
  return missing


def run_checked(command: Sequence[str]) -> None:
  printable = " ".join(command)
  print(f"+ {printable}", flush=True)
  subprocess.run(list(command), cwd=ROOT, check=True)


def install_linux_system_dependencies() -> None:
  """Install native dependencies only when their validated requirements are absent."""
  if platform.system() != "Linux":
    return

  if os.environ.get(SYSTEM_DEPS_ENV, "1").strip().lower() in {"0", "false", "no", "off"}:
    missing = native_prerequisites_missing()
    if missing:
      raise InitError(
        f"{SYSTEM_DEPS_ENV}=0 but required native prerequisites are missing: "
        + ", ".join(missing)
      )
    return

  missing = native_prerequisites_missing()
  if not missing:
    print("Native Tauri prerequisites: already satisfied.", flush=True)
    return

  print(
    "Native Tauri prerequisites missing: " + ", ".join(missing),
    flush=True,
  )
  release = os_release()
  geteuid = getattr(os, "geteuid", None)
  root = bool(callable(geteuid) and geteuid() == 0)
  if not root:
    # Fail early with a specific message when escalation is impossible.
    privilege_prefix()

  for command in package_manager_commands(release, root=root):
    run_checked(command)

  remaining = native_prerequisites_missing()
  if remaining:
    raise InitError(
      "system package installation completed but required native prerequisites are still missing: "
      + ", ".join(remaining)
    )
  print("Native Tauri prerequisites: installed.", flush=True)


def validate_release_identity() -> None:
  """Fail before system changes when release files were mixed or extracted stale.

  This makes an overlay/stale extraction obvious before `apt`, npm, or any other
  mutating command is executed.
  """
  package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
  actual = package.get("version")
  if actual != INIT_VERSION:
    raise InitError(
      f"initializer version {INIT_VERSION} does not match package.json version {actual!r}; "
      "extract the release into a new empty directory instead of overlaying releases"
    )


def validate_npm_policy() -> None:
  """Require the exact reviewed install-script approval committed for this release."""
  package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
  allow_scripts = package.get("allowScripts")
  if allow_scripts != {"esbuild@0.25.12": True}:
    raise InitError(
      "package.json must approve exactly the reviewed esbuild@0.25.12 install script"
    )


def command_succeeds(command: Sequence[str]) -> bool:
  """Run a capability probe without turning an expected miss into an init failure."""
  result = subprocess.run(
    list(command),
    cwd=ROOT,
    check=False,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
  )
  return result.returncode == 0


def ensure_pinned_rust_toolchain() -> None:
  """Install the repository-pinned Rust toolchain and formatting/lint components."""
  if not shutil.which("rustup"):
    raise InitError(
      "rustup is required to enforce Tauridium's pinned Rust 1.97.1 toolchain; "
      "install rustup, then rerun `just init`"
    )
  run_checked([
    "rustup",
    "toolchain",
    "install",
    "1.97.1",
    "--profile",
    "minimal",
    "--component",
    "rustfmt",
    "--component",
    "clippy",
  ])
  if not command_succeeds(["cargo", "fmt", "--version"]):
    raise InitError("the pinned Rust 1.97.1 rustfmt component is unavailable after installation")
  print("+ Rust toolchain: pinned 1.97.1 with rustfmt and clippy", flush=True)


def ensure_tauri_cli() -> None:
  """Ensure the Cargo-installed Tauri v2 CLI is available on Unix hosts."""
  if not shutil.which("cargo"):
    raise InitError(
      "Rust/Cargo is required but cargo was not found in PATH; install the stable Rust "
      "toolchain, then rerun `just init`"
    )

  probe = ["cargo", "tauri", "--version"]
  if command_succeeds(probe):
    print("+ Tauri CLI: available", flush=True)
    return

  run_checked(["cargo", "install", "tauri-cli", "--locked", "--version", "^2"])
  if not command_succeeds(probe):
    raise InitError(
      "cargo install tauri-cli completed but `cargo tauri` is still unavailable; "
      "ensure Cargo's bin directory is present in PATH"
    )
  print("+ Tauri CLI: installed", flush=True)


def install_javascript_dependencies() -> None:
  if not shutil.which("node"):
    raise InitError("Node.js is required but was not found in PATH")
  if not shutil.which("npm"):
    raise InitError("npm is required but was not found in PATH")

  validate_npm_policy()
  run_checked(["npm", "ci"])
  run_checked(["npm", "audit", "--audit-level=high"])

  # Verify the approved dependency is actually runnable. esbuild's install
  # script may replace its JavaScript shim with a platform-native executable,
  # so invoking node on node_modules/esbuild/bin/esbuild is incorrect (ELF on
  # Linux, PE on Windows). npm exec resolves and launches the local package bin
  # using the platform-appropriate mechanism. --offline prevents registry
  # fallback and therefore also verifies that npm ci installed it locally.
  run_checked(["npm", "exec", "--offline", "--", "esbuild", "--version"])


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Initialize Tauridium development prerequisites")
  parser.add_argument(
    "--native-only",
    action="store_true",
    help="validate/install only native prerequisites; skip npm setup",
  )
  return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
  args = parse_args(argv)
  try:
    validate_release_identity()
    print(f"Tauridium initializer {INIT_VERSION}.", flush=True)
    install_linux_system_dependencies()
    if not args.native_only:
      ensure_pinned_rust_toolchain()
      ensure_tauri_cli()
      install_javascript_dependencies()
  except subprocess.CalledProcessError as exc:
    command = " ".join(str(part) for part in exc.cmd)
    print(
      f"error: initialization command failed with exit code {exc.returncode}: {command}",
      file=sys.stderr,
    )
    return exc.returncode or 1
  except (InitError, OSError, json.JSONDecodeError) as exc:
    print(f"error: {exc}", file=sys.stderr)
    return 1

  print("Tauridium development environment initialized.", flush=True)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
