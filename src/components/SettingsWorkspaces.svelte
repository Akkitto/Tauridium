<script lang="ts">

  import type { WorkspaceEditorController } from "../lib/controllers/workspaceEditor.svelte";
  import type { AppSettings, DownloadPreferenceOverride, PortablePayload, Service, Workspace } from "../lib/api";
  import { downloadDirectoryLabel } from "../lib/settingsMaps";
  import { serviceLabel } from "../lib/ui";

  interface Props {
    workspaceEditor: WorkspaceEditorController;
    MANAGED_SERVICE_PAGE_SIZE: 100;
    appSettings: AppSettings;
    chooseWorkspaceDownloadDirectory: (workspaceId: string) => Promise<void>;
    displayedServiceIcon: (service: Service) => string;
    doPortableExport: (kind: "workspaces" | "sandbox" | "workspace" | "sandboxes", label: string, payload: PortablePayload) => Promise<void>;
    downloadSettingsBusy: boolean;
    failedWorkspaceIcons: Set<string>;
    inheritedDownloadPreference: () => DownloadPreferenceOverride;
    managedWorkspace: Workspace | null;
    markIconFailed: (service: Service) => void;
    markWorkspaceIconFailed: (workspaceId: string) => void;
    moveManagedWorkspace: (workspaceId: string, delta: number) => Promise<void>;
    portableExportStatus: string;
    resetWorkspaceUsageHistory: () => Promise<void>;
    saveAppSetting: (key: keyof AppSettings, value: unknown) => Promise<void>;
    saveRestoreLastWorkspaceOnStartup: (enabled: boolean) => Promise<void>;
    saveWorkspaceDownloadOverride: (workspaceId: string, preference: DownloadPreferenceOverride | null) => Promise<void>;
    serviceIconFailed: (service: Service) => boolean;
    serviceIconInverted: (serviceId: string) => boolean;
    sorted: Service[];
    sortedWorkspaces: Workspace[];
    workspaceDownloadOverride: (workspaceId: string) => DownloadPreferenceOverride | null;
    workspaceIcon: (workspace: Workspace) => string | null;
    workspacePortablePayload: (workspaceId?: string | undefined) => PortablePayload;
    workspaces: Workspace[];
  }

  let {
    workspaceEditor,
    MANAGED_SERVICE_PAGE_SIZE,
    appSettings = $bindable(),
    chooseWorkspaceDownloadDirectory,
    displayedServiceIcon,
    doPortableExport,
    downloadSettingsBusy,
    failedWorkspaceIcons,
    inheritedDownloadPreference,
    managedWorkspace,
    markIconFailed,
    markWorkspaceIconFailed,
    moveManagedWorkspace,
    portableExportStatus,
    resetWorkspaceUsageHistory,
    saveAppSetting,
    saveRestoreLastWorkspaceOnStartup,
    saveWorkspaceDownloadOverride,
    serviceIconFailed,
    serviceIconInverted,
    sorted,
    sortedWorkspaces,
    workspaceDownloadOverride,
    workspaceIcon,
    workspacePortablePayload,
    workspaces,
  }: Props = $props();

</script>

