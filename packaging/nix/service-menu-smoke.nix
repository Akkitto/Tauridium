{ pkgs, package }:
pkgs.writeShellApplication {
  name = "tauridium-service-menu-smoke";
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
    exec xvfb-run -a -s '-screen 0 1600x1000x24' \
      python3 ${../../tools/service_menu_smoke.py} \
      --binary ${package}/bin/tauridium \
      --output "$PWD/release/evidence/service-menu" "$@"
  '';
}
