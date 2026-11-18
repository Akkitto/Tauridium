{ pkgs, package }:
let
  inputHelper =
    pkgs.runCommandCC "tauridium-wayland-input"
      {
        nativeBuildInputs = [ pkgs.pkg-config ];
        buildInputs = [ pkgs.wayland ];
      }
      ''
        mkdir -p "$out/bin"
        $CC -std=c11 -O2 -Wall -Wextra -Werror \
          ${../../tools/wayland_input.c} \
          $(pkg-config --cflags --libs wayland-client) \
          -o "$out/bin/tauridium-wayland-input"
      '';
in
pkgs.writeShellApplication {
  name = "tauridium-service-menu-wayland-smoke";
  runtimeInputs = with pkgs; [
    dbus
    sway-unwrapped
    grim
    wtype
    imagemagick
    tesseract
    python3
  ];
  text = ''
    export PYTHONPATH=${pkgs.writeTextDir "nix_smoke.py" (builtins.readFile ../../tools/nix_smoke.py)}
    exec python3 ${../../tools/service_menu_wayland_smoke.py} \
      --binary ${package}/bin/tauridium \
      --input-helper ${inputHelper}/bin/tauridium-wayland-input \
      --output "$PWD/release/evidence/service-menu-wayland" "$@"
  '';
}
