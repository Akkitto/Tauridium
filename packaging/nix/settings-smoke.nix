{ pkgs, package }:
pkgs.writeShellApplication {
  name = "tauridium-settings-smoke";
  runtimeInputs = with pkgs; [
    dbus
    xvfb-run
    xdotool
    imagemagick
    tesseract
    python3
  ];
  text = ''
    export PYTHONPATH=${pkgs.writeTextDir "nix_smoke.py" (builtins.readFile ../../tools/nix_smoke.py)}
    exec xvfb-run -a -s '-screen 0 1600x1100x24' \
      python3 ${../../tools/settings_smoke.py} \
      --binary ${package}/bin/tauridium \
      --dbus-config ${pkgs.dbus}/share/dbus-1/session.conf "$@"
  '';
}
