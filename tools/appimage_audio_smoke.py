"""Play synthetic notification audio through a real AppImage's service WebView.

Uses a new Xvfb display, private D-Bus/profile and private PulseAudio null sink.
Never uses an existing Tauridium account, desktop audio server or real speaker.
"""
from __future__ import annotations

import argparse
import array
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import math
import os
from pathlib import Path
import platform
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import wave

from linux_audio import validate_appdir
from nix_smoke import isolated_environment
from tauri_build import build_environment

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {"x86_64-unknown-linux-gnu": 62, "aarch64-unknown-linux-gnu": 183}
PAGE = br'''<!doctype html><meta charset="utf-8"><title>Synthetic audio fixture</title>
<h1>Account-free audio regression</h1><script>
let previous = -1, audio, context;
async function report(value) {
  await fetch('/report', {method:'POST',body:JSON.stringify(value)});
}
async function tick() {
  const next = await fetch('/state', {cache:'no-store'}).then(r=>r.json());
  if (previous === next.step) return;
  previous = next.step;
  try {
    if (audio) { audio.pause(); audio.removeAttribute('src'); audio.load(); audio = null; }
    if (context) { await context.close(); context = null; }
    if (next.phase === 'wav' || next.phase === 'ogg') {
      audio = new Audio('/tone.' + next.phase); audio.loop = true;
      await audio.play();
    } else if (next.phase === 'web-audio') {
      context = new AudioContext();
      const gain = context.createGain(); gain.gain.value = 0.15;
      const oscillator = context.createOscillator(); oscillator.frequency.value = 880;
      oscillator.connect(gain).connect(context.destination); oscillator.start();
      await context.resume();
      if (context.state !== 'running') throw new Error('AudioContext is not running');
    }
    await report({step:next.step, phase:next.phase, started:true});
  } catch (error) { await report({step:next.step, error:String(error)}); }
}
tick(); setInterval(tick,200);
</script>'''
BUS = '''<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>
<policy context="default"><allow send_destination="*" eavesdrop="true"/>
<allow eavesdrop="true"/><allow own="*"/></policy></busconfig>'''


def stop(process):
  if process is None:
    return
  try:
    os.killpg(process.pid, signal.SIGTERM)
  except ProcessLookupError:
    pass
  try:
    process.wait(timeout=5)
  except subprocess.TimeoutExpired:
    os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=5)


