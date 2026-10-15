"""Install only checksum-pinned official Linux x64 scanner binaries, never artifact payloads."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import tarfile
import tempfile
from urllib.parse import urlparse
from urllib.request import build_opener, HTTPRedirectHandler, Request

ROOT = Path(__file__).resolve().parents[1]


class HttpsOnlyRedirect(HTTPRedirectHandler):
  def redirect_request(self, request, fp, code, message, headers, newurl):
    if urlparse(newurl).scheme != "https":
      raise ValueError("Scanner download must not downgrade HTTPS")
    return super().redirect_request(request, fp, code, message, headers, newurl)


def install(output: Path) -> None:
  if platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
    raise SystemExit("error: isolated public artifact scanning runs on Linux x64")
  if output.exists() or output.is_symlink():
    raise SystemExit("error: scanner installation requires a fresh directory")
  output.parent.mkdir(parents=True, exist_ok=True)
  policy = json.loads((ROOT / "data/security-tools.json").read_text(encoding="utf-8"))
  opener = build_opener(HttpsOnlyRedirect())
  with tempfile.TemporaryDirectory(prefix=".tauridium-scanners-", dir=output.parent) as temporary:
    staged = Path(temporary)
    for name, entry in policy.items():
      if not entry["url"].startswith("https://github.com/"):
        raise SystemExit("error: unapproved scanner origin")
      with opener.open(Request(entry["url"], headers={"User-Agent": "Tauridium-security-tools"}), timeout=60) as response:
        data = response.read(64 * 1024**2 + 1)
      if len(data) > 64 * 1024**2 or hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise SystemExit("error: scanner archive checksum/size verification failed")
      with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
        matches = [member for member in archive.getmembers() if member.name == entry["member"]]
        if len(matches) != 1 or not matches[0].isfile() or not 0 < matches[0].size < 64 * 1024**2:
          raise SystemExit("error: scanner archive has no unique regular executable")
        stream = archive.extractfile(matches[0])
        if stream is None:
          raise SystemExit("error: scanner archive executable cannot be read")
        (staged / name).write_bytes(stream.read())
        (staged / name).chmod(0o755)
    os.rename(staged, output)
  print(f"Verified scanner tools installed: {output}")


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("output", type=Path)
  install(parser.parse_args().output)
