"""Fail-closed Linux media probes, partial bundle rejection and real PCM accounting."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import linux_audio as audio
import tauri_build


class LinuxAudioTests(unittest.TestCase):
  def test_missing_inspector_is_actionable(self):
    with patch.object(audio.shutil, 'which', return_value=None):
      self.assertEqual(audio.missing_gstreamer_components(), ['tool:gst-inspect-1.0'])

  def test_installed_libraries_cannot_hide_a_missing_web_audio_factory(self):
    def inspect(command, **kwargs):
      self.assertIn('GST_REGISTRY', kwargs['env'])
      self.assertEqual(kwargs['env']['GST_REGISTRY'], kwargs['env']['GST_REGISTRY_1_0'])
      self.assertEqual(kwargs['env']['LC_ALL'], 'C')
      return subprocess.CompletedProcess(command, 1 if command[-1] == 'appsrc' else 0)
    with patch.object(audio.shutil, 'which', return_value='/synthetic/gst-inspect'), patch.object(audio.subprocess, 'run', side_effect=inspect):
      self.assertEqual(audio.missing_gstreamer_components(), ['gstreamer:appsrc'])

  def test_at_least_one_real_output_backend_is_required(self):
    def inspect(command, **_kwargs):
      return subprocess.CompletedProcess(command, 1 if command[-1] in audio.AUDIO_SINKS else 0)
    with patch.object(audio.shutil, 'which', return_value='/synthetic/gst-inspect'), patch.object(audio.subprocess, 'run', side_effect=inspect):
      self.assertEqual(audio.missing_gstreamer_components(), ['gstreamer:audio-output(pulsesink|alsasink|pipewiresink)'])

  def test_alsa_only_hosts_are_accepted(self):
    def inspect(command, **_kwargs):
      return subprocess.CompletedProcess(command, 1 if command[-1] == 'pulsesink' else 0)
    with patch.object(audio.shutil, 'which', return_value='/synthetic/gst-inspect'), patch.object(audio.subprocess, 'run', side_effect=inspect):
      self.assertEqual(audio.missing_gstreamer_components(), [])

  def test_inspection_failures_are_not_silently_accepted(self):
    for error in (OSError('synthetic'), subprocess.TimeoutExpired('synthetic', 15)):
      with self.subTest(error=type(error).__name__), patch.object(audio.shutil, 'which', return_value='/synthetic/gst-inspect'), patch.object(audio.subprocess, 'run', side_effect=error):
        self.assertEqual(audio.missing_gstreamer_components(), ['gstreamer:inspection-failed-or-timed-out'])

  def test_native_and_non_linux_builds_do_not_acquire_appimage_requirements(self):
    with patch.object(tauri_build.platform, 'system', return_value='Linux'):
      for args in (['--no-bundle', '--ci'], ['--bundles', 'deb'], ['--target', 'x86_64-pc-windows-msvc'], ['--target=aarch64-apple-darwin']):
        self.assertFalse(tauri_build.needs_linux_media(args))
      for args in ([], ['--target', 'aarch64-unknown-linux-gnu'], ['--bundles=appimage'], ['--bundles', 'deb,appimage'], ['--bundles', 'all']):
        self.assertTrue(tauri_build.needs_linux_media(args))
    for system in ('Windows', 'Darwin'):
      with patch.object(tauri_build.platform, 'system', return_value=system):
        self.assertFalse(tauri_build.needs_linux_media([]))

  def make_appdir(self, root):
    plugins = root / 'usr/lib/gstreamer-1.0'
    plugins.mkdir(parents=True)
    elf = b'\x7fELF\x02\x01' + b'\0' * 12 + (62).to_bytes(2, 'little')
    for name in (*audio.REQUIRED_PLUGIN_FILES, 'libgstpulseaudio.so'):
      (plugins / name).write_bytes(elf)
    scanner = root / 'usr/lib/gstreamer1.0/gstreamer-1.0/gst-plugin-scanner'
    scanner.parent.mkdir(parents=True)
    scanner.write_bytes(elf)
    hooks = root / 'apprun-hooks'
    hooks.mkdir()
    (hooks / 'linuxdeploy-plugin-gstreamer.sh').write_text('''export GST_PLUGIN_SYSTEM_PATH_1_0="${APPDIR}/usr/lib/gstreamer-1.0"
export GST_PLUGIN_PATH_1_0="${APPDIR}/usr/lib/gstreamer-1.0"
export GST_PLUGIN_SCANNER_1_0="${APPDIR}/usr/lib/gstreamer1.0/gstreamer-1.0/gst-plugin-scanner"
''', encoding='utf-8')
    return plugins, scanner

  def test_complete_bundle_passes_and_partial_or_wrong_architecture_bundles_fail(self):
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      plugins, scanner = self.make_appdir(root)
      audio.validate_appdir(root, 62)
      with self.assertRaisesRegex(RuntimeError, 'ELF architecture'):
        audio.validate_appdir(root, 183)
      scanner.unlink()
      with self.assertRaisesRegex(RuntimeError, 'gst-plugin-scanner'):
        audio.validate_appdir(root, 62)
      scanner.write_bytes((plugins / 'libgstapp.so').read_bytes())
      (plugins / 'libgstapp.so').unlink()
      with self.assertRaisesRegex(RuntimeError, 'libgstapp.so'):
        audio.validate_appdir(root, 62)

  def test_a_host_fallback_hook_cannot_pass_as_a_self_contained_bundle(self):
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      self.make_appdir(root)
      (root / 'apprun-hooks/linuxdeploy-plugin-gstreamer.sh').write_text('export GST_PLUGIN_PATH_1_0=/usr/lib/gstreamer-1.0\n', encoding='utf-8')
      with self.assertRaisesRegex(RuntimeError, 'confine'):
        audio.validate_appdir(root, 62)


if __name__ == '__main__':
  unittest.main()
