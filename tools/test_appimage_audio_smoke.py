"""The audio gate must require actual samples and never access a signing session."""
import os
import unittest
from unittest.mock import patch

import appimage_audio_smoke as smoke


class AppImageAudioSmokeTests(unittest.TestCase):
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
