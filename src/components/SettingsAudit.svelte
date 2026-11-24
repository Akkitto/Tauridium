<script lang="ts">

  import type { AuditController } from "../lib/controllers/audit.svelte";

  interface Props {
    audit: AuditController;
  }

  let {
    audit,
  }: Props = $props();

  const observeMore = (node: HTMLElement) => audit.auditLoadMoreObserver(node);
</script>

<section class="settings-section" aria-labelledby="settings-audit-log">
                <div class="section-heading"><h3 id="settings-audit-log">Audit log</h3><p>Review application-setting changes, backup exports/restores, scheduled backups, portable exports, warnings, and failures. Secret-like fields are redacted before persistence.</p></div>
                <div class="audit-toolbar">
                  <input class="setting-text-input" type="search" bind:value={audit.auditQuery} placeholder="Search audit events…" aria-label="Search audit events" />
                  <select class="select" bind:value={audit.auditLevel} aria-label="Filter audit events by level"><option value="all">All levels</option><option value="info">Info</option><option value="warning">Warnings</option><option value="error">Errors</option></select>
                  <button class="secondary sm" disabled={audit.auditBusy} onclick={audit.refreshAuditLog}>Refresh</button>
                  <button class="secondary sm" disabled={audit.auditBusy || !audit.auditEntries.length} onclick={audit.doExportAuditLog}>Export…</button>
                  <button class="secondary sm" disabled={audit.auditBusy || !audit.auditEntries.length} onclick={audit.doClearAuditLog}>Clear…</button>
                </div>
                {#if audit.auditStatus}<p class="settings-status">{audit.auditStatus}</p>{/if}
                {#if audit.auditHasMore && (audit.auditQuery.trim() || audit.auditLevel !== "all")}<p class="settings-note">Filters apply to loaded events. Load older events to expand the searchable history.</p>{/if}
                <div class="audit-list" role="list" aria-label="Tauridium audit events">
                  {#each audit.filteredAuditEntries as entry}
                    <article class="audit-entry" class:audit-warning={entry.level === "warning"} class:audit-error={entry.level === "error"} role="listitem">
                      <div class="audit-entry-head"><time datetime={new Date(entry.timestampUnixMs).toISOString()}>{new Date(entry.timestampUnixMs).toLocaleString()}</time><span class="audit-level">{entry.level}</span><span>{entry.category} · {entry.action} · {entry.outcome}</span></div>
                      <strong>{entry.message}</strong>
                      {#if entry.details && JSON.stringify(entry.details) !== "{}"}<pre>{JSON.stringify(entry.details, null, 2)}</pre>{/if}
                    </article>
                  {:else}
                    <div class="managed-empty"><strong>No matching audit events</strong><span>Change the filter or refresh the log.</span></div>
                  {/each}
                  {#if audit.auditHasMore}
                    <div class="audit-load-more" use:observeMore>
                      <button class="secondary sm" disabled={audit.auditBusy} onclick={audit.loadOlderAuditLog}>{audit.auditBusy ? "Loading…" : "Load older events"}</button>
                    </div>
                  {:else if audit.auditInitialized && audit.auditEntries.length}
                    <div class="audit-history-end">End of retained audit history.</div>
                  {/if}
                </div>
                <p class="settings-note">Audit files rotate locally when they grow large. The UI initially loads the newest 100 events and loads older retained history on demand; exported JSONL preserves chronological order.</p>
              </section>

<style>

  button, input, select { font-family: inherit; }
  input {
    padding: 9px 11px; border-radius: 8px; border: 1px solid var(--border2);
    background: var(--input); color: var(--text); font-size: 14px;
  }
  .select {
    margin-left: auto; padding: 6px 9px; border-radius: 8px;
    border: 1px solid var(--border2); background: var(--input); color: var(--text); font-size: 13px;
  }
  .secondary { padding: 9px 12px; border: 1px solid var(--border2); border-radius: 8px; background: var(--input); color: var(--text2); font-weight: 600; cursor: pointer; }
  .secondary:hover { background: var(--hover); border-color: var(--accent); }
  .secondary:disabled { opacity: 0.55; cursor: default; }
  .secondary.sm { padding: 6px 10px; font-size: 12px; }
  .managed-empty {
    display: flex; flex-direction: column; gap: 4px; padding: 18px; border: 1px dashed var(--border2);
    border-radius: 10px; color: var(--muted); text-align: center;
  }
  .managed-empty strong { color: var(--text2); font-size: 14px; }
  .managed-empty span { font-size: 12px; }
  .secondary:focus-visible, .select:focus-visible, .setting-text-input:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 2px;
  }
  .settings-section { display: flex; flex-direction: column; gap: 10px; }
  .section-heading { display: flex; flex-direction: column; gap: 4px; padding: 0 2px; }
  .section-heading h3 { margin: 0; font-size: 13px; line-height: 1.3; font-weight: 700; color: var(--text); }
  .section-heading p { margin: 0; max-width: 840px; color: var(--muted); font-size: 12.5px; line-height: 1.45; }
  .setting-text-input { width: 100%; box-sizing: border-box; }
  .settings-note, .settings-status { margin: 0 2px; color: var(--muted); font-size: 12px; line-height: 1.45; }
  .settings-status { color: var(--text2); }
  :global(.settings-panel) .select { padding: 8px 10px; font-size: 13px; }
  :global(.settings-panel) .secondary { min-height: 34px; display: inline-flex; align-items: center; justify-content: center; }
  :global(.settings-panel) .secondary.sm { min-height: 30px; }
  .audit-toolbar { display: grid; grid-template-columns: minmax(220px, 1fr) minmax(120px, 160px) auto auto auto; gap: 8px; align-items: center; }
  .audit-list { display: flex; flex-direction: column; gap: 8px; max-height: min(56vh, 620px); overflow-y: auto; overscroll-behavior: contain; scrollbar-gutter: stable; padding-right: 2px; }
  .audit-entry { display: flex; flex-direction: column; gap: 6px; padding: 11px 12px; border: 1px solid var(--border); border-radius: 9px; background: var(--input); content-visibility: auto; contain-intrinsic-size: 88px; }
  .audit-entry.audit-warning { border-color: color-mix(in srgb, #ffbf69 55%, var(--border)); }
  .audit-entry.audit-error { border-color: color-mix(in srgb, #ff7373 62%, var(--border)); }
  .audit-entry-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; color: var(--muted); font-size: 11px; }
  .audit-entry-head time { font-variant-numeric: tabular-nums; }
  .audit-level { min-height: 20px; display: inline-flex; align-items: center; padding: 0 6px; border: 1px solid var(--border2); border-radius: 999px; color: var(--text2); font-weight: 700; text-transform: uppercase; font-size: 10px; }
  .audit-entry strong { color: var(--text2); font-size: 13px; line-height: 1.35; }
  .audit-entry pre { max-height: 190px; margin: 0; padding: 9px; overflow: auto; border-radius: 7px; background: var(--bg); color: var(--muted); font: 11px/1.45 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
  .audit-load-more { display: flex; justify-content: center; padding: 4px 0 2px; }
  .audit-history-end { padding: 6px 0 2px; color: var(--muted); font-size: 11px; text-align: center; }
  @media (max-width: 760px) {
    .audit-toolbar { grid-template-columns: 1fr; }
  }

</style>
