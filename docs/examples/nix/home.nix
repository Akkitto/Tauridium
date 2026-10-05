{ pkgs, tauridium, ... }:
{
  home.packages = [ tauridium.packages.${pkgs.stdenv.hostPlatform.system}.default ];
}
