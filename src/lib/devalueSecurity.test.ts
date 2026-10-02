import { parse } from "devalue";
import { describe, expect, it } from "vitest";

describe("devalue security regression", () => {
  it("rejects non-string null-prototype keys that coerce to __proto__", () => {
    const malicious = JSON.stringify([["null", ["__proto__"], 1], { polluted: true }]);
    expect(() => parse(malicious)).toThrow("non-string key");
  });

  it("still accepts valid null-prototype objects", () => {
    const result = parse('[["null","safe",1],42]');
    expect(Object.getPrototypeOf(result)).toBeNull();
    expect(result.safe).toBe(42);
  });
});
