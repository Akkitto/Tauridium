"""Deterministic CycloneDX inventory of locked candidates, NOT a runtime reachability claim."""
import argparse
import json
from pathlib import Path
import tomllib
from urllib.parse import quote

from package_release import version, git_output
from npm_policy import LOCAL_PATH, validate_local_sources

ROOT = Path(__file__).resolve().parents[1]


def generate(root: Path, release_version: str, commit: str) -> dict:
  components = {}
  for lock, group in (("src-tauri/Cargo.lock", "application-all-target-candidates"),
                      ("flatpak/tauri-cli.Cargo.lock", "pinned-builder-all-target-candidates")):
    data = tomllib.loads((root / lock).read_text(encoding="utf-8"))
    for package in data["package"]:
      name, ver = package["name"], package["version"]
      ref = f"{group}:cargo:{name}@{ver}"
      component = {"type": "library", "name": name, "version": ver, "bom-ref": ref,
                   "scope": "optional", "purl": f"pkg:cargo/{quote(name)}@{quote(ver)}",
                   "properties": [{"name": "tauridium:dependency-set", "value": group},
                                  {"name": "tauridium:source", "value": package.get("source", "repository-path-patch")}]}
      if package.get("checksum"):
        component["hashes"] = [{"alg": "SHA-256", "content": package["checksum"]}]
      components[ref] = component
  npm = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))
  manifest = json.loads((root / "package.json").read_text(encoding="utf-8"))
  validate_local_sources(root, manifest, npm["packages"])
  for path, package in npm["packages"].items():
    if not path or path == LOCAL_PATH:
      # A local link and its lock target describe one package, not two components.
      continue
    name = path.rsplit("node_modules/", 1)[-1]
    if package.get("link"):
      local = package["resolved"]
      ver = npm["packages"][local]["version"]
      provenance = json.loads((root / local / "TAURIDIUM-PATCH.json").read_text(encoding="utf-8"))
      upstream = provenance["upstream"]
      ref = f"frontend:repository-path-patch:{local}@{ver}"
      # This modified in-tree source is not the upstream registry package. Keep
      # its upstream identity and individual source hashes explicitly qualified;
      # an npm purl or upstream checksum would misidentify the patched component.
      components[ref] = {
        "type": "library", "name": name, "version": ver, "bom-ref": ref,
        "scope": "optional",
        "properties": [
          {"name": "tauridium:dependency-set", "value": "frontend-build-input"},
          {"name": "tauridium:source", "value": "repository-path-patch:" + local},
          {"name": "tauridium:source-provenance", "value": local + "/TAURIDIUM-PATCH.json"},
          {"name": "tauridium:upstream-name", "value": upstream["name"]},
          {"name": "tauridium:upstream-version", "value": upstream["version"]},
          {"name": "tauridium:upstream-url", "value": upstream["url"]},
          {"name": "tauridium:upstream-integrity", "value": upstream["sha512"]},
        ] + [{"name": "tauridium:source-file-sha256:" + filename, "value": digest}
             for filename, digest in sorted(provenance["files"].items())],
      }
      continue
    ver = package["version"]
    purl = f"pkg:npm/{quote(name, safe='/')}@{quote(ver)}"
    ref = "frontend:" + purl
    components[ref] = {"type": "library", "name": name, "version": ver, "bom-ref": ref,
                       "purl": purl, "scope": "optional",
                       "properties": [{"name": "tauridium:dependency-set", "value": "frontend-build-input"},
                                      {"name": "tauridium:lock-integrity", "value": package.get("integrity", "")} ]}
  return {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
          "metadata": {"component": {"type": "application", "name": "Tauridium", "version": release_version},
                       "properties": [{"name": "tauridium:commit", "value": commit},
                                      {"name": "tauridium:scope", "value": "All locked optional/platform build candidates; not proof of installed runtime reachability"}]},
          "components": [components[key] for key in sorted(components)]}


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("output", type=Path)
  args = parser.parse_args()
  args.output.write_text(json.dumps(generate(ROOT, version(), git_output("rev-parse", "HEAD")),
                                   indent=2, sort_keys=True) + "\n", encoding="utf-8")
