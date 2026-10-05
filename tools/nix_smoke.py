#!/usr/bin/env python3
"""Exercise a real Nix wrapper and WebKit UI with an isolated temporary XDG profile.

Run through the flake's `smoke` app, which supplies a private D-Bus/Xvfb session.
No sandbox or TLS disabling workarounds are permitted by this test.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path


def validate_build_info(info: dict) -> None:
  if info.get("buildMode") != "production":
    raise RuntimeError("Nix package is not a production custom-protocol build")
  distribution = info.get("distribution", {})
  if distribution.get("mode") != "nix" or distribution.get("updaterManagedExternally") is not True:
    raise RuntimeError("Nix package must delegate updates to Nix")
  for flag in (
    "portalFileAccess", "portalNotifications", "portalAutostart",
    "downloadsRequireDestination", "automaticBackupsUsePrivateStorage",
  ):
    if distribution.get(flag) is not False:
      raise RuntimeError(f"Nix must not inherit Flatpak sandbox policy: {flag}")


def sign_in_screen_rendered(text: str) -> bool:
  return all(label in text for label in ("Tauridium", "Email", "Password", "without an account"))


def isolated_environment(profile: Path) -> dict[str, str]:
  env = dict(os.environ)
  for variable, directory in (
    ("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
    ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state"),
    ("XDG_RUNTIME_DIR", "runtime"),
  ):
    path = profile / directory
    path.mkdir(mode=0o700)
    env[variable] = str(path)
  # The private bus must not discover host desktop portal services. Otherwise
  # their FUSE mounts can outlive the test process and break profile cleanup.
  # The installed package still supplies its own GTK/WebKit data directories.
  env["XDG_DATA_DIRS"] = env["XDG_DATA_HOME"]
  return env


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("executable", type=Path)
  parser.add_argument("--dbus-config", type=Path, required=True)
  parser.add_argument("--timeout", type=int, default=90, choices=range(30, 601), metavar="SECONDS")
  parser.add_argument("--output", type=Path, default=Path("release/evidence/nix-smoke"))
  args = parser.parse_args()
  executable = args.executable.resolve(strict=True)
  output = args.output.resolve()
  output.mkdir(parents=True, exist_ok=True)
  if os.environ.get("WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS"):
    raise RuntimeError("Remove the WebKit sandbox override before running this smoke test")
  with tempfile.TemporaryDirectory(prefix="tauridium-nix-smoke-") as temporary:
    profile = Path(temporary)
    env = isolated_environment(profile)
    # Only the test selects Xvfb/software rendering; the installed app does not.
    env["GDK_BACKEND"] = "x11"
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    build_info = output / "build-info.json"
    subprocess.run([str(executable), "--build-info-file", str(build_info)], env=env, check=True, timeout=20)
    info = json.loads(build_info.read_text(encoding="utf-8"))
    validate_build_info(info)
    with (output / "application.log").open("w", encoding="utf-8") as log:
      process = subprocess.Popen(["dbus-run-session", f"--config-file={args.dbus_config}", "--", str(executable), "--startup-diagnostics"], env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
      try:
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
          if process.poll() is not None:
            raise RuntimeError(f"Tauridium exited early ({process.returncode}); see {output / 'application.log'}")
          windows = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", "Tauridium"], env=env, capture_output=True, text=True, check=False, timeout=5)
          if windows.returncode == 0 and windows.stdout.strip():
            window = windows.stdout.splitlines()[-1]
            subprocess.run(["magick", "import", "-window", window, str(output / "window.png")], env=env, check=True, timeout=10)
            ocr = subprocess.run(["tesseract", str(output / "window.png"), "stdout"], env=env, capture_output=True, text=True, check=True, timeout=60)
            (output / "window.txt").write_text(ocr.stdout, encoding="utf-8")
            if sign_in_screen_rendered(ocr.stdout):
              (output / "result.json").write_text(json.dumps({"passed": True, "production": True, "distribution": "nix", "realWebKitUiRendered": True, "isolatedXdgProfile": True}, indent=2) + "\n", encoding="utf-8")
              print(f"Nix wrapper and real WebKit UI smoke passed: {output}")
              return 0
          time.sleep(1)
        raise RuntimeError(f"WebKit UI did not render the sign-in screen; see {output}")
      finally:
        try:
          os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
          pass
        try:
          process.wait(timeout=10)
        except subprocess.TimeoutExpired:
          os.killpg(process.pid, signal.SIGKILL)
          process.wait(timeout=10)
  return 1


if __name__ == "__main__":
  raise SystemExit(main())
