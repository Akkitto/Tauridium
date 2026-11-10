"""Account-free production sidebar badge tests with real pinned recipe DOM selectors."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time

from nix_smoke import isolated_environment

ROOT = Path(__file__).resolve().parents[1]
HTML = br'''<!doctype html><html><head><meta charset="utf-8">
<meta property="og:url" content="https://web.telegram.org/k/"><title>Badge fixture</title></head>
<body><h1>Synthetic badge fixture</h1><p>No accounts or messages.</p><div id="rows"></div><script>
let step = -1;
async function tick() {
  const next = await fetch('/state').then(r => r.json());
  if (step === next.step) return;
  step = next.step;
  try {
    if (next.kind === 'api') {
      window.__pakeUnread = 9; // Explicit browser clears must override a stale recipe.
      if (next.clear) await navigator.clearAppBadge();
      else await navigator.setAppBadge(next.count);
    } else if (next.kind === 'github') {
      document.getElementById('rows').innerHTML =
        '<li data-item-id="inbox"><span class="Counter">'+next.direct+'</span></li>'+
        '<span data-target="notification-indicator.badge" '+(next.indirect?'':'hidden')+'></span>';
    } else if (next.kind === 'discord') {
      document.title = next.indirect ? '\u2022 Discord' : 'Discord';
      document.getElementById('rows').innerHTML =
        '<div class="lowerBadge_test"><span class="numberBadge_test">'+next.direct+'</span></div>';
    } else if (next.kind === 'telegram') {
      document.getElementById('rows').innerHTML =
        '<div class="rp" data-peer-id="42"><span class="dialog-subtitle-badge">'+next.direct+'</span></div>'+
        '<div class="rp" data-peer-id="-42"><span class="dialog-subtitle-badge">'+next.indirect+'</span></div>';
    }
    await fetch('/result', {method:'POST', body:JSON.stringify({step})});
  } catch (error) {
    await fetch('/result', {method:'POST', body:JSON.stringify({step, error:String(error)})});
  }
}
tick(); setInterval(tick, 200);
</script></body></html>'''


def wait_for(predicate, description, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for {description}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--dbus-config", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, default=ROOT / "tools/fixtures/badges")
    parser.add_argument("--recipe-revision", required=True)
    parser.add_argument("--output", type=Path, default=Path("release/evidence/unread-badges"))
    parser.add_argument("--case", choices=("api", "github", "discord", "discord-indirect", "telegram"), action="append")
    args = parser.parse_args()
    if not args.binary.is_file() or not args.dbus_config.is_file() or not os.environ.get("DISPLAY"):
        parser.error("requires a production binary, private D-Bus configuration and isolated X11 DISPLAY")
    if os.environ.get("WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS"):
        parser.error("remove the WebKit sandbox override before testing")
    if len(args.recipe_revision) != 40 or any(c not in "0123456789abcdef" for c in args.recipe_revision):
        parser.error("recipe revision must be a full immutable commit")
    binary = args.binary.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    completed = []
    cases = args.case or ["api", "github", "discord", "discord-indirect", "telegram"]
    for case in cases:
        kind = "discord" if case == "discord-indirect" else case
        include_indirect = case == "discord-indirect"
        pairs = [(3, 1), (0, 1), (0, 0), (5, 1), (0, 0)]
        states = [(17, False), (3, False), (0, False), (4, False), (0, True)]
        if kind != "api":
            states = [(d or i if kind == "github" else d + (i if include_indirect else 0), False) for d, i in pairs]
        state = {"step": 0, "kind": kind, "count": states[0][0], "direct": 3, "indirect": 1, "clear": False}
        reports = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                if self.path not in ("/state", "/fixture"):
                    self.send_error(404)
                    return
                body = json.dumps(state).encode() if self.path == "/state" else HTML
                self.send_response(200)
                self.send_header("Content-Type", "application/json" if self.path == "/state" else "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                size = int(self.headers.get("Content-Length", 0))
                if self.path != "/result" or not 0 < size <= 4096:
                    self.send_error(400)
                    return
                reports.append(json.loads(self.rfile.read(size)))
                self.send_response(204)
                self.end_headers()

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        destination = output / case
        destination.mkdir(exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix="tauridium-badge-smoke-") as temporary:
                profile = Path(temporary)
                environment = isolated_environment(profile)
                environment.update(GDK_BACKEND="x11", LIBGL_ALWAYS_SOFTWARE="1")
                info = profile / "build-info.json"
                subprocess.run([str(binary), "--build-info-file", str(info)], env=environment, check=True, timeout=20)
                if json.loads(info.read_text(encoding="utf-8")).get("buildMode") != "production":
                    raise RuntimeError("Badge smoke requires an actual production executable")
                data = profile / "data/dev.brani.tauridium"
                data.mkdir(parents=True)
                url = f"http://127.0.0.1:{server.server_port}/fixture"
                recipe_id = "github" if kind == "github" else "badge-probe"
                service = {"id": "badge-probe", "recipeId": recipe_id, "name": "Badge probe",
                           "isLocalRecipe": kind != "github", "isEnabled": True,
                           "isIndirectMessageBadgeEnabled": include_indirect, "customUrl": url}
                for name, value in {
                    "session.json": {"mode": "local", "version": 1},
                    "local_profile.json": {"version": 1, "services": [service], "workspaces": []},
                    "app_settings.json": {"fetchMissingServiceIcons": False, "preloadServices": False,
                                          "closeToSystemTray": False, "downloadToasts": False},
                }.items():
                    (data / name).write_text(json.dumps(value), encoding="utf-8")
                package = {"id": recipe_id, "name": "Badge probe", "version": "1.0.0",
                           "config": {"serviceURL": url, "hasCustomUrl": True}}
                if kind == "github":
                    # Exercise the real pinned-cache loader, not a personal recipe
                    # that intentionally bypasses the stock GitHub adapter.
                    cache = profile / "cache/dev.brani.tauridium/remote-recipes" / args.recipe_revision
                    cache.mkdir(parents=True)
                    (cache / "github.json").write_text(json.dumps(package), encoding="utf-8")
                    (cache / "github.webview.js").write_bytes((args.fixtures / "github.js").read_bytes())
                else:
                    recipe = profile / "config/dev.brani.tauridium/recipes" / recipe_id
                    recipe.mkdir(parents=True)
                    (recipe / "package.json").write_text(json.dumps(package), encoding="utf-8")
                    if kind != "api":
                        (recipe / "webview.js").write_bytes((args.fixtures / f"{kind}.js").read_bytes())
                with (destination / "application.log").open("w", encoding="utf-8") as log:
                    process = subprocess.Popen(["dbus-run-session", f"--config-file={args.dbus_config}", "--", str(binary)],
                                               env=environment, stdout=log, stderr=log, start_new_session=True)
                    try:
                        wait_for(lambda: reports, f"{case} live fixture")
                        def window():
                            result = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", "Tauridium"],
                                                    env=environment, capture_output=True, text=True, encoding="utf-8", timeout=10)
                            return result.stdout.strip().splitlines()[-1] if result.stdout.strip() else None
                        identifier = wait_for(window, f"{case} native window")
                        for index, (count, clear) in enumerate(states):
                            state.update(step=index, count=count, clear=clear,
                                         direct=pairs[index][0], indirect=pairs[index][1])
                            row = wait_for(lambda: next((r for r in reports if r.get("step") == index), None), f"{case} phase {index}")
                            if row.get("error"):
                                raise RuntimeError(f"{case} browser badge fixture failed")
                            png = destination / f"phase-{index}.png"
                            def rendered():
                                subprocess.run(["magick", "import", "-window", identifier, str(png)], env=environment, check=True, timeout=10)
                                # The page is plain black text. Find the actual red sidebar
                                # badge in the upper-left area instead of fixing its position.
                                rgb = subprocess.check_output(["magick", str(png), "-crop", "500x200+0+0", "-depth", "8", "rgb:-"], env=environment, timeout=10)
                                points = [(i // 3 % 500, i // 3 // 500) for i in range(0, len(rgb), 3)
                                          if rgb[i] > 180 and rgb[i + 1] < 100 and rgb[i + 2] < 130]
                                if not count:
                                    return not points
                                if len(points) < 10:
                                    return False
                                left = max(0, min(x for x, _ in points) - 4)
                                top = max(0, min(y for _, y in points) - 4)
                                width = max(x for x, _ in points) - left + 5
                                height = max(y for _, y in points) - top + 5
                                crop = subprocess.check_output(["magick", str(png), "-crop", f"{width}x{height}+{left}+{top}", "-resize", "600%", "png:-"], env=environment, timeout=10)
                                text = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "7", "-c", "tessedit_char_whitelist=0123456789"],
                                                      input=crop, env=environment, capture_output=True, check=True, timeout=10).stdout.decode("utf-8").strip()
                                return text == str(count)
                            wait_for(rendered, f"{case} rendered badge {count}")
                            completed.append({"case": case, "phase": index, "count": count})
                            print(f"Verified production badge: {case}, phase {index}, count {count}", flush=True)
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
        finally:
            server.shutdown()
            server.server_close()
    result = {"passed": True, "productionWebview": True, "isolatedProfiles": True,
              "authenticatedAccountsUsed": False, "states": completed}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "renderedStates": len(completed)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
