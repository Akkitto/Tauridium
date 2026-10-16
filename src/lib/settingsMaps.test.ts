import { describe, expect, it } from "vitest";
import source from "../App.svelte?raw";
import { ownValue, setOwnValue, copyOwnEntry, downloadOverride, downloadDirectoryLabel } from "./settingsMaps";

const ids = ["__proto__", "constructor", "toString", "hasOwnProperty", "normal-id"];

describe("ID-keyed settings dictionaries", () => {
  it.each(ids)("does not treat inherited %s as an override", (id) => {
    const values = {};
    expect(ownValue(values, id)).toBeUndefined();
    expect(downloadOverride(values, id)).toBeNull();
  });

  it.each(ids)("round trips, renders and removes a genuine %s override without prototype mutation", (id) => {
    const values: Record<string, { directory: string; askEachDownload: boolean }> = {};
    const prototype = Object.getPrototypeOf(values);
    setOwnValue(values, id, { directory: " /synthetic/downloads ", askEachDownload: false });
    expect(Object.getPrototypeOf(values)).toBe(prototype);
    const parsed = JSON.parse(JSON.stringify(values));
    const preference = downloadOverride(parsed, id);
    if (preference === null) throw new Error("A genuine own setting was lost");
    expect(downloadDirectoryLabel(preference.directory)).toBe("/synthetic/downloads");
    delete values[id];
    expect(downloadOverride(values, id)).toBeNull();
  });

  it("validates the shape and own fields rather than trusting a map's nominal type", () => {
    const inherited = Object.create({ directory: "bad", askEachDownload: true });
    for (const invalid of [undefined, null, [], true, 12, "bad", {}, inherited,
      { directory: 12, askEachDownload: true }, { directory: "", askEachDownload: "bad" }]) {
      expect(downloadOverride({ id: invalid }, "id")).toBeNull();
    }
    expect(downloadDirectoryLabel("")).toBe("System Downloads folder");
  });

  it.each(ids)("copies only own %s entries and retains legitimate false settings", (id) => {
    const values: Record<string, unknown> = {};
    copyOwnEntry(values, id, "missing");
    expect(Object.hasOwn(values, "missing")).toBe(false);
    setOwnValue(values, id, false);
    copyOwnEntry(values, id, "__proto__");
    expect(ownValue(values, "__proto__")).toBe(false);
    expect(Object.getPrototypeOf(values)).toBe(Object.prototype);
    const objects = { origin: { directory: "", askEachDownload: true } };
    copyOwnEntry(objects, "origin", id);
    expect(ownValue(objects, id)).toEqual(objects.origin);
    expect(ownValue(objects, id)).not.toBe(objects.origin);
  });

  it("copies reactive proxy records without DataCloneError or shared mutation", () => {
    const original = { directory: "/synthetic", askEachDownload: true };
    const values = { source: new Proxy(original, {}) };
    copyOwnEntry(values, "source", "constructor");
    const copied = downloadOverride(values, "constructor");
    expect(copied).toEqual(original);
    expect(ownValue(values, "constructor")).not.toBe(original);
  });

  it("wires both rendered Settings branches through validated own-entry preferences", () => {
    for (const marker of ["downloadOverride(appSettings.serviceDownloadSettings, serviceId)",
      "downloadOverride(appSettings.workspaceDownloadSettings, workspaceId)",
      "downloadDirectoryLabel(settingsServiceDownload.directory)",
      "downloadDirectoryLabel(selectedWorkspaceDownload.directory)"]) {
      expect(source.includes(marker), marker).toBe(true);
    }
    expect(/(?:serviceDownloadSettings|workspaceDownloadSettings)\?\.\[/.test(source)).toBe(false);
  });
});
