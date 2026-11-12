"""The audio gate must require actual samples and never access a signing session."""
import os
import unittest
from unittest.mock import MagicMock, patch

import appimage_audio_smoke as smoke


class AppImageAudioSmokeTests(unittest.TestCase):
  def test_sampler_waits_for_real_pcm_after_delayed_sink_startup(self):
    process = MagicMock()
    process.poll.return_value = None
    selector = MagicMock()
    selector.__enter__.return_value.select.return_value = [(None, None)]
    with (patch.object(smoke.subprocess, 'Popen', return_value=process),
          patch.object(smoke.selectors, 'DefaultSelector', return_value=selector),
          patch.object(smoke.time, 'monotonic', side_effect=[0, 0.1, 0.2, 2.1, 2.2]),
          patch.object(smoke.os, 'read', side_effect=[b'\0' * 1000, b'\0' * 31000]) as read,
          patch.object(smoke, 'stop') as stop):
      self.assertEqual(smoke.capture_audio({}), (16000, 0))
      self.assertEqual(read.call_count, 2)
      stop.assert_called_once_with(process)

  def test_no_pcm_samples_cannot_be_reported_as_silence(self):
    process = MagicMock()
    process.poll.return_value = None
    selector = MagicMock()
    selector.__enter__.return_value.select.return_value = []
    with (patch.object(smoke.subprocess, 'Popen', return_value=process),
          patch.object(smoke.selectors, 'DefaultSelector', return_value=selector),
          patch.object(smoke.time, 'monotonic', side_effect=[0, 0.1, 0.2, 11]),
          patch.object(smoke, 'stop')):
      with self.assertRaisesRegex(RuntimeError, 'Insufficient PCM samples'):
        smoke.capture_audio({})

  def test_pcm_measurement_distinguishes_silence_from_actual_samples(self):
    self.assertEqual(smoke.pcm_rms(b'\0' * 32000), 0)
    self.assertEqual(smoke.pcm_rms(b''), 0)
    self.assertEqual(smoke.pcm_rms(b'\xe8\x03\x18\xfc' * 200), 1000)

  def test_a_signing_session_is_rejected_before_running_any_artifact(self):
    with (patch.dict(os.environ, {'TAURI_SIGNING_PRIVATE_KEY': 'synthetic-not-a-key'}),
          patch.object(smoke.sys, 'argv', ['appimage_audio_smoke.py', '--appimage', 'synthetic.AppImage']),
          patch.object(smoke.platform, 'system', return_value='Linux'),
          patch.object(smoke.platform, 'machine', return_value='x86_64'),
          patch.object(smoke.subprocess, 'run') as run):
      with self.assertRaisesRegex(SystemExit, 'never accept signing'):
        smoke.main()
      run.assert_not_called()


if __name__ == '__main__':
  unittest.main()
