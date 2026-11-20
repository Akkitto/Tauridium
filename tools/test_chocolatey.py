"""Local package trust, containment, preservation and reproducibility controls."""
from __future__ import annotations
import copy
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile
import chocolatey as c


class ChocolateyTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.lock = c.load_json(c.TEMPLATES / 'releases/1.0.12.json')
    self.assets = self.root / 'assets';self.assets.mkdir()
    for name, row in self.lock['assets'].items():
      data = b'signature' if name.endswith('.sig') else bytes.fromhex('d0cf11e0a1b11ae1') + name.encode()
      (self.assets / name).write_bytes(data)
      row.update(size=len(data),sha256=hashlib.sha256(data).hexdigest())
    for name in ('ensure_minisign','verify'):
      patch = mock.patch.object(c,name,return_value='verified');patch.start();self.addCleanup(patch.stop)

  def test_committed_release_locks_are_valid(self):
    locks = list((c.TEMPLATES / 'releases').glob('*.json'))
    self.assertGreaterEqual(len(locks),2)
    for path in locks:
      lock=c.load_json(path);c.validate_lock(lock);self.assertEqual(lock['version'],path.stem)

  def test_invalid_or_injectable_release_identity_is_rejected(self):
    for field, values in {'schema':[True,2], 'version':['../escape','1.0.12-beta','01.0.12',"1.0.12';exit"],
                          'commit':[None,'master'], 'releaseId':[True,0], 'runId':[True,-1]}.items():
      for value in values:
        with self.subTest(field=field,value=value):
          lock=copy.deepcopy(self.lock);lock[field]=value
          with self.assertRaises(ValueError):c.validate_lock(lock)

  def test_mixed_missing_extra_or_wrong_arch_assets_are_rejected(self):
    for operation in ('extra','missing','wrong'):
      lock=copy.deepcopy(self.lock);name=next(iter(lock['assets']))
      if operation=='extra':lock['assets']['extra.exe']=lock['assets'][name]
      elif operation=='missing':del lock['assets'][name]
      else:lock['assets'][name.replace('arm64','x86')]=lock['assets'].pop(name)
      with self.assertRaises(ValueError):c.validate_lock(lock)

  def test_bad_size_hash_and_unknown_fields_are_rejected(self):
    for field,value in [('size',True),('size',0),('size',2**32),('sha256',None),('sha256','X'*64),('extra',1)]:
      lock=copy.deepcopy(self.lock);next(iter(lock['assets'].values()))[field]=value
      with self.assertRaises(ValueError):c.validate_lock(lock)

  def test_every_signature_is_verified_with_exact_version_and_pinned_tool(self):
    c.verify_assets(self.lock,self.assets)
    self.assertEqual(c.verify.call_count,2)
    for call in c.verify.call_args_list:
      self.assertEqual(call.args[2],'1.0.12');self.assertEqual(call.kwargs['executable'],'verified')

  def test_tampering_stops_before_signature_or_output(self):
    path=self.assets/next(iter(self.lock['assets']));path.write_bytes(b'tampered')
    with self.assertRaises(ValueError):c.prepare(self.lock,self.assets,self.root/'stage')
    c.verify.assert_not_called();self.assertFalse((self.root/'stage').exists())

  def test_extra_asset_and_asset_symlink_are_rejected(self):
    (self.assets/'extra').write_text('private')
    with self.assertRaises(ValueError):c.verify_assets(self.lock,self.assets)
    (self.assets/'extra').unlink()
    path=self.assets/next(iter(self.lock['assets']));path.unlink();path.symlink_to(self.root/'elsewhere')
    with self.assertRaises(ValueError):c.verify_assets(self.lock,self.assets)

  def test_prepare_is_exact_reusable_and_deterministic(self):
    first=self.root/'a';second=self.root/'b'
    c.prepare(self.lock,self.assets,first);c.prepare(self.lock,self.assets,first);c.prepare(self.lock,self.assets,second)
    expected=c.staging_files(self.lock,self.assets)
    c.check_tree(first,expected);c.check_tree(second,expected)
    self.assertEqual(len(expected),11)
    self.assertNotIn(b'<dependencies',expected['tauridium.nuspec'])
    self.assertNotIn(b'choco push',b'\n'.join(expected.values()))

  def test_existing_stage_changes_are_preserved_and_rejected(self):
    output=self.root/'stage';c.prepare(self.lock,self.assets,output)
    p=output/'tools/chocolateyInstall.ps1';p.write_text('keep changed source')
    with self.assertRaises(ValueError):c.prepare(self.lock,self.assets,output)
    self.assertEqual(p.read_text(),'keep changed source')

  def test_extra_or_linked_stage_files_are_rejected(self):
    output=self.root/'stage';c.prepare(self.lock,self.assets,output)
    (output/'private').write_text('private')
    with self.assertRaises(ValueError):c.check_tree(output,c.staging_files(self.lock,self.assets))
    (output/'private').unlink();(output/'link').symlink_to(self.assets)
    with self.assertRaises(ValueError):c.check_tree(output,c.staging_files(self.lock,self.assets))

  def fixture(self, identifier='abc', extra=None, mutation=None):
    expected=c.staging_files(self.lock,self.assets);payload=dict(expected)
    core=f'package/services/metadata/core-properties/{identifier}.psmdcp'
    payload[core]=b'<coreProperties><modified>2026-01-01</modified></coreProperties>'
    payload['_rels/.rels']=f'<Relationships><Relationship Id="{identifier}" Target="/{core}" /></Relationships>'.encode()
    payload['[Content_Types].xml']=f'<Types><Override PartName="/{core}" /></Types>'.encode()
    if extra:payload.update(extra)
    if mutation:mutation(payload)
    file=self.root/(identifier+'.nupkg')
    with zipfile.ZipFile(file,'w') as z:
      for name,data in payload.items():z.writestr(name,data)
    return file,expected

  def test_nuget_entropy_normalizes_without_changing_payloads(self):
    a,expected=self.fixture('first');b,_=self.fixture('second')
    self.assertEqual(c.normalized_package(a,expected),c.normalized_package(b,expected))

  def test_extra_executable_path_escape_and_changed_payload_are_rejected(self):
    for extra in ({'tools/evil.exe':b'MZ'},{'../escape':b'x'}):
      file,expected=self.fixture('extra',extra)
      with self.assertRaises((ValueError,SystemExit)):c.normalized_package(file,expected)
    file,expected=self.fixture('modified',mutation=lambda p:p.update({'tools/chocolateyInstall.ps1':b'exit 0'}))
    with self.assertRaises(ValueError):c.normalized_package(file,expected)

  def test_new_nuget_dependency_or_dtd_is_rejected(self):
    for data in (b'<package><metadata><dependencies /></metadata></package>',b'<!DOCTYPE package><package/>'):
      file,expected=self.fixture('metadata',mutation=lambda p:p.update({'tauridium.nuspec':data}))
      with self.assertRaises(ValueError):c.normalized_package(file,expected)

  def test_pack_requires_native_windows_and_never_publishes(self):
    stage=self.root/'stage';c.prepare(self.lock,self.assets,stage)
    with mock.patch.object(c.os,'name','posix'),self.assertRaises(ValueError):c.pack(self.lock,self.assets,stage,self.root/'package.nupkg')
    self.assertFalse((self.root/'package.nupkg').exists())

  def fake_api(self):
    version=self.lock['version'];commit=self.lock['commit'];run=self.lock['runId']
    release={'draft':False,'prerelease':False,'tag_name':'v'+version,'published_at':'2026-11-18T13:29:26Z','id':self.lock['releaseId'],
             'assets':[{'name':name,'state':'uploaded','browser_download_url':c.release_url(version,name),'digest':'sha256:'+row['sha256'],'size':row['size']} for name,row in self.lock['assets'].items()]}
    return {'/releases/tags/v'+version:release,
            '/git/ref/tags/v'+version:{'object':{'type':'tag','sha':'a'*40}},
            '/git/tags/'+'a'*40:{'object':{'type':'commit','sha':commit}},
            '/actions/runs/'+str(run):{'head_sha':commit,'head_branch':'v'+version,'conclusion':'success','status':'completed','event':'push','path':'.github/workflows/release.yml','repository':{'full_name':'Akkitto/Tauridium'}}}

  def test_intake_binds_the_real_tag_and_successful_workflow_before_review_output(self):
    responses=self.fake_api();output=self.root/'candidate.json'
    with mock.patch.object(c,'api',side_effect=lambda path:responses[path]),mock.patch.object(c,'fetch') as fetch:
      c.intake(self.lock['version'],self.lock['commit'],self.lock['runId'],output)
    self.assertEqual(c.load_json(output),self.lock);fetch.assert_called_once()

  def test_intake_rejects_wrong_tag_failed_run_and_duplicate_assets_before_fetch(self):
    for change in ('tag','run','duplicate','draft'):
      responses=self.fake_api()
      if change=='tag':responses['/git/tags/'+'a'*40]['object']['sha']='b'*40
      elif change=='run':responses['/actions/runs/'+str(self.lock['runId'])]['conclusion']='failure'
      elif change=='draft':responses['/releases/tags/v'+self.lock['version']]['draft']=True
      else:
        rows=responses['/releases/tags/v'+self.lock['version']]['assets'];rows.append(rows[0])
      with mock.patch.object(c,'api',side_effect=lambda path:responses[path]),mock.patch.object(c,'fetch') as fetch:
        with self.assertRaises(ValueError):c.intake(self.lock['version'],self.lock['commit'],self.lock['runId'],self.root/'rejected.json')
        fetch.assert_not_called()
      self.assertFalse((self.root/'rejected.json').exists())

  def test_nuget_scalar_reordering_and_space_annotation_preserve_exact_identity(self):
    import xml.etree.ElementTree as ET
    def reorder(payload):
      package=ET.fromstring(payload['tauridium.nuspec']);metadata=next(iter(package))
      metadata[:]=list(reversed(list(metadata)))
      for node in metadata:node.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
      payload['tauridium.nuspec']=ET.tostring(package)
    archive,expected=self.fixture('reordered',mutation=reorder)
    self.assertIn('tauridium.nuspec',c.normalized_package(archive,expected))

  def test_duplicate_nuget_scalar_identity_is_rejected(self):
    import xml.etree.ElementTree as ET
    def duplicate(payload):
      package=ET.fromstring(payload['tauridium.nuspec']);metadata=next(iter(package));metadata.append(copy.deepcopy(metadata[0]))
      payload['tauridium.nuspec']=ET.tostring(package)
    archive,expected=self.fixture('duplicate',mutation=duplicate)
    with self.assertRaises(ValueError):c.normalized_package(archive,expected)
