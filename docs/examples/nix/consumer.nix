# Evaluation-only examples: merge the chosen pattern into your existing configuration.
{
  nixpkgs,
  home-manager,
  tauridium,
  system,
}:
let
  pkgs = import nixpkgs { inherit system; };
  overlayPkgs = import nixpkgs {
    inherit system;
    overlays = [ tauridium.overlays.default ];
  };
  homeBase = {
    home.username = "demo";
    home.homeDirectory = "/home/demo";
    home.stateVersion = "26.05";
  };
in
{
  nixosConfigurations = {
    direct = nixpkgs.lib.nixosSystem {
      inherit system;
      specialArgs = { inherit tauridium; };
      modules = [ ./nixos.nix ];
    };
    overlay = nixpkgs.lib.nixosSystem {
      inherit system;
      modules = [
        {
          nixpkgs.overlays = [ tauridium.overlays.default ];
        }
        ({ pkgs, ... }: { environment.systemPackages = [ pkgs.tauridium ]; })
      ];
    };
    closure = nixpkgs.lib.nixosSystem {
      inherit system;
      modules = [
        ({ pkgs, ... }: {
          environment.systemPackages = [ tauridium.packages.${pkgs.stdenv.hostPlatform.system}.default ];
        })
      ];
    };
    integrated = nixpkgs.lib.nixosSystem {
      inherit system;
      modules = [
        home-manager.nixosModules.home-manager
        {
          users.users.demo.isNormalUser = true;
          home-manager.useGlobalPkgs = true;
          home-manager.useUserPackages = true;
          home-manager.extraSpecialArgs = { inherit tauridium; };
          home-manager.users.demo = {
            imports = [ ./home.nix ];
            home.stateVersion = homeBase.home.stateVersion;
          };
        }
      ];
    };
    integratedOverlay = nixpkgs.lib.nixosSystem {
      inherit system;
      modules = [
        home-manager.nixosModules.home-manager
        {
          nixpkgs.overlays = [ tauridium.overlays.default ];
          users.users.demo.isNormalUser = true;
          home-manager.useGlobalPkgs = true;
          home-manager.useUserPackages = true;
          home-manager.users.demo = {
            home.stateVersion = homeBase.home.stateVersion;
            imports = [ ({ pkgs, ... }: { home.packages = [ pkgs.tauridium ]; }) ];
          };
        }
      ];
    };
  };
  homeConfigurations = {
    direct = home-manager.lib.homeManagerConfiguration {
      inherit pkgs;
      extraSpecialArgs = { inherit tauridium; };
      modules = [
        homeBase
        ./home.nix
      ];
    };
    overlay = home-manager.lib.homeManagerConfiguration {
      pkgs = overlayPkgs;
      modules = [
        homeBase
        ({ pkgs, ... }: { home.packages = [ pkgs.tauridium ]; })
      ];
    };
    inputs = home-manager.lib.homeManagerConfiguration {
      inherit pkgs;
      extraSpecialArgs = {
        inputs = { inherit tauridium; };
      };
      modules = [
        homeBase
        (
          { pkgs, inputs, ... }:
          {
            home.packages = [ inputs.tauridium.packages.${pkgs.stdenv.hostPlatform.system}.default ];
          }
        )
      ];
    };
    closure = home-manager.lib.homeManagerConfiguration {
      inherit pkgs;
      modules = [
        homeBase
        ({ pkgs, ... }: {
          home.packages = [ tauridium.packages.${pkgs.stdenv.hostPlatform.system}.default ];
        })
      ];
    };
  };
}
