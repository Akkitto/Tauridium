{ pkgs, package }:
pkgs.writeShellApplication {
  name = "tauridium-download-toast-smoke";
  runtimeInputs = with pkgs; [
    dbus
    xvfb-run
    xdotool
    imagemagick
    tesseract
    python3
  ];
  text = ''
    exec xvfb-run -a -s '-screen 0 1600x1000x24' \
      python3 ${../../tools/download_toast_smoke.py} \
      --binary ${package}/bin/tauridium \
      --dbus-config ${pkgs.dbus}/share/dbus-1/session.conf \
      --output "$PWD/release/evidence/download-toast-smoke" "$@"
  '';
}
