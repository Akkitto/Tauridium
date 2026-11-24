import { beforeEach, describe, expect, it, vi } from "vitest";
import { createAuditController } from "./audit.svelte";
import { getAuditLogPage } from "../api";
import type { AuditEntry, AuditLogPage } from "../api";

vi.mock("../api", () => ({
  getAuditLogPage: vi.fn(),
  exportAuditLog: vi.fn(),
  clearAuditLog: vi.fn(),
}));
vi.mock("@tauri-apps/plugin-dialog", () => ({ save: vi.fn() }));

const entry = (message: string, level = "info"): AuditEntry => ({
  timestampUnixMs: 1, level, category: "synthetic", action: "fixture",
  outcome: "success", message, details: {},
});
const page = (entries: AuditEntry[]): AuditLogPage => ({ entries, nextCursor: null, hasMore: false });

describe("Audit controller ownership and reactivity", () => {
  beforeEach(() => vi.resetAllMocks());

  it("keeps query, level and loaded history independent between application instances", async () => {
    vi.mocked(getAuditLogPage).mockResolvedValue(page([entry("alpha")]));
    const first = createAuditController({ confirmAsk: async () => true });
    const second = createAuditController({ confirmAsk: async () => true });
    first.auditQuery = "alpha";
    first.auditLevel = "warning";
    await first.refreshAuditLog();
    expect(second.auditQuery).toBe("");
    expect(second.auditLevel).toBe("all");
    expect(second.auditEntries).toEqual([]);
  });

  it("reacts to newly loaded history and subsequent filter edits", async () => {
    vi.mocked(getAuditLogPage).mockResolvedValue(page([entry("alpha"), entry("beta", "warning")]));
    const audit = createAuditController({ confirmAsk: async () => true });
    expect(audit.filteredAuditEntries).toEqual([]);
    await audit.refreshAuditLog();
    expect(audit.filteredAuditEntries.map((item) => item.message)).toEqual(["alpha", "beta"]);
    audit.auditQuery = "beta";
    expect(audit.filteredAuditEntries.map((item) => item.message)).toEqual(["beta"]);
    audit.auditLevel = "error";
    expect(audit.filteredAuditEntries).toEqual([]);
  });

  it("blocks duplicate requests while history is loading and resets busy state after failure", async () => {
    const pending = Promise.withResolvers<AuditLogPage>();
    vi.mocked(getAuditLogPage).mockReturnValue(pending.promise);
    const audit = createAuditController({ confirmAsk: async () => true });
    const request = audit.refreshAuditLog();
    expect(audit.auditBusy).toBe(true);
    await audit.refreshAuditLog();
    expect(getAuditLogPage).toHaveBeenCalledExactlyOnceWith(null, 100);
    pending.reject(new Error("synthetic failure"));
    await request;
    expect(audit.auditBusy).toBe(false);
    expect(audit.auditStatus).toContain("synthetic failure");
  });
});
