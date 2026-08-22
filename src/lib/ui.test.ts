import { describe, it, expect } from "vitest";
import {
  DEFAULT_KEYBINDINGS,
  accentFg,
  bindingStrokes,
  duplicateServiceName,
  filterRecipes,
  hexToHsl,
  hslToHex,
  iconSrc,
  keyStrokeFromEvent,
  normalizeHexColor,
  orderWorkspacesForQuickSwitch,
  resolveStartupWorkspaceId,
  paged,
  recipeIcon,
  sameDownloadPreference,
  shortcutConflicts,
  snapIconSize,
} from "./ui";

describe("sameDownloadPreference", () => {
  it("compares values rather than object key insertion order", () => {
    const frontend = { directory: "D:/Downloads", askEachDownload: true };
    const backend = { askEachDownload: true, directory: "D:/Downloads" };
    expect(sameDownloadPreference(frontend, backend)).toBe(true);
  });

  it("distinguishes changed fields and treats nullish inheritance equally", () => {
    expect(sameDownloadPreference(null, undefined)).toBe(true);
    expect(sameDownloadPreference({ directory: "", askEachDownload: false }, { directory: "", askEachDownload: true })).toBe(false);
  });
});

describe("accentFg", () => {
  it("returns dark text on light accents (Tauri yellow)", () => {
    expect(accentFg("#ffc131")).toBe("#000000");
    expect(accentFg("#ffffff")).toBe("#000000");
  });
  it("returns white text on dark accents", () => {
    expect(accentFg("#4f46e5")).toBe("#ffffff");
    expect(accentFg("#000000")).toBe("#ffffff");
    expect(accentFg("#16a34a")).toBe("#000000");
  });
  it("tolerates short / malformed hex", () => {
    expect(accentFg("#abc")).toBe("#ffffff");
    expect(accentFg("")).toBe("#ffffff");
  });
});

describe("0.4.0 appearance and navigation helpers", () => {
  it("normalizes and round-trips custom colors", () => {
    expect(normalizeHexColor(" FFC131 ")).toBe("#ffc131");
    expect(normalizeHexColor("#xyzxyz")).toBeNull();
    for (const color of ["#ffc131", "#4f46e5", "#16a34a", "#000000", "#ffffff"]) {
      const hsl = hexToHsl(color);
      expect(hslToHex(hsl.hue, hsl.saturation, hsl.lightness)).toBe(color);
    }
  });

  it("supports single shortcuts, two-stroke chords, and conflict detection", () => {
    expect(DEFAULT_KEYBINDINGS.quickWorkspaceSwitch).toBe("Ctrl+D");
    expect(DEFAULT_KEYBINDINGS.quickServiceSwitch).toBe("Ctrl+S");
    expect(DEFAULT_KEYBINDINGS.addWorkspace).toBe("Ctrl+Shift+N");
    expect(DEFAULT_KEYBINDINGS.toggleSidebar).toBe("Ctrl+Shift+B");
    expect(bindingStrokes("Ctrl+K   Ctrl+S")).toEqual(["Ctrl+K", "Ctrl+S"]);
    const conflicts = shortcutConflicts({ a: "Ctrl+K Ctrl+S", b: "Ctrl+K Ctrl+S", c: "Ctrl+D" });
    expect(conflicts.get("Ctrl+K Ctrl+S")).toEqual(["a", "b"]);
  });


  it("matches every built-in default from stable physical key codes", () => {
    const event = (code: string, key: string, ctrl = true, alt = false, shift = false) => ({
      code,
      key,
      ctrlKey: ctrl,
      altKey: alt,
      shiftKey: shift,
      metaKey: false,
    }) as KeyboardEvent;
    const strokes = [
      keyStrokeFromEvent(event("KeyD", "d")),
      keyStrokeFromEvent(event("KeyS", "s")),
      keyStrokeFromEvent(event("Comma", ";")), // layout-independent Ctrl+Comma
      keyStrokeFromEvent(event("KeyN", "n")),
      keyStrokeFromEvent(event("KeyN", "N", true, false, true)),
      keyStrokeFromEvent(event("KeyB", "B", true, false, true)),
      keyStrokeFromEvent(event("Tab", "Tab")),
      keyStrokeFromEvent(event("Tab", "Tab", true, false, true)),
      keyStrokeFromEvent(event("ArrowDown", "ArrowDown", true, true)),
      keyStrokeFromEvent(event("ArrowUp", "ArrowUp", true, true)),
      keyStrokeFromEvent(event("KeyR", "r")),
      keyStrokeFromEvent(event("KeyR", "R", true, false, true)),
      keyStrokeFromEvent(event("KeyI", "i", true, true)),
    ];
    expect(strokes).toEqual(Object.values(DEFAULT_KEYBINDINGS));
  });

  it("pages large lists without mutating them", () => {
    const values = Array.from({ length: 250 }, (_, index) => index);
    expect(paged(values, 1, 100)).toEqual(values.slice(100, 200));
    expect(values).toHaveLength(250);
  });
});

