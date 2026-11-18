#!/usr/bin/env python3
"""Exercise production menu/toast rendering on a private native Wayland display.

The pinned Nix app supplies Sway, software rendering, persistent virtual input,
OCR and screenshots. Nothing connects to an existing desktop or account.
"""
from __future__ import annotations

import argparse
import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import re
import select
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit

from nix_smoke import isolated_environment

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 1280, 960
TITLE = "Tauridium native Wayland regression"
DOWNLOAD = b"Real native Tauridium download\n" + bytes(range(256))
BUS = '''<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>
<policy context="default"><allow send_destination="*" eavesdrop="true"/>
<allow eavesdrop="true"/><allow own="*"/></policy></busconfig>'''
TOPLEVEL = re.compile(r"->\s+xdg_surface[@#]\d+\.get_toplevel\(")


def stop(process):
    if process is None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


class NativeDisplay:
    def __init__(self, root, output, helper):
        self.root, self.output, self.helper = root, output, helper
        self.env = isolated_environment(root)
        for key in ("DISPLAY", "XAUTHORITY", "WAYLAND_SOCKET", "DBUS_SESSION_BUS_ADDRESS",
                    "DBUS_STARTER_ADDRESS", "DBUS_STARTER_BUS_TYPE"):
            self.env.pop(key, None)
        self.env.update(GDK_BACKEND="wayland", GDK_SCALE="1", GDK_DPI_SCALE="1",
                        GSETTINGS_BACKEND="memory", WAYLAND_DISPLAY="wayland-1",
                        SWAYSOCK=str(root / "runtime/sway-ipc.sock"),
                        WLR_BACKENDS="headless", WLR_RENDERER="pixman",
                        WLR_HEADLESS_OUTPUTS="1", WLR_LIBINPUT_NO_DEVICES="1",
                        LIBGL_ALWAYS_SOFTWARE="1", WEBKIT_DISABLE_DMABUF_RENDERER="1")
        self.app = self.sway = self.pointer = self.keyboard = None
        self.logs = []
        self.trace = output / "application-wayland.log"

    def log(self, name):
        handle = (self.output / name).open("w", encoding="utf-8")
        self.logs.append(handle)
        return handle

    def run(self, *args):
        return subprocess.run(list(map(str, args)), env=self.env, check=True,
                              capture_output=True, text=True, timeout=15).stdout

    def live(self):
        for label, process in (("compositor", self.sway), ("pointer", self.pointer),
                               ("keyboard", self.keyboard), ("application", self.app)):
            if process is not None and process.poll() is not None:
                raise RuntimeError(f"Private {label} exited with {process.returncode}; see {self.output}")

    def wait(self, predicate, label, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.live()
            if predicate():
                return
            time.sleep(.12)
        raise RuntimeError(f"Timed out: {label}; see {self.output}")

    def reply(self, expected):
        if not select.select([self.pointer.stdout], [], [], 5)[0]:
            raise RuntimeError("Persistent Wayland pointer did not acknowledge its request")
        response = self.pointer.stdout.readline().strip()
        if response != expected:
            raise RuntimeError(f"Persistent Wayland pointer returned {response!r}, expected {expected}")

    def pointer_command(self, command):
        self.live()
        self.pointer.stdin.write(command + "\n")
        self.pointer.stdin.flush()
        self.reply("DONE")

    def click(self, x, y, button=272, settle=.18):
        if not (0 <= x < WIDTH and 0 <= y < HEIGHT):
            raise RuntimeError("Input coordinate outside the private display")
        self.pointer_command(f"move {x} {y}")
        time.sleep(.04)
        self.pointer_command(f"button {button} 1")
        time.sleep(.035)
        self.pointer_command(f"button {button} 0")
        time.sleep(settle)

    def key(self, *args):
        self.run("wtype", *args)
        time.sleep(.2)

    def text(self, value):
        self.run("wtype", "--", value)
        time.sleep(.35)

    def tree(self):
        tree = json.loads(self.run("swaymsg", "-t", "get_tree"))
        windows = []
        def visit(node):
            if node.get("app_id") or node.get("window"):
                windows.append(node)
            for child in node.get("nodes", []) + node.get("floating_nodes", []):
                visit(child)
        visit(tree)
        return tree, windows

    def protocol_toplevels(self):
        return len(TOPLEVEL.findall(self.trace.read_text(encoding="utf-8", errors="replace")))

    def assert_native(self, name):
        tree, windows = self.tree()
        (self.output / f"{name}-tree.json").write_text(json.dumps(tree, indent=2) + "\n", encoding="utf-8")
        own = [window for window in windows if window.get("app_id") == "tauridium"]
        if len(windows) != 1 or len(own) != 1 or own[0].get("shell") != "xdg_shell" or own[0].get("window") is not None:
            raise RuntimeError("Expected exactly one native Wayland Tauridium toplevel")
        if os.getpgid(own[0]["pid"]) != self.app.pid:
            raise RuntimeError("Mapped window does not belong to the private app process group")
        count = self.protocol_toplevels()
        # An unwanted promoted GTK child never maps, so get_tree alone misses it.
        if count != 1:
            raise RuntimeError(f"Unexpected xdg_toplevel constructions: {count} (expected only the main window)")

    def screenshot(self, name):
        self.live()
        path = self.output / f"{name}.png"
        self.run("grim", str(path))
        rows = []
        # The bright native service otherwise dominates OCR's thresholding of
        # the dark sidebar and small menu, so inspect them independently.
        for left, top, width, height in ((0, 25, 220, 680), (220, 25, 360, 680),
                                         (220, 120, 1060, 240), (250, 650, 900, 310)):
            png = subprocess.run(["magick", str(path), "-crop", f"{width}x{height}+{left}+{top}",
                                  "+repage", "-resize", "300%", "-colorspace", "Gray", "-normalize", "png:-"],
                                 env=self.env, check=True, capture_output=True, timeout=15).stdout
            ocr = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "11", "tsv"], input=png,
                                 env=self.env, check=True, capture_output=True, timeout=30).stdout.decode()
            for row in csv.DictReader(io.StringIO(ocr), delimiter="\t"):
                if not row.get("text", "").strip():
                    continue
                for field in ("left", "top", "width", "height"):
                    row[field] = round(int(row[field]) / 3)
                row["left"] += left
                row["top"] += top
                rows.append(row)
        # The focus outline around the light-theme Settings row can be read as
        # a box. Inspect that line alone, as the existing X11 gate does.
        if any(row["text"] == "Reload" for row in rows) and not any(row["text"] == "Settings" for row in rows):
            reload = min((row for row in rows if row["text"] == "Reload"), key=lambda row: row["top"])
            left, top = reload["left"], max(0, reload["top"] - 40)
            png = subprocess.run(["magick", str(path), "-crop", f"210x26+{left}+{top}", "+repage",
                                  "-resize", "300%", "png:-"], env=self.env, check=True,
                                 capture_output=True, timeout=15).stdout
            ocr = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "7", "tsv"], input=png,
                                 env=self.env, check=True, capture_output=True, timeout=30).stdout.decode()
            for row in csv.DictReader(io.StringIO(ocr), delimiter="\t"):
                if row.get("text") != "Settings":
                    continue
                for field in ("left", "top", "width", "height"):
                    row[field] = round(int(row[field]) / 3)
                row["left"] += left
                row["top"] += top
                rows.append(row)
        # Read each zoom line separately. A whole-window OCR pass can retain
        # only the disabled Reset label in the light theme, which must never be
        # mistaken for the enabled Zoom in action.
        reloads = [row for row in rows if row["text"] == "Reload"]
        if reloads:
            reload = min(reloads, key=lambda row: row["top"])
            for offset in (36, 70, 104):
                left, top = reload["left"], reload["top"] + offset
                png = subprocess.run(["magick", str(path), "-crop", f"210x28+{left}+{top}",
                                      "+repage", "-resize", "300%", "png:-"], env=self.env,
                                     check=True, capture_output=True, timeout=15).stdout
                ocr = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "7", "tsv"], input=png,
                                     env=self.env, check=True, capture_output=True, timeout=30).stdout.decode()
                for row in csv.DictReader(io.StringIO(ocr), delimiter="\t"):
                    if not row.get("text", "").strip():
                        continue
                    for field in ("left", "top", "width", "height"):
                        row[field] = round(int(row[field]) / 3)
                    row["left"] += left
                    row["top"] += top
                    rows.append(row)
        text = " ".join(row["text"] for row in rows)
        (self.output / f"{name}.txt").write_text(text + "\n", encoding="utf-8")
        return text, rows

    def start(self, binary):
        config = self.root / "sway.conf"
        config.write_text(f'''output HEADLESS-1 mode {WIDTH}x{HEIGHT}@60Hz position 0 0 scale 1
output * bg #182030 solid_color
seat seat0 fallback true
input * xkb_layout us
font pango:Sans 10
default_border none
default_floating_border none
focus_follows_mouse no
xwayland disable
bar {{ mode invisible }}
''', encoding="utf-8")
        self.sway = subprocess.Popen(["sway", "--unsupported-gpu", "--config", str(config), "--debug"],
                                     env=self.env, stdout=self.log("compositor.log"), stderr=subprocess.STDOUT,
                                     start_new_session=True)
        self.wait(lambda: (self.root / "runtime/wayland-1").is_socket()
                  and (self.root / "runtime/sway-ipc.sock").is_socket(), "private compositor sockets")
        outputs = json.loads(self.run("swaymsg", "-t", "get_outputs"))
        if len(outputs) != 1 or outputs[0]["name"] != "HEADLESS-1":
            raise RuntimeError("Compositor did not create exactly one private headless output")
        self.pointer = subprocess.Popen([str(self.helper), str(WIDTH), str(HEIGHT)], env=self.env,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.log("pointer.log"), text=True, bufsize=1,
                                        start_new_session=True)
        self.reply("READY")
        self.keyboard = subprocess.Popen(["wtype", "-s", "3600000"], env=self.env,
                                         stdout=self.log("keyboard.log"), stderr=subprocess.STDOUT,
                                         start_new_session=True)
        time.sleep(.3)
        self.pointer_command("move 1100 800")
        bus = self.root / "session.conf"
        bus.write_text(BUS, encoding="utf-8")
        info = self.output / "build-info.json"
        self.run(binary, "--build-info-file", info)
        if json.loads(info.read_text(encoding="utf-8")).get("buildMode") != "production":
            raise RuntimeError("Wayland gate requires a genuine production custom-protocol build")
        app_env = dict(self.env, WAYLAND_DEBUG="client")
        self.app = subprocess.Popen(["dbus-run-session", f"--config-file={bus}", "--", str(binary),
                                     "--startup-diagnostics"], env=app_env, stdout=self.log("application-wayland.log"),
                                    stderr=subprocess.STDOUT, start_new_session=True)
        self.wait(lambda: any(window.get("app_id") == "tauridium" and window.get("visible")
                              for window in self.tree()[1]), "native fixture window")

    def close(self):
        for process in (self.app, self.keyboard, self.pointer, self.sway):
            stop(process)
        for handle in self.logs:
            handle.close()