{#if managedWorkspace}
                {@const selectedWorkspaceId = managedWorkspace.id}
                {@const selectedWorkspaceName = managedWorkspace.name}
                {@const selectedWorkspaceServices = managedWorkspace.services}
                {@const selectedWorkspaceDownload = workspaceDownloadOverride(selectedWorkspaceId)}
                <section class="settings-section workspace-detail-section" aria-labelledby="settings-workspace-detail">
                  <div class="section-heading workspace-detail-heading">
                    <div>
                      <h3 id="settings-workspace-detail">Workspace settings · {selectedWorkspaceName}</h3>
                      <p>Rename this workspace, assign its icon, and manage exactly which services belong to it.</p>
                    </div>
                    <button class="secondary sm" onclick={workspaceEditor.closeManagedWorkspace}>← Workspaces</button>
                  </div>
                  <div class="settings-list">
                    <div class="setting-card">
                      <div class="setting-copy">
                        <span class="setting-label">Name</span>
                        <span class="setting-description">Used in the quick switcher and Navigate menu.</span>
                      </div>
                      <div class="workspace-name-control">
                        <input class="setting-text-input" bind:value={workspaceEditor.managedWorkspaceNameDraft} maxlength="80" aria-label="Workspace name" />
                        <button class="primary" disabled={workspaceEditor.managedWorkspaceBusy || !workspaceEditor.managedWorkspaceNameDraft.trim() || workspaceEditor.managedWorkspaceNameDraft.trim() === selectedWorkspaceName} onclick={workspaceEditor.saveManagedWorkspaceName}>Save</button>
                      </div>
                    </div>
                    <div class="setting-card setting-card-stack workspace-icon-card">
                      <div class="setting-copy">
                        <span class="setting-label">Icon</span>
                        <span class="setting-description">Choose from the same resolved service icons Tauridium already uses. The selected icon is stored with application settings and embedded in workspace exports and backups.</span>
                      </div>
                      <div class="workspace-icon-current">
                        {#if workspaceIcon(managedWorkspace) && !failedWorkspaceIcons.has(selectedWorkspaceId)}
                          <img class="workspace-avatar workspace-icon-preview" src={workspaceIcon(managedWorkspace) ?? ""} alt="" onerror={() => markWorkspaceIconFailed(selectedWorkspaceId)} />
                        {:else}
                          <span class="workspace-avatar workspace-icon-preview" aria-hidden="true">{selectedWorkspaceName.slice(0, 1).toUpperCase()}</span>
                        {/if}
                        <div class="setting-copy">
                          <strong>{workspaceIcon(managedWorkspace) ? "Custom workspace icon" : "Automatic initial"}</strong>
                          <span class="setting-description">Select a configured service below to copy its currently resolved icon into this workspace.</span>
                        </div>
                        <button class="secondary sm" disabled={workspaceEditor.managedWorkspaceBusy || !workspaceIcon(managedWorkspace)} onclick={() => workspaceEditor.saveManagedWorkspaceIcon(null)}>Use initial</button>
                      </div>
                      <div class="workspace-icon-url-row">
                        <input
                          class="setting-text-input"
                          type="url"
                          bind:value={workspaceEditor.managedWorkspaceIconUrlDraft}
                          placeholder="https://example.com/icon.png or https://example.com/"
                          aria-label={`Icon URL for ${selectedWorkspaceName}`}
                          onkeydown={(event) => { if (event.key === "Enter") { event.preventDefault(); void workspaceEditor.assignManagedWorkspaceIconFromUrl(); } }}
                        />
                        <button class="secondary sm" disabled={workspaceEditor.managedWorkspaceBusy || !workspaceEditor.managedWorkspaceIconUrlDraft.trim()} onclick={workspaceEditor.assignManagedWorkspaceIconFromUrl}>Fetch and use</button>
                      </div>
                      <p class="settings-note">Enter a direct image URL or a website URL. Tauridium downloads the icon once, validates its size/type, and stores it with the workspace so later backups and portable workspace exports do not depend on the remote site.</p>
                      <div class="workspace-icon-choices">
                        {#each sorted as service (service.id)}
                          {@const candidateIcon = displayedServiceIcon(service)}
                          <button
                            type="button"
                            class="workspace-icon-choice"
                            class:selected={workspaceIcon(managedWorkspace) === candidateIcon}
                            disabled={workspaceEditor.managedWorkspaceBusy}
                            onclick={() => workspaceEditor.assignManagedWorkspaceIconFromService(service)}
                            aria-label={`Use ${serviceLabel(service)} icon for ${selectedWorkspaceName}`}
                          >
                            {#if !serviceIconFailed(service)}
                              <img class:service-icon-inverted={serviceIconInverted(service.id)} src={candidateIcon} alt="" onerror={() => markIconFailed(service)} />
                            {:else}
                              <span aria-hidden="true">{serviceLabel(service).slice(0, 1).toUpperCase()}</span>
                            {/if}
                            <small>{serviceLabel(service)}</small>
                          </button>
                        {:else}
                          <div class="managed-empty"><strong>No service icons available</strong><span>Add a service before assigning a workspace icon.</span></div>
                        {/each}
                      </div>
                    </div>
                    <div class="setting-card setting-card-stack workspace-download-card">
                      <div class="setting-copy">
                        <span class="setting-label">Downloads</span>
                        <span class="setting-description">Optionally override the global Advanced download defaults whenever a service is opened in this workspace. A per-service override still takes priority.</span>
                      </div>
                      <label class="row-toggle download-override-toggle">
                        <input
                          type="checkbox"
                          checked={selectedWorkspaceDownload !== null}
                          disabled={downloadSettingsBusy}
                          onchange={(event) => saveWorkspaceDownloadOverride(
                            selectedWorkspaceId,
                            event.currentTarget.checked ? inheritedDownloadPreference() : null,
                          )}
                        />
                        <span>Override download settings for this workspace</span>
                      </label>
                      {#if selectedWorkspaceDownload}
                        <div class="download-setting-row">
                          <div class="setting-copy">
                            <strong>Download directory</strong>
                            <span class="setting-description" title={downloadDirectoryLabel(selectedWorkspaceDownload.directory)}>{downloadDirectoryLabel(selectedWorkspaceDownload.directory)}</span>
                          </div>
                          <div class="setting-actions">
                            <button class="secondary sm" disabled={downloadSettingsBusy} onclick={() => chooseWorkspaceDownloadDirectory(selectedWorkspaceId)}>Choose folder…</button>
                            <button class="secondary sm" disabled={downloadSettingsBusy || !selectedWorkspaceDownload.directory} onclick={() => saveWorkspaceDownloadOverride(selectedWorkspaceId, { ...selectedWorkspaceDownload, directory: "" })}>Use system Downloads</button>
                          </div>
                        </div>
                        <label class="download-setting-row setting-card-toggle">
                          <span class="setting-copy"><strong>Ask where to save each download</strong><span class="setting-description">Show a native Save dialog for each download while this workspace is active.</span></span>
                          <span class="switch-control">
                            <input class="switch-input" type="checkbox" checked={selectedWorkspaceDownload.askEachDownload} disabled={downloadSettingsBusy} aria-label={`Ask where to save downloads in ${selectedWorkspaceName}`} onchange={(event) => saveWorkspaceDownloadOverride(selectedWorkspaceId, { ...selectedWorkspaceDownload, askEachDownload: event.currentTarget.checked })} />
                            <span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>
                          </span>
                        </label>
                      {:else}
                        <p class="settings-note">Inherited global directory: <strong>{downloadDirectoryLabel(appSettings.downloadDirectory)}</strong> · Ask each time: <strong>{appSettings.askEachDownload ? "On" : "Off"}</strong>.</p>
                      {/if}
                    </div>
                    <div class="setting-card setting-card-stack workspace-membership-card">
                      <div class="setting-copy">
                        <span class="setting-label">Services</span>
                        <span class="setting-description">Membership changes are saved immediately. Search and pagination keep this usable with large service collections.</span>
                      </div>
                      <input
                        class="setting-text-input"
                        type="search"
                        placeholder="Search services…"
                        bind:value={workspaceEditor.managedWorkspaceServiceQuery}
                        oninput={() => (workspaceEditor.managedWorkspaceServicePage = 0)}
                        aria-label={`Search services in ${selectedWorkspaceName}`}
                      />
                      <div class="workspace-service-list" role="list" aria-label={`Services in ${selectedWorkspaceName}`}>
                        {#each workspaceEditor.managedWorkspaceServiceRows as service (service.id)}
                          <label class="workspace-service-row" role="listitem">
                            <span>
                              <strong>{serviceLabel(service)}</strong>
                              <small>{service.recipeId || "Unknown recipe"}{service.isEnabled === false ? " · Disabled" : ""}</small>
                            </span>
                            <input
                              type="checkbox"
                              checked={selectedWorkspaceServices.includes(service.id)}
                              disabled={workspaceEditor.managedWorkspaceBusy}
                              onchange={(event) => workspaceEditor.toggleManagedWorkspaceService(service.id, event.currentTarget.checked)}
                              aria-label={`${selectedWorkspaceServices.includes(service.id) ? "Remove" : "Add"} ${serviceLabel(service)} ${selectedWorkspaceServices.includes(service.id) ? "from" : "to"} ${selectedWorkspaceName}`}
                            />
                          </label>
                        {:else}
                          <div class="managed-empty"><strong>No services match this search</strong><span>Change the search to manage other services.</span></div>
                        {/each}
                      </div>
                      {#if workspaceEditor.managedWorkspaceServices.length > MANAGED_SERVICE_PAGE_SIZE}
                        <div class="pagination" aria-label="Workspace service pages">
                          <button class="secondary sm" disabled={workspaceEditor.managedWorkspaceServicePage === 0} onclick={() => (workspaceEditor.managedWorkspaceServicePage = Math.max(0, workspaceEditor.managedWorkspaceServicePage - 1))}>Previous</button>
                          <span>Page {workspaceEditor.managedWorkspaceServicePage + 1} of {workspaceEditor.managedWorkspaceServicePageCount} · {workspaceEditor.managedWorkspaceServices.length} services</span>
                          <button class="secondary sm" disabled={workspaceEditor.managedWorkspaceServicePage >= workspaceEditor.managedWorkspaceServicePageCount - 1} onclick={() => (workspaceEditor.managedWorkspaceServicePage = Math.min(workspaceEditor.managedWorkspaceServicePageCount - 1, workspaceEditor.managedWorkspaceServicePage + 1))}>Next</button>
                        </div>
                      {/if}
                      <div class="workspace-detail-actions">
                        <button class="secondary" onclick={() => doPortableExport("workspace", `workspace ${selectedWorkspaceName}`, workspacePortablePayload(selectedWorkspaceId))}>Export workspace…</button>
                        <button class="secondary danger-button" onclick={workspaceEditor.deleteManagedWorkspace}>Delete workspace</button>
                      </div>
                    </div>
                  </div>
                </section>
              {:else}
                <section class="settings-section" aria-labelledby="settings-workspaces-startup">
                  <div class="section-heading">
                    <h3 id="settings-workspaces-startup">Startup workspace</h3>
                    <p>Choose which workspace Tauridium opens after restoring a session. Last-workspace restore takes precedence; the default remains the fallback if that workspace no longer exists.</p>
                  </div>
                  <div class="settings-list">
                    <div class="setting-card" id="settings-option-defaultWorkspaceId">
                      <div class="setting-copy">
                        <span class="setting-label">Default workspace</span>
                        <span class="setting-description">Used at startup when restoring the last workspace is disabled, or when the remembered workspace is unavailable.</span>
                      </div>
                      <select
                        class="select setting-control workspace-startup-select"
                        aria-label="Default workspace"
                        bind:value={appSettings.defaultWorkspaceId}
                        onchange={() => saveAppSetting("defaultWorkspaceId", appSettings.defaultWorkspaceId)}
                      >
                        <option value="">All services</option>
                        {#each sortedWorkspaces as workspace (workspace.id)}
                          <option value={workspace.id}>{workspace.name}</option>
                        {/each}
                      </select>
                    </div>
                    <label class="setting-card setting-card-toggle" id="settings-option-restoreLastWorkspace">
                      <span class="setting-copy">
                        <span class="setting-label">Restore last workspace on startup</span>
                        <span class="setting-description">Start with the workspace that was active most recently. Enabling this remembers the workspace active right now.</span>
                      </span>
                      <span class="switch-control">
                        <input
                          class="switch-input"
                          type="checkbox"
                          checked={appSettings.restoreLastWorkspaceOnStartup}
                          aria-label="Restore last workspace on startup"
                          onchange={(event) => saveRestoreLastWorkspaceOnStartup(event.currentTarget.checked)}
                        />
                        <span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>
                      </span>
                    </label>
                  </div>
                </section>

                <section class="settings-section" aria-labelledby="settings-workspaces-switcher">
                  <div class="section-heading">
                    <h3 id="settings-workspaces-switcher">Quick workspace switcher</h3>
                    <p>Choose how Ctrl+D orders workspaces. “All services” always remains first so you can leave a workspace filter quickly.</p>
                  </div>
                  <div class="settings-list">
                    <div class="setting-card" id="settings-option-workspaceQuickSwitchOrder">
                      <div class="setting-copy">
                        <span class="setting-label">Workspace switch order</span>
                        <span class="setting-description">Custom order is managed below. Recent modes use the last time each workspace was selected.</span>
                      </div>
                      <select
                        class="select setting-control workspace-order-select"
                        aria-label="Workspace switch order"
                        bind:value={appSettings.workspaceQuickSwitchOrder}
                        onchange={() => saveAppSetting("workspaceQuickSwitchOrder", appSettings.workspaceQuickSwitchOrder)}
                      >
                        <option value="custom">Custom</option>
                        <option value="customReverse">Custom — reverse</option>
                        <option value="alphabetical">Alphabetical — A to Z</option>
                        <option value="alphabeticalReverse">Alphabetical — Z to A</option>
                        <option value="recent">Most recently used</option>
                        <option value="recentReverse">Least recently used</option>
                      </select>
                    </div>
                    <div class="setting-card" id="settings-option-workspaceHistory">
                      <div class="setting-copy">
                        <span class="setting-label">Workspace usage history</span>
                        <span class="setting-description">Clear remembered workspace-use times without changing custom ordering or membership.</span>
                      </div>
                      <button class="secondary" disabled={Object.keys(appSettings.workspaceLastUsed).length === 0} onclick={resetWorkspaceUsageHistory}>Reset history</button>
                    </div>
                  </div>
                </section>

                <section class="settings-section" aria-labelledby="settings-workspaces-configured">
                  <div class="section-heading">
                    <h3 id="settings-workspaces-configured">Configured workspaces <span class="section-count">{workspaces.length}</span></h3>
                    <p>Create, search, reorder, export, and manage workspace membership. Reordering a filtered result moves only the matching workspace slots in the canonical custom order.</p>
                  </div>
                  <div class="managed-toolbar workspace-managed-toolbar">
                    <input
                      class="setting-text-input"
                      type="search"
                      placeholder="Search configured workspaces…"
                      bind:value={workspaceEditor.managedWorkspaceQuery}
                      oninput={() => (workspaceEditor.managedWorkspacePage = 0)}
                      aria-label="Search configured workspaces"
                    />
                    <button class="secondary" disabled={!sortedWorkspaces.length} onclick={() => doPortableExport("workspaces", "all workspaces", workspacePortablePayload())}>Export all…</button>
                  </div>
                  <div class="workspace-create-row">
                    <input class="setting-text-input" bind:value={workspaceEditor.newWorkspaceName} maxlength="80" placeholder="New workspace name" aria-label="New workspace name" />
                    <button class="primary" disabled={!workspaceEditor.newWorkspaceName.trim()} onclick={workspaceEditor.handleCreateWorkspace}>Create workspace</button>
                  </div>
                  {#if portableExportStatus}<p class="settings-status">{portableExportStatus}</p>{/if}
                  <div class="managed-list workspace-managed-list" role="list" aria-label="Configured workspaces">
                    {#each workspaceEditor.managedWorkspaceRows as workspace, index (workspace.id)}
                      <div class="managed-row" class:selected={workspaceEditor.managedWorkspaceId === workspace.id} role="listitem">
                        <div class="managed-identity workspace-managed-identity">
                          {#if workspaceIcon(workspace) && !failedWorkspaceIcons.has(workspace.id)}
                            <img class="workspace-avatar workspace-avatar-image" src={workspaceIcon(workspace) ?? ""} alt="" onerror={() => markWorkspaceIconFailed(workspace.id)} />
                          {:else}
                            <span class="workspace-avatar" aria-hidden="true">{workspace.name.slice(0, 1).toUpperCase()}</span>
                          {/if}
                          <div class="managed-copy">
                            <strong>{workspace.name}</strong>
                            <span>{workspace.services.length} service{workspace.services.length === 1 ? "" : "s"}</span>
                          </div>
                        </div>
                        <div class="managed-actions">
                          <button class="icon-button compact" disabled={workspaceEditor.managedWorkspacePage * MANAGED_SERVICE_PAGE_SIZE + index === 0} aria-label={`Move ${workspace.name} up`} title="Move up" onclick={() => moveManagedWorkspace(workspace.id, -1)}>↑</button>
                          <button class="icon-button compact" disabled={workspaceEditor.managedWorkspacePage * MANAGED_SERVICE_PAGE_SIZE + index === workspaceEditor.managedWorkspaces.length - 1} aria-label={`Move ${workspace.name} down`} title="Move down" onclick={() => moveManagedWorkspace(workspace.id, 1)}>↓</button>
                          <button class="secondary sm" onclick={() => workspaceEditor.manageWorkspace(workspace)}>Workspace settings</button>
                        </div>
                      </div>
                    {:else}
                      <div class="managed-empty">
                        <strong>{workspaces.length ? "No workspaces match this search" : "No workspaces configured"}</strong>
                        <span>{workspaces.length ? "Change the search to see more workspaces." : "Create a workspace above, then add services to it."}</span>
                      </div>
                    {/each}
                  </div>
                  {#if workspaceEditor.managedWorkspaces.length > MANAGED_SERVICE_PAGE_SIZE}
                    <div class="pagination" aria-label="Configured workspace pages">
                      <button class="secondary sm" disabled={workspaceEditor.managedWorkspacePage === 0} onclick={() => (workspaceEditor.managedWorkspacePage = Math.max(0, workspaceEditor.managedWorkspacePage - 1))}>Previous</button>
                      <span>Page {workspaceEditor.managedWorkspacePage + 1} of {workspaceEditor.managedWorkspacePageCount} · {workspaceEditor.managedWorkspaces.length} workspaces</span>
                      <button class="secondary sm" disabled={workspaceEditor.managedWorkspacePage >= workspaceEditor.managedWorkspacePageCount - 1} onclick={() => (workspaceEditor.managedWorkspacePage = Math.min(workspaceEditor.managedWorkspacePageCount - 1, workspaceEditor.managedWorkspacePage + 1))}>Next</button>
                    </div>
                  {/if}
                </section>
              {/if}

<style>

  button, input, select { font-family: inherit; }
  label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); }
  input {
    padding: 9px 11px; border-radius: 8px; border: 1px solid var(--border2);
    background: var(--input); color: var(--text); font-size: 14px;
  }
  .primary {
    padding: 10px 14px; border: none; border-radius: 8px; background: var(--accent);
    color: var(--accent-fg); font-weight: 700; cursor: pointer;
  }
  .primary:disabled { opacity: 0.6; cursor: default; }
  .service-icon-inverted { filter: invert(1); }
  .row-toggle { flex-direction: row; align-items: center; gap: 10px; color: var(--text2); font-size: 14px; cursor: pointer; }
  .row-toggle input { width: auto; }
  .select {
    margin-left: auto; padding: 6px 9px; border-radius: 8px;
    border: 1px solid var(--border2); background: var(--input); color: var(--text); font-size: 13px;
  }
  .secondary { padding: 9px 12px; border: 1px solid var(--border2); border-radius: 8px; background: var(--input); color: var(--text2); font-weight: 600; cursor: pointer; }
  .secondary:hover { background: var(--hover); border-color: var(--accent); }
  .secondary:disabled { opacity: 0.55; cursor: default; }
  .secondary.sm { padding: 6px 10px; font-size: 12px; }
  .icon-button.compact { width: 30px; height: 30px; border-color: var(--border); background: var(--input); }
  .icon-button.compact:disabled { opacity: 0.35; cursor: default; }
  .managed-list { display: flex; flex-direction: column; gap: 7px; }
  .managed-row {
    min-height: 62px; display: flex; align-items: center; justify-content: space-between; gap: 16px;
    padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--input);
  }
  .managed-identity { min-width: 0; display: flex; align-items: center; gap: 10px; }
  .managed-copy { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .managed-copy strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text2); font-size: 14px; }
  .managed-copy span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); font-size: 11.5px; }
  .managed-actions { display: inline-flex; align-items: center; gap: 5px; flex: none; }
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
  .icon-button {
    width: 34px; height: 34px; display: inline-grid; place-items: center; flex: none;
    border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--muted);
    cursor: pointer; font-size: 15px; line-height: 1;
  }
  .icon-button:hover { background: var(--hover); color: var(--text); border-color: var(--border); }
  .icon-button:focus-visible, .setting-card:focus-visible, .primary:focus-visible, .secondary:focus-visible, .select:focus-visible, .setting-text-input:focus-visible {
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
  .setting-card-stack { grid-template-columns: 1fr; align-items: stretch; gap: 10px; }
  .setting-copy { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .setting-label { color: var(--text2); font-size: 14px; line-height: 1.35; font-weight: 650; }
  .setting-description { max-width: 760px; color: var(--muted); font-size: 12.5px; line-height: 1.45; font-weight: 400; }
  .setting-control { min-width: 176px; max-width: 230px; margin-left: 0; }
  .setting-text-input { width: 100%; box-sizing: border-box; }
  .setting-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
  .settings-note, .settings-status { margin: 0 2px; color: var(--muted); font-size: 12px; line-height: 1.45; }
  .settings-status { color: var(--text2); }
  .switch-control { position: relative; width: 38px; height: 22px; flex: none; }
  .switch-input { position: absolute; inset: 0; width: 38px; height: 22px; margin: 0; opacity: 0; cursor: pointer; z-index: 1; }
  .switch-track { position: absolute; inset: 0; border: 1px solid var(--border2); border-radius: 999px; background: var(--bg); transition: background 0.15s ease, border-color 0.15s ease; }
  .switch-thumb { position: absolute; width: 16px; height: 16px; left: 2px; top: 2px; border-radius: 50%; background: var(--muted); transition: transform 0.15s ease, background 0.15s ease; }
  .switch-input:checked + .switch-track { background: var(--accent); border-color: var(--accent); }
  .switch-input:checked + .switch-track .switch-thumb { transform: translateX(16px); background: var(--accent-fg); }
  .switch-input:focus-visible + .switch-track { outline: 2px solid var(--accent); outline-offset: 2px; }
  .setting-card-toggle { cursor: pointer; }
  .setting-card-toggle:hover { background: var(--hover); border-color: var(--border2); }
  :global(.settings-panel) .select { padding: 8px 10px; font-size: 13px; }
  :global(.settings-panel) .primary, :global(.settings-panel) .secondary { min-height: 34px; display: inline-flex; align-items: center; justify-content: center; }
  :global(.settings-panel) .secondary.sm { min-height: 30px; }
  .managed-toolbar { display: grid; grid-template-columns: minmax(0, 1fr) minmax(160px, 220px); gap: 8px; }
  .workspace-managed-list {
    max-height: min(58vh, 680px);
    overflow-y: auto;
    overscroll-behavior: contain;
    scrollbar-gutter: stable;
    padding-right: 3px;
  }
  .workspace-managed-toolbar { grid-template-columns: minmax(0, 1fr) auto; }
  .workspace-create-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: center; }
  .workspace-order-select { min-width: 210px; max-width: 280px; }
  .workspace-managed-identity { min-width: 0; flex: 1 1 auto; }
  .workspace-avatar { width: 34px; height: 34px; display: grid; place-items: center; flex: none; border-radius: 8px; background: var(--hover); color: var(--text2); font-size: 13px; font-weight: 750; }
  .workspace-avatar-image { object-fit: contain; padding: 3px; box-sizing: border-box; }
  .workspace-icon-card { gap: 10px; }
  .workspace-icon-current { display: grid; grid-template-columns: 44px minmax(0, 1fr) auto; align-items: center; gap: 12px; width: 100%; }
  .workspace-icon-url-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 8px; width: 100%; }
  .workspace-icon-preview { width: 44px; height: 44px; border-radius: 10px; object-fit: contain; padding: 5px; box-sizing: border-box; }
  .workspace-icon-choices { width: 100%; display: grid; grid-template-columns: repeat(auto-fill, minmax(112px, 1fr)); gap: 7px; max-height: 250px; overflow-y: auto; overscroll-behavior: contain; padding: 3px; border: 1px solid var(--border); border-radius: 9px; background: var(--bg); }
  .workspace-icon-choice { min-width: 0; min-height: 72px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 5px; padding: 8px; border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--text2); cursor: pointer; font: inherit; }
  .workspace-icon-choice:hover:not(:disabled) { background: var(--hover); border-color: var(--border); }
  .workspace-icon-choice.selected { border-color: color-mix(in srgb, var(--accent) 58%, var(--border)); background: color-mix(in srgb, var(--accent) 8%, var(--input)); }
  .workspace-icon-choice:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  .workspace-icon-choice:disabled { cursor: wait; opacity: 0.68; }
  .workspace-icon-choice img, .workspace-icon-choice > span { width: 32px; height: 32px; display: grid; place-items: center; object-fit: contain; padding: 3px; box-sizing: border-box; border-radius: 7px; background: var(--hover); font-size: 12px; font-weight: 750; }
  .workspace-icon-choice small { width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); text-align: center; }
  .managed-row.selected { border-color: color-mix(in srgb, var(--accent) 62%, var(--border)); background: color-mix(in srgb, var(--accent) 8%, var(--input)); }
  .workspace-detail-section { padding-top: 4px; border-top: 1px solid var(--border); }
  .workspace-detail-heading { flex-direction: row; align-items: flex-start; justify-content: space-between; gap: 12px; }
  .workspace-detail-heading > div { min-width: 0; }
  .workspace-name-control { min-width: min(430px, 48vw); display: grid; grid-template-columns: minmax(160px, 1fr) auto; gap: 8px; align-items: center; }
  .workspace-membership-card { gap: 9px; }
  .workspace-service-list { display: flex; flex-direction: column; gap: 5px; max-height: min(46vh, 520px); overflow-y: auto; overscroll-behavior: contain; padding: 3px; border: 1px solid var(--border); border-radius: 9px; background: var(--bg); }
  .workspace-service-row { min-height: 46px; display: flex; flex-direction: row; align-items: center; justify-content: space-between; gap: 12px; padding: 7px 9px; border-radius: 7px; cursor: pointer; }
  .workspace-service-row:hover { background: var(--hover); }
  .workspace-service-row > span { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .workspace-service-row strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text2); font-size: 13px; }
  .workspace-service-row small { color: var(--muted); font-size: 11px; }
  .workspace-service-row input { width: 18px; height: 18px; flex: none; accent-color: var(--accent); }
  .workspace-detail-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
  .danger-button { color: #ff9b9b; border-color: color-mix(in srgb, #ff7373 45%, var(--border2)); }
  .pagination { display: flex; align-items: center; justify-content: center; gap: 10px; color: var(--muted); font-size: 12px; }
  .download-override-toggle { width: fit-content; max-width: 100%; }
  .download-setting-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 12px; width: 100%; box-sizing: border-box; padding: 10px 0 0; border-top: 1px solid var(--border); }
  label.download-setting-row { cursor: pointer; }
  .workspace-download-card .download-setting-row { padding: 10px 0 0; }
  @media (max-width: 760px) {
    .setting-card { grid-template-columns: 1fr; gap: 10px; align-items: stretch; }
    .setting-card-toggle { grid-template-columns: minmax(0, 1fr) auto; align-items: center; }
    .setting-control { width: 100%; max-width: none; }
    .setting-actions { justify-content: flex-start; }
    .managed-row { align-items: flex-start; flex-direction: column; }
    .managed-actions { width: 100%; justify-content: flex-end; flex-wrap: wrap; }
    .workspace-detail-heading { align-items: center; }
    .workspace-name-control { min-width: 0; }
    .managed-toolbar, .workspace-create-row, .workspace-name-control, .workspace-icon-current, .workspace-icon-url-row, .download-setting-row { grid-template-columns: 1fr; }
  }

</style>