describe("0.5.3 workspace startup selection", () => {
  const workspaceIds = ["work", "personal"];

  it("uses the configured default when last-workspace restore is disabled", () => {
    expect(resolveStartupWorkspaceId(workspaceIds, "work", false, "personal")).toBe("work");
    expect(resolveStartupWorkspaceId(workspaceIds, "", false, "personal")).toBeNull();
  });

  it("gives the remembered workspace precedence when restore is enabled", () => {
    expect(resolveStartupWorkspaceId(workspaceIds, "work", true, "personal")).toBe("personal");
    expect(resolveStartupWorkspaceId(workspaceIds, "work", true, "")).toBeNull();
  });

  it("falls back safely when a persisted workspace no longer exists", () => {
    expect(resolveStartupWorkspaceId(workspaceIds, "work", true, "deleted")).toBe("work");
    expect(resolveStartupWorkspaceId(workspaceIds, "deleted", true, "missing")).toBeNull();
  });
});

describe("0.4.13 workspace ordering helpers", () => {
  const workspaces = [
    { id: "gamma", name: "Gamma" },
    { id: "alpha", name: "Alpha" },
    { id: "beta", name: "Beta" },
  ];
  const ids = (mode: Parameters<typeof orderWorkspacesForQuickSwitch>[1]) =>
    orderWorkspacesForQuickSwitch(workspaces, mode, { gamma: 20, alpha: 10, beta: 30 }).map((workspace) => workspace.id);

  it("supports custom and reverse-custom quick-switch ordering", () => {
    expect(ids("custom")).toEqual(["gamma", "alpha", "beta"]);
    expect(ids("customReverse")).toEqual(["beta", "alpha", "gamma"]);
  });

  it("supports alphabetical ordering in both directions", () => {
    expect(ids("alphabetical")).toEqual(["alpha", "beta", "gamma"]);
    expect(ids("alphabeticalReverse")).toEqual(["gamma", "beta", "alpha"]);
  });

  it("supports recent-use ordering in both directions with custom-order tie breaking", () => {
    expect(ids("recent")).toEqual(["beta", "gamma", "alpha"]);
    expect(ids("recentReverse")).toEqual(["alpha", "gamma", "beta"]);
    expect(orderWorkspacesForQuickSwitch(workspaces, "recent", {}).map((workspace) => workspace.id)).toEqual([
      "gamma",
      "alpha",
      "beta",
    ]);
  });
});

describe("0.4.9 service duplication helpers", () => {
  it("creates stable non-conflicting copy names", () => {
    expect(duplicateServiceName("Slack", ["Slack"])).toBe("Slack Copy");
    expect(duplicateServiceName("Slack", ["Slack", "slack copy"])).toBe("Slack Copy 2");
    expect(duplicateServiceName("", ["Service Copy"])).toBe("Service Copy 2");
  });
});

describe("recipeIcon / iconSrc", () => {
  it("builds the ferdium-recipes icon URL", () => {
    expect(recipeIcon("whatsapp")).toBe(
      "https://raw.githubusercontent.com/ferdium/ferdium-recipes/main/recipes/whatsapp/icon.svg",
    );
  });
  it("prefers the server custom icon when present", () => {
    expect(iconSrc({ iconUrl: "https://srv/icon/42", recipeId: "slack" })).toBe(
      "https://srv/icon/42",
    );
  });
  it("falls back to the recipe icon when no custom icon", () => {
    expect(iconSrc({ iconUrl: null, recipeId: "slack" })).toBe(recipeIcon("slack"));
    expect(iconSrc({ recipeId: "gmail" })).toBe(recipeIcon("gmail"));
  });
});

