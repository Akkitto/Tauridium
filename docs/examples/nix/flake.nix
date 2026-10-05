{
  description = "Tauridium consumption examples (evaluation only; adapt your existing host/user configuration)";
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    tauridium.url = "github:Akkitto/Tauridium/v0.9.2";
  };
  outputs =
    {
      nixpkgs,
      home-manager,
      tauridium,
      ...
    }:
    import ./consumer.nix {
      inherit nixpkgs home-manager tauridium;
      system = "x86_64-linux";
    };
}
