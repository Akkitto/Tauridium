import { describe, expect, it } from "vitest";
import { resolveEffectiveSpellcheck, toggleLanguage, withServiceSpellcheckPatch, type SpellcheckSettings } from "./spelling";

const base: SpellcheckSettings = {
  spellcheckEnabled: true,
  spellcheckLanguages: ["en-US"],
  serviceSpellcheck: {},
};

describe("resolveEffectiveSpellcheck", () => {
  it("inherits the global settings without an override", () => {
    expect(resolveEffectiveSpellcheck(base, "a")).toEqual({ enabled: true, languages: ["en-US"] });
  });

  it("applies per-field overrides independently", () => {
    const settings = { ...base, serviceSpellcheck: { a: { enabled: false }, b: { languages: ["de"] } } };
    expect(resolveEffectiveSpellcheck(settings, "a")).toEqual({ enabled: false, languages: ["en-US"] });
    expect(resolveEffectiveSpellcheck(settings, "b")).toEqual({ enabled: true, languages: ["de"] });
  });

  it("treats an empty language override as the system language, not as inherited", () => {
    const settings = { ...base, serviceSpellcheck: { a: { languages: [] } } };
    expect(resolveEffectiveSpellcheck(settings, "a").languages).toEqual([]);
  });

  it("does not read inherited object properties as overrides", () => {
    expect(resolveEffectiveSpellcheck(base, "constructor")).toEqual({ enabled: true, languages: ["en-US"] });
    expect(resolveEffectiveSpellcheck(base, "__proto__")).toEqual({ enabled: true, languages: ["en-US"] });
  });

  it("returns a copy so callers cannot mutate settings", () => {
    const result = resolveEffectiveSpellcheck(base, "a");
    result.languages.push("fr");
    expect(base.spellcheckLanguages).toEqual(["en-US"]);
  });
});

describe("toggleLanguage", () => {
  it("adds without duplicating and removes", () => {
    expect(toggleLanguage(["en-US"], "de-DE", true)).toEqual(["en-US", "de-DE"]);
    expect(toggleLanguage(["en-US", "de-DE"], "en-US", true)).toEqual(["de-DE", "en-US"]);
    expect(toggleLanguage(["en-US", "de-DE"], "en-US", false)).toEqual(["de-DE"]);
    expect(toggleLanguage([], "en-US", false)).toEqual([]);
  });
});

describe("withServiceSpellcheckPatch", () => {
  it("sets fields without mutating the input", () => {
    const current = { a: { enabled: false } };
    const next = withServiceSpellcheckPatch(current, "b", { languages: ["de"] });
    expect(next).toEqual({ a: { enabled: false }, b: { languages: ["de"] } });
    expect(current).toEqual({ a: { enabled: false } });
  });

  it("clears a field with null and drops an override that becomes empty", () => {
    const current = { a: { enabled: false, languages: ["de"] } };
    expect(withServiceSpellcheckPatch(current, "a", { enabled: null })).toEqual({ a: { languages: ["de"] } });
    expect(withServiceSpellcheckPatch({ a: { enabled: true } }, "a", { enabled: null })).toEqual({});
  });

  it("keeps an explicitly empty language list, which means the system language", () => {
    expect(withServiceSpellcheckPatch({}, "a", { languages: [] })).toEqual({ a: { languages: [] } });
  });

  it("treats hostile ids as plain data", () => {
    const next = withServiceSpellcheckPatch({}, "__proto__", { enabled: true });
    expect(Object.keys(next)).toEqual(["__proto__"]);
    expect(({} as Record<string, unknown>).enabled).toBeUndefined();
  });
});
