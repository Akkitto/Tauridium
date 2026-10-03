{ pkgs, package }:
pkgs.writeShellApplication {
  name = "tauridium-nix-smoke";
  runtimeInputs = with pkgs; [
    dbus
    xvfb-run
    xdotool
    imagemagick
    tesseract
    python3
  ];
  text = ''
    exec xvfb-run -a -s '-screen 0 1280x800x24' \
      python3 ${../../tools/nix_smoke.py} ${package}/bin/tauridium \
      --dbus-config ${pkgs.dbus}/share/dbus-1/session.conf "$@"
  '';
}
