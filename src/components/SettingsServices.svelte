<script lang="ts">

  import type { AppSettings, Service, Workspace } from "../lib/api";
  import { serviceLabel } from "../lib/ui";
  import SettingsToggle from "./SettingsToggle.svelte";

  interface Props {
    MANAGED_SERVICE_PAGE_SIZE: 100;
    appSettings: AppSettings;
    clearServiceExportSelection: () => void;
    configuredServiceRecipeLabel: (service: Service) => string;
    displayedServiceIcon: (service: Service) => string;
    doServiceExport: (selectedServices: Service[]) => Promise<void>;
    managedServicePage: number;
    managedServicePageCount: number;
    managedServiceQuery: string;
    managedServiceRows: Service[];
    managedServices: Service[];
    managedWorkspaceFilter: string;
    markIconFailed: (service: Service) => void;
    moveManagedService: (serviceId: string, delta: number) => Promise<void>;
    openAdd: () => Promise<void>;
    openServiceSettings: (s: Service, returnToSettings?: boolean) => void;
    saveAppSetting: (key: keyof AppSettings, value: unknown) => Promise<void>;
    selectAllServiceExports: () => void;
    selectedServiceExports: Service[];
    serviceExportBusy: boolean;
    serviceExportIncludeAllPersonalRecipes: boolean;
    serviceExportIncludeSensitiveRecipeScripts: boolean;
    serviceExportSelection: Set<string>;
    serviceExportStatus: string;
    serviceIconFailed: (service: Service) => boolean;
    serviceIconInverted: (serviceId: string) => boolean;
    serviceOrderBusy: boolean;
    services: Service[];
    setServiceExportSelected: (serviceId: string, selected: boolean) => void;
    sortedWorkspaces: Workspace[];
  }

  let {
    MANAGED_SERVICE_PAGE_SIZE,
    appSettings = $bindable(),
    clearServiceExportSelection,
    configuredServiceRecipeLabel,
    displayedServiceIcon,
    doServiceExport,
    managedServicePage = $bindable(),
    managedServicePageCount,
    managedServiceQuery = $bindable(),
    managedServiceRows,
    managedServices,
    managedWorkspaceFilter = $bindable(),
    markIconFailed,
    moveManagedService,
    openAdd,
    openServiceSettings,
    saveAppSetting,
    selectAllServiceExports,
    selectedServiceExports,
    serviceExportBusy,
    serviceExportIncludeAllPersonalRecipes = $bindable(),
    serviceExportIncludeSensitiveRecipeScripts = $bindable(),
    serviceExportSelection,
    serviceExportStatus,
    serviceIconFailed,
    serviceIconInverted,
    serviceOrderBusy,
    services,
    setServiceExportSelected,
    sortedWorkspaces,
  }: Props = $props();

</script>

