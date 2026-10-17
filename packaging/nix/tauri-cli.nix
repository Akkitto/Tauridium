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
    hash = "sha256-mm9H6GXHxSaIDZ46DEu4QlXW4/RfrCaErfgkWO5WWhg=";
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
cargo-tauri.overrideAttrs (_old: {
  pname = "tauri-cli";
  version = policy.tauriCliBuild;
  src = source;
  patches = [ ];
  postPatch = "";
  cargoDeps = rustPlatform.fetchCargoVendor {
    src = source;
    name = "tauri-cli-${policy.tauriCliBuild}";
    hash = "sha256-bKz9XNLr4rV7OZVMh5boTy1MhrgtInBGEmgkbt9V0+o=";
  };
})
