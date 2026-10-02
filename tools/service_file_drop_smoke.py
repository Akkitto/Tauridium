#!/usr/bin/env python3
"""Opt-in X11 test of real OS file drops into the production Tauridium app."""

from __future__ import annotations

import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
TITLE = "Tauridium File Drop Test"


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--binary", type=Path, default=ROOT / "src-tauri/target/release/tauridium")
  parser.add_argument("--output", type=Path, default=ROOT / "release/file-drop-smoke.json")
  parser.add_argument("--input-only", action="store_true", help="diagnose the browser's native file-input drop path")
  parser.add_argument("--linux-fallback-only", action="store_true", help="verify actionable guidance for engine-blocked file drops")
  args = parser.parse_args()
  if not args.binary.is_file() or not os.environ.get("DISPLAY") or not shutil.which("xdotool"):
    parser.error("requires a built native executable, isolated X11 DISPLAY, and xdotool")
  # WSL may also expose a Wayland session; both the source and app must use this X11 display.
  os.environ["GDK_BACKEND"] = "x11"
  import gi
  gi.require_version("Gtk", "3.0")
  gi.require_version("Gdk", "3.0")
  from gi.repository import Gdk, GLib, Gtk

  condition = threading.Condition()
  ready: dict[str, int] = {}
  reports: list[dict] = []
  cases: list[dict] = []
  failures: list[str] = []
  fixture = (ROOT / "tools/fixtures/file-drop.html").read_bytes()

  class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
      pass

    def do_GET(self):
      url = urlsplit(self.path)
      if url.path == "/ready":
        service = parse_qs(url.query)["service"][0]
        with condition:
          ready[service] = ready.get(service, 0) + 1
          condition.notify_all()
        self.send_response(204)
        self.end_headers()
      elif url.path == "/file-drop.html":
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(fixture)))
        self.end_headers()
        self.wfile.write(fixture)
      else:
        self.send_error(404)

    def do_POST(self):
      if self.path != "/result":
        self.send_error(404)
        return
      length = int(self.headers.get("Content-Length", 0))
      if not 0 < length < 4 * 1024 * 1024:
        self.send_error(413)
        return
      report = json.loads(self.rfile.read(length))
      with condition:
        reports.append(report)
        condition.notify_all()
      self.send_response(204)
      self.end_headers()

  server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
  server.daemon_threads = True
  threading.Thread(target=server.serve_forever, daemon=True).start()
  source = Gtk.Window(title="Tauridium file drop source")
  source.set_default_size(260, 160)
  source.move(1250, 80)
  button = Gtk.Button(label="Drag test files")
  source.add(button)
  button.drag_source_set(Gdk.ModifierType.BUTTON1_MASK,
                         [Gtk.TargetEntry.new("text/uri-list", 0, 0)], Gdk.DragAction.COPY)
  selected: list[Path] = []

  def provide_files(_widget, _context, data, _info, _time):
    print(f"OS drag provided {len(selected)} file URIs", flush=True)
    data.set_uris([path.as_uri() for path in selected])

  button.connect("drag-data-get", provide_files)
  button.connect("drag-begin", lambda *_: print("OS drag started", flush=True))
  button.connect("drag-failed", lambda _widget, _context, reason: print(f"OS drag failed: {reason}", flush=True))
  source.show_all()

  def xdo(*arguments: str) -> str:
    return subprocess.check_output(["xdotool", *arguments], text=True).strip()

  def wait_for(predicate, description: str, timeout: float = 20):
    with condition:
      if not condition.wait_for(predicate, timeout):
        raise RuntimeError(f"Timed out waiting for {description}")

  def drag(target: tuple[int, int], cancel: bool = False):
    xdo("mousemove", "--sync", "1380", "155")
    xdo("mousedown", "1")
    try:
      for step in range(1, 21):
        x = round(1380 + (target[0] - 1380) * step / 20)
        y = round(155 + (target[1] - 155) * step / 20)
        xdo("mousemove", "--sync", str(x), str(y))
        time.sleep(0.03)
      time.sleep(0.3)
      if cancel:
        xdo("mousemove", "--sync", "1380", "900")
        time.sleep(0.2)
    finally:
      xdo("mouseup", "1")

  def exercise():
    app = None
    try:
      with tempfile.TemporaryDirectory(prefix="tauridium-file-drop-") as temporary:
        root = Path(temporary)
        samples = {
          "attachment.txt": b"Native browser attachment\n",
          "Gr\u00fc\u00dfe \u65e5\u672c\u8a9e with spaces.txt": "Unicode attachment contents: caf\u00e9 \u65e5\u672c\u8a9e\n".encode(),
          "empty.txt": b"",
          "binary.bin": bytes(range(256)) * 4096,
        }
        for name, data in samples.items():
          (root / name).write_bytes(data)
        data_dir = root / "data/dev.brani.tauridium"
        data_dir.mkdir(parents=True)
        services = [
          {"id": name, "name": name, "recipeId": "custom-website", "isEnabled": True,
           "isLocalRecipe": True, "order": index,
           "customUrl": f"http://127.0.0.1:{server.server_port}/file-drop.html?service={name}"}
          for index, name in enumerate(("drop-one", "drop-two", "drop-three"))
        ]
        if args.input_only:
          services = services[:1]
        profile = {"version": 1, "services": services, "workspaces": []}
        settings = {"preloadServices": not args.input_only, "fetchMissingServiceIcons": False,
                    "closeToSystemTray": False, "customTitleTemplatesEnabled": True,
                    "windowTitleTemplate": TITLE, "taskbarTitleTemplate": TITLE,
                    "serviceZoomLevels": {"drop-one": 50, "drop-two": 200, "drop-three": 100}}
        for name, value in (("session.json", {"mode": "local", "version": 1}),
                            ("local_profile.json", profile), ("app_settings.json", settings)):
          (data_dir / name).write_text(json.dumps(value), encoding="utf-8")
        env = dict(os.environ, XDG_DATA_HOME=str(root / "data"),
                   XDG_CONFIG_HOME=str(root / "config"), XDG_CACHE_HOME=str(root / "cache"),
                   GDK_BACKEND="x11", WEBKIT_DISABLE_DMABUF_RENDERER="1")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.with_suffix(".log").open("w", encoding="utf-8") as log:
          def launch():
            nonlocal app
            app = subprocess.Popen([str(args.binary.resolve())], env=env, stdout=log, stderr=log)
            wait_for(lambda: all(ready.get(service["id"], 0) for service in services), "all service pages")
            window = xdo("search", "--name", f"^{TITLE}$").splitlines()[0]
            xdo("windowmove", window, "0", "0")
            xdo("windowsize", window, "1100", "720")
            time.sleep(0.5)
            return app, window

          app, window = launch()

          def check(name: str, service: str, filenames: list[str], target: str = "zone"):
            selected[:] = [root / filename for filename in filenames]
            before = len(reports)
            drag((650, 610 if args.input_only else (220 if target == "zone" else 490)))
            wait_for(lambda: len(reports) > before, name)
            time.sleep(0.2)
            if len(reports) != before + 1:
              raise RuntimeError(f"{name}: duplicate file delivery")
            report = reports[-1]
            if report["service"] != service or report["target"] != target or report["trusted"] is not True:
              raise RuntimeError(f"{name}: wrong service, target, or untrusted event")
            if target == "zone" and not all(event in report["events"] for event in ("dragenter", "dragover", "drop")):
              raise RuntimeError(f"{name}: incomplete native drag event sequence")
            if args.linux_fallback_only:
              if report["files"] or report.get("helpVisible") is not True or report.get("prevented") is not True:
                raise RuntimeError(f"{name}: Linux blocked-drop guidance was not displayed")
              cases.append({"case": name, "nativeDrop": True, "filesDelivered": False, "guidanceVisible": True})
              print(f"PASS {name}", flush=True)
              return
            expected = {filename: hashlib.sha256(samples[filename]).hexdigest() for filename in filenames}
            actual = {}
            for file in report["files"]:
              content = base64.b64decode(file["data"], validate=True)
              if file["size"] != len(content):
                raise RuntimeError(f"{name}: incorrect file size")
              actual[file["name"]] = hashlib.sha256(content).hexdigest()
            if actual != expected or len(report["files"]) != len(filenames):
              raise RuntimeError(f"{name}: filename or content mismatch ({actual!r} != {expected!r}); types={report.get('types')!r}, uri={report.get('uri')!r}")
            cases.append({"case": name, "service": service, "target": target,
                          "trusted": True, "files": actual})
            print(f"PASS {name}", flush=True)

          def shortcut(key: str):
            xdo("windowfocus", window)
            xdo("key", "--clearmodifiers", key)
            time.sleep(0.5)

          if args.input_only:
            check("native file input diagnostic", "drop-one", list(samples), "input")
            return
          if args.linux_fallback_only:
            check("Linux engine-blocked drop guidance", "drop-one", ["attachment.txt"])
            return
          check("single file at 50% zoom", "drop-one", ["attachment.txt"])
          check("multiple, Unicode, empty and binary files", "drop-one", list(samples))
          check("native file input", "drop-one", ["attachment.txt", "empty.txt"], "input")
          before = len(reports)
          drag((650, 220), cancel=True)
          time.sleep(0.5)
          if len(reports) != before:
            raise RuntimeError("Cancelled drag delivered files")
          cases.append({"case": "cancelled drag", "delivered": False})
          print("PASS cancelled drag", flush=True)
          shortcut("ctrl+Tab")
          check("preloaded second service at 200% zoom", "drop-two", list(samples))
          shortcut("ctrl+Tab")
          check("third service at 100% zoom", "drop-three", ["attachment.txt"])
          loaded = ready["drop-three"]
          shortcut("ctrl+r")
          wait_for(lambda: ready["drop-three"] > loaded, "service reload")
          check("after service reload", "drop-three", list(samples))
          shortcut("ctrl+Tab")
          check("after switching back", "drop-one", ["attachment.txt"])
          app.terminate()
          app.wait(timeout=10)
          with condition:
            ready.clear()
          app, window = launch()
          check("after application restart", "drop-one", list(samples))
    except Exception as error:
      failures.append(str(error))
      print(f"FAIL {error}", flush=True)
      def capture_failure():
        window = Gdk.get_default_root_window()
        screenshot = Gdk.pixbuf_get_from_window(window, 0, 0, window.get_width(), window.get_height())
        screenshot.savev(str(args.output.with_suffix(".png")), "png", [], [])
        return False
      GLib.idle_add(capture_failure)
    finally:
      if app is not None and app.poll() is None:
        app.terminate()
        try:
          app.wait(timeout=10)
        except subprocess.TimeoutExpired:
          app.kill()
          app.wait()
      args.output.parent.mkdir(parents=True, exist_ok=True)
      args.output.write_text(json.dumps({"binary": str(args.binary.resolve()), "cases": cases,
                                         "failures": failures}, indent=2) + "\n", encoding="utf-8")
      GLib.idle_add(Gtk.main_quit)

  threading.Thread(target=exercise, daemon=False).start()
  Gtk.main()
  server.shutdown()
  server.server_close()
  return 1 if failures else 0


if __name__ == "__main__":
  raise SystemExit(main())
