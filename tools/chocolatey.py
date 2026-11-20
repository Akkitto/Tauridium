#!/usr/bin/env python3
"""Build self-contained local Chocolatey packages; never submit to any registry."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from security_tools import ensure_minisign
from updater_signature import require_regular, verify
from winget import ARCHES, HEX, VERSION, api, download, load_json, release_url
from release_policy import zip_layout

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'packaging/chocolatey'
SCRIPTS = ('chocolateyInstall.ps1', 'chocolateyUninstall.ps1', 'tauridium.ps1')
PACKAGE = 'tauridium'


def names(version: str) -> set[str]:
  return {f'tauridium-{version}-windows-{arch}.msi{suffix}' for arch in ARCHES for suffix in ('', '.sig')}


def validate_lock(lock: dict) -> None:
  if set(lock) != {'schema', 'version', 'commit', 'releaseId', 'runId', 'assets'} or type(lock['schema']) is not int or lock['schema'] != 1:
    raise ValueError('Unsupported Chocolatey release lock')
  if (not isinstance(lock['version'], str) or not VERSION.fullmatch(lock['version'])
      or not isinstance(lock['commit'], str) or not re.fullmatch('[a-f0-9]{40}', lock['commit'])
      or any(type(lock[k]) is not int or lock[k] <= 0 for k in ('releaseId', 'runId'))):
    raise ValueError('Invalid stable release identity')
  if not isinstance(lock['assets'], dict) or set(lock['assets']) != names(lock['version']):
    raise ValueError('Expected exactly the x64/ARM64 MSI and signature pairs')
  for name, row in lock['assets'].items():
    if (not isinstance(row, dict) or set(row) != {'size', 'sha256'}
        or type(row['size']) is not int or not 0 < row['size'] <= (16384 if name.endswith('.sig') else 256 * 1024**2)
        or not isinstance(row['sha256'], str) or not HEX.fullmatch(row['sha256'])):
      raise ValueError('Invalid exact MSI/signature size or SHA-256')


def verify_assets(lock: dict, assets: Path) -> None:
  validate_lock(lock)
  if assets.is_symlink() or not assets.is_dir() or {f.name for f in assets.iterdir()} != names(lock['version']):
    raise ValueError('Asset directory must contain exactly the reviewed MSI/signature pairs')
  for name, row in lock['assets'].items():
    path = assets / name
    require_regular(path)
    with path.open('rb') as source:
      digest = hashlib.file_digest(source, 'sha256').hexdigest()
    if path.stat().st_size != row['size'] or digest != row['sha256']:
      raise ValueError('MSI/signature differs from the reviewed release lock')
    if name.endswith('.msi') and path.read_bytes()[:8] != bytes.fromhex('d0cf11e0a1b11ae1'):
      raise ValueError('Expected an MSI compound document')
  executable = ensure_minisign()
  for arch in ARCHES:
    artifact = assets / f'tauridium-{lock["version"]}-windows-{arch}.msi'
    verify(artifact, artifact.with_suffix('.msi.sig'), lock['version'], executable=executable)


def fetch(lock: dict, output: Path) -> None:
  validate_lock(lock)
  if output.exists() or output.is_symlink():
    verify_assets(lock, output)
    return
  output.parent.mkdir(parents=True, exist_ok=True)
  with tempfile.TemporaryDirectory(prefix='.chocolatey-assets-', dir=output.parent) as temporary:
    stage = Path(temporary)
    for name, row in sorted(lock['assets'].items()):
      download(release_url(lock['version'], name), row, stage / name)
    verify_assets(lock, stage)
    stage.rename(output)


def intake(version: str, commit: str, run_id: int, output: Path) -> None:
  if output.exists() or output.is_symlink():
    raise ValueError('Release intake requires a new review candidate; existing output is preserved')
  if not VERSION.fullmatch(version) or not re.fullmatch('[a-f0-9]{40}', commit) or run_id <= 0:
    raise ValueError('Expected an explicit stable version, commit and successful release run')
  release = api('/releases/tags/v' + version)
  if (release.get('draft') is not False or release.get('prerelease') is not False
      or release.get('tag_name') != 'v' + version or not release.get('published_at')):
    raise ValueError('Expected a published stable release')
  obj = api('/git/ref/tags/v' + version)['object']
  for _ in range(4):
    if obj.get('type') == 'commit': break
    if obj.get('type') != 'tag' or not re.fullmatch('[a-f0-9]{40}', obj.get('sha', '')):
      raise ValueError('Unexpected tag object')
    obj = api('/git/tags/' + obj['sha'])['object']
  if obj.get('type') != 'commit' or obj.get('sha') != commit:
    raise ValueError('Release tag does not match the expected commit')
  run = api('/actions/runs/' + str(run_id))
  if (run.get('head_sha') != commit or run.get('head_branch') != 'v' + version
      or run.get('conclusion') != 'success' or run.get('status') != 'completed'
      or run.get('event') != 'push' or run.get('path') != '.github/workflows/release.yml'
      or run.get('repository', {}).get('full_name') != 'Akkitto/Tauridium'):
    raise ValueError('Expected the successful protected release workflow for this tag')
  rows = {}
  for row in release.get('assets', []):
    name = row.get('name')
    if name not in names(version): continue
    if (name in rows or row.get('state') != 'uploaded'
        or row.get('browser_download_url') != release_url(version, name)
        or not isinstance(row.get('digest'), str) or not row['digest'].startswith('sha256:')):
      raise ValueError('Unexpected or duplicate public MSI asset')
    rows[name] = {'size': row.get('size'), 'sha256': row['digest'][7:]}
  lock = dict(schema=1, version=version, commit=commit, releaseId=release['id'], runId=run_id, assets=rows)
  validate_lock(lock)
  with tempfile.TemporaryDirectory(prefix='tauridium-chocolatey-intake-') as temporary:
    fetch(lock, Path(temporary) / 'assets')
  output.parent.mkdir(parents=True, exist_ok=True)
  with output.open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(json.dumps(lock, indent=2, sort_keys=True) + '\n')


def nuspec(version: str) -> bytes:
  package = ET.Element('package', xmlns='http://schemas.microsoft.com/packaging/2015/06/nuspec.xsd')
  metadata = ET.SubElement(package, 'metadata')
  for name, value in {
      'id': PACKAGE, 'version': version, 'title': 'Tauridium', 'authors': 'brani',
      'projectUrl': 'https://github.com/Akkitto/Tauridium',
      'licenseUrl': f'https://github.com/Akkitto/Tauridium/blob/v{version}/LICENSE',
      'requireLicenseAcceptance': 'false', 'summary': 'Native WebView desktop hub for web services.',
      'description': 'Tauridium local package for Windows x64 and ARM64. Uses verified machine-wide MSI installers. Application data is preserved on removal.',
      'releaseNotes': f'https://github.com/Akkitto/Tauridium/releases/tag/v{version}',
      'tags': 'tauridium chat messaging productivity tauri',
  }.items():
    ET.SubElement(metadata, name).text = value
  files = ET.SubElement(package, 'files')
  ET.SubElement(files, 'file', src='tools/**', target='tools')
  ET.SubElement(files, 'file', src='LICENSE.txt', target='')
  ET.SubElement(files, 'file', src='VERIFICATION.txt', target='')
  return ET.tostring(package, encoding='utf-8', xml_declaration=True) + b'\n'


def staging_files(lock: dict, assets: Path) -> dict[str, bytes]:
  validate_lock(lock)
  files = {'tauridium.nuspec': nuspec(lock['version']),
           'LICENSE.txt': (ROOT / 'LICENSE').read_bytes(),
           'VERIFICATION.txt': ('Self-contained local package; no registry submission.\n'
              'MSI sizes, SHA-256 and version-bound publisher signatures verified before packaging.\n'
              f'Source: https://github.com/Akkitto/Tauridium/tree/{lock["commit"]}\n'
              f'Release workflow: https://github.com/Akkitto/Tauridium/actions/runs/{lock["runId"]}\n'
              'Review package source before elevated installation. Updater signatures are not Authenticode.\n').encode(),
           'tools/release.json': (json.dumps(lock, indent=2, sort_keys=True) + '\n').encode()}
  for name in SCRIPTS:
    files['tools/' + name] = (TEMPLATES / name).read_text(encoding='utf-8').replace('\r\n', '\n').encode()
  for name in sorted(names(lock['version'])):
    files['tools/installers/' + name] = (assets / name).read_bytes()
  return files


def check_tree(directory: Path, expected: dict[str, bytes]) -> None:
  if directory.is_symlink() or not directory.is_dir(): raise ValueError('Expected a regular package directory')
  actual = {}
  for path in directory.rglob('*'):
    metadata = path.lstat()
    if path.is_symlink() or getattr(metadata, 'st_file_attributes', 0) & 0x400:
      raise ValueError('Package staging must not contain links or reparse points')
    if not stat.S_ISREG(metadata.st_mode) and not stat.S_ISDIR(metadata.st_mode):
      raise ValueError('Package staging must not contain special files')
    if path.is_file():
      require_regular(path)
      actual[path.relative_to(directory).as_posix()] = path.read_bytes()
  if actual != expected: raise ValueError('Package staging differs from its exact reviewed inputs; preserve it for review')


def prepare(lock: dict, assets: Path, output: Path) -> None:
  verify_assets(lock, assets)
  expected = staging_files(lock, assets)
  if output.exists() or output.is_symlink():
    check_tree(output, expected)
    return
  output.parent.mkdir(parents=True, exist_ok=True)
  with tempfile.TemporaryDirectory(prefix='.chocolatey-stage-', dir=output.parent) as temporary:
    stage = Path(temporary)
    for name, payload in expected.items():
      path = stage / name;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(payload)
    check_tree(stage, expected)
    stage.rename(output)


def normalized_package(archive: Path, expected: dict[str, bytes]) -> dict[str, bytes]:
  """Check real choco pack output, normalizing only NuGet entropy/ZIP metadata."""
  require_regular(archive)
  if archive.stat().st_size > 600 * 1024**2: raise ValueError('Package exceeds its size limit')
  with zipfile.ZipFile(archive) as package:
    zip_layout(package)
    records = package.infolist()
    if len(records) > len(expected) + 16 or sum(r.file_size for r in records) > 600 * 1024**2:
      raise ValueError('NuGet package expansion exceeds its budget')
    if len(records) != len({r.filename for r in records}): raise ValueError('Duplicate package member')
    contents = {}
    for entry in records:
      if entry.is_dir(): continue
      if entry.filename in expected and entry.filename != 'tauridium.nuspec':
        if entry.file_size != len(expected[entry.filename]): raise ValueError('Packed input size changed')
      elif entry.file_size > 128 * 1024:
        raise ValueError('Unexpected large package metadata')
      if (entry.file_size > 256 * 1024**2 or entry.flag_bits & 1
          or stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG)):
        raise ValueError('Unsafe package member')
      contents[entry.filename] = package.read(entry)
  allowed = set(expected) | {'[Content_Types].xml', '_rels/.rels'}
  cores = [n for n in contents if re.fullmatch(r'package/services/metadata/core-properties/[a-zA-Z0-9-]+\.psmdcp', n)]
  if len(cores) != 1 or set(contents) != allowed | set(cores): raise ValueError('Unexpected NuGet package inventory')
  for name, payload in expected.items():
    if name == 'tauridium.nuspec': continue
    if contents[name] != payload: raise ValueError('Packed payload differs from its verified staging input')
  # NuGet serializes the nuspec and removes the source-file map. Validate its
  # metadata semantically, then keep its emitted representation.
  def xml(data):
    if b'<!' in data: raise ValueError('DTD/declarations are not permitted in package metadata')
    return ET.fromstring(data)
  def metadata(data):
    document = xml(data)
    nodes = [e for e in document if e.tag.rsplit('}', 1)[-1] == 'metadata']
    if len(nodes) != 1: raise ValueError('Invalid NuGet metadata')
    result = {}
    for element in nodes[0]:
      name = element.tag.rsplit('}', 1)[-1]
      if name in result or len(element): raise ValueError('Duplicate or nested NuGet metadata')
      attributes = dict(element.attrib)
      # NuGet can add an XML whitespace-preservation annotation and reorder
      # scalar metadata. Neither changes identity or introduces dependencies.
      if attributes.get('{http://www.w3.org/XML/1998/namespace}space') == 'preserve':
        del attributes['{http://www.w3.org/XML/1998/namespace}space']
      result[name] = (element.text, sorted(attributes.items()))
    return result
  if metadata(contents['tauridium.nuspec']) != metadata(expected['tauridium.nuspec']):
    raise ValueError('NuGet changed package identity, dependencies or metadata')
  core = cores[0];fixed = 'package/services/metadata/core-properties/tauridium.psmdcp'
  for name in ('[Content_Types].xml', '_rels/.rels', core):
    document = xml(contents.pop(name))
    for index, node in enumerate(document.iter()):
      for key, value in list(node.attrib.items()):
        if value.lstrip('/') == core: node.set(key, ('/' if value.startswith('/') else '') + fixed)
        if node.tag.rsplit('}', 1)[-1] == 'Relationship' and key == 'Id': node.set(key, 'R' + str(index))
      if node.tag.rsplit('}', 1)[-1] in ('created', 'modified'): node.text = '1980-01-01T00:00:00Z'
    contents[fixed if name == core else name] = ET.tostring(document, encoding='utf-8', xml_declaration=True)
  return contents


def pack(lock: dict, assets: Path, stage: Path, output: Path) -> None:
  verify_assets(lock, assets)
  expected = staging_files(lock, assets);check_tree(stage, expected)
  if os.name != 'nt': raise ValueError('Actual choco pack requires native Windows; preparation works on Linux')
  command = shutil.which('choco.exe')
  if not command: raise ValueError('Install Chocolatey before building a local package')
  with tempfile.TemporaryDirectory(prefix='tauridium-choco-pack-') as temporary:
    subprocess.run([command, 'pack', str(stage / 'tauridium.nuspec'), '--outputdirectory', temporary, '--no-progress'], check=True, timeout=120)
    files = list(Path(temporary).iterdir())
    if len(files) != 1 or files[0].name != f'{PACKAGE}.{lock["version"]}.nupkg': raise ValueError('Unexpected choco pack output')
    contents = normalized_package(files[0], expected)
    # Rebuild in fixed order with fixed ZIP attributes after validating real NuGet output.
    buffer = Path(temporary) / 'canonical.nupkg'
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
      for name, payload in sorted(contents.items()):
        entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0));entry.create_system = 3;entry.external_attr = 0o100644 << 16;entry.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(entry, payload)
    if output.exists() or output.is_symlink():
      require_regular(output)
      if output.read_bytes() != buffer.read_bytes():
        differences = []
        with zipfile.ZipFile(output) as prior:
          for name, payload in contents.items():
            before = prior.read(name)
            if before == payload: continue
            fields = []
            if name.endswith(('.xml', '.rels', '.psmdcp', '.nuspec')):
              old_nodes = list(ET.fromstring(before).iter())
              new_nodes = list(ET.fromstring(payload).iter())
              for a, b in zip(old_nodes, new_nodes):
                if a.text != b.text or a.attrib != b.attrib:
                  field = b.tag.rsplit('}', 1)[-1]
                  fields.append(field if field in {'Relationship','Override','Default','creator','identifier','version','title','description','keywords','lastModifiedBy','created','modified'} else 'other')
            # Only generated allowlisted names/field labels are reported, not
            # arbitrary metadata values or possible credentials.
            label = name if name in expected or name in {'_rels/.rels','[Content_Types].xml','package/services/metadata/core-properties/tauridium.psmdcp'} else 'unexpected'
            differences.append({'member': label, 'fields': fields})
        raise ValueError('Existing local package differs; preserve it for review: ' + json.dumps(differences))
    else:
      output.parent.mkdir(parents=True, exist_ok=True)
      with output.open('xb') as stream: stream.write(buffer.read_bytes())


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__);sub = parser.add_subparsers(dest='command', required=True)
  p = sub.add_parser('intake');p.add_argument('--version', required=True);p.add_argument('--commit', required=True);p.add_argument('--run-id', type=int, required=True);p.add_argument('--output', type=Path, required=True)
  for command in ('fetch', 'prepare', 'pack'):
    p = sub.add_parser(command);p.add_argument('--lock', type=Path, required=True);p.add_argument('--assets-dir', type=Path, required=True)
    if command in ('prepare', 'pack'): p.add_argument('--stage', type=Path, required=True)
    if command == 'pack': p.add_argument('--output', type=Path, required=True)
  args = parser.parse_args()
  if args.command == 'intake': intake(args.version, args.commit, args.run_id, args.output)
  else:
    lock = load_json(args.lock)
    if args.command == 'fetch': fetch(lock, args.assets_dir)
    elif args.command == 'prepare': prepare(lock, args.assets_dir, args.stage)
    else: pack(lock, args.assets_dir, args.stage, args.output)
  print('Chocolatey ' + args.command + ' passed; no registry submission performed')


if __name__ == '__main__':
  try: main()
  except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
    raise SystemExit('error: ' + str(error)) from None
