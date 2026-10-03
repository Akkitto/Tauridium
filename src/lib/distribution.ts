import type { DistributionInfo } from "./api";

export function managedUpdateText(mode: DistributionInfo["mode"]) {
  if (mode === "nix") {
    return {
      description: "This package is updated by Nix. Upgrade your profile or rebuild your NixOS/Home Manager configuration.",
      badge: "Managed by Nix",
      status: "Native GitHub update checks and installation are disabled in this Nix build.",
    };
  }
  return {
    description: "This package is updated by Flatpak/Flathub.",
    badge: "Managed by Flatpak",
    status: "Native GitHub update checks and installation are disabled in this Flatpak build.",
  };
}
