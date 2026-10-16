"""Production WebKit negative test with synthetic profiles, native IPC and live origin transitions."""
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
NAVIGATIONS = ("tauri://localhost/index.html", "http://tauri.localhost/index.html",
               "https://tauri.localhost/index.html", "http://asset.localhost/test",
               "file:///tmp/tauridium-boundary-nonexistent.txt", "data:text/html,untrusted")
COMMANDS = ("get_app_metadata", "get_app_settings", "set_app_settings", "clear_service_cache", "export_backup")


def validate_reports(reports: list[dict], first: str, second: str) -> None:
  expected = {"initial", "cross-origin"} | {f"navigation-{index}" for index in range(len(NAVIGATIONS))}
  if len(reports) != len(expected) or {row.get("case") for row in reports} != expected:
    raise RuntimeError("Missing/duplicate production heartbeat; silence is never proof of blocked navigation")
  for row in reports:
    cross = row["case"] == "cross-origin"
    origin = second if cross else first
    if row.get("origin") != origin or row.get("url") != origin + "/fixture":
      raise RuntimeError("Service left its expected HTTP fixture after a prohibited navigation")
    if row.get("recipe") is not (not cross):
      raise RuntimeError("Personal recipe did not run initially or escaped its configured origin")
    commands = row.get("commands")
    if row["case"] in ("initial", "cross-origin") or commands is not None:
      if not isinstance(commands, dict):
        raise RuntimeError("Missing native command authorization observations")
      if set(commands) != set(COMMANDS) or any(value not in ("interface-absent", "authorization-denied") for value in commands.values()):
        raise RuntimeError("Service native command succeeded or failed for a reason other than authorization")


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--binary", type=Path, default=ROOT / "src-tauri/target/release/tauridium")
  parser.add_argument("--dbus-config", type=Path, required=True)
  parser.add_argument("--output", type=Path, default=Path("release/evidence/security-boundary-smoke"))
  args = parser.parse_args()
  binary = args.binary.resolve(strict=True)
  if not args.dbus_config.is_file():
    parser.error("private D-Bus configuration does not exist")
  if not os.environ.get("DISPLAY") or os.environ.get("WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS"):
    parser.error("requires isolated X11; WebKit sandbox disabling is forbidden")
  output = args.output.resolve()
  output.mkdir(parents=True, exist_ok=True)
  output.chmod(0o700)
  reports: list[dict] = []
  condition = threading.Condition()
  failures: list[str] = []
  servers: list[ThreadingHTTPServer] = []

  class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
      pass

    def do_POST(self):
      length = int(self.headers.get("Content-Length", "0"))
      if self.path != "/report" or not 0 < length <= 16 * 1024:
        self.send_error(400)
        return
      try:
        report = json.loads(self.rfile.read(length))
        with condition:
          reports.append(report)
          condition.notify_all()
      except (ValueError, TypeError):
        failures.append("Invalid fixture report")
      self.send_response(204)
      self.end_headers()

    def do_GET(self):
      if self.path != "/fixture":
        self.send_error(404)
        return
      settings = {"cross": self.server is servers[1], "next": f"http://127.0.0.1:{servers[1].server_port}/fixture",
                  "navigations": NAVIGATIONS, "commands": COMMANDS, "canary": str(canary), "export": str(export)}
      script = r'''
        const config = CONFIG;
        const pause = () => new Promise(resolve => setTimeout(resolve, 400));
        async function checkCommands() {
          const results = {};
          for (const name of config.commands) {
            const invoke = window.__TAURI_INTERNALS__?.invoke;
            if (typeof invoke !== 'function') { results[name] = 'interface-absent'; continue; }
            try {
              await Promise.race([invoke(name, {serviceId: config.canary, path: config.export,
                patch: {downloadToasts: true}}), new Promise((_, reject) => setTimeout(() => reject('timeout'), 2500))]);
              results[name] = 'UNEXPECTED-SUCCESS';
            } catch (error) {
              results[name] = /not authorized|not allowed|forbidden|denied/i.test(String(error))
                ? 'authorization-denied' : 'WRONG-FAILURE';
            }
          }
          return results;
        }
        async function report(name, commands) {
          await fetch('/report', {method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({case:name, origin:location.origin, url:location.href,
              recipe:window.__tauridiumRecipeBoundaryProbe === true, ...(commands ? {commands} : {})})});
        }
        (async () => {
          await report(config.cross ? 'cross-origin' : 'initial', await checkCommands());
          if (config.cross) return;
          for (let i = 0; i < config.navigations.length; i++) {
            try { location.assign(config.navigations[i]); } catch (_) {}
            await pause();
            await report('navigation-' + i);
          }
          location.assign(config.next);
        })();
      '''.replace("CONFIG", json.dumps(settings))
      body = ("<!doctype html><html><meta charset='utf-8'><title>Security boundary fixture</title>"
              "<h1>Isolated production security fixture</h1><script>" + script + "</script></html>").encode()
      self.send_response(200)
      self.send_header("Content-Type", "text/html; charset=utf-8")
      self.send_header("Content-Length", str(len(body)))
      self.end_headers()
      self.wfile.write(body)

  with tempfile.TemporaryDirectory(prefix="tauridium-private-boundary-") as temporary:
    root = Path(temporary)
    environment = isolated_environment(root)
    environment.update(GDK_BACKEND="x11", LIBGL_ALWAYS_SOFTWARE="1")
    build_info = root / "build-info.json"
    subprocess.run([str(binary), "--build-info-file", str(build_info)], env=environment, check=True, timeout=20)
    if json.loads(build_info.read_text(encoding="utf-8")).get("buildMode") != "production":
      raise RuntimeError("Security boundary smoke requires an actual production binary")
    canary = root / "outside-service-root"
    canary.mkdir()
    (canary / "sentinel").write_text("Synthetic safety canary", encoding="utf-8")
    export = root / "unexpected-export.json"
    for _ in range(2):
      server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
      server.daemon_threads = True
      servers.append(server)
    for server in servers:
      threading.Thread(target=server.serve_forever, daemon=True).start()
    first, second = (f"http://127.0.0.1:{server.server_port}" for server in servers)
    data = root / "data/dev.brani.tauridium"
    recipe = root / "config/dev.brani.tauridium/recipes/security-probe"
    data.mkdir(parents=True)
    recipe.mkdir(parents=True)
    settings = {"fetchMissingServiceIcons": False, "preloadServices": False, "downloadToasts": False,
                "closeToSystemTray": False}
    profile = {"version": 1, "services": [{"id": "security-probe", "name": "Security boundary probe",
               "recipeId": "security-probe", "isLocalRecipe": True, "isEnabled": True,
               "customUrl": first + "/fixture"}], "workspaces": []}
    for name, value in (("session.json", {"mode": "local", "version": 1}), ("local_profile.json", profile),
                        ("app_settings.json", settings)):
      (data / name).write_text(json.dumps(value), encoding="utf-8")
    (recipe / "package.json").write_text(json.dumps({"id": "security-probe", "name": "Security boundary probe",
        "version": "1.0.0", "config": {"serviceURL": first + "/fixture"}}), encoding="utf-8")
    (recipe / "webview.js").write_text("window.__tauridiumRecipeBoundaryProbe = true;", encoding="utf-8")
    try:
      with (output / "application.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(["dbus-run-session", f"--config-file={args.dbus_config}", "--", str(binary)],
                                   env=environment, stdout=log, stderr=log, start_new_session=True)
        try:
          with condition:
            if not condition.wait_for(lambda: any(row.get("case") == "cross-origin" for row in reports) or failures, timeout=40):
              raise RuntimeError("Production fixture did not complete; navigation/IPC silence is not a pass")
          if failures:
            raise RuntimeError(failures[0])
          validate_reports(reports, first, second)
          if not (canary / "sentinel").is_file() or export.exists():
            raise RuntimeError("Remote service deleted a synthetic canary or wrote an unauthorized export")
          persisted = json.loads((data / "app_settings.json").read_text(encoding="utf-8"))
          if persisted.get("downloadToasts") is not False:
            raise RuntimeError("Service changed privileged application settings")
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
      for server in servers:
        server.shutdown()
        server.server_close()
  result = {"passed": True, "productionWebview": True, "nativeCommandsDenied": len(COMMANDS),
            "prohibitedNavigations": len(NAVIGATIONS), "liveHeartbeatsVerified": len(reports),
            "recipeBoundToInitialOrigin": True, "syntheticCanaryPreserved": True,
            "unauthorizedExportAbsent": True, "isolatedProfile": True,
            "craftedBackupUiTested": False, "nativeWindowsRuntimeTested": False}
  (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
  print(json.dumps(result, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
