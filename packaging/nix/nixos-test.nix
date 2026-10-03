{
  pkgs,
  package,
  smoke,
}:
pkgs.testers.runNixOSTest {
  name = "tauridium-nixos";
  # TCG is permitted on hosts without KVM; no daemon configuration changes needed.
  requiredFeatures.kvm = false;
  requiredFeatures.nixos-test = false;
  nodes.desktop = { pkgs, ... }: {
    environment.systemPackages = [
      package
      smoke
    ];
    users.users.tester = {
      isNormalUser = true;
    };
    services.dbus.enable = true;
    fonts.packages = [ pkgs.dejavu_fonts ];
    virtualisation.memorySize = 4096;
    virtualisation.cores = 2;
  };
  testScript = ''
    desktop.start()
    desktop.wait_for_unit("multi-user.target")
    desktop.succeed("su - tester -c 'tauridium-nix-smoke --timeout 300 --output /tmp/tauridium-evidence'")
    desktop.succeed("test ! -e /home/tester/.config/autostart/dev.brani.tauridium.desktop")
    desktop.copy_from_machine("/tmp/tauridium-evidence", "evidence")
  '';
}
