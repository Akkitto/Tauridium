{ pkgs, tauridium, ... }:
{
  environment.systemPackages = [ tauridium.packages.${pkgs.stdenv.hostPlatform.system}.default ];
}
