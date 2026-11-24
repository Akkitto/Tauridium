import { backupTimestamp } from "../ui";
import { save as saveDialog } from "@tauri-apps/plugin-dialog";
import { getAuditLogPage, exportAuditLog, clearAuditLog, type AuditEntry } from "../api";

export interface AuditHost {
  readonly confirmAsk: (message: string) => Promise<boolean>;
}

/** Feature state is created once per application instance; host accessors stay live. */
export function createAuditController(host: AuditHost) {
  const AUDIT_PAGE_SIZE = 100;

  let auditEntries = $state<AuditEntry[]>([]);

  let auditQuery = $state("");

  let auditLevel = $state("all");

  let auditBusy = $state(false);

  let auditStatus = $state("");

  let auditCursor = $state<string | null>(null);

  let auditHasMore = $state(false);

  let auditInitialized = $state(false);

  let auditRequestGeneration = 0;

  const filteredAuditEntries = $derived.by(() => {
    const query = auditQuery.trim().toLowerCase();
    return auditEntries.filter((entry) => {
      if (auditLevel !== "all" && entry.level !== auditLevel) return false;
      if (!query) return true;
      const details = JSON.stringify(entry.details ?? {});
      return `${entry.level} ${entry.category} ${entry.action} ${entry.outcome} ${entry.message} ${details}`
        .toLowerCase()
        .includes(query);
    });
  });

  function auditLoadedStatus() {
    return auditHasMore
      ? `${auditEntries.length} audit event(s) loaded. Older retained history is available.`
      : `${auditEntries.length} audit event(s) loaded. End of retained history reached.`;
  }

  async function refreshAuditLog() {
    if (auditBusy) return;
    const requestGeneration = ++auditRequestGeneration;
    auditBusy = true;
    auditStatus = "";
    try {
      const page = await getAuditLogPage(null, AUDIT_PAGE_SIZE);
      if (requestGeneration !== auditRequestGeneration) return;
      auditEntries = page.entries;
      auditCursor = page.nextCursor;
      auditHasMore = page.hasMore;
      auditInitialized = true;
      auditStatus = auditLoadedStatus();
    } catch (err) {
      if (requestGeneration === auditRequestGeneration) {
        auditStatus = `Unable to load audit log: ${err}`;
      }
    } finally {
      if (requestGeneration === auditRequestGeneration) auditBusy = false;
    }
  }

  async function loadOlderAuditLog() {
    if (auditBusy || !auditHasMore || !auditCursor) return;
    const cursor = auditCursor;
    const requestGeneration = ++auditRequestGeneration;
    auditBusy = true;
    try {
      const page = await getAuditLogPage(cursor, AUDIT_PAGE_SIZE);
      if (requestGeneration !== auditRequestGeneration || auditCursor !== cursor) return;
      auditEntries = [...auditEntries, ...page.entries];
      auditCursor = page.nextCursor;
      auditHasMore = page.hasMore;
      auditStatus = auditLoadedStatus();
    } catch (err) {
      if (requestGeneration === auditRequestGeneration) {
        auditStatus = `Unable to load older audit events: ${err}`;
      }
    } finally {
      if (requestGeneration === auditRequestGeneration) auditBusy = false;
    }
  }

  function auditLoadMoreObserver(node: HTMLElement) {
    if (typeof IntersectionObserver === "undefined") return {};
    const root = node.closest(".audit-list");
    const observer = new IntersectionObserver(
      (entries) => {
        if (
          entries.some((entry) => entry.isIntersecting)
          && !auditQuery.trim()
          && auditLevel === "all"
        ) {
          void loadOlderAuditLog();
        }
      },
      { root, rootMargin: "0px 0px 180px 0px" },
    );
    observer.observe(node);
    return {
      destroy() {
        observer.disconnect();
      },
    };
  }

  async function doExportAuditLog() {
    if (auditBusy) return;
    const requestGeneration = ++auditRequestGeneration;
    let refreshAfterExport = false;
    auditBusy = true;
    try {
      const path = await saveDialog({
        title: "Export Tauridium audit log",
        defaultPath: `tauridium-audit-${backupTimestamp()}.jsonl`,
        filters: [{ name: "JSON Lines", extensions: ["jsonl"] }],
      });
      if (!path) return;
      const count = await exportAuditLog(path);
      if (requestGeneration !== auditRequestGeneration) return;
      auditStatus = `Exported ${count} audit event(s).`;
      refreshAfterExport = true;
    } catch (err) {
      if (requestGeneration === auditRequestGeneration) {
        auditStatus = `Audit export failed: ${err}`;
      }
    } finally {
      if (requestGeneration === auditRequestGeneration) auditBusy = false;
    }
    if (refreshAfterExport) await refreshAuditLog();
  }

  async function doClearAuditLog() {
    if (auditBusy) return;
    const requestGeneration = ++auditRequestGeneration;
    auditBusy = true;
    try {
      const confirmed = await host.confirmAsk(
        "Clear the local Tauridium audit history? A new audit event recording this clear action will remain.",
      );
      if (!confirmed) return;
      await clearAuditLog();
      if (requestGeneration !== auditRequestGeneration) return;
      auditEntries = [];
      auditCursor = null;
      auditHasMore = false;
      auditInitialized = false;
    } catch (err) {
      if (requestGeneration === auditRequestGeneration) {
        auditStatus = `Unable to clear audit log: ${err}`;
      }
      return;
    } finally {
      if (requestGeneration === auditRequestGeneration) auditBusy = false;
    }
    await refreshAuditLog();
  }

  return {
    get auditInitialized() { return auditInitialized; },
    set auditInitialized(value: typeof auditInitialized) { auditInitialized = value; },
    refreshAuditLog,
    auditLoadMoreObserver,
    get auditBusy() { return auditBusy; },
    get auditEntries() { return auditEntries; },
    get auditHasMore() { return auditHasMore; },
    get auditLevel() { return auditLevel; },
    set auditLevel(value: typeof auditLevel) { auditLevel = value; },
    get auditQuery() { return auditQuery; },
    set auditQuery(value: typeof auditQuery) { auditQuery = value; },
    get auditStatus() { return auditStatus; },
    doClearAuditLog,
    doExportAuditLog,
    get filteredAuditEntries() { return filteredAuditEntries; },
    loadOlderAuditLog,
  };
}

export type AuditController = ReturnType<typeof createAuditController>;
