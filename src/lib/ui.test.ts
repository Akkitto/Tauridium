import { describe, it, expect } from "vitest";
import { accentFg, recipeIcon, iconSrc, filterRecipes, snapIconSize } from "./ui";

describe("accentFg", () => {
  it("returns dark text on light accents (Tauri yellow)", () => {
    expect(accentFg("#ffc131")).toBe("#1f2230");
    expect(accentFg("#ffffff")).toBe("#1f2230");
  });
  it("returns white text on dark accents", () => {
    expect(accentFg("#4f46e5")).toBe("#ffffff");
    expect(accentFg("#000000")).toBe("#ffffff");
    expect(accentFg("#16a34a")).toBe("#ffffff");
  });
  it("tolerates short / malformed hex", () => {
    expect(accentFg("#abc")).toBe("#ffffff");
    expect(accentFg("")).toBe("#ffffff");
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
