{
  description = "Isolated real NixOS/Home Manager consumer evaluation, never activation";
  inputs = {
    tauridium.url = "path:../..";
    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "tauridium/nixpkgs";
    };
  };
  outputs =
    { tauridium, home-manager, ... }:
    let
      nixpkgs = tauridium.inputs.nixpkgs;
      forSystems = nixpkgs.lib.genAttrs [
        "x86_64-linux"
        "aarch64-linux"
      ];
      examples =
        system:
        import ../../docs/examples/nix/consumer.nix {
          inherit
            system
            nixpkgs
            home-manager
            tauridium
            ;
        };
      homeBase = {
        home.username = "demo";
        home.homeDirectory = "/home/demo";
        home.stateVersion = "26.05";
      };
    in
    {
      reports = forSystems (
        system:
        let
          package = tauridium.packages.${system}.default;
          configs = examples system;
          contains = packages: builtins.elem package.drvPath (map (p: p.drvPath) packages);
          homeChecks = nixpkgs.lib.mapAttrs (
            name: value:
            assert contains value.config.home.packages;
            assert builtins.all (a: a.assertion) value.config.assertions;
            {
              activation = value.activationPackage.drvPath;
            }
          ) configs.homeConfigurations;
          nixosChecks = nixpkgs.lib.mapAttrs (
            name: value:
            if
              builtins.elem name [
                "integrated"
                "integratedOverlay"
              ]
            then
              let
                home = value.config.home-manager.users.demo;
              in
              assert contains home.home.packages;
              assert builtins.all (a: a.assertion) home.assertions;
              {
                activation = home.home.activationPackage.drvPath;
              }
            else
              assert contains value.config.environment.systemPackages;
              {
                package = package.drvPath;
              }
          ) configs.nixosConfigurations;
        in
        {
          inherit homeChecks nixosChecks;
          directAlias =
            assert package.drvPath == tauridium.packages.${system}.tauridium.drvPath;
            true;
        }
      );
      failures = forSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        {
          homeMissingArgument =
            (home-manager.lib.homeManagerConfiguration {
              inherit pkgs;
              modules = [
                homeBase
                ../../docs/examples/nix/home.nix
              ];
            }).activationPackage.drvPath;
          nixosMissingArgument =
            (nixpkgs.lib.nixosSystem {
              inherit system;
              modules = [ ../../docs/examples/nix/nixos.nix ];
            }).config.environment.systemPackages;
          integratedMissingArgument =
            (nixpkgs.lib.nixosSystem {
              inherit system;
              # NixOS specialArgs does not reach the nested Home Manager modules.
              specialArgs = { inherit tauridium; };
              modules = [
                home-manager.nixosModules.home-manager
                {
                  users.users.demo.isNormalUser = true;
                  home-manager.users.demo = {
                    imports = [ ../../docs/examples/nix/home.nix ];
                    home.stateVersion = "26.05";
                  };
                }
              ];
            }).config.home-manager.users.demo.home.activationPackage.drvPath;
        }
      );
    };
}