<section class="settings-section" aria-labelledby="settings-services-configured">
                <div class="section-heading">
                  <h3 id="settings-services-configured">Configured services <span class="section-count">{services.length}</span></h3>
                  <p>Search or separate the list by workspace. Recipe origins are shown as Ferdium recipe, Tauridium built-in, Personal recipe, or Custom website. Reordering a filtered workspace changes only those visible service slots while preserving the canonical global order.</p>
                </div>
                <div class="managed-toolbar service-managed-toolbar">
                  <input
                    class="setting-text-input"
                    type="search"
                    placeholder="Search configured services…"
                    bind:value={managedServiceQuery}
                    oninput={() => (managedServicePage = 0)}
                    aria-label="Search configured services"
                  />
                  <select
                    class="select"
                    bind:value={managedWorkspaceFilter}
                    onchange={() => (managedServicePage = 0)}
                    aria-label="Filter configured services by workspace"
                  >
                    <option value="all">All workspaces</option>
                    {#each sortedWorkspaces as workspace (workspace.id)}
                      <option value={workspace.id}>{workspace.name}</option>
                    {/each}
                  </select>
                  <button class="primary" onclick={openAdd}>Create service</button>
                </div>
                <div class="service-export-panel" id="settings-option-serviceExport">
                  <div class="service-export-summary">
                    <div class="setting-copy">
                      <span class="setting-label">Portable service export</span>
                      <span class="setting-description">Select any subset below, then export one ZIP. Known credential fields and sensitive URL values are redacted; browser sessions are excluded. Personal scripts are off by default. Review the complete bundle before sharing: arbitrary private content cannot be guaranteed safe automatically.</span>
                    </div>
                    <div class="setting-actions service-export-actions">
                      <span class="status-badge service-export-selected-count">{selectedServiceExports.length} selected</span>
                      <button class="secondary sm service-export-select-all" disabled={!services.length || serviceExportBusy} onclick={selectAllServiceExports}>Select all</button>
                      <button class="secondary sm service-export-clear" disabled={!serviceExportSelection.size || serviceExportBusy} onclick={clearServiceExportSelection}>Clear</button>
                      <button class="primary sm service-export-submit" disabled={serviceExportBusy || (!selectedServiceExports.length && !serviceExportIncludeAllPersonalRecipes)} onclick={() => doServiceExport(selectedServiceExports)}>{selectedServiceExports.length ? "Export selected…" : "Export personal recipes…"}</button>
                    </div>
                  </div>
                  <label class="setting-card setting-card-toggle service-export-recipe-toggle">
                    <div class="setting-copy">
                      <span class="setting-label">Include all personal recipes & custom websites</span>
                      <span class="setting-description">Also include every recipe you created or imported on this device plus every Custom Website service, even when it is not selected. Referenced personal recipes and selected Custom Websites are always included. Ferdium catalog recipes and Tauridium built-in recipes are referenced by id rather than bulk-exported.</span>
                    </div>
                    <span class="switch-control">
                      <input class="switch-input" type="checkbox" bind:checked={serviceExportIncludeAllPersonalRecipes} disabled={serviceExportBusy} aria-label="Include all personal recipes and custom websites in service export" />
                      <span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>
                    </span>
                  </label>
                  <label class="setting-card setting-card-toggle service-export-recipe-toggle">
                    <span class="setting-copy"><span class="setting-label">Include personal executable recipe scripts</span><span class="setting-description">Off by default. Scripts are copied unchanged and may contain private literals. Enable only for a reviewed, trusted export. Generated recipe stubs remain included without personal code.</span></span>
                    <span class="switch-control"><input class="switch-input" type="checkbox" bind:checked={serviceExportIncludeSensitiveRecipeScripts} disabled={serviceExportBusy} aria-label="Include personal executable recipe scripts" /><span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span></span>
                  </label>
                </div>
                {#if serviceExportStatus}<p class="settings-status">{serviceExportStatus}</p>{/if}
                <div class="managed-list service-managed-list" role="list" aria-label="Configured services">
                  {#each managedServiceRows as service, index (service.id)}
                    <div class="managed-row service-export-row" class:selected={serviceExportSelection.has(service.id)} role="listitem">
                      <label
                        class="service-export-row-toggle"
                        for={`service-export-${service.id}`}
                        title={`Select ${serviceLabel(service)} for export`}
                      ></label>
                      <div class="managed-identity service-export-identity">
                        <input
                          id={`service-export-${service.id}`}
                          class="service-export-checkbox"
                          type="checkbox"
                          checked={serviceExportSelection.has(service.id)}
                          aria-label={`Select ${serviceLabel(service)} for export`}
                          onchange={(event) => setServiceExportSelected(service.id, event.currentTarget.checked)}
                        />
                        {#if serviceIconFailed(service)}
                          <span class="managed-icon fallback">{serviceLabel(service).slice(0, 1).toUpperCase()}</span>
                        {:else}
                          <img class="managed-icon" class:service-icon-inverted={serviceIconInverted(service.id)} src={displayedServiceIcon(service)} alt="" onerror={() => markIconFailed(service)} />
                        {/if}
                        <div class="managed-copy">
                          <strong>{serviceLabel(service)}</strong>
                          <span>{service.isEnabled ? "Enabled" : "Disabled"} · {service.recipeId || "Unknown recipe"} · {configuredServiceRecipeLabel(service)}</span>
                        </div>
                      </div>
                      <div class="managed-actions">
                        <button class="icon-button compact" disabled={serviceOrderBusy || managedServicePage * MANAGED_SERVICE_PAGE_SIZE + index === 0} aria-label={`Move ${serviceLabel(service)} up`} title="Move up" onclick={() => moveManagedService(service.id, -1)}>↑</button>
                        <button class="icon-button compact" disabled={serviceOrderBusy || managedServicePage * MANAGED_SERVICE_PAGE_SIZE + index === managedServices.length - 1} aria-label={`Move ${serviceLabel(service)} down`} title="Move down" onclick={() => moveManagedService(service.id, 1)}>↓</button>
                        <button class="secondary sm" onclick={() => openServiceSettings(service, true)}>Service settings</button>
                      </div>
                    </div>
                  {:else}
                    <div class="managed-empty">
                      <strong>{services.length ? "No services match this view" : "No services configured"}</strong>
                      <span>{services.length ? "Change the search or workspace filter." : "Create a service above or use the Tauridium application menu."}</span>
                    </div>
                  {/each}
                </div>
                {#if managedServices.length > MANAGED_SERVICE_PAGE_SIZE}
                  <div class="pagination" aria-label="Configured services pages">
                    <button class="secondary sm" disabled={managedServicePage === 0} onclick={() => (managedServicePage = Math.max(0, managedServicePage - 1))}>Previous</button>
                    <span>Page {managedServicePage + 1} of {managedServicePageCount} · {managedServices.length} services</span>
                    <button class="secondary sm" disabled={managedServicePage >= managedServicePageCount - 1} onclick={() => (managedServicePage = Math.min(managedServicePageCount - 1, managedServicePage + 1))}>Next</button>
                  </div>
                {/if}
              </section>
              <section class="settings-section" aria-labelledby="settings-services-list">
                <div class="section-heading">
                  <h3 id="settings-services-list">Service list</h3>
                  <p>Control what appears in the sidebar and how unread activity is represented.</p>
                </div>
                <div class="settings-list">
                  <SettingsToggle
                    label={"Show disabled services"}
                    description={"Keep disabled services visible in the sidebar with reduced emphasis."}
                    settingKey={"showDisabledServices"}
                    checked={appSettings.showDisabledServices}
                    onsave={saveAppSetting}
                  />
                  <SettingsToggle
                    label={"Show service names"}
                    description={"Display each service name beside its icon in the sidebar."}
                    settingKey={"showServiceName"}
                    checked={appSettings.showServiceName}
                    onsave={saveAppSetting}
                  />
                  <SettingsToggle
                    label={"Unread badges for muted services"}
                    description={"Continue displaying unread counts for services whose notifications are muted."}
                    settingKey={"showMessageBadgeWhenMuted"}
                    checked={appSettings.showMessageBadgeWhenMuted}
                    onsave={saveAppSetting}
                  />
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-services-performance">
                <div class="section-heading">
                  <h3 id="settings-services-performance">Performance</h3>
                  <p>Balance faster switching against memory use.</p>
                </div>
                <div class="settings-list">
                  <div class="setting-card" id="settings-option-hibernationTimer">
                    <div class="setting-copy">
                      <span class="setting-label">Hibernate inactive services</span>
                      <span class="setting-description">Unload inactive services to save memory. Per-service “Allow hibernation” must also be enabled.</span>
                    </div>
                    <select class="select setting-control" aria-label="Hibernate inactive services" bind:value={appSettings.hibernationTimer} onchange={() => saveAppSetting("hibernationTimer", appSettings.hibernationTimer)}>
                      <option value={0}>Off</option>
                      <option value={30}>After 30 seconds</option>
                      <option value={60}>After 1 minute</option>
                      <option value={300}>After 5 minutes</option>
                    </select>
                  </div>
                  <SettingsToggle
                    label={"Preload services"}
                    description={"Load services in the background after startup for faster switching. This uses more memory."}
                    settingKey={"preloadServices"}
                    checked={appSettings.preloadServices}
                    onsave={saveAppSetting}
                  />
                </div>
              </section>

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
  .primary.sm { padding: 6px 12px; font-size: 13px; }
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
  .managed-icon { width: 34px; height: 34px; border-radius: 8px; object-fit: cover; flex: none; }
  .managed-icon.fallback { display: grid; place-items: center; background: var(--hover); color: var(--text2); font-weight: 750; }
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
  .setting-copy { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .setting-label { color: var(--text2); font-size: 14px; line-height: 1.35; font-weight: 650; }
  .setting-description { max-width: 760px; color: var(--muted); font-size: 12.5px; line-height: 1.45; font-weight: 400; }
  .setting-control { min-width: 176px; max-width: 230px; margin-left: 0; }
  .setting-text-input { width: 100%; box-sizing: border-box; }
  .setting-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
  .settings-status { margin: 0 2px; color: var(--muted); font-size: 12px; line-height: 1.45; }
  .settings-status { color: var(--text2); }
  .status-badge {
    display: inline-flex; align-items: center; min-height: 24px; padding: 0 9px;
    border: 1px solid var(--border2); border-radius: 999px; background: var(--hover);
    color: var(--text2); font-size: 11px; font-weight: 700;
  }
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
  :global(.settings-panel) .primary.sm, :global(.settings-panel) .secondary.sm { min-height: 30px; }
  .managed-toolbar { display: grid; grid-template-columns: minmax(0, 1fr) minmax(160px, 220px); gap: 8px; }
  .service-managed-toolbar { grid-template-columns: minmax(0, 1fr) minmax(160px, 220px) auto; }
  .service-export-panel { display: flex; flex-direction: column; gap: 8px; }
  .service-export-summary { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 18px; padding: 11px 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--input); }
  .service-export-actions {
    display: grid;
    grid-template-columns: 104px 82px 62px 184px;
    align-items: center;
    gap: 8px;
  }
  .service-export-actions > * { width: 100%; box-sizing: border-box; }
  .service-export-selected-count { justify-content: center; white-space: nowrap; }
  .service-export-submit { white-space: nowrap; }
  .service-export-recipe-toggle { min-height: 62px; }
  .service-export-row { position: relative; isolation: isolate; }
  .service-export-row-toggle { position: absolute; inset: 0; z-index: 0; border-radius: inherit; cursor: pointer; }
  .service-export-row:hover:not(.selected) { border-color: var(--border2); background: var(--hover); }
  .service-export-identity { position: relative; z-index: 1; flex: 1 1 auto; pointer-events: none; }
  .service-export-checkbox { width: 17px; height: 17px; margin: 0; flex: none; accent-color: var(--accent); pointer-events: auto; cursor: pointer; }
  .service-export-row .managed-actions { position: relative; z-index: 1; pointer-events: none; }
  .service-export-row .managed-actions > * { pointer-events: auto; }
  .service-managed-list {
    max-height: min(58vh, 680px);
    overflow-y: auto;
    overscroll-behavior: contain;
    scrollbar-gutter: stable;
    padding-right: 3px;
  }
  .managed-row.selected { border-color: color-mix(in srgb, var(--accent) 62%, var(--border)); background: color-mix(in srgb, var(--accent) 8%, var(--input)); }
  .pagination { display: flex; align-items: center; justify-content: center; gap: 10px; color: var(--muted); font-size: 12px; }
  @media (max-width: 760px) {
    .setting-card { grid-template-columns: 1fr; gap: 10px; align-items: stretch; }
    .setting-card-toggle { grid-template-columns: minmax(0, 1fr) auto; align-items: center; }
    .setting-control { width: 100%; max-width: none; }
    .setting-actions { justify-content: flex-start; }
    .managed-row { align-items: flex-start; flex-direction: column; }
    .managed-actions { width: 100%; justify-content: flex-end; flex-wrap: wrap; }
    .service-export-actions {
      width: 100%;
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    .service-export-submit { grid-column: 1 / -1; }
    .managed-toolbar, .service-export-summary { grid-template-columns: 1fr; }
  }

</style>
