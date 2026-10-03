import { describe, expect, it } from "vitest";
import { managedUpdateText } from "./distribution";

describe("distribution-managed updates", () => {
  it("explains Nix upgrades without suggesting Flatpak", () => {
    const text = managedUpdateText("nix");
    expect(text.badge).toBe("Managed by Nix");
    expect(text.description).toContain("NixOS/Home Manager");
    expect(text.description).not.toContain("Flatpak");
    expect(text.status).toContain("disabled");
  });
  it("preserves Flatpak update guidance", () => {
    expect(managedUpdateText("flatpak").badge).toBe("Managed by Flatpak");
  });
});
