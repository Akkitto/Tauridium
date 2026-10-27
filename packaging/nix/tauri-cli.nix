{
  cargo-tauri,
  fetchurl,
  lib,
  python3,
  runCommand,
  rustPlatform,
}:
let
  policy = lib.importJSON ../../data/build-toolchain.json;
  upstream = fetchurl {
    url = "https://static.crates.io/crates/tauri-cli/tauri-cli-${policy.tauriCli}.crate";
    name = "tauri-cli-${policy.tauriCli}.tar.gz";
    hash = "sha256-mWZVjalP0clIXQ148SIzvqX9QjWCb7eOkw/nomkQuVY=";
  };
  bundler = fetchurl {
    url = "https://static.crates.io/crates/tauri-bundler/tauri-bundler-${policy.tauriBundler}.crate";
    sha256 = policy.tauriBundlerCrateSha256;
  };
  source =
    runCommand "tauri-cli-${policy.tauriCliBuild}-source" { nativeBuildInputs = [ python3 ]; }
      ''
        python3 ${../../flatpak/prepare-tauri-cli.py} \
          --cli ${upstream} --bundler ${bundler} \
          --policy ${../../data/build-toolchain.json} \
          --lock ${../../flatpak/tauri-cli.Cargo.lock} --output "$out"
      '';
in
# Retain nixpkgs' platform dependencies and Tauri build hook, but build the
# checksum-verified stable CLI with the explicit shared ZIP 9 security migration.
(cargo-tauri.override { inherit rustPlatform; }).overrideAttrs (
  finalAttrs: oldAttrs: {
    pname = "tauri-cli";
    version = policy.tauriCliBuild;
    src = source;
    patches = [ ];
    postPatch = "";
    # The upstream hook separately propagates nixpkgs' Cargo. Pin that too so the
    # production application cannot discover a different toolchain through PATH.
    passthru = oldAttrs.passthru // {
      gst-plugin = oldAttrs.passthru.gst-plugin.override { inherit rustPlatform; };
      hook = oldAttrs.passthru.hook.override {
        cargo = rustPlatform.rust.cargo;
        cargo-tauri = finalAttrs.finalPackage;
      };
    };
    cargoDeps = rustPlatform.fetchCargoVendor {
      src = source;
      name = "tauri-cli-${policy.tauriCliBuild}";
      hash = "sha256-vWjSOeqxVg87qOLbcFBaZsdxEjxNPtEwyfLVkL+wUos=";
    };
  }
)
