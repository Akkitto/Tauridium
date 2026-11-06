#!/usr/bin/env python3
"""Prepare WinGet manifests from reviewed release locks and signed installers.

No credentials, package execution or registry writes are used by this adapter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from updater_signature import require_regular, verify
from security_tools import ensure_minisign

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "Akkitto.Tauridium"
SCHEMA = "1.12.0"
REPOSITORY = "Akkitto/Tauridium"
ARCHES = ("x64", "arm64")
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
HOSTS = {"github.com", "api.github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}


def load_json(path: Path) -> dict:
  require_regular(path)
  if path.stat().st_size > 128 * 1024:
    raise ValueError("WinGet metadata exceeds the size limit")
  def unique(pairs):
    result = {}
    for key, value in pairs:
      if key in result:
        raise ValueError("Duplicate metadata key")
      result[key] = value
    return result
  value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
  if not isinstance(value, dict):
    raise ValueError("Expected a metadata object")
  return value


def check_url(url: str) -> None:
  parsed = urlsplit(url)
  if (parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username
      or parsed.password or parsed.port not in (None, 443) or parsed.fragment):
    raise ValueError("Unapproved download URL")


class ReleaseRedirect(HTTPRedirectHandler):
  def redirect_request(self, request, fp, code, message, headers, newurl):
    check_url(newurl)
    return super().redirect_request(request, fp, code, message, headers, newurl)


def download(url: str, row: dict, output: Path) -> None:
  check_url(url)
  if output.exists() or output.is_symlink():
    raise ValueError("Download output must be new")
  size, checksum = row.get("size"), row.get("sha256")
  if type(size) is not int or not 0 < size < 512 * 1024**2 or not HEX.fullmatch(checksum or ""):
    raise ValueError("Invalid pinned download size/hash")
  opener = build_opener(ReleaseRedirect())
  with opener.open(Request(url, headers={"User-Agent": "Tauridium-WinGet/1"}), timeout=90) as source:
    check_url(source.url)
    digest, total = hashlib.sha256(), 0
    with output.open("xb") as destination:
      while block := source.read(1024 * 1024):
        total += len(block)
        if total > size:
          raise ValueError("Download exceeds pinned size")
        digest.update(block)
        destination.write(block)
  if total != size or digest.hexdigest() != checksum:
    raise ValueError("Download failed pinned size/hash verification")


def validate_lock(lock: dict) -> None:
  if set(lock) != {"schema", "version", "commit", "releaseId", "assets"} or type(lock["schema"]) is not int or lock["schema"] != 1:
    raise ValueError("Unsupported release lock")
  if not isinstance(lock["version"], str) or not VERSION.fullmatch(lock["version"]):
    raise ValueError("A stable numeric release version is required")
  if not isinstance(lock["commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", lock["commit"]) or type(lock["releaseId"]) is not int or lock["releaseId"] <= 0:
    raise ValueError("Invalid release identity")
  names = {f"tauridium-{lock['version']}-windows-{arch}-setup.exe{suffix}"
           for arch in ARCHES for suffix in ("", ".sig")}
  if not isinstance(lock["assets"], dict) or set(lock["assets"]) != names:
    raise ValueError("Release lock must contain the exact two installer/signature pairs")
  for name, row in lock["assets"].items():
    if (not isinstance(row, dict) or set(row) != {"sha256", "size"}
        or not isinstance(row.get("sha256"), str) or not HEX.fullmatch(row["sha256"]) or type(row.get("size")) is not int
        or not 0 < row["size"] <= (16384 if name.endswith(".sig") else 256 * 1024**2)):
      raise ValueError("Invalid locked asset")


def release_url(version: str, name: str) -> str:
  return f"https://github.com/{REPOSITORY}/releases/download/v{version}/{name}"


def verify_assets(lock: dict, directory: Path) -> None:
  validate_lock(lock)
  for name, row in lock["assets"].items():
    path = directory / name
    require_regular(path)
    if path.stat().st_size != row["size"] or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
      raise ValueError("Installer/signature size or SHA-256 differs from the reviewed lock")
  executable = ensure_minisign()
  for arch in ARCHES:
    path = directory / f"tauridium-{lock['version']}-windows-{arch}-setup.exe"
    if path.read_bytes()[:2] != b"MZ":
      raise ValueError("Expected a Windows installer")
    verify(path, path.with_suffix(".exe.sig"), lock["version"], executable=executable)


def fetch(lock: dict, output: Path) -> None:
  validate_lock(lock)
  if output.is_symlink():
    raise ValueError("Asset destination must not be a symlink")
  if output.exists():
    if not output.is_dir():
      raise ValueError("Asset destination must be a directory")
    verify_assets(lock, output)
    return
  output.parent.mkdir(parents=True, exist_ok=True)
  with tempfile.TemporaryDirectory(prefix=".winget-assets-", dir=output.parent) as temporary:
    stage = Path(temporary)
    for name, row in lock["assets"].items():
      download(release_url(lock["version"], name), row, stage / name)
    verify_assets(lock, stage)
    stage.rename(output)


def yaml(value, indent=0) -> list[str]:
  """Emit only our small deterministic YAML subset, quoting every scalar string."""
  prefix = " " * indent
  result = []
  if isinstance(value, dict):
    for key, child in value.items():
      if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", key):
        raise ValueError("Invalid manifest key")
      if isinstance(child, (dict, list)):
        result.append(prefix + key + ":")
        result.extend(yaml(child, indent + 2))
      else:
        result.append(prefix + key + ": " + json.dumps(child, ensure_ascii=False))
  elif isinstance(value, list):
    for child in value:
      if isinstance(child, dict):
        lines = yaml(child, indent + 2)
        result.append(prefix + "- " + lines[0].lstrip())
        result.extend(lines[1:])
      else:
        result.append(prefix + "- " + json.dumps(child, ensure_ascii=False))
  else:
    raise ValueError("Unsupported YAML value")
  return result


def manifests(lock: dict) -> dict[str, bytes]:
  validate_lock(lock)
  version = lock["version"]
  common = {"PackageIdentifier": PACKAGE, "PackageVersion": version}
  installer = common | {
    "InstallerType": "nullsoft", "Scope": "user", "UpgradeBehavior": "install",
    "InstallerSwitches": {"Silent": "/S", "SilentWithProgress": "/S"},
    "AppsAndFeaturesEntries": [{"DisplayName": "Tauridium", "Publisher": "brani", "ProductCode": "Tauridium"}],
    "Installers": [{"Architecture": arch,
                    "InstallerUrl": release_url(version, name := f"tauridium-{version}-windows-{arch}-setup.exe"),
                    "InstallerSha256": lock["assets"][name]["sha256"].upper()}
                   for arch in ARCHES],
    "ManifestType": "installer", "ManifestVersion": SCHEMA,
  }
  locale = common | {
    "PackageLocale": "en-US", "Publisher": "brani", "PublisherUrl": "https://github.com/Akkitto",
    "PackageName": "Tauridium", "PackageUrl": "https://github.com/Akkitto/Tauridium",
    "License": "MIT", "LicenseUrl": f"https://github.com/Akkitto/Tauridium/blob/v{version}/LICENSE",
    "ShortDescription": "Native WebView desktop hub for web services and workspaces.",
    "Moniker": "tauridium", "Tags": ["chat", "messaging", "productivity", "tauri", "web-apps"],
    "ReleaseNotesUrl": f"https://github.com/Akkitto/Tauridium/releases/tag/v{version}",
    "ManifestType": "defaultLocale", "ManifestVersion": SCHEMA,
  }
  documents = {f"{PACKAGE}.yaml": common | {"DefaultLocale": "en-US", "ManifestType": "version", "ManifestVersion": SCHEMA},
               f"{PACKAGE}.installer.yaml": installer, f"{PACKAGE}.locale.en-US.yaml": locale}
  result = {}
  for name, document in documents.items():
    kind = document["ManifestType"]
    schema = f"https://aka.ms/winget-manifest.{kind}.{SCHEMA}.schema.json"
    result[name] = (f"# yaml-language-server: $schema={schema}\r\n\r\n" + "\r\n".join(yaml(document)) + "\r\n").encode("utf-8")
  return result


def prepare(lock: dict, assets: Path, output: Path) -> None:
  verify_assets(lock, assets)
  if output.is_symlink():
    raise ValueError("Manifest output must not be a symlink")
  expected = manifests(lock)
  if output.exists():
    if not output.is_dir() or {path.name for path in output.iterdir()} != set(expected):
      raise ValueError("Existing manifest output has an unexpected inventory; preserve it for review")
    for name, payload in expected.items():
      path = output / name
      require_regular(path)
      if path.read_bytes() != payload:
        raise ValueError("Existing manifest bytes differ; preserve them for review")
    return
  output.parent.mkdir(parents=True, exist_ok=True)
  with tempfile.TemporaryDirectory(prefix=".winget-manifest-", dir=output.parent) as temporary:
    stage = Path(temporary)
    for name, payload in manifests(lock).items():
      (stage / name).write_bytes(payload)
    stage.rename(output)


def api(path: str) -> dict:
  url = 'https://api.github.com/repos/' + REPOSITORY + path
  with build_opener(ReleaseRedirect()).open(Request(url, headers={"User-Agent": "Tauridium-WinGet/1", "Accept": "application/vnd.github+json"}), timeout=60) as response:
    payload = response.read(8 * 1024**2 + 1)
  if len(payload) > 8 * 1024**2:
    raise ValueError("GitHub metadata exceeds its size limit")
  result = json.loads(payload)
  if not isinstance(result, dict):
    raise ValueError("Invalid GitHub metadata")
  return result


def intake(version: str, commit: str, run_id: int, output: Path) -> None:
  """Create a review candidate, never silently modify the committed release locks."""
  if not VERSION.fullmatch(version) or not re.fullmatch(r"[0-9a-f]{40}", commit) or run_id <= 0:
    raise ValueError("Expected an explicit stable version, commit and successful release run")
  release = api('/releases/tags/v' + version)
  if release.get('draft') is not False or release.get('prerelease') is not False or release.get('tag_name') != 'v' + version or not release.get('published_at'):
    raise ValueError("Expected a published stable release")
  obj = api('/git/ref/tags/v' + version)['object']
  for _ in range(4):
    if obj.get('type') == 'commit':
      break
    if obj.get('type') != 'tag' or not re.fullmatch(r'[0-9a-f]{40}', obj.get('sha', '')):
      raise ValueError('Unexpected release tag object')
    obj = api('/git/tags/' + obj['sha'])['object']
  if obj.get('type') != 'commit' or obj.get('sha') != commit:
    raise ValueError('Tag does not identify the expected commit')
  run = api('/actions/runs/' + str(run_id))
  if (run.get('head_sha') != commit or run.get('conclusion') != 'success'
      or run.get('status') != 'completed' or run.get('event') != 'push'
      or run.get('path') != '.github/workflows/release.yml'
      or run.get('repository', {}).get('full_name') != REPOSITORY):
    raise ValueError('Release workflow did not successfully verify this commit')
  wanted = {f'tauridium-{version}-windows-{arch}-setup.exe{suffix}' for arch in ARCHES for suffix in ('', '.sig')}
  assets = {}
  for row in release.get('assets', []):
    name = row.get('name')
    if name not in wanted:
      continue
    if name in assets or row.get('state') != 'uploaded' or row.get('browser_download_url') != release_url(version, name):
      raise ValueError('Duplicate or unexpected published asset')
    digest = row.get('digest', '')
    if not isinstance(digest, str) or not digest.startswith('sha256:'):
      raise ValueError('Published SHA-256 digest is missing')
    assets[name] = {'size': row.get('size'), 'sha256': digest[7:]}
  lock = {'schema': 1, 'version': version, 'commit': commit, 'releaseId': release['id'], 'assets': assets}
  validate_lock(lock)
  with tempfile.TemporaryDirectory(prefix='tauridium-winget-intake-') as directory:
    fetch(lock, Path(directory) / 'assets')
  output.parent.mkdir(parents=True, exist_ok=True)
  with output.open('x', encoding='utf-8', newline='\n') as destination:
    destination.write(json.dumps(lock, indent=2) + '\n')
  print(f'Candidate bound to successful release run {run_id}; review and commit this lock before submission')


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  sub = parser.add_subparsers(dest="command", required=True)
  p = sub.add_parser('intake')
  p.add_argument('--version', required=True)
  p.add_argument('--commit', required=True)
  p.add_argument('--run-id', required=True, type=int)
  p.add_argument('--output', required=True, type=Path)
  for command in ("fetch", "prepare"):
    p = sub.add_parser(command)
    p.add_argument("--lock", type=Path, required=True)
    p.add_argument("--assets-dir", type=Path, required=True)
    if command == "prepare":
      p.add_argument("--output", type=Path, required=True)
  args = parser.parse_args()
  if args.command == 'intake':
    intake(args.version, args.commit, args.run_id, args.output)
    return
  lock = load_json(args.lock)
  if args.command == "fetch":
    fetch(lock, args.assets_dir)
  else:
    prepare(lock, args.assets_dir, args.output)
  print(f"WinGet {args.command} passed for Tauridium {lock['version']}")


if __name__ == "__main__":
  try:
    main()
  except (ValueError, OSError, KeyError) as error:
    raise SystemExit(f"error: {error}") from None
