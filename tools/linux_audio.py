"""Linux media requirements shared by bootstrap, bundle preflight and audio tests."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile

# WebKit's WebAudio bridge needs appsrc; checking only development libraries is
# insufficient. These factories also cover ordinary WAV/Ogg notification audio.
REQUIRED_FACTORIES = (
  "appsrc", "autoaudiosink", "audioconvert", "audioresample", "volume",
  "playbin", "decodebin", "typefind", "wavparse", "oggdemux", "vorbisdec", "opusdec",
)
AUDIO_SINKS = ("pulsesink", "alsasink", "pipewiresink")
REQUIRED_PLUGIN_FILES = (
  "libgstapp.so", "libgstautodetect.so", "libgstaudioconvert.so",
  "libgstaudioresample.so", "libgstvolume.so", "libgstplayback.so",
  "libgstcoreelements.so", "libgsttypefindfunctions.so", "libgstwavparse.so",
  "libgstogg.so", "libgstvorbis.so", "libgstopus.so",
)


def missing_gstreamer_components() -> list[str]:
  """Probe the effective plugin search path without reading/updating a user registry.

  Preserve distro/Nix search paths. Package names or plugin filenames alone do
  not prove that a loadable factory (and its shared libraries) is available.
  """
  inspector = shutil.which("gst-inspect-1.0")
  if not inspector:
    return ["tool:gst-inspect-1.0"]
  with tempfile.TemporaryDirectory(prefix="tauridium-gstreamer-probe-") as temporary:
    registry = str(Path(temporary) / "registry.bin")
    environment = dict(os.environ, LC_ALL="C", GST_REGISTRY=registry, GST_REGISTRY_1_0=registry)

    def available(factory: str) -> bool:
      return subprocess.run([inspector, "--exists", factory], env=environment,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=False, timeout=15).returncode == 0

    try:
      missing = ["gstreamer:" + name for name in REQUIRED_FACTORIES if not available(name)]
      if not any(available(name) for name in AUDIO_SINKS):
        missing.append("gstreamer:audio-output(" + "|".join(AUDIO_SINKS) + ")")
      return missing
    except (OSError, subprocess.TimeoutExpired):
      return ["gstreamer:inspection-failed-or-timed-out"]


def require_gstreamer() -> None:
  missing = missing_gstreamer_components()
  if missing:
    raise SystemExit("error: Linux media prerequisites are missing: " + ", ".join(missing)
                     + "; run just init before building an AppImage")


def validate_appdir(appdir: Path, machine: int) -> None:
  """Reject partial bundles, wrong-architecture plugins and missing scanner hooks."""
  plugins = appdir / "usr/lib/gstreamer-1.0"
  required = [plugins / name for name in REQUIRED_PLUGIN_FILES]
  sinks = [plugins / name for name in ("libgstpulseaudio.so", "libgstalsa.so", "libgstpipewire.so")]
  if not any(path.is_file() for path in sinks):
    raise RuntimeError("AppImage has no bundled GStreamer audio output plugin")
  required.extend(path for path in sinks if path.is_file())
  required.append(appdir / "usr/lib/gstreamer1.0/gstreamer-1.0/gst-plugin-scanner")
  for path in required:
    if path.is_symlink() or not path.is_file():
      raise RuntimeError("AppImage is missing a bundled GStreamer component: " + path.name)
    with path.open("rb") as stream:
      header = stream.read(20)
    if (len(header) != 20 or header[:6] != b"\x7fELF\x02\x01"
        or int.from_bytes(header[18:20], "little") != machine):
      raise RuntimeError("AppImage GStreamer component has the wrong ELF architecture: " + path.name)
  hook = appdir / "apprun-hooks/linuxdeploy-plugin-gstreamer.sh"
  if not hook.is_file() or hook.is_symlink():
    raise RuntimeError("AppImage is missing its GStreamer runtime hook")
  text = hook.read_text(encoding="utf-8")
  for setting in (
    'GST_PLUGIN_SYSTEM_PATH_1_0="${APPDIR}/usr/lib/gstreamer-1.0"',
    'GST_PLUGIN_PATH_1_0="${APPDIR}/usr/lib/gstreamer-1.0"',
    'GST_PLUGIN_SCANNER_1_0="${APPDIR}/usr/lib/gstreamer1.0/gstreamer-1.0/gst-plugin-scanner"',
  ):
    if setting not in text:
      raise RuntimeError("AppImage media hook does not confine plugin/scanner lookup to its bundle")
