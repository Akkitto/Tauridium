{
  description = "Tauridium: source-built Linux desktop package and development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    rust-overlay = {
      url = "github:oxalica/rust-overlay";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      rust-overlay,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      pkgsFor =
        system:
        import nixpkgs {
          inherit system;
          overlays = [ rust-overlay.overlays.default ];
        };
    in
    {
      # Keep the tested compiler/dependency lock even on an older NixOS channel.
      overlays.default = final: prev: {
        tauridium = self.packages.${final.stdenv.hostPlatform.system}.tauridium;
      };
      packages = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        {
          tauridium = pkgs.callPackage ./packaging/nix/package.nix { };
          default = self.packages.${system}.tauridium;
          smoke = import ./packaging/nix/smoke.nix {
            inherit pkgs;
            package = self.packages.${system}.tauridium;
          };
          download-toast-smoke = import ./packaging/nix/download-toast-smoke.nix {
            inherit pkgs;
            package = self.packages.${system}.tauridium;
          };
          settings-smoke = import ./packaging/nix/settings-smoke.nix {
            inherit pkgs;
            package = self.packages.${system}.tauridium;
          };
          nixos-test = import ./packaging/nix/nixos-test.nix {
            inherit pkgs;
            package = self.packages.${system}.tauridium;
            smoke = self.packages.${system}.smoke;
          };
        }
      );
      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.tauridium}/bin/tauridium";
          meta.description = "Tauridium desktop service hub";
        };
        smoke = {
          type = "app";
          program = "${self.packages.${system}.smoke}/bin/tauridium-nix-smoke";
          meta.description = "Isolated production Nix/WebKit graphical smoke test";
        };
        download-toast-smoke = {
          type = "app";
          program = "${self.packages.${system}.download-toast-smoke}/bin/tauridium-download-toast-smoke";
          meta.description = "Isolated production download and notification UI tests";
        };
        settings-smoke = {
          type = "app";
          program = "${self.packages.${system}.settings-smoke}/bin/tauridium-settings-smoke";
          meta.description = "Isolated production Settings navigation and control tests";
        };
      });
      formatter = forAllSystems (system: (pkgsFor system).nixfmt);
      checks = forAllSystems (system: {
        package = self.packages.${system}.tauridium;
      });
      devShells = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
          toolchain = pkgs.rust-bin.fromRustupToolchainFile ./rust-toolchain.toml;
        in
        {
          default = pkgs.mkShell {
            packages = with pkgs; [
              toolchain
              cargo-tauri
              nodejs_24
              python3
              just
              pkg-config
              git
              appstream
              desktop-file-utils
              nixfmt
            ];
            buildInputs = with pkgs; [
              gtk3
              webkitgtk_4_1
              openssl
              glib-networking
              librsvg
              libayatana-appindicator
              xdotool
              gst_all_1.gst-plugins-base
              gst_all_1.gst-plugins-good
              gst_all_1.gst-plugins-bad
              gst_all_1.gst-libav
            ];
            TAURIDIUM_NIX_DEV_SHELL = "1";
            LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [ pkgs.libayatana-appindicator ];
          };
        }
      );
    };
}
