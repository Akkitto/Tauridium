import { describe, expect, it } from "vitest";
import { nextMenuIndex, SERVICE_MENU_ACTIONS, serviceMenuEntries, type ServiceMenuEntry } from "./serviceMenu";

const items = (entries: ServiceMenuEntry[]) => entries.flatMap((entry) => (entry.kind === "item" ? [entry] : []));

describe("service menu entries", () => {
  it("keeps the original order, grouping and short toggle labels", () => {
    const entries = serviceMenuEntries({ enabled: true, zoomPercent: 100 });
    expect(entries.map((entry) => (entry.kind === "item" ? entry.label : "-"))).toEqual([
      "Settings",
      "Reload",
      "-",
      "Zoom in (110%)",
      "Zoom out (90%)",
      "Reset zoom (100%)",
      "-",
      "Duplicate",
      "-",
      "Disable",
    ]);
    // The native overlay is sized for exactly seven items and three separators.
    expect(items(entries)).toHaveLength(7);
    expect(entries.filter((entry) => entry.kind === "separator")).toHaveLength(3);
  });

  it("only offers actions the native layer accepts", () => {
    expect(items(serviceMenuEntries({ enabled: true, zoomPercent: 100 })).map((entry) => entry.action)).toEqual([
      ...SERVICE_MENU_ACTIONS,
    ]);
  });

  it("disables reload for disabled services and offers enabling", () => {
    const entries = items(serviceMenuEntries({ enabled: false, zoomPercent: 100 }));
    expect(entries.find((entry) => entry.action === "reload")?.disabled).toBe(true);
    const toggle = entries.find((entry) => entry.action === "toggle");
    expect(toggle).toMatchObject({ label: "Enable", danger: false });
  });

  it("marks disabling as the destructive action", () => {
    const toggle = items(serviceMenuEntries({ enabled: true, zoomPercent: 100 })).find((entry) => entry.action === "toggle");
    expect(toggle).toMatchObject({ label: "Disable", danger: true });
  });

  it("disables zoom actions at their limits and reset at the default", () => {
    const at = (zoomPercent: number) => {
      const entries = items(serviceMenuEntries({ enabled: true, zoomPercent }));
      return Object.fromEntries(entries.map((entry) => [entry.action, entry.disabled]));
    };
    expect(at(200)).toMatchObject({ "zoom-in": true, "zoom-out": false, "zoom-reset": false });
    expect(at(50)).toMatchObject({ "zoom-in": false, "zoom-out": true, "zoom-reset": false });
    expect(at(100)).toMatchObject({ "zoom-in": false, "zoom-out": false, "zoom-reset": true });
  });
});

describe("service menu keyboard navigation", () => {
  const enabled = [true, false, true, true, false, true];

  it("skips disabled items and wraps in both directions", () => {
    expect(nextMenuIndex("ArrowDown", 0, enabled)).toBe(2);
    expect(nextMenuIndex("ArrowDown", 5, enabled)).toBe(0);
    expect(nextMenuIndex("ArrowUp", 0, enabled)).toBe(5);
    expect(nextMenuIndex("ArrowUp", 2, enabled)).toBe(0);
  });

  it("starts at the first item going down and the last going up when nothing is focused", () => {
    expect(nextMenuIndex("ArrowDown", -1, enabled)).toBe(0);
    expect(nextMenuIndex("ArrowUp", -1, enabled)).toBe(5);
  });

  it("jumps to the first and last enabled items", () => {
    expect(nextMenuIndex("Home", 3, [false, true, true, false])).toBe(1);
    expect(nextMenuIndex("End", 1, [false, true, true, false])).toBe(2);
  });

  it("ignores other keys and menus without enabled items", () => {
    expect(nextMenuIndex("a", 0, enabled)).toBeNull();
    expect(nextMenuIndex("ArrowDown", 0, [false, false])).toBeNull();
    expect(nextMenuIndex("ArrowDown", 0, [])).toBeNull();
  });
});
