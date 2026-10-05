#!/usr/bin/env python3
"""Exercise production Settings navigation and download controls in isolated profiles."""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import tempfile
import time

from nix_smoke import isolated_environment


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--binary", type=Path, required=True)
  parser.add_argument("--dbus-config", type=Path, required=True)
  parser.add_argument("--output", type=Path, default=Path("release/evidence/settings-smoke"))
  parser.add_argument("--theme", choices=("dark", "light", "oled"), action="append")
  args = parser.parse_args()
  if not args.binary.is_file() or not os.environ.get("DISPLAY"):
    parser.error("requires a production executable and an isolated X11 DISPLAY")
  if os.environ.get("WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS"):
    parser.error("remove the WebKit sandbox override before testing")
  output = args.output.resolve()
  output.mkdir(parents=True, exist_ok=True)
  reports = []

  def xdo(*arguments):
    return subprocess.check_output(["xdotool", *map(str, arguments)], text=True, timeout=10).strip()

  def wait_for(predicate, description, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
      if predicate():
        return
      time.sleep(0.15)
    raise RuntimeError(f"Timed out waiting for {description}")

  def capture(window, name):
    png = output / f"{name}.png"
    subprocess.run(["magick", "import", "-window", window, str(png)], check=True, timeout=10)
    rows = []
    # Active tabs have dark text on a bright accent; OCR needs the opposite
    # polarity as well. Keep the actual evidence image unmodified.
    for transform in ([], ["-colorspace", "Gray", "-negate"]):
      enlarged = subprocess.run(["magick", str(png), "-resize", "200%", *transform, "png:-"], capture_output=True, check=True, timeout=10)
      ocr = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "11", "tsv"], input=enlarged.stdout, capture_output=True, check=True, timeout=30)
      rows.extend(csv.DictReader(io.StringIO(ocr.stdout.decode("utf-8")), delimiter="\t"))
    rows = [row for row in rows if row["text"].strip()]
    for row in rows:
      for key in ("left", "top", "width", "height"):
        row[key] = round(int(row[key]) / 2)
    text = " ".join(row["text"] for row in rows)
    (output / f"{name}.txt").write_text(text + "\n", encoding="utf-8")
    return text, rows, struct.unpack(">II", png.read_bytes()[16:24])

  def word(rows, label):
    matches = [row for row in rows if row["text"].strip().lower() == label.lower()]
    if not matches:
      raise RuntimeError(f"Rendered UI control not found: {label}")
    row = min(matches, key=lambda item: item["top"])
    return row["left"] + row["width"] // 2, row["top"] + row["height"] // 2

  def click(point):
    xdo("mousemove", "--sync", *point)
    xdo("click", 1)
    time.sleep(0.3)

  def top(width, height):
    xdo("mousemove", "--sync", width - 25, height // 2)
    xdo("click", "--repeat", 30, "--delay", 15, 4)
    time.sleep(0.3)

  for theme in args.theme or ("dark", "light", "oled"):
    for width, height in ((1100, 900), (760, 600)):
      name = f"{theme}-{width}"
      print(f"Production Settings case: {name}", flush=True)
      with tempfile.TemporaryDirectory(prefix="tauridium-settings-smoke-") as temporary:
        root = Path(temporary)
        env = isolated_environment(root)
        env.update(GDK_BACKEND="x11", LIBGL_ALWAYS_SOFTWARE="1", WEBKIT_DISABLE_DMABUF_RENDERER="1")
        data = root / "data/dev.brani.tauridium"
        data.mkdir()
        settings = {"theme": theme, "closeToSystemTray": False, "fetchMissingServiceIcons": False,
                    "customTitleTemplatesEnabled": True, "windowTitleTemplate": "Tauridium UI Regression",
                    "taskbarTitleTemplate": "Tauridium UI Regression", "downloadToasts": False}
        for filename, value in (("session.json", {"mode": "local", "version": 1}),
                                ("local_profile.json", {"version": 1, "services": [], "workspaces": []}),
                                ("app_settings.json", settings)):
          (data / filename).write_text(json.dumps(value), encoding="utf-8")

        def saved(key, value):
          return json.loads((data / "app_settings.json").read_text(encoding="utf-8")).get(key) == value

        with (output / f"{name}.log").open("w", encoding="utf-8") as log:
          process = subprocess.Popen(["dbus-run-session", f"--config-file={args.dbus_config}", "--", str(args.binary.resolve()), "--startup-diagnostics"], env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
          try:
            def visible_window():
              if process.poll() is not None:
                raise RuntimeError(f"Production app exited: {process.returncode}; see {name}.log")
              result = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", "^Tauridium UI Regression$"], capture_output=True, text=True, check=False, timeout=5)
              return result.returncode == 0 and bool(result.stdout.strip())

            wait_for(visible_window, "production window")
            window = xdo("search", "--onlyvisible", "--name", "^Tauridium UI Regression$").splitlines()[0]
            xdo("windowmove", window, 0, 0)
            xdo("windowsize", window, width, height)
            xdo("windowfocus", "--sync", window)
            time.sleep(0.5)
            xdo("key", "ctrl+comma")
            time.sleep(0.5)
            text, rows, _ = capture(window, f"{name}-general")
            assert "Startup" in text, text
            advanced = word(rows, "Advanced")
            click(advanced)
            text, rows, _ = capture(window, f"{name}-advanced")
            assert "Service context menu" in text, f"Advanced layout obscures its content: {text}"
            general = word(rows, "General")
            click(general)
            text, _, _ = capture(window, f"{name}-return-general")
            assert "Startup" in text, f"Advanced intercepted General navigation: {text}"
            click(advanced)
            for step in range(16):
              text, rows, _ = capture(window, f"{name}-downloads-{step}")
              if "Show download completion toasts" in text:
                break
              xdo("mousemove", "--sync", width - 25, height // 2)
              xdo("click", "--repeat", 2, "--delay", 30, 5)
              time.sleep(0.2)
            else:
              raise RuntimeError("Download notification toggle is not reachable by scrolling")
            assert saved("downloadToasts", False), "Notifications must default to off"
            click(word(rows, "completion"))
            wait_for(lambda: saved("downloadToasts", True), "enabled notification toggle")
            # Native keyboard focus must reach each newly-enabled form control.
            xdo("key", "Tab", "End")
            wait_for(lambda: saved("downloadToastLocation", "partial"), "partial-path selector")
            xdo("key", "Tab", "ctrl+a")
            xdo("type", "--clearmodifiers", "3")
            xdo("key", "Tab")
            wait_for(lambda: saved("downloadToastParentLevels", 3), "parent-folder input")
            xdo("key", "End")
            wait_for(lambda: saved("downloadToastDuration", 0), "display-time selector")
            text, rows, _ = capture(window, f"{name}-enabled-controls")
            click(word(rows, "completion"))
            wait_for(lambda: saved("downloadToasts", False), "disabled notification toggle")
            top(width, height)
            text, rows, size = capture(window, f"{name}-navigation-after-toggle")
            click(word(rows, "General"))
            text, rows, _ = capture(window, f"{name}-final-general")
            assert "Startup" in text, text
            click((size[0] - (57 if size[0] > 760 else 47), word(rows, "Settings")[1]))
            text, _, _ = capture(window, f"{name}-closed")
            assert "application-wide" not in text and "Startup" not in text, "Close Settings remained blocked"
            xdo("key", "ctrl+comma")
            time.sleep(0.3)
            text, rows, _ = capture(window, f"{name}-reopened")
            assert "Startup" in text, "Settings could not reopen after Advanced"
            click(word(rows, "Advanced"))
            text, _, _ = capture(window, f"{name}-advanced-again")
            assert "Service context menu" in text, text
            reports.append({"theme": theme, "size": [width, height], "navigation": True,
                            "closeAndReopen": True, "downloadControlsPersisted": True})
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
  (output / "result.json").write_text(json.dumps({"passed": True, "cases": reports}, indent=2) + "\n", encoding="utf-8")
  print(f"Production Settings smoke passed: {len(reports)} cases; {output}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
