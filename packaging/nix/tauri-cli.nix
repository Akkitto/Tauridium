{
  cargo-tauri,
  fetchurl,
  lib,
  rustPlatform,
}:
let
  policy = lib.importJSON ../../data/build-toolchain.json;
  source = fetchurl {
    url = "https://static.crates.io/crates/tauri-cli/tauri-cli-${policy.tauriCli}.crate";
    name = "tauri-cli-${policy.tauriCli}.tar.gz";
    hash = "sha256-mm9H6GXHxSaIDZ46DEu4QlXW4/RfrCaErfgkWO5WWhg=";
  };
in
# Retain nixpkgs' platform dependencies and Tauri build hook, but build the
# exact reviewed published CLI crate, not an older workspace/dependency lock.
cargo-tauri.overrideAttrs (_old: {
  pname = "tauri-cli";
  version = policy.tauriCli;
  src = source;
  patches = [ ];
  postPatch = "";
  cargoDeps = rustPlatform.fetchCargoVendor {
    src = source;
    name = "tauri-cli-${policy.tauriCli}";
    hash = "sha256-VXoUAw3Eu+AzMS5LCHDgrdv/DjEBla4vxnl0+tlRlu0=";
  };
})
