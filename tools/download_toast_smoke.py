#!/usr/bin/env python3
"""Opt-in production-app test of actual downloads and private, visible toasts."""
from __future__ import annotations

import argparse
import csv
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
import subprocess
import tempfile
import threading
import time
from urllib.parse import parse_qs, quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
TITLE = "Tauridium Download Notification Test"
CONTENTS = b"Real native Tauridium download\n" + bytes(range(256))


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--binary", type=Path, default=ROOT / "src-tauri/target/release/tauridium")
  parser.add_argument("--output", type=Path, default=ROOT / "release/evidence/download-toast-smoke")
  parser.add_argument("--case", help="run one named case for diagnosis")
  parser.add_argument("--dbus-config", type=Path, help="start a private bus inheriting each temporary profile")
  args = parser.parse_args()
  if not args.binary.is_file() or not os.environ.get("DISPLAY"):
    parser.error("requires a production executable and an isolated X11 DISPLAY")
  for command in ("xdotool", "magick", "tesseract"):
    if not shutil.which(command):
      parser.error(f"requires {command}; run in the documented test environment")
  if os.environ.get("WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS"):
    parser.error("remove the WebKit sandbox override before testing")
  output = args.output.resolve()
  output.mkdir(parents=True, exist_ok=True)
  reports: list[dict] = []
  ready: set[str] = set()
  denied: set[str] = set()
  leaks: list[dict] = []
  condition = threading.Condition()

  class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
      pass

    def do_GET(self):
      request = urlsplit(self.path)
      query = parse_qs(request.query)
      if request.path in ("/ready", "/security", "/leak"):
        service = query.get("service", [""])[0]
        with condition:
          if request.path == "/ready":
            ready.add(service)
          elif request.path == "/security" and query.get("denied") == ["true"]:
            denied.add(service)
          else:
            leaks.append(query)
          condition.notify_all()
        self.send_response(204)
        self.end_headers()
      elif request.path == "/fixture":
        service = query["service"][0]
        document = f'''<!doctype html><html><head><meta charset="utf-8"><title>Download fixture</title>
          <style>body{{font:18px system-ui;background:#fff;color:#111;margin:24px}}a{{display:block;margin:16px 0;padding:8px;width:240px}}</style></head>
          <body><h2>Native download fixture</h2><p>Service {service}</p>
          <a href="/download?name=alpha.txt">Download alpha</a>
          <a href="/download?name=beta.txt">Download beta</a>
          <a href="/download?name=gamma.txt">Download gamma</a>
          <a href="/broken">Broken download</a>
          <script>
            fetch('/ready?service={service}');
            window.__TAURI_INTERNALS__.invoke('get_download_toast').then(
              () => fetch('/security?service={service}&denied=false'),
              () => fetch('/security?service={service}&denied=true'));
            new MutationObserver(() => {{
              if (document.body.textContent.includes('private-marker') || document.getElementById('__tauridium-toast-overlay'))
                fetch('/leak?service={service}');
            }}).observe(document.body, {{subtree:true,childList:true,characterData:true}});
          </script></body></html>'''.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(document)))
        self.end_headers()
        self.wfile.write(document)
      elif request.path in ("/download", "/broken"):
        filename = query.get("name", ["broken.txt"])[0]
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(filename)}")
        self.send_header("Content-Length", str(len(CONTENTS) + (1000 if request.path == "/broken" else 0)))
        self.end_headers()
        if request.path == "/broken":
          self.wfile.write(CONTENTS[:128])
          self.wfile.flush()
          # A normal EOF can be accepted by WebKit despite Content-Length.
          # Reset a genuinely started transfer instead of relying on that hint.
          time.sleep(0.25)
          self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
          self.connection.close()
          self.close_connection = True
        else:
          self.wfile.write(CONTENTS)
      else:
        self.send_error(404)

  server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
  server.daemon_threads = True
  threading.Thread(target=server.serve_forever, daemon=True).start()

  def xdo(*arguments: str) -> str:
    return subprocess.check_output(["xdotool", *arguments], text=True, timeout=10).strip()

  def wait_for(predicate, label: str, timeout: float = 30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
      if predicate():
        return
      time.sleep(0.1)
    raise RuntimeError(f"Timed out waiting for {label}")

  def screenshot(window: str, name: str) -> tuple[str, list[dict]]:
    png = output / f"{name}.png"
    subprocess.run(["magick", "import", "-window", window, str(png)], check=True, timeout=10)
    # Upscale small native UI text for OCR without changing the captured evidence
    # or relaxing path/privacy assertions. Convert coordinates back for clicks.
    enlarged = subprocess.run(["magick", str(png), "-resize", "200%", "png:-"], capture_output=True, check=True, timeout=10)
    result = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "11", "tsv"], input=enlarged.stdout, capture_output=True, check=True, timeout=30)
    rows = list(csv.DictReader(io.StringIO(result.stdout.decode()), delimiter="\t"))
    for row in rows:
      for key in ("left", "top", "width", "height"):
        row[key] = str(round(int(row[key]) / 2))
    text = " ".join(row["text"] for row in rows if row.get("text", "").strip())
    (output / f"{name}.txt").write_text(text + "\n", encoding="utf-8")
    return text, rows

  def find_word(rows: list[dict], word: str) -> dict:
    found = [row for row in rows if row["text"].strip().lower() == word.lower()]
    if not found:
      raise RuntimeError(f"UI text not found: {word}")
    return min(found, key=lambda row: int(row["top"]))

  def click_word(window: str, word: str, name: str):
    _, rows = screenshot(window, name)
    row = find_word(rows, word)
    x = int(row["left"]) + int(row["width"]) // 2
    y = int(row["top"]) + int(row["height"]) // 2
    xdo("mousemove", "--sync", str(x), str(y))
    xdo("click", "1")

  def verify_file(path: Path):
    wait_for(lambda: path.is_file() and path.read_bytes() == CONTENTS, f"verified download {path.name}")
    return hashlib.sha256(path.read_bytes()).hexdigest()

  try:
    cases = [
      ("default-off", {}, None),
      ("filename", {"downloadToasts": True}, "none"),
      ("folder", {"downloadToasts": True, "downloadToastLocation": "directory", "theme": "light"}, "directory"),
      ("full", {"downloadToasts": True, "downloadToastLocation": "full"}, "full"),
      ("partial-one", {"downloadToasts": True, "downloadToastLocation": "partial", "downloadToastParentLevels": 1}, "partial-one"),
      ("partial-two", {"downloadToasts": True, "downloadToastLocation": "partial", "downloadToastParentLevels": 2, "theme": "oled"}, "partial-two"),
      ("queue-and-restack", {"downloadToasts": True, "downloadToastLocation": "partial"}, "queue"),
      ("failed", {"downloadToasts": True}, "failed"),
      ("cancelled", {"downloadToasts": True, "askEachDownload": True}, "cancelled"),
      ("timed", {"downloadToasts": True, "downloadToastDuration": 8}, "timed"),
    ]
    if args.case:
      cases = [case for case in cases if case[0] == args.case]
      if not cases:
        parser.error("unknown case")
    for name, patch, mode in cases:
      print(f"Native download notification case: {name}", flush=True)
      with tempfile.TemporaryDirectory(prefix="tauridium-download-toast-") as temporary:
        root = Path(temporary)
        (root / "runtime").mkdir(mode=0o700)
        destination = root / "private-marker" / "Downloads" / "Reports"
        destination.mkdir(parents=True)
        data_dir = root / "data/dev.brani.tauridium"
        data_dir.mkdir(parents=True)
        services = [
          {"id": f"{name}-{index}", "name": f"Fixture {index}", "recipeId": "custom-website", "isEnabled": True,
           "isLocalRecipe": True, "order": index,
           "customUrl": f"http://127.0.0.1:{server.server_port}/fixture?service={name}-{index}"}
          for index in range(2)
        ]
        settings = {"preloadServices": False, "fetchMissingServiceIcons": False, "closeToSystemTray": False,
                    "customTitleTemplatesEnabled": True, "windowTitleTemplate": TITLE, "taskbarTitleTemplate": TITLE,
                    "downloadDirectory": str(destination), "downloadToastDuration": 0, **patch}
        for filename, value in (("session.json", {"mode": "local", "version": 1}),
                                ("local_profile.json", {"version": 1, "services": services, "workspaces": []}),
                                ("app_settings.json", settings)):
          (data_dir / filename).write_text(json.dumps(value), encoding="utf-8")
        env = dict(os.environ, XDG_DATA_HOME=str(root / "data"), XDG_CONFIG_HOME=str(root / "config"),
                   XDG_DATA_DIRS=str(root / "data"),
                   XDG_CACHE_HOME=str(root / "cache"), XDG_STATE_HOME=str(root / "state"),
                   XDG_RUNTIME_DIR=str(root / "runtime"),
                   GDK_BACKEND="x11", LIBGL_ALWAYS_SOFTWARE="1",
                   WEBKIT_DISABLE_DMABUF_RENDERER="1")
        with (output / f"{name}.log").open("w", encoding="utf-8") as log:
          command = [str(args.binary.resolve()), "--startup-diagnostics"]
          if args.dbus_config:
            command = ["dbus-run-session", f"--config-file={args.dbus_config}", "--", *command]
          process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
          try:
            wait_for(lambda: services[0]["id"] in ready, "service fixture")
            window = xdo("search", "--onlyvisible", "--name", f"^{TITLE}$").splitlines()[0]
            xdo("windowmove", window, "0", "0")
            xdo("windowsize", window, "1100", "720")
            xdo("windowfocus", "--sync", window)
            time.sleep(0.5)
            click_word(window, "Broken" if mode == "failed" else "alpha", f"{name}-before")
            if mode == "cancelled":
              time.sleep(1)
              xdo("key", "Escape")
              time.sleep(0.5)
              if (destination / "alpha.txt").exists():
                raise RuntimeError("Cancelled download unexpectedly produced a file")
            elif mode != "failed":
              digest = verify_file(destination / "alpha.txt")
            time.sleep(1.0)
            text, rows = screenshot(window, name)
            if mode in (None, "failed", "cancelled"):
              if "Download complete" in text:
                raise RuntimeError(f"Unexpected success toast: {name}")
              if mode == "failed":
                # A failed transfer must not poison later completions in this view.
                click_word(window, "alpha", f"{name}-recovery-before")
                verify_file(destination / "alpha.txt")
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                  text, _ = screenshot(window, f"{name}-recovery")
                  if "Download complete" in text and "alpha.txt" in text:
                    break
                  time.sleep(0.5)
                else:
                  raise RuntimeError("A failed transfer suppressed a later successful download")
            else:
              deadline = time.monotonic() + 30
              while "Download complete" not in text and time.monotonic() < deadline:
                if process.poll() is not None:
                  raise RuntimeError(f"Production app exited: {process.returncode}; see {name}.log")
                time.sleep(0.5)
                text, rows = screenshot(window, name)
              if "Download complete" not in text or "alpha.txt" not in text:
                raise RuntimeError(f"Actual downloaded file was not visibly notified: {text}")
              compact_text = "".join(text.split())
              if mode == "none" and ("private-marker" in compact_text or "Reports" in text):
                raise RuntimeError("Filename-only toast revealed a location")
              if mode == "directory" and ("Reports" not in text or "private-marker" in compact_text or "Downloads" in text):
                raise RuntimeError("Directory toast did not show only the final folder")
              if mode == "full" and "private-marker" not in compact_text:
                raise RuntimeError("Full path toast did not show the actual destination")
              if mode.startswith("partial"):
                if "Reports" not in text or "private-marker" in compact_text:
                  raise RuntimeError("Partial path toast revealed incorrect ancestors")
                if mode == "partial-one" and "Downloads" in text:
                  raise RuntimeError("One-level path showed a second parent")
                if mode == "partial-two" and "Downloads" not in text:
                  raise RuntimeError("Two-level path omitted a parent")
              if mode == "queue":
                for filename in ("beta", "gamma"):
                  click_word(window, filename, f"{name}-{filename}-before")
                  verify_file(destination / f"{filename}.txt")
                time.sleep(0.5)
                text, _ = screenshot(window, f"{name}-waiting")
                if "alpha.txt" not in text or "2 more downloads waiting" not in text:
                  raise RuntimeError(f"Simultaneous downloads did not queue: {text}")
                xdo("key", "ctrl+Tab")
                wait_for(lambda: services[1]["id"] in ready, "newly created second service")
                time.sleep(0.5)
                text, rows = screenshot(window, f"{name}-restacked")
                if "alpha.txt" not in text:
                  raise RuntimeError("New service covered the notification")
                for expected in ("beta.txt", "gamma.txt"):
                  row = max((row for row in rows if row["text"] == "Download"), key=lambda row: int(row["top"]))
                  xdo("mousemove", "--sync", "781", str(int(row["top"]) + int(row["height"]) // 2 + 6))
                  xdo("click", "1")
                  time.sleep(0.5)
                  text, rows = screenshot(window, f"{name}-next-{expected}")
                  if expected not in text:
                    raise RuntimeError(f"Dismissing toast skipped a download: {text}")
                xdo("windowsize", window, "760", "520")
                time.sleep(0.5)
                text, _ = screenshot(window, f"{name}-resized")
                if "gamma.txt" not in text:
                  raise RuntimeError("Resizing covered or lost the toast")
              if mode == "timed":
                heading = max((row for row in rows if row["text"] == "Download"), key=lambda row: int(row["top"]))
                xdo("mousemove", "--sync", str(int(heading["left"]) + int(heading["width"]) // 2), str(int(heading["top"]) + int(heading["height"]) // 2))
                time.sleep(8.5)
                text, _ = screenshot(window, f"{name}-hover-paused")
                if "Download complete" not in text:
                  raise RuntimeError("Notification expired while hovered")
                xdo("mousemove", "--sync", "40", "40")
                time.sleep(8.5)
                text, _ = screenshot(window, f"{name}-expired")
                if "Download complete" in text:
                  raise RuntimeError("Notification did not expire after its display time")
            wait_for(lambda: services[0]["id"] in denied, "remote IPC denial")
            if leaks:
              raise RuntimeError(f"Service page observed privileged notification data: {leaks}")
            reports.append({"case": name, "passed": True, "downloadSha256": digest if mode not in ("failed", "cancelled") else None,
                            "remoteIpcDenied": True, "serviceDomUnaffected": True})
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
    (output / "result.json").write_text(json.dumps({"passed": True, "softwareX11Renderer": True, "sandboxDisabled": False, "cases": reports}, indent=2) + "\n", encoding="utf-8")
    print(f"Production download notification smoke passed: {len(reports)} cases; {output}")
    return 0
  finally:
    server.shutdown()
    server.server_close()


if __name__ == "__main__":
  raise SystemExit(main())
