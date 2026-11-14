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
  it("explains system package ownership without claiming a specific registry", () => {
    const text = managedUpdateText("system-package");
    expect(text.badge).toBe("Managed by your package manager");
    expect(text.description).toContain("Rebuild or upgrade");
    expect(text.status).toContain("disabled");
    expect(text.description).not.toMatch(/Flathub|Nix|AUR/);
  });
  it("preserves Flatpak update guidance", () => {
    expect(managedUpdateText("flatpak").badge).toBe("Managed by Flatpak");
  });
});