describe("filterRecipes", () => {
  const recipes = [
    { id: "whatsapp", name: "WhatsApp" },
    { id: "slack", name: "Slack" },
    { id: "telegram", name: "Telegram" },
  ];
  it("returns all, sorted by name, when the query is empty", () => {
    expect(filterRecipes(recipes, "  ").map((r) => r.id)).toEqual([
      "slack",
      "telegram",
      "whatsapp",
    ]);
  });
  it("matches name or id, case-insensitively", () => {
    expect(filterRecipes(recipes, "SLA").map((r) => r.id)).toEqual(["slack"]);
    expect(filterRecipes(recipes, "gram").map((r) => r.id)).toEqual(["telegram"]);
  });
  it("returns nothing when no recipe matches", () => {
    expect(filterRecipes(recipes, "zzz")).toEqual([]);
  });
});

describe("snapIconSize", () => {
  it("keeps valid Ferdium levels", () => {
    expect(snapIconSize(24)).toBe(24);
    expect(snapIconSize(34)).toBe(34);
  });
  it("snaps legacy values to the nearest level", () => {
    expect(snapIconSize(30)).toBe(28);
    expect(snapIconSize(20)).toBe(21);
    expect(snapIconSize(100)).toBe(34);
  });
});

describe("local recipe helpers", () => {
  it("creates safe deterministic recipe ids", async () => {
    const { recipeIdFromName } = await import("./ui");
    expect(recipeIdFromName("My AI Service")).toBe("my-ai-service");
    expect(recipeIdFromName("Cr\u00e8me & Chat")).toBe("creme-chat");
    expect(recipeIdFromName("***")).toBe("custom-recipe");
  });

  it("normalizes custom website URLs and names", async () => {
    const { normalizeWebsiteUrl, websiteName, looksLikeWebsite } = await import("./ui");
    expect(normalizeWebsiteUrl("example.com/chat")).toBe("https://example.com/chat");
    expect(normalizeWebsiteUrl("http://localhost:4096")).toBe("http://localhost:4096");
    expect(websiteName("https://www.example.com/a")).toBe("example.com");
    expect(looksLikeWebsite("chat.example.com")).toBe(true);
    expect(looksLikeWebsite("not a site")).toBe(false);
  });
});

describe("persisted ordering helpers", () => {
  it("applies saved ids and deterministically appends newly discovered items", async () => {
    const { orderedBySavedIds } = await import("./ui");
    const items = [
      { id: "a", order: 0 },
      { id: "b", order: 1 },
      { id: "c", order: 2 },
    ];
    expect(orderedBySavedIds(items, ["c", "a"]).map((item) => item.id)).toEqual([
      "c",
      "a",
      "b",
    ]);
    expect(items.map((item) => item.id)).toEqual(["a", "b", "c"]);
  });

  it("reorders a filtered workspace subset without moving hidden service slots", async () => {
    const { reorderVisibleSubset } = await import("./ui");
    expect(reorderVisibleSubset(["a", "b", "c", "d"], ["a", "c", "d"], "d", "a")).toEqual([
      "d",
      "b",
      "a",
      "c",
    ]);
  });

  it("supports explicit before/after sidebar drop placement without disturbing hidden slots", async () => {
    const { reorderVisibleSubsetAt } = await import("./ui");
    const full = ["a", "hidden-1", "b", "c", "hidden-2", "d"];
    const visible = ["a", "b", "c", "d"];
    expect(reorderVisibleSubsetAt(full, visible, "a", "c", "before")).toEqual([
      "b",
      "hidden-1",
      "a",
      "c",
      "hidden-2",
      "d",
    ]);
    expect(reorderVisibleSubsetAt(full, visible, "a", "c", "after")).toEqual([
      "b",
      "hidden-1",
      "c",
      "a",
      "hidden-2",
      "d",
    ]);
  });

  it("treats stale or duplicate drag-order input as a safe no-op", async () => {
    const { reorderVisibleSubsetAt } = await import("./ui");
    expect(reorderVisibleSubsetAt(["a", "b", "c"], ["a", "b", "c"], "missing", "b", "before")).toEqual(["a", "b", "c"]);
    expect(reorderVisibleSubsetAt(["a", "b", "c"], ["a", "b", "c"], "a", "missing", "after")).toEqual(["a", "b", "c"]);
    expect(reorderVisibleSubsetAt(["a", "b", "b"], ["a", "b"], "a", "b", "after")).toEqual(["a", "b", "b"]);
  });

  it("selects contiguous sidebar ranges without changing their canonical order", async () => {
    const { contiguousIdRange } = await import("./ui");
    expect(contiguousIdRange(["a", "b", "c", "d"], "c", "a")).toEqual(["a", "b", "c"]);
    expect(contiguousIdRange(["a", "b", "c", "d"], "b", "d")).toEqual(["b", "c", "d"]);
    expect(contiguousIdRange(["a", "b", "c"], "missing", "c")).toEqual([]);
    expect(contiguousIdRange(["a", "b", "b"], "a", "b")).toEqual([]);
  });

  it("moves a selected service group as one stable block while preserving hidden slots", async () => {
    const { reorderVisibleGroupAt } = await import("./ui");
    const full = ["a", "hidden-1", "b", "c", "hidden-2", "d", "e"];
    const visible = ["a", "b", "c", "d", "e"];
    expect(reorderVisibleGroupAt(full, visible, ["b", "c"], "e", "after")).toEqual([
      "a",
      "hidden-1",
      "d",
      "e",
      "hidden-2",
      "b",
      "c",
    ]);
    expect(reorderVisibleGroupAt(full, visible, ["d", "e"], "a", "before")).toEqual([
      "d",
      "hidden-1",
      "e",
      "a",
      "hidden-2",
      "b",
      "c",
    ]);
  });

  it("treats drops onto the selected drag group as safe no-ops", async () => {
    const { reorderVisibleGroupAt } = await import("./ui");
    const ids = ["a", "b", "c", "d"];
    expect(reorderVisibleGroupAt(ids, ids, ["b", "c"], "c", "after")).toEqual(ids);
    expect(reorderVisibleGroupAt(ids, ids, ["missing"], "d", "after")).toEqual(ids);
  });

  it("returns stable service labels when names are missing", async () => {
    const { serviceLabel } = await import("./ui");
    expect(serviceLabel({ name: " Mail ", recipeId: "gmail" })).toBe("Mail");
    expect(serviceLabel({ name: "", recipeId: "gmail" })).toBe("gmail");
    expect(serviceLabel({ name: "", recipeId: "" })).toBe("Unnamed service");
  });
});


