#!/usr/bin/env python3
"""Run a fixture file manager and Tauridium on the same isolated test bus."""
from __future__ import annotations
import argparse
import subprocess
import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file-manager", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("requires an application command")
    manager = subprocess.Popen([args.file_manager, "--daemon"], stdin=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            result = subprocess.run(["gdbus", "call", "--session", "--dest", "org.freedesktop.DBus",
                                     "--object-path", "/org/freedesktop/DBus", "--method",
                                     "org.freedesktop.DBus.NameHasOwner", "org.freedesktop.FileManager1"],
                                    capture_output=True, text=True, timeout=3)
            if result.returncode == 0 and result.stdout.strip() == "(true,)":
                return subprocess.call(command)
            if manager.poll() is not None:
                raise RuntimeError("Fixture file manager exited before owning FileManager1")
            time.sleep(0.1)
        raise RuntimeError("Fixture file manager did not acquire FileManager1")
    finally:
        if manager.poll() is None:
            manager.terminate()
            try:
                manager.wait(timeout=5)
            except subprocess.TimeoutExpired:
                manager.kill()
                manager.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
