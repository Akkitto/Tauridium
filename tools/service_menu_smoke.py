#!/usr/bin/env python3
"""Exercise the production styled menu over real, isolated native service views."""
from __future__ import annotations

import argparse
import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit

from nix_smoke import isolated_environment

ROOT = Path(__file__).resolve().parents[1]
TITLE = "Tauridium service menu regression"
BUS = '''<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>
<policy context="default"><allow send_destination="*" eavesdrop="true"/>
<allow eavesdrop="true"/><allow own="*"/></policy></busconfig>'''


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--binary', type=Path, default=ROOT / 'src-tauri/target/release/tauridium')
  parser.add_argument('--output', type=Path, default=ROOT / 'release/evidence/service-menu')
  parser.add_argument('--case', choices=('dark', 'light', 'oled', 'native'))
  args = parser.parse_args()
  if not args.binary.is_file() or not os.environ.get('DISPLAY'):
    parser.error('requires a production binary and an isolated X11 display')
  for command in ('xdotool', 'magick', 'tesseract', 'dbus-run-session'):
    if not shutil.which(command): parser.error(f'requires {command}')
  if os.environ.get('WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS'):
    parser.error('remove the WebKit sandbox override')
  output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
  requests: dict[str, int] = {}
  denied: set[str] = set()
  lock = threading.Lock()

  class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args): pass
    def do_GET(self):
      path = urlsplit(self.path).path
      if path.startswith('/denied/'):
        with lock: denied.add(path.rsplit('/', 1)[-1])
        self.send_response(204); self.end_headers(); return
      if path not in ('/alpha', '/beta'):
        self.send_error(404); return
      with lock: requests[path] = requests.get(path, 0) + 1
      body = b'''<!doctype html><meta charset="utf-8"><title>Service fixture</title>
      <style>html,body{margin:0;min-height:100%;background:#20e0a0;color:#111;font:20px sans-serif}</style>
      <h1>REAL NATIVE SERVICE VIEW</h1><p>Account-free menu fixture</p>
      <script>const request={serviceId:'alpha',label:'Fixture',enabled:true,zoomPercent:100,x:10,y:10,pixelRatio:1,theme:'dark'};
      const probes={get_service_menu:{},measure_service_menu:{id:1,measurement:{width:270,height:309,pixelRatio:1,insetX:16,insetY:16}},choose_service_menu:{id:1,action:'settings'},prepare_service_menu:{request}};
      Promise.all(Object.entries(probes).map(async([command,args])=>{
        try { await window.__TAURI_INTERNALS__.invoke(command,args); }
        catch(error) { if(/not permitted|not authorized|restricted|not allowed|denied/i.test(String(error))) await fetch('/denied/'+command); }
      }));</script>'''
      self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8')
      self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

  server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); server.daemon_threads = True
  threading.Thread(target=server.serve_forever, daemon=True).start()
  checks: list[str] = []

  def wait(predicate, label, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
      if predicate(): return
      time.sleep(.15)
    raise RuntimeError(f'Timed out: {label}')

  def xdo(*arguments):
    return subprocess.check_output(['xdotool', *map(str, arguments)], text=True, stderr=subprocess.PIPE, timeout=10).strip()

  def screenshot(window, name):
    path = output / f'{name}.png'
    subprocess.run(['magick', 'import', '-window', 'root' if theme == 'native' else window, str(path)], check=True, timeout=10)
    rows = []
    # Tile the small menu/sidebar separately: whole-window OCR thresholding can
    # discard their text beside the bright fixture or a large service heading.
    for left, width in [(0, 220), (220, 330)]:
      png = subprocess.run(['magick', str(path), '-crop', f'{width}x680+{left}+25', '+repage', '-resize', '300%', '-colorspace', 'Gray', '-normalize', 'png:-'], check=True, capture_output=True, timeout=10).stdout
      ocr = subprocess.run(['tesseract', 'stdin', 'stdout', '--psm', '11', 'tsv'], input=png, check=True, capture_output=True, timeout=30).stdout.decode()
      for row in csv.DictReader(io.StringIO(ocr), delimiter='\t'):
        if not row.get('text', '').strip(): continue
        for field in ('left', 'top', 'width', 'height'): row[field] = round(int(row[field]) / 3)
        row['left'] += left; row['top'] += 25
        rows.append(row)
    # A focused light-theme first row has an outline that OCR can mistake for
    # an enclosing box. Read that text line independently, without the outline.
    if any(row['text'] == 'Reload' for row in rows) and not any(row['text'] == 'Settings' for row in rows):
      reload = next(row for row in rows if row['text'] == 'Reload')
      left, top = reload['left'], max(0, reload['top'] - 40)
      png = subprocess.run(['magick', str(path), '-crop', f'210x26+{left}+{top}', '+repage', '-resize', '300%', 'png:-'], check=True, capture_output=True, timeout=10).stdout
      ocr = subprocess.run(['tesseract', 'stdin', 'stdout', '--psm', '7', 'tsv'], input=png, check=True, capture_output=True, timeout=30).stdout.decode()
      for row in csv.DictReader(io.StringIO(ocr), delimiter='\t'):
        if row.get('text') != 'Settings': continue
        for field in ('left', 'top', 'width', 'height'): row[field] = round(int(row[field]) / 3)
        row['left'] += left; row['top'] += top; rows.append(row)
    text = ' '.join(row['text'] for row in rows)
    (output / f'{name}.txt').write_text(text + '\n', encoding='utf-8')
    return text, rows

  def word(rows, text):
    values = [row for row in rows if row['text'].lower().strip('.,:') == text.lower()]
    if not values: raise RuntimeError(f'Missing rendered menu word: {text}')
    return min(values, key=lambda row: row['top'])

  def click(window, x, y, button=1):
    xdo('mousemove', '--sync', '--window', window, x, y); xdo('click', button)

  def read_settings(path): return json.loads(path.read_text(encoding='utf-8'))

  try:
    for theme in ([args.case] if args.case else ['dark', 'light', 'oled', 'native']):
      print(f'Native service-menu case: {theme}', flush=True)
      with lock: requests.clear(); denied.clear()
      with tempfile.TemporaryDirectory(prefix='tauridium-menu-ui-') as temporary:
        root = Path(temporary); env = isolated_environment(root)
        env.update(GDK_BACKEND='x11', GDK_SCALE='1', GDK_DPI_SCALE='1', LIBGL_ALWAYS_SOFTWARE='1', WEBKIT_DISABLE_DMABUF_RENDERER='1')
        data = root / 'data/dev.brani.tauridium'; data.mkdir(parents=True)
        services = [{'id': key, 'name': name, 'recipeId': 'custom-website', 'isEnabled': True, 'isLocalRecipe': True,
                     'order': index, 'customUrl': f'http://127.0.0.1:{server.server_port}/{key}'}
                    for index, (key, name) in enumerate([('alpha', 'Alpha fixture'), ('beta', 'Beta fixture')])]
        settings = {'preloadServices': False, 'fetchMissingServiceIcons': False, 'closeToSystemTray': False,
                    'sidebarWidth': 220, 'sidebarWidthMode': 'pixels', 'theme': theme if theme != 'native' else 'dark',
                    'prettyServiceContextMenu': theme != 'native', 'customTitleTemplatesEnabled': True,
                    'windowTitleTemplate': TITLE, 'taskbarTitleTemplate': TITLE}
        for name, value in [('session.json', {'mode': 'local', 'version': 1}),
                            ('local_profile.json', {'version': 1, 'services': services, 'workspaces': []}),
                            ('app_settings.json', settings)]:
          (data / name).write_text(json.dumps(value), encoding='utf-8')
        info_path = output / f'{theme}-build-info.json'
        subprocess.run([str(args.binary.resolve()), '--build-info-file', str(info_path)], env=env, check=True, timeout=20)
        if json.loads(info_path.read_text(encoding='utf-8')).get('buildMode') != 'production':
          raise RuntimeError('Menu interaction gate requires a genuine production build')
        bus = root / 'session.conf'; bus.write_text(BUS, encoding='utf-8')
        command = ['dbus-run-session', f'--config-file={bus}', '--', str(args.binary.resolve()), '--startup-diagnostics']
        with (output / f'{theme}.log').open('w', encoding='utf-8') as log:
          process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
          try:
            windows = []
            def visible():
              result = subprocess.run(['xdotool', 'search', '--onlyvisible', '--name', f'^{TITLE}$'], text=True, capture_output=True, timeout=5)
              windows.clear()
              for candidate in result.stdout.splitlines():
                try:
                  pid = int(xdo('getwindowpid', candidate))
                  if os.getpgid(pid) == process.pid: windows.append(candidate)
                except (ProcessLookupError, ValueError, subprocess.CalledProcessError): pass
              return result.returncode == 0 and bool(windows)
            wait(visible, 'fixture window'); window = windows[0]
            xdo('windowmove', window, 0, 0); xdo('windowsize', window, 1100, 720); xdo('windowfocus', '--sync', window)
            wait(lambda: requests.get('/alpha', 0) > 0, 'real service load')
            wait(lambda: len(denied) == 4, 'remote renderer command rejection')
            time.sleep(.7)
            _, initial = screenshot(window, f'{theme}-initial')
            row = word(initial, 'Beta'); anchor_y = row['top'] + row['height'] // 2
            # The right edge of the sidebar makes most of the menu overlap the
            # native service, where a shell-only DOM menu used to disappear.
            anchor_x = 212
            def open_menu():
              click(window, anchor_x, anchor_y, 3)
              time.sleep(.5)
              return screenshot(window, f'{theme}-open')
            if theme != 'native':
              click(window, anchor_x, anchor_y, 3); click(window, 900, 450)
              time.sleep(1)
              text, _ = screenshot(window, f'{theme}-cancel-during-opening')
              if 'Duplicate' in text: raise RuntimeError('A pending menu appeared after clicking the native service')
              checks.append(f'{theme}: native service click cancels an opening before presentation')
            text, rows = open_menu()
            for label in ('Settings', 'Reload', 'Duplicate', 'Disable'):
              word(rows, label)
            zoom = word(rows, 'Zoom')
            if zoom['left'] <= 220: raise RuntimeError('Menu fixture did not extend over the native service view')
            checks.append(f'{theme}: all menu rows visibly above native service')
            if theme == 'native':
              xdo('key', 'Escape'); continue
            # A real pointer click over the service area must activate the menu,
            # and changing an inactive target must not alter the active service.
            click(window, zoom['left'] + 5, zoom['top'] + zoom['height'] // 2)
            path = data / 'app_settings.json'
            wait(lambda: read_settings(path).get('serviceZoomLevels', {}).get('beta', 100) > 100, 'inactive target zoom action')
            if read_settings(path).get('serviceZoomLevels', {}).get('alpha', 100) != 100: raise RuntimeError('Menu changed the wrong service')
            checks.append(f'{theme}: overlapping menu accepts pointer action for the correct service')
            open_menu(); click(window, 900, 450); time.sleep(.4)
            text, _ = screenshot(window, f'{theme}-click-away')
            if 'Duplicate' in text or 'Reset zoom' in text: raise RuntimeError('Clicking the service did not dismiss the menu')
            checks.append(f'{theme}: click-away into native service dismisses')
            for _ in range(3):
              click(window, anchor_x, anchor_y, 3); click(window, 900, 450)
            time.sleep(1)
            text, _ = screenshot(window, f'{theme}-warm-opening-cancel')
            if 'Duplicate' in text: raise RuntimeError('A warm opening survived immediate native click-away')
            checks.append(f'{theme}: repeated warm openings cancel on immediate native click-away')
            open_menu(); xdo('windowfocus', 0); time.sleep(.4)
            text, _ = screenshot(window, f'{theme}-deactivated')
            if 'Duplicate' in text: raise RuntimeError('Deactivation did not dismiss the menu')
            xdo('windowfocus', '--sync', window)
            checks.append(f'{theme}: app deactivation dismisses without a blur shield')
            # Escape returns focus to the opening row; selecting a service by
            # left click intentionally moves focus into that service instead.
            open_menu(); xdo('key', 'Escape'); time.sleep(.3)
            xdo('key', 'shift+F10'); time.sleep(.5)
            text, rows = screenshot(window, f'{theme}-keyboard')
            word(rows, 'Duplicate'); xdo('key', 'End'); xdo('key', 'Escape'); time.sleep(.3)
            text, _ = screenshot(window, f'{theme}-escape')
            if 'Duplicate' in text: raise RuntimeError('Escape did not dismiss the keyboard menu')
            checks.append(f'{theme}: keyboard opening, navigation and Escape')
            for _ in range(3): open_menu(); xdo('key', 'Escape')
            open_menu(); xdo('windowsize', window, 800, 560); time.sleep(.4)
            text, _ = screenshot(window, f'{theme}-resize')
            if 'Duplicate' in text: raise RuntimeError('Resize left a stale menu')
            checks.append(f'{theme}: repeated openings and resize cleanup')
            click(window, 100, anchor_y)
            wait(lambda: requests.get('/beta', 0) > 0, 'new service created after closing a menu')
            switched = output / f'{theme}-service-switch.png'
            def service_repainted():
              subprocess.run(['magick', 'import', '-window', window, str(switched)], check=True, timeout=10)
              color = subprocess.check_output(['magick', str(switched), '-crop', '1x1+230+450', '+repage', '-format', '%[fx:round(255*r)],%[fx:round(255*g)],%[fx:round(255*b)]', 'info:'], text=True, timeout=10)
              return color == '32,224,160'
            wait(service_repainted, 'uncovered native service pixels after switching', timeout=15)
            checks.append(f'{theme}: service switching leaves no menu input or paint residue')
          finally:
            try: os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=10)
    result = {'passed': True, 'checks': checks, 'realNativeServiceViews': True, 'realPrivateAccountsUsed': False}
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0
  finally:
    server.shutdown(); server.server_close()


if __name__ == '__main__':
  raise SystemExit(main())
