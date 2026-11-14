import type { DistributionInfo } from "./api";

export function managedUpdateText(mode: DistributionInfo["mode"]) {
  if (mode === "system-package") {
    return {
      description: "This package is updated by your system package manager. Rebuild or upgrade your Tauridium package to update it.",
      badge: "Managed by your package manager",
      status: "Native GitHub update checks and installation are disabled in this system package build.",
    };
  }
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
