"""WinGet release trust, strict inventory and deterministic manifest regressions."""
from __future__ import annotations
import copy
import hashlib
import json
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import winget


class WinGetTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    pinned = mock.patch.object(winget, 'ensure_minisign', return_value='verified-pinned-minisign')
    self.pinned = pinned.start()
    self.addCleanup(pinned.stop)
    self.lock = winget.load_json(winget.ROOT / 'packaging/winget/releases/1.0.3.json')

  def fake_assets(self):
    assets = self.root / 'assets'
    assets.mkdir()
    for name, row in self.lock['assets'].items():
      payload = b'signature' if name.endswith('.sig') else b'MZinstaller'
      (assets / name).write_bytes(payload)
      row.update(size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    return assets

  def test_checked_in_locks_are_valid(self):
    for path in (winget.ROOT / 'packaging/winget/releases').glob('*.json'):
      lock = winget.load_json(path)
      winget.validate_lock(lock)
      self.assertEqual(lock['version'], path.stem)

  def test_invalid_version_identity_and_hash_are_rejected(self):
    for field, values in {'schema': [True, 2], 'version': ['1.0.3-beta', '../escape', '01.0.3'],
                          'commit': [None, 5, 'main'], 'releaseId': [True, -1]}.items():
      for value in values:
        with self.subTest(field=field, value=value):
          lock = copy.deepcopy(self.lock)
          lock[field] = value
          with self.assertRaises(ValueError): winget.validate_lock(lock)
    for value in ('', 'x' * 64, 7):
      lock = copy.deepcopy(self.lock)
      next(iter(lock['assets'].values()))['sha256'] = value
      with self.assertRaises(ValueError): winget.validate_lock(lock)

  def test_exact_inventory_rejects_missing_extra_and_wrong_architecture(self):
    for change in ('missing', 'extra', 'wrong_arch'):
      lock = copy.deepcopy(self.lock)
      name = next(iter(lock['assets']))
      if change == 'missing': del lock['assets'][name]
      elif change == 'extra': lock['assets']['unexpected.exe'] = lock['assets'][name]
      else: lock['assets'][name.replace('x64', 'x86')] = lock['assets'].pop(name)
      with self.assertRaises(ValueError): winget.validate_lock(lock)

  def test_duplicate_json_keys_are_rejected(self):
    path = self.root / 'duplicate.json'
    path.write_text('{"version":"1.0.3","version":"1.0.4"}', encoding='utf-8')
    with self.assertRaises(ValueError): winget.load_json(path)

  def test_https_redirect_allowlist(self):
    for url in ('http://github.com/a', 'https://github.com.evil/a', 'https://user:pass@github.com/a', 'https://example.org/a', 'https://github.com:444/a'):
      with self.subTest(url=url), self.assertRaises(ValueError): winget.check_url(url)
    with self.assertRaises(ValueError):
      winget.ReleaseRedirect().redirect_request(None, None, 302, '', {}, 'http://github.com/file')

  def test_manifests_are_deterministic_crlf_and_version_bound(self):
    documents = winget.manifests(self.lock)
    self.assertEqual(documents, winget.manifests(copy.deepcopy(self.lock)))
    self.assertEqual(set(documents), {winget.PACKAGE + suffix for suffix in ('.yaml', '.installer.yaml', '.locale.en-US.yaml')})
    for data in documents.values():
      self.assertFalse(data.startswith(b'\xef\xbb\xbf'))
      self.assertNotIn(b'\n', data.replace(b'\r\n', b''))
      self.assertIn(b'# yaml-language-server: $schema=', data)
      self.assertIn(b'PackageVersion: "1.0.3"', data)
    installer = documents[winget.PACKAGE + '.installer.yaml'].decode()
    for arch in winget.ARCHES:
      self.assertIn('Architecture: "' + arch + '"', installer)
    self.assertNotIn('/latest/', installer)
    self.assertIn('Scope: "user"', installer)

  def test_prepare_verifies_both_signatures_and_exact_versions(self):
    assets = self.fake_assets()
    with mock.patch.object(winget, 'verify') as verifier:
      winget.prepare(self.lock, assets, self.root / 'manifest')
    self.assertEqual(verifier.call_count, 2)
    self.assertEqual([c.args[2] for c in verifier.call_args_list], ['1.0.3', '1.0.3'])

  def test_signatures_use_only_the_hash_verified_native_verifier(self):
    assets = self.fake_assets()
    with mock.patch.object(winget, 'verify') as verifier:
      winget.verify_assets(self.lock, assets)
    self.pinned.assert_called_once_with()
    self.assertEqual([c.kwargs['executable'] for c in verifier.call_args_list], ['verified-pinned-minisign'] * 2)

  def test_damaged_verifier_cache_stops_manifest_generation(self):
    assets = self.fake_assets()
    self.pinned.side_effect = SystemExit('verifier hash mismatch')
    with mock.patch.object(winget, 'verify') as verifier, self.assertRaises(SystemExit):
      winget.prepare(self.lock, assets, self.root / 'manifest')
    verifier.assert_not_called()
    self.assertFalse((self.root / 'manifest').exists())

  def test_tampered_asset_rejected_before_signature_or_manifest_generation(self):
    assets = self.fake_assets()
    (assets / next(iter(self.lock['assets']))).write_bytes(b'MZtampered')
    with mock.patch.object(winget, 'verify') as verifier, self.assertRaises(ValueError):
      winget.prepare(self.lock, assets, self.root / 'manifest')
    verifier.assert_not_called()
    self.assertFalse((self.root / 'manifest').exists())

  def test_existing_output_is_preserved(self):
    assets = self.fake_assets()
    output = self.root / 'manifest'
    output.mkdir()
    (output / 'marker').write_text('keep', encoding='utf-8')
    with mock.patch.object(winget, 'verify'), self.assertRaises(ValueError):
      winget.prepare(self.lock, assets, output)
    self.assertEqual((output / 'marker').read_text(encoding='utf-8'), 'keep')

  def test_failed_signature_produces_no_manifests(self):
    assets = self.fake_assets()
    with mock.patch.object(winget, 'verify', side_effect=ValueError('signature mismatch')), self.assertRaises(ValueError):
      winget.prepare(self.lock, assets, self.root / 'manifest')
    self.assertFalse((self.root / 'manifest').exists())

  def test_symlink_asset_rejected(self):
    assets = self.fake_assets()
    path = assets / next(iter(self.lock['assets']))
    target = self.root / 'target'
    path.rename(target)
    try: path.symlink_to(target)
    except OSError: self.skipTest('Host cannot create a symlink')
    with self.assertRaises(ValueError): winget.verify_assets(self.lock, assets)

  def test_failed_download_never_promotes_partial_directory(self):
    output = self.root / 'output'
    with mock.patch.object(winget, 'download', side_effect=ValueError('bad hash')), self.assertRaises(ValueError):
      winget.fetch(self.lock, output)
    self.assertFalse(output.exists())

  def test_intake_rejects_failed_workflow_before_any_download(self):
    release = {'draft': False, 'prerelease': False, 'tag_name': 'v1.0.3', 'published_at': '2026-11-03'}
    obj = {'object': {'type': 'commit', 'sha': self.lock['commit']}}
    with mock.patch.object(winget, 'api', side_effect=[release, obj, {'conclusion':'failure'}]), mock.patch.object(winget, 'fetch') as fetch:
      with self.assertRaises(ValueError): winget.intake('1.0.3', self.lock['commit'], 1, self.root/'candidate.json')
    fetch.assert_not_called()

  def test_download_checks_actual_bytes_and_size(self):
    for payload, digest, size, succeeds in ((b'data', hashlib.sha256(b'data').hexdigest(), 4, True),
                                           (b'evil', hashlib.sha256(b'data').hexdigest(), 4, False),
                                           (b'too long', hashlib.sha256(b'data').hexdigest(), 4, False)):
      with self.subTest(payload=payload):
        stream = io.BytesIO(payload)
        stream.url = 'https://release-assets.githubusercontent.com/file'
        path = self.root / ('download-' + payload.hex())
        with mock.patch.object(winget, 'build_opener') as opener:
          opener.return_value.open.return_value = stream
          if succeeds:
            winget.download('https://github.com/asset', {'sha256':digest, 'size':size}, path)
            self.assertEqual(path.read_bytes(), payload)
          else:
            with self.assertRaises(ValueError):
              winget.download('https://github.com/asset', {'sha256':digest, 'size':size}, path)

  def test_intake_binds_public_release_tag_run_and_exact_assets(self):
    release = {'id': self.lock['releaseId'], 'draft':False, 'prerelease':False,
               'tag_name':'v1.0.3', 'published_at':'2026-11-03', 'assets':[]}
    for name, row in self.lock['assets'].items():
      release['assets'].append({'name':name, 'size':row['size'], 'digest':'sha256:'+row['sha256'],
                               'state':'uploaded', 'browser_download_url':winget.release_url('1.0.3',name)})
    ref = {'object':{'type':'tag', 'sha':'a'*40}}
    tag = {'object':{'type':'commit', 'sha':self.lock['commit']}}
    run = {'head_sha':self.lock['commit'], 'conclusion':'success', 'status':'completed',
           'event':'push', 'path':'.github/workflows/release.yml', 'repository':{'full_name':winget.REPOSITORY}}
    for mutation in ('valid', 'wrong-tag', 'wrong-workflow', 'duplicate-asset', 'draft'):
      rows = copy.deepcopy([release, ref, tag, run])
      if mutation == 'wrong-tag': rows[2]['object']['sha'] = 'b'*40
      elif mutation == 'wrong-workflow': rows[3]['path'] = '.github/workflows/untrusted.yml'
      elif mutation == 'duplicate-asset': rows[0]['assets'].append(rows[0]['assets'][0])
      elif mutation == 'draft': rows[0]['draft'] = True
      output = self.root / (mutation+'.json')
      with self.subTest(mutation=mutation), mock.patch.object(winget, 'api', side_effect=rows), mock.patch.object(winget, 'fetch') as fetch:
        if mutation == 'valid':
          winget.intake('1.0.3', self.lock['commit'], 41613150420, output)
          self.assertEqual(winget.load_json(output), self.lock)
          fetch.assert_called_once()
        else:
          with self.assertRaises(ValueError): winget.intake('1.0.3', self.lock['commit'], 41613150420, output)
          fetch.assert_not_called()
          self.assertFalse(output.exists())


if __name__ == '__main__':
  unittest.main()
