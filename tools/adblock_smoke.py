#!/usr/bin/env python3
"""Account-free production ad blocking smoke test in isolated profiles.

Runs the real production executable against a local fixture site and uses the
fixture server's request log as ground truth: a request that was blocked never
reaches the server. Filter lists are pre-seeded into the profile cache, so no
list is downloaded and the test needs no internet.

Scenarios (each starts a fresh app process):
  block      blocking on, warm filter store: listed requests (including those in
             a cross-host iframe) are blocked on the FIRST load, an exception
             rule is honoured and clean requests load.
  cold       blocking on, no compiled filter yet: the filter is compiled and
             stored in the background (the first page may already be loaded).
  off        global switch off: nothing is blocked.
  service    global on, service override off: nothing is blocked.
  allowlist  global on, fixture host allowlisted: nothing is blocked.
  restart    the settings from `service` and `block` survive a restart of the
             same profile.
  offline    a due list refresh cannot reach the network (dead proxy): the
             cached list keeps blocking, the failure is recorded once, and the
             only connection attempts are for the selected list address.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ID = "adblock-probe"
LIST_TEXT = "[Adblock Plus 2.0]\n! Title: Fixture\n/adserver.js\n/tracker.gif\n@@/allowed/adserver.js\n"
CATALOG_URL = "https://easylist.to/easylist/easylist.txt"


def page(port: int, query: str) -> str:
  return (
    '<!doctype html><html><head><meta charset="utf-8"><title>Adblock fixture</title></head><body>'
    f'<script src="/adserver.js?{query}"></script>'
    f'<script src="/allowed/adserver.js?{query}"></script>'
    f'<script src="/clean.js?{query}"></script>'
    f'<img src="/tracker.gif?{query}">'
    f'<iframe src="http://localhost:{port}/frame.html?{query}"></iframe>'
    "</body></html>"
  )


class Fixture:
  """Fixture site whose request log shows what the web engine actually fetched."""

  def __init__(self) -> None:
    self.requests: list[tuple[str, str]] = []
    self.lock = threading.Lock()
    fixture = self

    class Handler(BaseHTTPRequestHandler):
      def log_message(self, *_args):
        pass

      def do_GET(self):
        host = (self.headers.get("Host") or "?").split(":")[0]
        with fixture.lock:
          fixture.requests.append((host, self.path))
        port = self.server.server_port
        if self.path.startswith("/fixture"):
          body, kind = page(port, "n=1").encode(), "text/html; charset=utf-8"
        elif self.path.startswith("/frame.html"):
          body, kind = b'<html><body><script src="/adserver.js?frame"></script></body></html>', "text/html; charset=utf-8"
        elif self.path.startswith("/tracker.gif"):
          body, kind = b"GIF89a", "image/gif"
        else:
          body, kind = b"1;", "application/javascript"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    self.server.daemon_threads = True
    threading.Thread(target=self.server.serve_forever, daemon=True).start()

  @property
  def port(self) -> int:
    return self.server.server_port

  def seen(self, prefix: str, *, frame: bool | None = None) -> bool:
    with self.lock:
      for _host, path in self.requests:
        if not path.startswith(prefix):
          continue
        in_frame = "frame" in path
        if frame is None or frame == in_frame:
          return True
    return False

  def summary(self) -> dict[str, bool]:
    return {
      "adserver": self.seen("/adserver.js", frame=False),
      "allowed": self.seen("/allowed/adserver.js"),
      "clean": self.seen("/clean.js"),
      "tracker": self.seen("/tracker.gif"),
      "iframe_adserver": self.seen("/adserver.js", frame=True),
    }

  def close(self) -> None:
    self.server.shutdown()
    self.server.server_close()


class Proxy:
  """Dead HTTP proxy that records every CONNECT target, simulating no network."""

  def __init__(self) -> None:
    self.targets: list[str] = []
    self.sock = socket.socket()
    self.sock.bind(("127.0.0.1", 0))
    self.sock.listen(16)
    threading.Thread(target=self._serve, daemon=True).start()

  @property
  def port(self) -> int:
    return self.sock.getsockname()[1]

  def _serve(self) -> None:
    while True:
      try:
        client, _ = self.sock.accept()
      except OSError:
        return
      try:
        data = client.recv(4096).decode("latin-1", "replace")
        first = data.split("\r\n", 1)[0].split()
        if len(first) >= 2:
          self.targets.append(first[1])
        client.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
      except OSError:
        pass
      finally:
        client.close()

  def close(self) -> None:
    self.sock.close()


def wait_for(predicate, description: str, timeout: float = 40.0):
  deadline = time.monotonic() + timeout
  while time.monotonic() < deadline:
    result = predicate()
    if result:
      return result
    time.sleep(0.2)
  raise RuntimeError(f"Timed out waiting for {description}")


def seed_profile(profile: Path, fixture_url: str, settings: dict, *, lists: bool, due: bool) -> Path:
  data = profile / "data/dev.brani.tauridium"
  data.mkdir(parents=True, exist_ok=True)
  service = {"id": SERVICE_ID, "recipeId": SERVICE_ID, "name": "Adblock probe", "isLocalRecipe": True,
             "isEnabled": True, "customUrl": fixture_url}
  base_settings = {"fetchMissingServiceIcons": False, "preloadServices": False, "closeToSystemTray": False,
                   "downloadToasts": False}
  base_settings.update(settings)
  for name, value in {
    "session.json": {"mode": "local", "version": 1},
    "local_profile.json": {"version": 1, "services": [service], "workspaces": []},
    "app_settings.json": base_settings,
  }.items():
    path = data / name
    if not path.exists() or name == "app_settings.json":
      path.write_text(json.dumps(value), encoding="utf-8")
  recipe = profile / "config/dev.brani.tauridium/recipes" / SERVICE_ID
  recipe.mkdir(parents=True, exist_ok=True)
  (recipe / "package.json").write_text(json.dumps({
    "id": SERVICE_ID, "name": "Adblock probe", "version": "1.0.0",
    "config": {"serviceURL": fixture_url, "hasCustomUrl": True}}), encoding="utf-8")
  if lists:
    cache = data / "adblock"
    (cache / "lists").mkdir(parents=True, exist_ok=True)
    (cache / "lists/easylist.txt").write_text(LIST_TEXT, encoding="utf-8")
    meta = {"url": CATALOG_URL, "lastUpdated": 1, "nextCheck": 1 if due else 4102444800, "etag": None,
            "networkRules": 3, "cosmeticRules": 0,
            "contentHash": hashlib.sha256(LIST_TEXT.encode()).hexdigest(), "lastError": None, "errorReported": False}
    (cache / "lists.json").write_text(json.dumps({"version": 1, "lists": {"easylist": meta}}), encoding="utf-8")
  return data


def environment(profile: Path, args, proxy: Proxy | None) -> dict[str, str]:
  env = dict(os.environ)
  for variable, directory in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"),
                              ("XDG_STATE_HOME", "state"), ("XDG_RUNTIME_DIR", "runtime")):
    env[variable] = str(profile / directory)
  if args.dbus_config:
    # CI uses a private bus that must not discover host portal services.
    env["XDG_DATA_DIRS"] = env["XDG_DATA_HOME"]
  # Otherwise keep the host data directories so GTK finds its schemas and themes.
  env.update(GDK_BACKEND="x11", LIBGL_ALWAYS_SOFTWARE="1", NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")
  if proxy:
    env.update(HTTPS_PROXY=f"http://127.0.0.1:{proxy.port}", https_proxy=f"http://127.0.0.1:{proxy.port}")
  return env


def run_app(profile: Path, args, fixture: Fixture, *, proxy: Proxy | None, until, log: Path) -> None:
  env = environment(profile, args, proxy)
  command = [str(args.binary)]
  if args.dbus_config:
    command = ["dbus-run-session", f"--config-file={args.dbus_config}", "--", *command]
  else:
    command = ["dbus-run-session", "--", *command]
  with log.open("w", encoding="utf-8") as stream:
    process = subprocess.Popen(command, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
    try:
      wait_for(lambda: fixture.seen("/clean.js"), "the service page to load")
      until()
    finally:
      try:
        os.killpg(process.pid, signal.SIGTERM)
      except ProcessLookupError:
        pass
      try:
        process.wait(timeout=15)
      except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=15)


def settle(seconds: float = 2.5) -> None:
  time.sleep(seconds)


def expect(case: str, got: dict[str, bool], want: dict[str, bool]) -> None:
  if got != want:
    raise AssertionError(f"{case}: fixture saw {got}, expected {want}")
  print(f"PASS {case}: {got}", flush=True)


BLOCKED = {"adserver": False, "allowed": True, "clean": True, "tracker": False, "iframe_adserver": False}
OPEN = {"adserver": True, "allowed": True, "clean": True, "tracker": True, "iframe_adserver": True}


def scenario(name: str, args, output: Path) -> dict:
  fixture = Fixture()
  proxy = Proxy() if name == "offline" else None
  url = f"http://127.0.0.1:{fixture.port}/fixture"
  settings_by_case = {
    "block": {"adblockEnabled": True, "adblockLists": ["easylist"]},
    "cold": {"adblockEnabled": True, "adblockLists": ["easylist"]},
    "off": {"adblockEnabled": False, "adblockLists": ["easylist"]},
    "service": {"adblockEnabled": True, "adblockLists": ["easylist"], "serviceAdblock": {SERVICE_ID: {"enabled": False}}},
    "allowlist": {"adblockEnabled": True, "adblockLists": ["easylist"], "adblockAllowlist": ["127.0.0.1"]},
    "offline": {"adblockEnabled": True, "adblockLists": ["easylist"]},
  }
  result: dict = {"case": name}
  destination = output / name
  destination.mkdir(parents=True, exist_ok=True)
  try:
    with tempfile.TemporaryDirectory(prefix="tauridium-adblock-smoke-") as temporary:
      profile = Path(temporary)
      for directory in ("config", "data", "cache", "state", "runtime"):
        (profile / directory).mkdir(mode=0o700, exist_ok=True)
      settings = settings_by_case["service" if name == "restart" else name]
      data = seed_profile(profile, url, settings, lists=True, due=name == "offline")
      if name in ("block", "restart"):
        # Warm the store with a first run, then judge a second, cold-process run.
        run_app(profile, args, fixture, proxy=None, until=lambda: wait_for(
          lambda: any((data / "adblock/filters").glob("ContentRuleList-*")), "the compiled filter"),
          log=destination / "warmup.log")
        fixture.requests.clear()
      if name == "restart":
        # The same profile and settings file, a fresh process: nothing is blocked
        # because the service override persisted.
        run_app(profile, args, fixture, proxy=None, until=settle, log=destination / "application.log")
        expect("restart (override persisted, nothing blocked)", fixture.summary(), OPEN)
        settings = settings_by_case["block"]
        seed_profile(profile, url, settings, lists=True, due=False)
        fixture.requests.clear()
        run_app(profile, args, fixture, proxy=None, until=settle, log=destination / "application2.log")
        expect("restart (blocking persisted, first load blocked)", fixture.summary(), BLOCKED)
      elif name == "cold":
        run_app(profile, args, fixture, proxy=None, until=lambda: wait_for(
          lambda: any((data / "adblock/filters").glob("ContentRuleList-*")), "the compiled filter"),
          log=destination / "application.log")
        result["firstLoad"] = fixture.summary()
        print(f"INFO cold start first load (informational): {result['firstLoad']}", flush=True)
        fixture.requests.clear()
        run_app(profile, args, fixture, proxy=None, until=settle, log=destination / "application2.log")
        expect("cold (second start, first load blocked)", fixture.summary(), BLOCKED)
      elif name == "offline":
        def refreshed() -> bool:
          meta = json.loads((data / "adblock/lists.json").read_text(encoding="utf-8"))["lists"]["easylist"]
          return meta.get("lastError") is not None
        run_app(profile, args, fixture, proxy=proxy, until=lambda: wait_for(refreshed, "the failed refresh to be recorded", 60), log=destination / "application.log")
        meta = json.loads((data / "adblock/lists.json").read_text(encoding="utf-8"))["lists"]["easylist"]
        if meta["contentHash"] != hashlib.sha256(LIST_TEXT.encode()).hexdigest():
          raise AssertionError("offline: the cached list was replaced by a failed update")
        if meta["errorReported"] is not True:
          raise AssertionError("offline: the failure episode was not recorded as reported")
        expect("offline (cached list still blocks)", fixture.summary(), BLOCKED)
        # The app makes its own unrelated connections (recipe catalog). Compare with
        # a run that has blocking off: blocking may add only the selected list host.
        with_blocking = {target.split(":")[0] for target in proxy.targets}
        proxy.targets.clear()
        seed_profile(profile, url, {"adblockEnabled": False, "adblockLists": ["easylist"]}, lists=True, due=True)
        fixture.requests.clear()
        run_app(profile, args, fixture, proxy=proxy, until=lambda: time.sleep(20), log=destination / "baseline.log")
        baseline = {target.split(":")[0] for target in proxy.targets}
        added = sorted(with_blocking - baseline)
        if added != ["easylist.to"]:
          raise AssertionError(f"offline: blocking contacted {added}, expected only easylist.to (baseline {sorted(baseline)})")
        print(f"PASS offline: blocking added only the selected list address (baseline {sorted(baseline)})", flush=True)
        result["addedHosts"] = added
      else:
        run_app(profile, args, fixture, proxy=None, until=settle, log=destination / "application.log")
        expect(name, fixture.summary(), BLOCKED if name == "block" else OPEN)
  finally:
    fixture.close()
    if proxy:
      proxy.close()
  result["passed"] = True
  return result


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--binary", type=Path, required=True)
  parser.add_argument("--dbus-config", type=Path, help="private D-Bus configuration (CI); omit for a local run")
  parser.add_argument("--output", type=Path, default=Path("release/evidence/adblock-smoke"))
  parser.add_argument("--case", choices=("block", "cold", "off", "service", "allowlist", "restart", "offline"), action="append")
  args = parser.parse_args()
  if not args.binary.is_file() or not os.environ.get("DISPLAY"):
    parser.error("requires a production executable and an X11 DISPLAY")
  if args.dbus_config and not args.dbus_config.is_file():
    parser.error("--dbus-config must name an existing file")
  if os.environ.get("WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS"):
    parser.error("remove the WebKit sandbox override before testing")
  args.binary = args.binary.resolve(strict=True)
  output = args.output.resolve()
  output.mkdir(parents=True, exist_ok=True)
  info = output / "build-info.json"
  subprocess.run([str(args.binary), "--build-info-file", str(info)], check=True, timeout=20)
  if json.loads(info.read_text(encoding="utf-8")).get("buildMode") != "production":
    raise RuntimeError("The ad blocking smoke test requires an actual production executable")
  results = [scenario(case, args, output) for case in (args.case or ["block", "cold", "off", "service", "allowlist", "restart", "offline"])]
  (output / "result.json").write_text(json.dumps({"passed": True, "productionWebview": True, "cases": results}, indent=2) + "\n", encoding="utf-8")
  print(json.dumps({"passed": True, "cases": [r["case"] for r in results]}))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
