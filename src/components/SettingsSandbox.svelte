<script lang="ts">

  import type { AppSettings, PortablePayload, SandboxDefinition, Service } from "../lib/api";
  import { serviceLabel } from "../lib/ui";

  interface Props {
    MANAGED_SERVICE_PAGE_SIZE: 100;
    appSettings: AppSettings;
    assignServiceSandbox: (serviceId: string, sandboxId: string) => Promise<void>;
    clearSandboxGroup: (sandbox: SandboxDefinition) => Promise<void>;
    createSandboxGroup: () => Promise<void>;
    deleteSandboxGroup: (sandbox: SandboxDefinition) => Promise<void>;
    doPortableExport: (kind: "workspaces" | "sandbox" | "workspace" | "sandboxes", label: string, payload: PortablePayload) => Promise<void>;
    newSandboxName: string;
    portableExportStatus: string;
    renameSandboxGroup: (sandboxId: string, name: string) => Promise<void>;
    sandboxAssignmentBusy: boolean;
    sandboxPortablePayload: (sandboxId?: string | undefined) => PortablePayload;
    sandboxServicePage: number;
    sandboxServicePageCount: number;
    sandboxServiceQuery: string;
    sandboxServiceRows: Service[];
    sandboxServices: Service[];
    serviceSandboxId: (serviceId: string) => string | null;
    services: Service[];
  }

  let {
    MANAGED_SERVICE_PAGE_SIZE,
    appSettings,
    assignServiceSandbox,
    clearSandboxGroup,
    createSandboxGroup,
    deleteSandboxGroup,
    doPortableExport,
    newSandboxName = $bindable(),
    portableExportStatus,
    renameSandboxGroup,
    sandboxAssignmentBusy,
    sandboxPortablePayload,
    sandboxServicePage = $bindable(),
    sandboxServicePageCount,
    sandboxServiceQuery = $bindable(),
    sandboxServiceRows,
    sandboxServices,
    serviceSandboxId,
    services,
  }: Props = $props();

</script>

