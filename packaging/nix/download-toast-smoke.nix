{ pkgs, package }:
let
  testTools = pkgs.runCommand "tauridium-download-test-tools" { } ''
    mkdir -p "$out"
    cp ${../../tools/download_toast_smoke.py} "$out/download_toast_smoke.py"
    cp ${../../tools/download_file_manager_fixture.py} "$out/download_file_manager_fixture.py"
  '';
in
pkgs.writeShellApplication {
  name = "tauridium-download-toast-smoke";
  runtimeInputs = with pkgs; [
    dbus
    xvfb-run
    xdotool
    imagemagick
    tesseract
    python3
    thunar
    xclip
    glib
  ];
  text = ''
    exec xvfb-run -a -s '-screen 0 1600x1000x24' \
      python3 ${testTools}/download_toast_smoke.py \
      --binary ${package}/bin/tauridium \
      --file-manager ${pkgs.thunar}/bin/thunar \
      --dbus-config ${pkgs.dbus}/share/dbus-1/session.conf \
      --output "$PWD/release/evidence/download-toast-smoke" "$@"
  '';
}
