import { describe, expect, it } from "vitest";
import { menuKeyIndex } from "./windowChrome";

describe("Unified title-bar keyboard access", () => {
  it("wraps across the menu bar in both directions", () => {
    expect(menuKeyIndex("ArrowRight", 5, 6)).toBe(0);
    expect(menuKeyIndex("ArrowLeft", 0, 6)).toBe(5);
    expect(menuKeyIndex("ArrowRight", 0, 6)).toBe(1);
  });
  it("supports Home/End and the single compact menu", () => {
    expect(menuKeyIndex("Home", 3, 6)).toBe(0);
    expect(menuKeyIndex("End", 3, 6)).toBe(5);
    expect(menuKeyIndex("ArrowLeft", 0, 1)).toBe(0);
    expect(menuKeyIndex("ArrowRight", 0, 1)).toBe(0);
  });
  it("leaves activation, dismissal and normal typing to their handlers", () => {
    for (const key of ["Enter", " ", "Tab", "Escape", "a", "ArrowDown"]) {
      expect(menuKeyIndex(key, 0, 6)).toBeNull();
    }
    expect(menuKeyIndex("ArrowRight", 0, 0)).toBeNull();
  });
});