<section class="settings-section" aria-labelledby="settings-sandbox-groups">
                <div class="section-heading"><h3 id="settings-sandbox-groups">Shared sandboxes</h3><p>Services assigned to the same sandbox use the same persistent webview data store, allowing compatible services to share login sessions and caches. Unassigned services remain isolated.</p></div>
                <div class="sandbox-create-row"><input class="setting-text-input" bind:value={newSandboxName} maxlength="80" placeholder="New sandbox name, e.g. Proton" aria-label="New sandbox name" /><button class="primary" disabled={!newSandboxName.trim()} onclick={createSandboxGroup}>Create sandbox</button></div>
                <div class="setting-actions sandbox-export-actions"><button class="secondary sm" disabled={!appSettings.sandboxes.length} onclick={() => doPortableExport("sandboxes", "all sandboxes", sandboxPortablePayload())}>Export all sandboxes…</button></div>
                {#if portableExportStatus}<p class="settings-status">{portableExportStatus}</p>{/if}
                <div class="settings-list">
                  {#each appSettings.sandboxes as sandbox (sandbox.id)}
                    <div class="setting-card sandbox-card">
                      <div class="setting-copy">
                        <input class="setting-text-input sandbox-name" value={sandbox.name} maxlength="80" aria-label={`Sandbox name ${sandbox.name}`} onchange={(event) => renameSandboxGroup(sandbox.id, event.currentTarget.value)} />
                        <span class="setting-description">{Object.values(appSettings.serviceSandboxes).filter((value) => value === sandbox.id).length} assigned service(s)</span>
                      </div>
                      <div class="setting-actions"><button class="secondary sm" onclick={() => doPortableExport("sandbox", `sandbox ${sandbox.name}`, sandboxPortablePayload(sandbox.id))}>Export…</button><button class="secondary sm" onclick={() => clearSandboxGroup(sandbox)}>Clear session</button><button class="link danger-link" onclick={() => deleteSandboxGroup(sandbox)}>Delete</button></div>
                    </div>
                  {:else}
                    <div class="managed-empty"><strong>No shared sandboxes</strong><span>Create one, then assign two or more compatible services below.</span></div>
                  {/each}
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-sandbox-services">
                <div class="section-heading"><h3 id="settings-sandbox-services">Service assignments <span class="section-count">{services.length}</span></h3><p>Changing an assignment closes only that service webview and recreates it using the selected data store.</p></div>
                <input class="setting-text-input" type="search" bind:value={sandboxServiceQuery} oninput={() => (sandboxServicePage = 0)} placeholder="Search services…" aria-label="Search sandbox service assignments" />
                <div class="managed-list" role="list" aria-label="Sandbox service assignments">
                  {#each sandboxServiceRows as service (service.id)}
                    <div class="managed-row" role="listitem">
                      <div class="managed-copy"><strong>{serviceLabel(service)}</strong><span>{service.recipeId}</span></div>
                      <select class="select sandbox-select" value={serviceSandboxId(service.id) ?? ""} disabled={sandboxAssignmentBusy} aria-label={`Sandbox for ${serviceLabel(service)}`} onchange={(event) => assignServiceSandbox(service.id, event.currentTarget.value)}>
                        <option value="">Isolated</option>
                        {#each appSettings.sandboxes as sandbox (sandbox.id)}<option value={sandbox.id}>{sandbox.name}</option>{/each}
                      </select>
                    </div>
                  {:else}<div class="managed-empty"><strong>No services match</strong><span>Change the search text.</span></div>{/each}
                </div>
                {#if sandboxServices.length > MANAGED_SERVICE_PAGE_SIZE}
                  <div class="pagination"><button class="secondary sm" disabled={sandboxServicePage === 0} onclick={() => (sandboxServicePage = Math.max(0, sandboxServicePage - 1))}>Previous</button><span>Page {sandboxServicePage + 1} of {sandboxServicePageCount}</span><button class="secondary sm" disabled={sandboxServicePage >= sandboxServicePageCount - 1} onclick={() => (sandboxServicePage = Math.min(sandboxServicePageCount - 1, sandboxServicePage + 1))}>Next</button></div>
                {/if}
              </section>

<style>

  button, input, select { font-family: inherit; }
  input {
    padding: 9px 11px; border-radius: 8px; border: 1px solid var(--border2);
    background: var(--input); color: var(--text); font-size: 14px;
  }
  .primary {
    padding: 10px 14px; border: none; border-radius: 8px; background: var(--accent);
    color: var(--accent-fg); font-weight: 700; cursor: pointer;
  }
  .primary:disabled { opacity: 0.6; cursor: default; }
  .link { background: none; border: none; color: var(--link); cursor: pointer; font-size: 12px; text-decoration: underline; }
  .select {
    margin-left: auto; padding: 6px 9px; border-radius: 8px;
    border: 1px solid var(--border2); background: var(--input); color: var(--text); font-size: 13px;
  }
  .secondary { padding: 9px 12px; border: 1px solid var(--border2); border-radius: 8px; background: var(--input); color: var(--text2); font-weight: 600; cursor: pointer; }
  .secondary:hover { background: var(--hover); border-color: var(--accent); }
  .secondary:disabled { opacity: 0.55; cursor: default; }
  .secondary.sm { padding: 6px 10px; font-size: 12px; }

  .danger-link { color: #e77d8e; }
  .managed-list { display: flex; flex-direction: column; gap: 7px; }
  .managed-row {
    min-height: 62px; display: flex; align-items: center; justify-content: space-between; gap: 16px;
    padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--input);
  }
  .managed-copy { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .managed-copy strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text2); font-size: 14px; }
  .managed-copy span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); font-size: 11.5px; }
  .managed-empty {
    display: flex; flex-direction: column; gap: 4px; padding: 18px; border: 1px dashed var(--border2);
    border-radius: 10px; color: var(--muted); text-align: center;
  }
  .managed-empty strong { color: var(--text2); font-size: 14px; }
  .managed-empty span { font-size: 12px; }
  .section-count {
    display: inline-flex; min-width: 22px; height: 20px; align-items: center; justify-content: center;
    margin-left: 4px; padding: 0 6px; border-radius: 999px; background: var(--hover); color: var(--muted);
    font-size: 11px; font-weight: 700; vertical-align: middle;
  }
  .setting-card:focus-visible, .primary:focus-visible, .secondary:focus-visible, .select:focus-visible, .setting-text-input:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 2px;
  }
  .settings-section { display: flex; flex-direction: column; gap: 10px; }
  .section-heading { display: flex; flex-direction: column; gap: 4px; padding: 0 2px; }
  .section-heading h3 { margin: 0; font-size: 13px; line-height: 1.3; font-weight: 700; color: var(--text); }
  .section-heading p { margin: 0; max-width: 840px; color: var(--muted); font-size: 12.5px; line-height: 1.45; }
  .settings-list { display: flex; flex-direction: column; gap: 8px; }
  .setting-card {
    width: 100%; box-sizing: border-box; display: grid; grid-template-columns: minmax(0, 1fr) auto;
    align-items: center; gap: 18px; min-height: 68px; padding: 13px 14px;
    border: 1px solid var(--border); border-radius: 10px; background: var(--input);
    color: var(--text); text-align: left; font: inherit;
  }
  .setting-copy { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .setting-description { max-width: 760px; color: var(--muted); font-size: 12.5px; line-height: 1.45; font-weight: 400; }
  .setting-text-input { width: 100%; box-sizing: border-box; }
  .setting-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
  .settings-status { margin: 0 2px; color: var(--muted); font-size: 12px; line-height: 1.45; }
  .settings-status { color: var(--text2); }
  :global(.settings-panel) .select { padding: 8px 10px; font-size: 13px; }
  :global(.settings-panel) .primary, :global(.settings-panel) .secondary { min-height: 34px; display: inline-flex; align-items: center; justify-content: center; }
  :global(.settings-panel) .secondary.sm { min-height: 30px; }
  .pagination { display: flex; align-items: center; justify-content: center; gap: 10px; color: var(--muted); font-size: 12px; }
  .sandbox-create-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }
  .sandbox-card { align-items: start; }
  .sandbox-name { max-width: 320px; }
  .sandbox-select { min-width: 180px; }
  .danger-link { color: #ff9b9b; }
  @media (max-width: 760px) {
    .setting-card { grid-template-columns: 1fr; gap: 10px; align-items: stretch; }
    .setting-actions { justify-content: flex-start; }
    .managed-row { align-items: flex-start; flex-direction: column; }
    .sandbox-create-row { grid-template-columns: 1fr; }
    .sandbox-select { width: 100%; margin-left: 0; }
  }

</style>
