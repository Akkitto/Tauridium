"""Build/install a prepared source recipe in a disposable, credential-free Arch container."""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
  subprocess.run(list(args), check=True)


def test(directory: Path) -> None:
  directory = directory.resolve(strict=True)
  if not (directory / "PKGBUILD").is_file():
    raise ValueError("prepared Arch recipe is missing")
  image = "tauridium-arch-test:" + uuid.uuid4().hex[:12]
  container = "tauridium-arch-test-" + uuid.uuid4().hex[:12]
  run("docker", "build", "--tag", image, str(ROOT / "packaging/aur"))
  try:
    run("docker", "run", "--detach", "--name", container, "--security-opt=no-new-privileges", image, "sleep", "infinity")
    try:
      run("docker", "cp", str(directory), container + ":/home/builder/package")
      run("docker", "exec", container, "chown", "-R", "builder:builder", "/home/builder/package")
      run("docker", "exec", "--user", "builder", "--workdir", "/home/builder/package", container,
          "bash", "-lc", "makepkg --verifysource && makepkg --printsrcinfo > .SRCINFO && namcap PKGBUILD && makepkg --noconfirm && namcap ./*.pkg.tar.zst")
      run("docker", "exec", container, "bash", "-lc", "pacman -U --noconfirm /home/builder/package/*.pkg.tar.zst && pacman -Qkk tauridium && desktop-file-validate /usr/share/applications/dev.brani.tauridium.desktop && appstreamcli validate --no-net /usr/share/metainfo/dev.brani.tauridium.metainfo.xml")
      run("docker", "exec", "--user", "builder", container, "bash", "-lc", "mkdir -p ~/.local/share/dev.brani.tauridium; printf 'synthetic preservation marker' > ~/.local/share/dev.brani.tauridium/arch-package-test.txt; /usr/bin/tauridium --build-info-file /tmp/installed-build-info.json")
      run("docker", "exec", container, "bash", "-lc", "pacman -R --noconfirm tauridium && test ! -e /usr/bin/tauridium && pacman -U --noconfirm /home/builder/package/*.pkg.tar.zst && pacman -Qkk tauridium")
      run("docker", "exec", "--user", "builder", container, "bash", "-lc", "test \"$(cat ~/.local/share/dev.brani.tauridium/arch-package-test.txt)\" = 'synthetic preservation marker'")
    finally:
      run("docker", "rm", "--force", container)
  finally:
    run("docker", "image", "rm", image)


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("directory", type=Path)
  test(parser.parse_args().directory)