describe("backup scheduling helpers", () => {
  it("includes local date, time, and milliseconds in backup names", async () => {
    const { backupTimestamp } = await import("./ui");
    const date = new Date(2026, 7, 19, 0, 11, 22, 37);
    expect(backupTimestamp(date)).toBe("2026-08-19-001122-037");
  });

  it("handles startup and interval schedules deterministically", async () => {
    const { automaticBackupDue } = await import("./ui");
    const day = 24 * 60 * 60 * 1000;
    expect(automaticBackupDue("off", 0, day, true, false)).toBe(false);
    expect(automaticBackupDue("startup", 0, day, true, false)).toBe(true);
    expect(automaticBackupDue("startup", 0, day, true, true)).toBe(false);
    expect(automaticBackupDue("startup", 0, day, false, false)).toBe(false);
    expect(automaticBackupDue("daily", day, day * 2 - 1, false, false)).toBe(false);
    expect(automaticBackupDue("daily", day, day * 2, false, false)).toBe(true);
    expect(automaticBackupDue("weekly", day, day * 8, false, false)).toBe(true);
    expect(automaticBackupDue("monthly", day, day * 31, false, false)).toBe(false);
    expect(automaticBackupDue("monthly", day, day * 32, false, false)).toBe(true);
  });

  it("uses calendar-month boundaries and clamps month ends", async () => {
    const { automaticBackupDue } = await import("./ui");

    const jan15 = new Date(2026, 0, 15, 10, 30, 0, 0).getTime();
    const feb15 = new Date(2026, 1, 15, 10, 30, 0, 0).getTime();
    expect(automaticBackupDue("monthly", jan15, feb15 - 1, false, false)).toBe(false);
    expect(automaticBackupDue("monthly", jan15, feb15, false, false)).toBe(true);

    const jan31 = new Date(2026, 0, 31, 8, 5, 0, 0).getTime();
    const feb28 = new Date(2026, 1, 28, 8, 5, 0, 0).getTime();
    expect(automaticBackupDue("monthly", jan31, feb28 - 1, false, false)).toBe(false);
    expect(automaticBackupDue("monthly", jan31, feb28, false, false)).toBe(true);

    const leapJan31 = new Date(2028, 0, 31, 8, 5, 0, 0).getTime();
    const leapFeb29 = new Date(2028, 1, 29, 8, 5, 0, 0).getTime();
    expect(automaticBackupDue("monthly", leapJan31, leapFeb29 - 1, false, false)).toBe(false);
    expect(automaticBackupDue("monthly", leapJan31, leapFeb29, false, false)).toBe(true);
  });
});
