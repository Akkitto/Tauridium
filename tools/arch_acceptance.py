"""Build/install a prepared source recipe in a disposable, credential-free Arch container."""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
  subprocess.run(list(args), check=True)


def test(directory: Path, kind: str = "source") -> None:
  if kind not in ("source", "binary"):
    raise ValueError("unknown Arch package kind")
  package = "tauridium" if kind == "source" else "tauridium-bin"
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
      run("docker", "exec", container, "mkdir", "/tmp/arch-test-tools")
      for tool in ("arch_namcap.py", "arch_check.py", "nix_smoke.py", "appimage_audio_smoke.py", "linux_audio.py", "tauri_build.py"):
        run("docker", "cp", str(ROOT / "tools" / tool), container + ":/tmp/arch-test-tools/" + tool)
      run("docker", "exec", container, "chown", "-R", "builder:builder", "/home/builder/package")
      run("docker", "exec", "--user", "builder", "--workdir", "/home/builder/package", container,
          "bash", "-lc", "makepkg --verifysource && makepkg --printsrcinfo > .SRCINFO && python3 /tmp/arch-test-tools/arch_namcap.py PKGBUILD && makepkg --noconfirm && python3 /tmp/arch-test-tools/arch_namcap.py ./*.pkg.tar.zst")
      run("docker", "exec", container, "bash", "-lc", f"pacman -U --noconfirm /home/builder/package/*.pkg.tar.zst && pacman -Qkk {package} && desktop-file-validate /usr/share/applications/dev.brani.tauridium.desktop && appstreamcli validate --no-net /usr/share/metainfo/dev.brani.tauridium.metainfo.xml")
      run("docker", "exec", "--user", "builder", container, "bash", "-lc", "mkdir -p ~/.local/share/dev.brani.tauridium; printf 'synthetic preservation marker' > ~/.local/share/dev.brani.tauridium/arch-package-test.txt; /usr/bin/tauridium --build-info-file /tmp/installed-build-info.json")
      run("docker", "exec", "--user", "builder", container, "xvfb-run", "-a", "-s", "-screen 0 1280x800x24", "python3", "/tmp/arch-test-tools/nix_smoke.py", "/usr/bin/tauridium", "--distribution", "system-package", "--dbus-config", "/usr/share/dbus-1/session.conf", "--output", "/home/builder/arch-ui-proof")
      run("docker", "exec", "--user", "builder", container, "python3", "/tmp/arch-test-tools/appimage_audio_smoke.py", "--system-package", "/usr/bin/tauridium", "--output", "/home/builder/arch-audio-proof")
      run("docker", "exec", container, "bash", "-lc", f"pacman -R --noconfirm {package} && test ! -e /usr/bin/tauridium && pacman -U --noconfirm /home/builder/package/*.pkg.tar.zst && pacman -Qkk {package}")
      run("docker", "exec", "--user", "builder", container, "bash", "-lc", "test \"$(cat ~/.local/share/dev.brani.tauridium/arch-package-test.txt)\" = 'synthetic preservation marker'")
    finally:
      run("docker", "rm", "--force", container)
  finally:
    run("docker", "image", "rm", image)


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("directory", type=Path)
  parser.add_argument("--kind", choices=("source", "binary"), default="source")
  args = parser.parse_args()
  test(args.directory, args.kind)
