import { describe, expect, it } from "vitest";
import { browserProfileNamespace, retainedTrackingExceptions } from "./browserPrivacy";

describe("Windows browser profile privacy", () => {
  it("shares exceptions only with the actual sandbox, not other isolated services", () => {
    expect(browserProfileNamespace("one", {})).toBe("service:one");
    expect(browserProfileNamespace("one", { one: "shared", two: "shared" })).toBe("sandbox:shared");
    expect(browserProfileNamespace("two", { one: "shared", two: "shared" })).toBe("sandbox:shared");
    expect(browserProfileNamespace("three", { one: "shared" })).toBe("service:three");
    expect(browserProfileNamespace("constructor", {})).toBe("service:constructor");
  });
  it("removes orphaned profile exceptions without inheriting them to new identities", () => {
    expect(retainedTrackingExceptions({ "service:old": true, "service:one": true, "sandbox:shared": true,
      "sandbox:gone": true, "unscoped": true }, new Set(["one", "two"]), new Set(["shared"])))
      .toEqual({ "service:one": true, "sandbox:shared": true });
  });
});
