import { describe, expect, it } from "vitest";
import { describeListStatus, resolveEffectiveAdblock, splitSiteInput, toggleListId, withServiceAdblockPatch } from "./adblock";

describe("resolveEffectiveAdblock", () => {
  it("follows the global value unless the service overrides it", () => {
    const settings = { adblockEnabled: true, serviceAdblock: { a: { enabled: false }, b: { allowlist: ["x.com"] } } };
    expect(resolveEffectiveAdblock(settings, "a")).toBe(false);
    expect(resolveEffectiveAdblock(settings, "b")).toBe(true);
    expect(resolveEffectiveAdblock(settings, "c")).toBe(true);
    expect(resolveEffectiveAdblock({ adblockEnabled: false, serviceAdblock: { a: { enabled: true } } }, "a")).toBe(true);
  });

  it("does not read inherited properties", () => {
    expect(resolveEffectiveAdblock({ adblockEnabled: false, serviceAdblock: {} }, "constructor")).toBe(false);
    expect(resolveEffectiveAdblock({ adblockEnabled: true, serviceAdblock: {} }, "__proto__")).toBe(true);
  });
});

describe("withServiceAdblockPatch", () => {
  it("sets, clears and drops empty overrides", () => {
    let map = withServiceAdblockPatch({}, "s1", { enabled: false });
    expect(map).toEqual({ s1: { enabled: false } });
    map = withServiceAdblockPatch(map, "s1", { allowlist: ["a.com"] });
    expect(map.s1).toEqual({ enabled: false, allowlist: ["a.com"] });
    map = withServiceAdblockPatch(map, "s1", { enabled: null });
    expect(map.s1).toEqual({ allowlist: ["a.com"] });
    map = withServiceAdblockPatch(map, "s1", { allowlist: [] });
    expect(map).toEqual({});
  });

  it("does not mutate its input and tolerates hostile ids", () => {
    const current = { s1: { enabled: true } };
    const next = withServiceAdblockPatch(current, "__proto__", { enabled: false });
    expect(current).toEqual({ s1: { enabled: true } });
    expect(Object.hasOwn(next, "__proto__")).toBe(true);
    expect(Object.getPrototypeOf(next)).toBe(Object.prototype);
  });
});

describe("list helpers", () => {
  it("toggles ids without duplicates", () => {
    expect(toggleListId(["a"], "b", true)).toEqual(["a", "b"]);
    expect(toggleListId(["a", "b"], "a", false)).toEqual(["b"]);
    expect(toggleListId(["a"], "a", true)).toEqual(["a"]);
  });

  it("splits site input on spaces, commas and lines", () => {
    expect(splitSiteInput("a.com, b.org\nc.net  ;d.io")).toEqual(["a.com", "b.org", "c.net", "d.io"]);
    expect(splitSiteInput("  ")).toEqual([]);
  });

  it("describes list status", () => {
    const now = Date.UTC(2026, 10, 14);
    const day = 86_400;
    expect(describeListStatus({ status: "waiting", lastUpdated: null, ruleCount: 0, lastError: null }, now)).toBe("Waiting to download");
    expect(describeListStatus({ status: "error", lastUpdated: null, ruleCount: 0, lastError: "boom" }, now)).toBe("boom");
    expect(describeListStatus({ status: "active", lastUpdated: now / 1000, ruleCount: 1234, lastError: null }, now)).toBe("1,234 rules, updated today");
    expect(describeListStatus({ status: "active", lastUpdated: now / 1000 - 3 * day, ruleCount: 5, lastError: "x" }, now)).toBe("5 rules, updated 3 days ago (latest update failed)");
  });
});