def pcm_rms(payload: bytes) -> float:
  samples = array.array('h')
  samples.frombytes(payload[:len(payload) // 2 * 2])
  return math.sqrt(sum(value * value for value in samples) / len(samples)) if samples else 0.0


def capture_audio(environment: dict[str, str], seconds=1.5) -> tuple[int, float]:
  process = subprocess.Popen(['parec', '--device=tauridium_audio.monitor', '--format=s16le',
    '--rate=16000', '--channels=1', '--latency-msec=30'], env=environment,
    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
  payload = bytearray()
  try:
    with selectors.DefaultSelector() as selector:
      selector.register(process.stdout, selectors.EVENT_READ)
      deadline = time.monotonic() + seconds
      while time.monotonic() < deadline:
        if process.poll() is not None:
          raise RuntimeError('Private null-sink monitor exited')
        if selector.select(timeout=min(0.1, max(0, deadline - time.monotonic()))):
          block = os.read(process.stdout.fileno(), 65536)
          if not block:
            raise RuntimeError('Private null-sink monitor returned EOF')
          payload.extend(block)
          if len(payload) > 256 * 1024:
            raise RuntimeError('Private audio monitor exceeded its sample budget')
    if len(payload) < 6400:
      raise RuntimeError('Insufficient PCM samples from the private audio sink')
    return len(payload) // 2, pcm_rms(payload)
  finally:
    stop(process)
    process.stdout.close()


def run(image: Path, output: Path) -> dict:
  state = {'step': 0, 'phase': 'silent'}
  reports = []
  lock = threading.Lock()
  app = pulse = server = None
  completed = []
  with tempfile.TemporaryDirectory(prefix='tauridium-audio-') as temporary:
    profile = Path(temporary)
    environment = isolated_environment(profile)
    home = profile / 'home'
    home.mkdir(mode=0o700)
    environment.update(HOME=str(home), GDK_BACKEND='x11', LIBGL_ALWAYS_SOFTWARE='1',
                       WEBKIT_DISABLE_DMABUF_RENDERER='1')
    environment['GST_REGISTRY'] = str(profile / 'encoder-registry.bin')
    environment['GST_REGISTRY_1_0'] = environment['GST_REGISTRY']
    for name in list(environment):
      if name.startswith('PULSE_'):
        environment.pop(name)
    socket = profile / 'pulse.sock'
    client_config = profile / 'pulse-client.conf'
    client_config.write_text(f'autospawn = no\ndefault-server = unix:{socket}\n', encoding='utf-8')
    environment.update(PULSE_SERVER='unix:' + str(socket), PULSE_SINK='tauridium_audio',
                       PULSE_CLIENTCONFIG=str(client_config))
    bus = profile / 'session.conf'
    bus.write_text(BUS, encoding='utf-8')
    # Downloaded snapshots need not preserve executable mode. Keep the original
    # artifact untouched and execute only a private byte-for-byte copy.
    executable = profile / 'Tauridium.AppImage'
    shutil.copyfile(image, executable)
    executable.chmod(0o700)
    with (output / 'extract.log').open('w', encoding='utf-8') as log:
      subprocess.run([str(executable), '--appimage-extract'], cwd=profile,
                     stdout=log, stderr=log, check=True, timeout=90)
    appdir = profile / 'squashfs-root'
    machine = 62 if platform.machine().lower() in ('x86_64', 'amd64') else 183
    validate_appdir(appdir, machine)
    if not (appdir / 'usr/lib/gstreamer-1.0/libgstpulseaudio.so').is_file():
      raise RuntimeError('AppImage needs its bundled PulseAudio plugin for the null-sink test')

    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
      wav.setnchannels(1)
      wav.setsampwidth(2)
      wav.setframerate(16000)
      tone = array.array('h', (round(5000 * math.sin(2 * math.pi * 440 * n / 16000)) for n in range(16000)))
      wav.writeframes(tone.tobytes())
    wav_bytes = buffer.getvalue()
    ogg = profile / 'tone.ogg'
    subprocess.run(['gst-launch-1.0', '-q', 'audiotestsrc', 'num-buffers=32', 'freq=660',
      '!', 'audioconvert', '!', 'vorbisenc', '!', 'oggmux', '!', 'filesink', 'location=' + str(ogg)],
      env=environment, check=True, timeout=30, stdout=subprocess.DEVNULL)
    ogg_bytes = ogg.read_bytes()

    class Handler(BaseHTTPRequestHandler):
      def log_message(self, *_args):
        pass

      def do_GET(self):
        with lock:
          current = dict(state)
        bodies = {'/': (PAGE, 'text/html; charset=utf-8'),
                  '/state': (json.dumps(current).encode(), 'application/json'),
                  '/tone.wav': (wav_bytes, 'audio/wav'), '/tone.ogg': (ogg_bytes, 'audio/ogg')}
        if self.path not in bodies:
          self.send_error(404)
          return
        body, mime = bodies[self.path]
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

      def do_POST(self):
        try:
          size = int(self.headers.get('Content-Length', 0))
          if self.path != '/report' or not 0 < size <= 4096:
            raise ValueError('Invalid report')
          report = json.loads(self.rfile.read(size))
          with lock:
            if len(reports) >= 64:
              raise ValueError('Report budget exceeded')
            reports.append(report)
        except (ValueError, TypeError):
          self.send_error(400)
          return
        self.send_response(204)
        self.end_headers()

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}/'
    data = profile / 'data/dev.brani.tauridium'
    data.mkdir(parents=True)
    for name, value in {
      'session.json': {'mode': 'local', 'version': 1},
      'local_profile.json': {'version': 1, 'services': [{'id': 'audio-probe', 'recipeId': 'audio-probe',
        'name': 'Synthetic audio', 'isLocalRecipe': True, 'isEnabled': True, 'customUrl': url}], 'workspaces': []},
      'app_settings.json': {'fetchMissingServiceIcons': False, 'preloadServices': False, 'closeToSystemTray': False},
    }.items():
      (data / name).write_text(json.dumps(value), encoding='utf-8')
    recipe = profile / 'config/dev.brani.tauridium/recipes/audio-probe'
    recipe.mkdir(parents=True)
    (recipe / 'package.json').write_text(json.dumps({'id': 'audio-probe', 'name': 'Synthetic audio',
      'version': '1.0.0', 'config': {'serviceURL': url, 'hasCustomUrl': True}}), encoding='utf-8')
    application_env = dict(environment)
    for name in list(application_env):
      if name.startswith('GST_') or name in ('LD_LIBRARY_PATH', 'LD_PRELOAD', 'LD_AUDIT', 'GTK_PATH',
          'GTK_EXE_PREFIX', 'GTK_DATA_PREFIX', 'GIO_EXTRA_MODULES', 'GDK_PIXBUF_MODULE_FILE', 'GI_TYPELIB_PATH'):
        application_env.pop(name)
    application_env.update(APPDIR=str(appdir), APPIMAGE=str(image),
      GST_REGISTRY=str(profile / 'application-registry.bin'), GST_DEBUG='2')
    try:
      with (output / 'pulse.log').open('w', encoding='utf-8') as pulse_log, (output / 'application.log').open('w', encoding='utf-8') as app_log:
        pulse = subprocess.Popen(['pulseaudio', '-n', '--daemonize=no', '--use-pid-file=no',
          '--exit-idle-time=-1', '--disable-shm', '--log-target=stderr',
          '--load=module-native-protocol-unix socket=' + str(socket) + ' auth-anonymous=1',
          '--load=module-null-sink sink_name=tauridium_audio rate=48000 channels=1'],
          env=environment, stdout=pulse_log, stderr=pulse_log, start_new_session=True)
        deadline = time.monotonic() + 15
        while not socket.exists():
          if pulse.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError('Private PulseAudio server failed to start')
          time.sleep(0.1)
        subprocess.run(['pactl', 'info'], env=environment, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        info = profile / 'build-info.json'
        subprocess.run([str(appdir / 'AppRun'), '--build-info-file', str(info)],
                       env=application_env, check=True, stdout=app_log, stderr=app_log, timeout=30)
        if json.loads(info.read_text(encoding='utf-8')).get('buildMode') != 'production':
          raise RuntimeError('Audio test requires a real production AppImage')
        app = subprocess.Popen(['dbus-run-session', '--config-file=' + str(bus), '--',
          str(appdir / 'AppRun'), '--startup-diagnostics'], env=application_env,
          stdout=app_log, stderr=app_log, start_new_session=True)
        for phase in ('silent', 'wav', 'silent', 'ogg', 'silent', 'web-audio', 'silent', 'wav', 'silent'):
          with lock:
            state['step'] += 1
            state['phase'] = phase
            step = state['step']
          deadline = time.monotonic() + 60
          while True:
            if app.poll() is not None or pulse.poll() is not None:
              raise RuntimeError('Application or private audio server exited')
            with lock:
              matches = [r for r in reports if r.get('step') == step]
            if matches:
              if matches[-1].get('error') or matches[-1].get('started') is not True:
                raise RuntimeError('WebView audio failed: ' + str(matches[-1].get('error')))
              break
            if time.monotonic() > deadline:
              raise RuntimeError('WebView stopped responding during ' + phase + '; inspect private application.log')
            time.sleep(0.1)
          # Require actual settled output, allowing bounded device-buffer drain.
          deadline = time.monotonic() + 12
          while True:
            if app.poll() is not None or pulse.poll() is not None:
              raise RuntimeError('Application or private audio server exited')
            frames, rms = capture_audio(environment)
            if (phase == 'silent' and rms <= 8) or (phase != 'silent' and rms >= 32):
              break
            if time.monotonic() > deadline:
              raise RuntimeError(f'Unexpected private audio output for {phase}: RMS {rms:.2f}')
          completed.append({'phase': phase, 'frames': frames, 'rms': round(rms, 2)})
          print(f'AppImage audio: {phase} passed ({frames} frames, RMS {rms:.2f})', flush=True)
    finally:
      stop(app)
      stop(pulse)
      server.shutdown()
      server.server_close()
  result = {'passed': True, 'production': True, 'bundledGstreamerVerified': True,
    'isolatedProfileDisplayBusAndNullSink': True, 'realSpeakersUsed': False, 'phases': completed}
  (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
  return result


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  group = parser.add_mutually_exclusive_group(required=True)
  group.add_argument('--appimage', type=Path)
  group.add_argument('--target', choices=TARGETS)
  parser.add_argument('--output', type=Path, default=ROOT / 'release/evidence/appimage-audio')
  parser.add_argument('--inside-display', action='store_true', help=argparse.SUPPRESS)
  args = parser.parse_args()
  if platform.system() != 'Linux' or sys.byteorder != 'little':
    parser.error('requires native Linux x64 or ARM64')
  if platform.machine().lower() not in ('x86_64', 'amd64', 'aarch64', 'arm64'):
    parser.error('requires native Linux x64 or ARM64')
  if os.environ.get('WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS'):
    parser.error('remove the WebKit sandbox override before testing')
  build_environment(dict(os.environ))  # Reject any signing credentials before running artifacts.
  for tool in ('xvfb-run', 'pulseaudio', 'pactl', 'parec', 'dbus-run-session', 'gst-launch-1.0'):
    if not shutil.which(tool):
      parser.error('missing test tool: ' + tool)
  if not args.inside_display:
    return subprocess.run(['xvfb-run', '-a', '-s', '-screen 0 1280x800x24 -nolisten tcp',
      sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], '--inside-display'], check=False).returncode
  if not os.environ.get('DISPLAY'):
    parser.error('the private display did not start')
  if args.target:
    images = list((ROOT / 'src-tauri/target' / args.target / 'release/bundle/appimage').glob('*.AppImage'))
    if len(images) != 1:
      parser.error('expected exactly one produced AppImage for this target')
    image = images[0]
  else:
    image = args.appimage
  image = image.resolve(strict=True)
  args.output.mkdir(parents=True, exist_ok=True)
  run(image, args.output.resolve())
  print('Production AppImage audio passed using only a private null sink.')
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
