{ pkgs, package }:
pkgs.writeShellApplication {
  name = "tauridium-security-boundary-smoke";
  runtimeInputs = with pkgs; [
    dbus
    xvfb-run
    python3
  ];
  text = ''
    export PYTHONPATH=${pkgs.writeTextDir "nix_smoke.py" (builtins.readFile ../../tools/nix_smoke.py)}
    exec xvfb-run -a -s '-screen 0 1280x800x24' \
      python3 ${../../tools/security_boundary_smoke.py} \
      --binary ${package}/bin/tauridium \
      --dbus-config ${pkgs.dbus}/share/dbus-1/session.conf "$@"
  '';
}
