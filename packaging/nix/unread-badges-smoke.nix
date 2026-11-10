{ pkgs, package }:
let
  privateBus = pkgs.writeText "tauridium-badge-session.conf" ''
    <!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN" "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
    <busconfig>
      <type>session</type>
      <listen>unix:tmpdir=/tmp</listen>
      <auth>EXTERNAL</auth>
      <policy context="default">
        <allow send_destination="*" eavesdrop="true"/>
        <allow eavesdrop="true"/>
        <allow own="*"/>
      </policy>
    </busconfig>
  '';
  revision = (builtins.fromJSON (builtins.readFile ../../data/recipe-source.json)).revision;
in
pkgs.writeShellApplication {
  name = "tauridium-unread-badges-smoke";
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
    exec xvfb-run -a -s '-screen 0 1280x800x24' \
      python3 ${../../tools/unread_badges_smoke.py} \
      --binary ${package}/bin/tauridium \
      --dbus-config ${privateBus} \
      --fixtures ${../../tools/fixtures/badges} \
      --recipe-revision ${revision} "$@"
  '';
}