def word(rows, label):
    matches = [row for row in rows if row["text"].lower().strip(".,:") == label.lower()]
    if not matches:
        raise RuntimeError(f"Missing visibly rendered word: {label}")
    return min(matches, key=lambda row: row["top"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "src-tauri/target/release/tauridium")
    parser.add_argument("--input-helper", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "release/evidence/service-menu-wayland")
    parser.add_argument("--case", choices=("dark", "light", "oled"))
    args = parser.parse_args()
    binary, helper = args.binary.resolve(), args.input_helper.resolve()
    for path in (binary, helper):
        if not path.is_file() or not os.access(path, os.X_OK):
            parser.error(f"requires executable: {path}")
    for command in ("sway", "swaymsg", "grim", "wtype", "magick", "tesseract", "dbus-run-session"):
        if not shutil.which(command):
            parser.error(f"requires pinned test dependency: {command}")
    if os.environ.get("WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS"):
        parser.error("remove the WebKit sandbox override")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # An interrupted/failed rerun must never leave an older successful result.
    (output / "result.json").unlink(missing_ok=True)
    requests, inputs, denied = {}, [], set()
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            path = url.path
            with lock:
                requests[path] = requests.get(path, 0) + 1
                if path == "/input":
                    inputs.append(parse_qs(url.query).get("value", [""])[0])
                if path.startswith("/denied/"):
                    denied.add(path.rsplit("/", 1)[-1])
            if path in ("/input", "/pointer") or path.startswith("/denied/"):
                self.send_response(204)
                self.end_headers()
                return
            if path == "/download":
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''alpha.txt")
                self.send_header("Content-Length", str(len(DOWNLOAD)))
                self.end_headers()
                self.wfile.write(DOWNLOAD)
                return
            if path not in ("/alpha", "/beta"):
                self.send_error(404)
                return
            body = b'''<!doctype html><meta charset="utf-8"><title>Service fixture</title>
<style>html,body{margin:0;min-height:100%;background:#20e0a0;color:#111;font:20px sans-serif}
input,button{font:20px sans-serif;margin:8px}a{display:block;margin:25px 8px}</style>
<h1>REAL NATIVE SERVICE VIEW</h1><p>Account-free menu fixture</p>
<input aria-label="Input recovery" placeholder="Input recovery" oninput="document.getElementById('typed').textContent=this.value;fetch('/input?value='+encodeURIComponent(this.value))">
<button onclick="document.getElementById('pointer').textContent='POINTEROK';fetch('/pointer')">Test pointer</button>
<p id="pointer">WAITING FOR POINTER</p><p id="typed">WAITING FOR KEYBOARD</p>
<a href="/download">Download alpha</a>
<script>const request={serviceId:'alpha',label:'Fixture',enabled:true,zoomPercent:100,x:10,y:10,pixelRatio:1,theme:'dark'};
const probes={get_service_menu:{},measure_service_menu:{id:1,measurement:{width:270,height:309,pixelRatio:1,insetX:16,insetY:16}},choose_service_menu:{id:1,action:'settings'},prepare_service_menu:{request}};
Promise.all(Object.entries(probes).map(async([command,args])=>{try{await window.__TAURI_INTERNALS__.invoke(command,args)}
catch(error){if(/not permitted|not authorized|restricted|not allowed|denied/i.test(String(error)))await fetch('/denied/'+command)}}));</script>'''
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    checks, cases = [], []
    theme = None
    try:
        for theme in ([args.case] if args.case else ["dark", "light", "oled"]):
            print(f"Native Wayland menu/toast case: {theme}", flush=True)
            with lock:
                requests.clear()
                inputs.clear()
                denied.clear()
            case_output = output / theme
            case_output.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="tauridium-wayland-menu-") as temporary:
                root = Path(temporary)
                display = NativeDisplay(root, case_output, helper)
                try:
                    data = root / "data/dev.brani.tauridium"
                    data.mkdir(parents=True)
                    downloads = root / "Downloads/Reports"
                    downloads.mkdir(parents=True)
                    services = [{"id": key, "name": name, "recipeId": "custom-website", "isEnabled": True,
                                 "isLocalRecipe": True, "order": index,
                                 "customUrl": f"http://127.0.0.1:{server.server_port}/{key}"}
                                for index, (key, name) in enumerate((("alpha", "Alpha fixture"), ("beta", "Beta fixture")))]
                    settings = {"preloadServices": False, "fetchMissingServiceIcons": False,
                                "closeToSystemTray": False, "sidebarWidth": 220, "sidebarWidthMode": "pixels",
                                "theme": theme, "prettyServiceContextMenu": True,
                                "customTitleTemplatesEnabled": True, "windowTitleTemplate": TITLE,
                                "taskbarTitleTemplate": TITLE, "downloadToasts": True,
                                "downloadToastDuration": 0, "downloadToastLocation": "none",
                                "askEachDownload": False, "downloadDirectory": str(downloads)}
                    for name, value in (("session.json", {"mode": "local", "version": 1}),
                                        ("local_profile.json", {"version": 1, "services": services, "workspaces": []}),
                                        ("app_settings.json", settings)):
                        (data / name).write_text(json.dumps(value), encoding="utf-8")
                    display.start(binary)
                    display.wait(lambda: requests.get("/alpha", 0) > 0 and len(denied) == 4,
                                 "real native service and rejected remote renderer commands")
                    time.sleep(.5)
                    _, initial = display.screenshot("initial")
                    beta = word(initial, "Beta")
                    anchor_y = beta["top"] + beta["height"] // 2
                    display.assert_native("initial")
                    checks.append(f"{theme}: native xdg_shell service and all four remote menu commands rejected")

                    def rendered(name, predicate, label):
                        latest = []
                        def visible():
                            snapshot = display.screenshot(name)
                            display.assert_native(name)
                            latest[:] = [snapshot]
                            return predicate(*snapshot)
                        display.wait(visible, label)
                        return latest[0]

                    def menu_open(name):
                        display.click(205, anchor_y, 273)
                        time.sleep(.3)
                        text, rows = rendered(name, lambda _text, values: all(
                            any(row["text"].strip(".,:") == label for row in values)
                            for label in ("Settings", "Reload", "Duplicate", "Disable")), "visibly painted menu rows")
                        zoom = word(rows, "Zoom")
                        if zoom["left"] + zoom["width"] <= 220:
                            raise RuntimeError("Rendered menu did not extend above the native service")
                        return text, rows

                    def menu_absent(name):
                        text, rows = display.screenshot(name)
                        display.assert_native(name)
                        if any(row["text"].strip(".,:") == "Duplicate" for row in rows):
                            raise RuntimeError(f"Stale menu after {name}")
                        return text, rows

                    # The first opening is deliberately cold: warming the menu or
                    # canceling a preparation first can hide the original stall.
                    _, rows = menu_open("cold-open")
                    checks.append(f"{theme}: cold menu visibly paints above WebKit without another xdg_toplevel")
                    zoom = word(rows, "Zoom")
                    display.click(max(225, zoom["left"] + 5), zoom["top"] + zoom["height"] // 2)
                    settings_path = data / "app_settings.json"
                    def saved():
                        return json.loads(settings_path.read_text(encoding="utf-8"))
                    display.wait(lambda: saved().get("serviceZoomLevels", {}).get("beta", 100) > 100,
                                 "inactive Beta zoom action persistence")
                    if saved().get("serviceZoomLevels", {}).get("alpha", 100) != 100 or requests.get("/beta", 0):
                        raise RuntimeError("Menu action modified or activated the wrong service")
                    menu_absent("action-dismissed")
                    checks.append(f"{theme}: overlapping pointer action persists on inactive target and dismisses")
                    _, rows = menu_open("reset-open")
                    reset = word(rows, "Reset")
                    display.click(reset["left"] + 5, reset["top"] + reset["height"] // 2)
                    display.wait(lambda: saved().get("serviceZoomLevels", {}).get("beta", 100) == 100, "Beta zoom reset")
                    menu_absent("reset-dismissed")

                    menu_open("click-away-open")
                    display.click(900, 450)
                    menu_absent("click-away")
                    for index in range(2):
                        menu_open(f"repeat-{index}-open")
                        display.key("-k", "Escape")
                        menu_absent(f"repeat-{index}-escape")
                    checks.append(f"{theme}: click-away and repeated Escape dismiss without a native-role leak")
                    for index, delay in enumerate((0, .03, .1)):
                        display.click(205, anchor_y, 273, settle=delay)
                        display.click(900, 450)
                        time.sleep(.4)
                        menu_absent(f"opening-cancel-{index}")
                    checks.append(f"{theme}: immediate native click-away cancels warm menu preparation")

                    menu_open("keyboard-restore-open")
                    display.key("-k", "Escape")
                    display.key("-M", "shift", "-k", "F10", "-m", "shift")
                    time.sleep(.35)
                    _, rows = display.screenshot("keyboard-open")
                    word(rows, "Duplicate")
                    display.assert_native("keyboard-open")
                    display.key("-k", "End", "-k", "Escape")
                    menu_absent("keyboard-escape")
                    checks.append(f"{theme}: Escape restores opener focus for keyboard reopening and navigation")

                    menu_open("deactivate-open")
                    display.run("swaymsg", "workspace 2")
                    time.sleep(.2)
                    display.run("swaymsg", "workspace 1")
                    time.sleep(.2)
                    menu_absent("deactivated")

                    def input_recovery(token, name):
                        display.click(350, 195)
                        # Native application shortcuts can own Select All. Verify
                        # fresh typing without assuming the existing value clears.
                        with lock:
                            before = len(inputs)
                        display.text(token)
                        def delivered():
                            with lock:
                                return any(token in value for value in inputs[before:])
                        try:
                            display.wait(delivered, "actual native WebKit keyboard delivery")
                        except RuntimeError:
                            display.screenshot(name + "-failed")
                            raise
                        rendered(name, lambda text, _rows: token in text.replace(" ", ""),
                                 "visibly repainted native service keyboard input")
                    input_recovery("KEYBOARDOK", "keyboard-recovery")
                    display.click(100, anchor_y)
                    display.wait(lambda: requests.get("/beta", 0) > 0, "Beta native service switch")
                    time.sleep(.4)
                    input_recovery("SERVICEOK", "service-switch-recovery")
                    before = requests.get("/pointer", 0)
                    display.click(585, 195)
                    display.wait(lambda: requests.get("/pointer", 0) > before, "native service pointer recovery")
                    text, _ = display.screenshot("pointer-recovery")
                    if "POINTEROK" not in text.replace(" ", ""):
                        raise RuntimeError("Native service did not visibly repaint its pointer action")
                    checks.append(f"{theme}: service switching, keyboard typing and pointer input visibly recover")

                    # A real attachment completion exercises toast allocation
                    # and resizing over native WebKit, not an injected preview.
                    _, rows = display.screenshot("download-link")
                    download = word(rows, "Download")
                    display.click(download["left"] + 10, download["top"] + download["height"] // 2)
                    target = downloads / "alpha.txt"
                    display.wait(lambda: target.is_file() and target.read_bytes() == DOWNLOAD, "exact real download bytes")
                    def toast_visible(text, rows):
                        return "Download complete" in text and any("alpha.txt" in row["text"] for row in rows)
                    rendered("download-toast", toast_visible, "real completed download toast")
                    trace = display.trace.read_text(encoding="utf-8", errors="replace")
                    for event in ("download.finished", "download.toast.created", "download.toast.layout"):
                        if event not in trace:
                            raise RuntimeError(f"Missing real native download diagnostic: {event}")
                    input_recovery("AFTERTOAST", "toast-input-recovery")
                    display.run("swaymsg", '[app_id="tauridium"] floating enable, resize set width 1100 px height 760 px, move position 0 0')
                    display.wait(lambda: any(window.get("rect", {}).get("width") == 1100
                                             and window.get("rect", {}).get("height") == 760
                                             for window in display.tree()[1]), "native owner resize")
                    time.sleep(.4)
                    rendered("download-toast-resized", toast_visible, "download toast after native owner resize")
                    input_recovery("AFTERRESIZE", "resized-input-recovery")
                    checks.append(f"{theme}: real exact-byte toast survives native resize and continued keyboard input without another xdg_toplevel")
                    cases.append({"theme": theme, "xdgToplevelConstructions": display.protocol_toplevels()})
                finally:
                    with lock:
                        events = {"requests": dict(requests), "inputs": list(inputs), "denied": sorted(denied)}
                    (case_output / "fixture-events.json").write_text(json.dumps(events, indent=2) + "\n", encoding="utf-8")
                    display.close()
        result = {"passed": True, "checks": checks, "cases": cases, "nativeWayland": True,
                  "headlessCompositor": "sway", "xwayland": False, "realNativeServiceViews": True,
                  "realPrivateAccountsUsed": False}
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    except Exception as error:
        result = {"passed": False, "case": theme, "error": str(error), "checks": checks, "cases": cases}
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        raise
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
