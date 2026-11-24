<script lang="ts">

  import type { ServiceEditorController } from "../lib/controllers/serviceEditor.svelte";
  import type { AppSettings, DownloadPreferenceOverride, Service, Workspace } from "../lib/api";
  import { SERVICE_ZOOM_LEVELS } from "../lib/ui";
  import { browserProfileNamespace } from "../lib/browserPrivacy";
  import { downloadDirectoryLabel } from "../lib/settingsMaps";
  import { ownValue } from "../lib/settingsMaps";
  import { serviceLabel } from "../lib/ui";
  import ServiceToggle from "./ServiceToggle.svelte";

  interface Props {
    serviceEditor: ServiceEditorController;
    MANAGED_SERVICE_PAGE_SIZE: 100;
    appSettings: AppSettings;
    assignServiceSandbox: (serviceId: string, sandboxId: string) => Promise<void>;
    chooseServiceDownloadDirectory: (serviceId: string) => Promise<void>;
    chooseServiceZoom: (service: Service | null, zoomPercent: number) => Promise<void>;
    dockWord: "Dock" | "taskbar";
    downloadSettingsBusy: boolean;
    error: string | null;
    failedWorkspaceIcons: Set<string>;
    handleClearCache: (s: Service) => Promise<void>;
    handleDelete: (s: Service) => Promise<void>;
    inheritedDownloadPreference: () => DownloadPreferenceOverride;
    loadServiceIcon: (service: Service, force?: boolean, report?: boolean, preferWebsiteIcon?: boolean) => Promise<void>;
    markWorkspaceIconFailed: (workspaceId: string) => void;
    osKind: "mac" | "win" | "linux";
    sandboxAssignmentBusy: boolean;
    saveServiceDownloadOverride: (serviceId: string, preference: DownloadPreferenceOverride | null) => Promise<void>;
    saveServiceIconInversion: (serviceId: string, inverted: boolean) => Promise<void>;
    saveTrackingException: (serviceId: string, enabled: boolean) => Promise<void>;
    serviceDownloadOverride: (serviceId: string) => DownloadPreferenceOverride | null;
    serviceIconInverted: (serviceId: string) => boolean;
    serviceSandboxId: (serviceId: string) => string | null;
    serviceZoomPercent: (serviceId: string) => number;
    settingsSvc: Service;
    toggleServiceEnabled: (service: Service) => Promise<void>;
    workspaceIcon: (workspace: Workspace) => string | null;
    workspaces: Workspace[];
  }

  let {
    serviceEditor,
    MANAGED_SERVICE_PAGE_SIZE,
    appSettings,
    assignServiceSandbox,
    chooseServiceDownloadDirectory,
    chooseServiceZoom,
    dockWord,
    downloadSettingsBusy,
    error,
    failedWorkspaceIcons,
    handleClearCache,
    handleDelete,
    inheritedDownloadPreference,
    loadServiceIcon,
    markWorkspaceIconFailed,
    osKind,
    sandboxAssignmentBusy,
    saveServiceDownloadOverride,
    saveServiceIconInversion,
    saveTrackingException,
    serviceDownloadOverride,
    serviceIconInverted,
    serviceSandboxId,
    serviceZoomPercent,
    settingsSvc,
    toggleServiceEnabled,
    workspaceIcon,
    workspaces,
  }: Props = $props();
  const settingsServiceId = $derived(settingsSvc.id);
  const settingsServiceDownload = $derived(serviceDownloadOverride(settingsServiceId));
  const settingsServiceZoom = $derived(serviceZoomPercent(settingsServiceId));
</script>

<div class="panel">
          <div class="panel-head">
            <h2>Settings — {serviceLabel(settingsSvc)}</h2>
            <span class="head-actions">
              <button class="primary sm" disabled={!serviceEditor.svcDirty && !serviceEditor.serviceTemplateDirty} onclick={serviceEditor.saveServiceSettings}>
                {serviceEditor.svcDirty || serviceEditor.serviceTemplateDirty ? "Save changes" : "Saved"}
              </button>
              <button class="link" onclick={serviceEditor.closeServiceSettings}>✕ close</button>
            </span>
          </div>
          <code class="recipe">recipe: {settingsSvc.recipeId}</code>

          <div class="set-title">General</div>
          <label class="block">
            Name
            <input value={settingsSvc.name} oninput={(e) => serviceEditor.saveText("name", e.currentTarget.value)} />
          </label>
          <div class="setrow">
            <label class="block">
              Custom URL
              <input value={settingsSvc.customUrl ?? ""} placeholder="https://… (for services that support it)" onchange={(e) => serviceEditor.saveText("customUrl", e.currentTarget.value, true)} />
            </label>
            <p class="desc">Override the recipe URL. Supports <code>{"{teamId}"}</code> for recipes with website workspace IDs and, when enabled below, <code>{"{{custom_id_1}}"}</code> / <code>{"{{custom_id_2}}"}</code>. Reloads the service.</p>
          </div>
          <div class="setrow">
            <label class="block">
              Team / workspace ID
              <input value={settingsSvc.team ?? ""} placeholder="wrk_01ABC123EXAMPLE" onchange={(e) => serviceEditor.saveText("team", e.currentTarget.value, true)} />
            </label>
            <p class="desc">Website-specific team/workspace slug or ID, not a Tauridium Workspace. Example: <code>wrk_01ABC123EXAMPLE</code> becomes <code>https://opencode.ai/workspace/wrk_01ABC123EXAMPLE/go</code> for OpenCode. Reloads the service.</p>
          </div>
          <div class="set-title">Custom URL placeholders</div>
          <div class="setrow">
            <label class="row-toggle">
              <input type="checkbox" checked={appSettings.customUrlTemplatesEnabled || serviceEditor.serviceTemplateDraft.enabled} disabled={appSettings.customUrlTemplatesEnabled} onchange={(e) => serviceEditor.saveServiceTemplateField("enabled", e.currentTarget.checked)} />
              <span>{appSettings.customUrlTemplatesEnabled ? "Custom URL placeholders enabled globally" : "Enable custom URL placeholders for this service"}</span>
            </label>
            <p class="desc">Allow exact <code>{"{{custom_id_1}}"}</code> and <code>{"{{custom_id_2}}"}</code> tokens in this service's Custom URL. Global enablement is available in Advanced settings.</p>
          </div>
          {#if appSettings.customUrlTemplatesEnabled || serviceEditor.serviceTemplateDraft.enabled}
            <div class="setrow">
              <div class="proxy-grid">
                <label>Custom ID 1<input value={serviceEditor.serviceTemplateDraft.customId1} placeholder="first replacement value" onchange={(e) => serviceEditor.saveServiceTemplateField("customId1", e.currentTarget.value)} /></label>
                <label>Custom ID 2 (optional)<input value={serviceEditor.serviceTemplateDraft.customId2} placeholder="second replacement value" onchange={(e) => serviceEditor.saveServiceTemplateField("customId2", e.currentTarget.value)} /></label>
              </div>
            </div>
          {/if}
          <ServiceToggle
            label={"Notifications"}
            description={"Show system notifications for new messages in this service."}
            settingKey={"isNotificationEnabled"}
            checked={settingsSvc.isNotificationEnabled !== false}
            onsave={serviceEditor.saveSetting}
          />
          <ServiceToggle
            label={"Muted"}
            description={"Silence this service — no notifications at all."}
            settingKey={"isMuted"}
            checked={settingsSvc.isMuted === true}
            onsave={serviceEditor.saveSetting}
          />
          <ServiceToggle
            label={"Unread badge"}
            description={`Count this service's unread messages in the ${dockWord} badge.`}
            settingKey={"isBadgeEnabled"}
            checked={settingsSvc.isBadgeEnabled !== false}
            onsave={serviceEditor.saveSetting}
          />
          <ServiceToggle
            label={"Indirect message badge"}
            description={"Also count indirect (group / channel) messages when the service reports them separately."}
            settingKey={"isIndirectMessageBadgeEnabled"}
            checked={settingsSvc.isIndirectMessageBadgeEnabled === true}
            onsave={serviceEditor.saveSetting}
          />
          <ServiceToggle
            label={"Only favorites in unread count"}
            description={"Count unread messages only from favorite chats in this service."}
            settingKey={"onlyShowFavoritesInUnreadCount"}
            checked={settingsSvc.onlyShowFavoritesInUnreadCount === true}
            onsave={serviceEditor.saveSetting}
          />
          <ServiceToggle
            label={"Media badge"}
            description={"Count calls / media activity in the badge."}
            settingKey={"isMediaBadgeEnabled"}
            checked={settingsSvc.isMediaBadgeEnabled === true}
            onsave={serviceEditor.saveSetting}
          />
          <ServiceToggle
            label={"Allow hibernation"}
            description={"Let this service sleep when inactive to save memory."}
            settingKey={"isHibernationEnabled"}
            checked={settingsSvc.isHibernationEnabled === true}
            onsave={serviceEditor.saveSetting}
          />
          <ServiceToggle
            label={"Open links externally"}
            description={"Open clicked links in your default browser instead of inside the service."}
            settingKey={"trapLinkClicks"}
            checked={settingsSvc.trapLinkClicks === true}
            onsave={serviceEditor.saveSetting}
          />
          <ServiceToggle
            label={"Allow wake up"}
            description={"Wake this service from hibernation on new activity."}
            settingKey={"isWakeUpEnabled"}
            checked={settingsSvc.isWakeUpEnabled === true}
            onsave={serviceEditor.saveSetting}
          />

          <div class="set-title">Page zoom</div>
          <div class="setrow">
            <label class="block">
              Zoom level
              <select class="select" aria-label={`Page zoom for ${serviceLabel(settingsSvc)}`} value={settingsServiceZoom} onchange={(event) => void chooseServiceZoom(settingsSvc, Number(event.currentTarget.value))}>
                {#each SERVICE_ZOOM_LEVELS as level}
                  <option value={level}>{level}%</option>
                {/each}
              </select>
            </label>
            <p class="desc">Scale this service's website without changing Tauridium's interface. Saved immediately and restored whenever the service webview is created.</p>
          </div>

          <div class="set-title">Keyboard shortcuts</div>
          <div class="setrow service-shortcut-policy">
            <div class="service-shortcut-copy">
              <strong>Shortcut priority</strong>
              <p class="desc">Choose who receives configured Tauridium shortcuts while this website has keyboard focus. Normal typing remains untouched unless a key or key sequence is explicitly assigned as a Tauridium shortcut.</p>
            </div>
            <select
              class="select"
              aria-label={`Shortcut priority for ${serviceLabel(settingsSvc)}`}
              value={serviceEditor.serviceShortcutCaptureMode(settingsServiceId)}
              onchange={(event) => serviceEditor.setServiceShortcutCaptureMode(settingsServiceId, event.currentTarget.value as "inherit" | "tauridium" | "website")}
            >
              <option value="inherit">Use global setting ({appSettings.captureServiceShortcuts ? "Tauridium" : "Website"})</option>
              <option value="tauridium">Tauridium shortcuts first</option>
              <option value="website">Website shortcuts first</option>
            </select>
            <p class="desc service-shortcut-effective">Effective behavior: <strong>{serviceEditor.effectiveServiceShortcutCapture(settingsServiceId) ? "Tauridium shortcuts work while the website is focused" : "the website receives matching shortcuts while focused"}</strong>. Applied when this service webview is next opened.</p>
          </div>

          <div class="set-title">Workspaces</div>
          <div class="service-workspace-manager">
            <div class="service-workspace-overview">
              <div class="setting-copy">
                <strong>Workspace membership</strong>
                <p class="desc">Select the workspaces that include this service. Click anywhere in a row to change membership; changes are saved immediately.</p>
              </div>
              <span class="status-badge">{serviceEditor.serviceWorkspaceJoinedCount} of {workspaces.length} included</span>
            </div>
            <div class="service-workspace-toolbar">
              <input
                class="service-workspace-search"
                type="search"
                bind:value={serviceEditor.serviceWorkspaceQuery}
                oninput={() => (serviceEditor.serviceWorkspacePage = 0)}
                placeholder="Search workspaces…"
                aria-label="Search workspaces for this service"
              />
              <div class="service-workspace-filters" role="group" aria-label="Filter workspace membership">
                <button
                  type="button"
                  class:active={serviceEditor.serviceWorkspaceFilter === "all"}
                  aria-pressed={serviceEditor.serviceWorkspaceFilter === "all"}
                  onclick={() => serviceEditor.setServiceWorkspaceFilter("all")}
                >All</button>
                <button
                  type="button"
                  class:active={serviceEditor.serviceWorkspaceFilter === "joined"}
                  aria-pressed={serviceEditor.serviceWorkspaceFilter === "joined"}
                  onclick={() => serviceEditor.setServiceWorkspaceFilter("joined")}
                >Included</button>
                <button
                  type="button"
                  class:active={serviceEditor.serviceWorkspaceFilter === "available"}
                  aria-pressed={serviceEditor.serviceWorkspaceFilter === "available"}
                  onclick={() => serviceEditor.setServiceWorkspaceFilter("available")}
                >Not included</button>
              </div>
            </div>
            <ul class="service-workspace-list" aria-label={`Workspace membership for ${serviceLabel(settingsSvc)}`}>
              {#each serviceEditor.serviceWorkspaceRows as workspace (workspace.id)}
                {@const joined = workspace.services.includes(settingsServiceId)}
                <li class="service-workspace-item">
                  <label class="service-workspace-option" class:joined class:busy={serviceEditor.serviceWorkspaceBusy}>
                    <input
                      class="service-workspace-checkbox"
                      type="checkbox"
                      checked={joined}
                      disabled={serviceEditor.serviceWorkspaceBusy}
                      onchange={(event) => serviceEditor.toggleCurrentServiceWorkspace(workspace, event.currentTarget.checked)}
                      aria-label={`Include ${serviceLabel(settingsSvc)} in ${workspace.name}`}
                    />
                    {#if workspaceIcon(workspace) && !failedWorkspaceIcons.has(workspace.id)}
                      <img class="workspace-avatar service-workspace-avatar workspace-avatar-image" src={workspaceIcon(workspace) ?? ""} alt="" onerror={() => markWorkspaceIconFailed(workspace.id)} />
                    {:else}
                      <span class="workspace-avatar service-workspace-avatar" aria-hidden="true">{workspace.name.slice(0, 1).toUpperCase()}</span>
                    {/if}
                    <span class="service-workspace-copy">
                      <strong>{workspace.name}</strong>
                      <small>{workspace.services.length} service{workspace.services.length === 1 ? "" : "s"}</small>
                    </span>
                    <span class="service-workspace-state" aria-hidden="true">{joined ? "Included" : "Not included"}</span>
                  </label>
                </li>
              {:else}
                <li class="managed-empty">
                  <strong>No workspaces match</strong>
                  <span>{workspaces.length ? "Change the search or membership filter." : "Create a workspace below to organize this service."}</span>
                </li>
              {/each}
            </ul>
            {#if serviceEditor.serviceWorkspaceCandidates.length > MANAGED_SERVICE_PAGE_SIZE}
              <div class="pagination" aria-label="Service workspace pages">
                <button class="secondary sm" disabled={serviceEditor.serviceWorkspacePage === 0} onclick={() => (serviceEditor.serviceWorkspacePage = Math.max(0, serviceEditor.serviceWorkspacePage - 1))}>Previous</button>
                <span>Page {serviceEditor.serviceWorkspacePage + 1} of {serviceEditor.serviceWorkspacePageCount} · {serviceEditor.serviceWorkspaceCandidates.length} workspaces</span>
                <button class="secondary sm" disabled={serviceEditor.serviceWorkspacePage >= serviceEditor.serviceWorkspacePageCount - 1} onclick={() => (serviceEditor.serviceWorkspacePage = Math.min(serviceEditor.serviceWorkspacePageCount - 1, serviceEditor.serviceWorkspacePage + 1))}>Next</button>
              </div>
            {/if}
            <div class="service-workspace-create-card">
              <div class="setting-copy">
                <strong>Create a workspace</strong>
                <p class="desc">Create a new workspace and include this service immediately.</p>
              </div>
              <div class="service-workspace-create">
                <input bind:value={serviceEditor.serviceWorkspaceNewName} maxlength="80" placeholder="Workspace name" aria-label="New workspace name for this service" />
                <button class="secondary sm" disabled={serviceEditor.serviceWorkspaceBusy || !serviceEditor.serviceWorkspaceNewName.trim()} onclick={serviceEditor.createWorkspaceForCurrentService}>Create and include</button>
              </div>
            </div>
          </div>

          <div class="set-title">Sandbox</div>
          <div class="service-workspace-manager service-sandbox-manager">
            <div class="service-workspace-overview">
              <div class="setting-copy">
                <strong>Sandbox assignment</strong>
                <p class="desc">Choose the persistent webview data store for this service. Services in the same shared sandbox can share compatible login sessions and caches. Changes are saved immediately.</p>
              </div>
              <span class="status-badge">{serviceEditor.currentServiceSandboxName}</span>
            </div>
            <input
              class="service-workspace-search service-sandbox-search"
              type="search"
              bind:value={serviceEditor.serviceSandboxQuery}
              oninput={() => (serviceEditor.serviceSandboxPage = 0)}
              placeholder="Search sandboxes…"
              aria-label={`Search sandboxes for ${serviceLabel(settingsSvc)}`}
            />
            <ul class="service-workspace-list service-sandbox-list" aria-label={`Sandbox assignment for ${serviceLabel(settingsSvc)}`}>
              {#each serviceEditor.serviceSandboxRows as sandbox (sandbox.id)}
                {@const assigned = (serviceSandboxId(settingsServiceId) ?? "") === sandbox.id}
                <li class="service-workspace-item">
                  <label class="service-workspace-option service-sandbox-option" class:joined={assigned} class:busy={sandboxAssignmentBusy}>
                    <input
                      class="service-workspace-checkbox"
                      type="radio"
                      name={`service-sandbox-${settingsServiceId}`}
                      value={sandbox.id}
                      checked={assigned}
                      disabled={sandboxAssignmentBusy}
                      onchange={() => assignServiceSandbox(settingsServiceId, sandbox.id)}
                      aria-label={`Use ${sandbox.name} for ${serviceLabel(settingsSvc)}`}
                    />
                    <span class="workspace-avatar service-workspace-avatar" aria-hidden="true">{sandbox.id ? sandbox.name.slice(0, 1).toUpperCase() : "I"}</span>
                    <span class="service-workspace-copy">
                      <strong>{sandbox.name}</strong>
                      <small>{sandbox.id ? `${Object.values(appSettings.serviceSandboxes).filter((value) => value === sandbox.id).length} assigned service(s)` : "Private storage for this service"}</small>
                    </span>
                    <span class="service-workspace-state" aria-hidden="true">{assigned ? "Selected" : "Available"}</span>
                  </label>
                </li>
              {:else}
                <li class="managed-empty"><strong>No sandboxes match</strong><span>Change the search text, or create a shared sandbox in Settings → Sandbox.</span></li>
              {/each}
            </ul>
            {#if serviceEditor.serviceSandboxCandidates.length > MANAGED_SERVICE_PAGE_SIZE}
              <div class="pagination" aria-label="Service sandbox pages">
                <button class="secondary sm" disabled={serviceEditor.serviceSandboxPage === 0} onclick={() => (serviceEditor.serviceSandboxPage = Math.max(0, serviceEditor.serviceSandboxPage - 1))}>Previous</button>
                <span>Page {serviceEditor.serviceSandboxPage + 1} of {serviceEditor.serviceSandboxPageCount} · {serviceEditor.serviceSandboxCandidates.length} options</span>
                <button class="secondary sm" disabled={serviceEditor.serviceSandboxPage >= serviceEditor.serviceSandboxPageCount - 1} onclick={() => (serviceEditor.serviceSandboxPage = Math.min(serviceEditor.serviceSandboxPageCount - 1, serviceEditor.serviceSandboxPage + 1))}>Next</button>
              </div>
            {/if}
            <p class="desc service-sandbox-help">Shared sandboxes are created and managed globally in Settings → Sandbox.</p>
          </div>

          <div class="set-title">Downloads</div>
          <div class="service-workspace-manager service-download-manager">
            <div class="service-workspace-overview">
              <div class="setting-copy">
                <strong>Service download settings</strong>
                <p class="desc">Optionally override download behavior for this service. A service override has highest priority. Without one, an active workspace override is used when present, then the global Advanced defaults.</p>
              </div>
              <span class="status-badge">{settingsServiceDownload ? "Override" : "Inherited"}</span>
            </div>
            <label class="row-toggle download-override-toggle">
              <input
                type="checkbox"
                checked={settingsServiceDownload !== null}
                disabled={downloadSettingsBusy}
                onchange={(event) => saveServiceDownloadOverride(
                  settingsServiceId,
                  event.currentTarget.checked ? inheritedDownloadPreference() : null,
                )}
              />
              <span>Override download settings for this service</span>
            </label>
            {#if settingsServiceDownload}
              <div class="download-setting-row">
                <div class="setting-copy">
                  <strong>Download directory</strong>
                  <p class="desc" title={downloadDirectoryLabel(settingsServiceDownload.directory)}>{downloadDirectoryLabel(settingsServiceDownload.directory)}</p>
                </div>
                <div class="setting-actions">
                  <button class="secondary sm" disabled={downloadSettingsBusy} onclick={() => chooseServiceDownloadDirectory(settingsServiceId)}>Choose folder…</button>
                  <button class="secondary sm" disabled={downloadSettingsBusy || !settingsServiceDownload.directory} onclick={() => saveServiceDownloadOverride(settingsServiceId, { ...settingsServiceDownload, directory: "" })}>Use system Downloads</button>
                </div>
              </div>
              <label class="download-setting-row setting-card-toggle">
                <span class="setting-copy"><strong>Ask where to save each download</strong><span class="desc">Show a native Save dialog for every download, initialized with the website's suggested filename and this directory.</span></span>
                <span class="switch-control">
                  <input class="switch-input" type="checkbox" checked={settingsServiceDownload.askEachDownload} disabled={downloadSettingsBusy} aria-label={`Ask where to save downloads for ${serviceLabel(settingsSvc)}`} onchange={(event) => saveServiceDownloadOverride(settingsServiceId, { ...settingsServiceDownload, askEachDownload: event.currentTarget.checked })} />
                  <span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>
                </span>
              </label>
            {:else}
              <p class="desc download-inherited-copy">Inherited global directory: <strong>{downloadDirectoryLabel(appSettings.downloadDirectory)}</strong> · Ask each time: <strong>{appSettings.askEachDownload ? "On" : "Off"}</strong>. Workspace settings can override these values when this service is opened through that workspace.</p>
            {/if}
          </div>

          <div class="set-title">Appearance</div>
          <div class="setrow">
            <label class="row-toggle">
              <input
                type="checkbox"
                checked={serviceIconInverted(settingsServiceId)}
                onchange={(event) => saveServiceIconInversion(settingsServiceId, event.currentTarget.checked)}
              />
              <span>Invert service icon colors</span>
            </label>
            <p class="desc">Invert this service icon in Tauridium's UI so black or very dark artwork stays visible on Black OLED backgrounds. This affects only the icon, not the website.</p>
          </div>
          <ServiceToggle
            label={"Dark mode"}
            description={"Force a dark theme on this service (via Dark Reader). Reloads the service when changed."}
            settingKey={"isDarkModeEnabled"}
            checked={settingsSvc.isDarkModeEnabled === true}
            onsave={serviceEditor.saveSetting}
          />
          {#if settingsSvc.isDarkModeEnabled}
            <div class="setrow">
              <div class="num-row">
                <label>Brightness<input class="num" type="number" value={settingsSvc.darkReaderBrightness ?? 100} onchange={(e) => serviceEditor.saveNum("darkReaderBrightness", e.currentTarget.value)} /></label>
                <label>Contrast<input class="num" type="number" value={settingsSvc.darkReaderContrast ?? 90} onchange={(e) => serviceEditor.saveNum("darkReaderContrast", e.currentTarget.value)} /></label>
                <label>Sepia<input class="num" type="number" value={settingsSvc.darkReaderSepia ?? 10} onchange={(e) => serviceEditor.saveNum("darkReaderSepia", e.currentTarget.value)} /></label>
              </div>
              <p class="desc">Dark Reader fine-tuning (applies to this service's dark mode).</p>
            </div>
          {/if}
          <ServiceToggle
            label={"Use website icon"}
            description={"Prefer this service's cached website icon over its recipe icon. Tauridium fetches it once and reuses the persistent local cache."}
            settingKey={"useFavicon"}
            checked={settingsSvc.useFavicon === true}
            onsave={serviceEditor.saveSetting}
          />
          <div class="setrow">
            <div><strong>Website icon cache</strong><p class="desc">Discard the cached result and fetch this service's current website icon again.</p></div>
            <button class="secondary sm" onclick={() => settingsSvc && loadServiceIcon(settingsSvc, true, true, true)}>Refetch icon</button>
          </div>
          <div class="setrow">
            <label class="block">
              Custom icon source URL
              <div class="workspace-icon-url-row">
                <input
                  bind:value={serviceEditor.serviceIconUrlDraft}
                  placeholder="example.com or https://example.com/path/icon.svg"
                  disabled={serviceEditor.serviceIconUrlBusy}
                  onkeydown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      void serviceEditor.assignServiceIconFromUrl();
                    }
                  }}
                />
                <button class="secondary sm" disabled={serviceEditor.serviceIconUrlBusy || !serviceEditor.serviceIconUrlDraft.trim()} onclick={serviceEditor.assignServiceIconFromUrl}>
                  {serviceEditor.serviceIconUrlBusy ? "Fetching…" : "Use icon"}
                </button>
              </div>
            </label>
            <p class="desc">Use an ordinary website URL to discover its icon, or a direct HTTP(S) image URL. Tauridium stores the compatible image in the persistent service-icon cache. Failed or incompatible sources are recorded in the Audit log and fall back to this service's default icon.</p>
          </div>
          <ServiceToggle
            label={"Progress bar"}
            description={"Service preference. Tauridium already shows a loading spinner per service."}
            settingKey={"isProgressbarEnabled"}
            checked={settingsSvc.isProgressbarEnabled === true}
            onsave={serviceEditor.saveSetting}
          />
          <div class="setrow">
            <label class="block">
              Custom user agent
              <input value={settingsSvc.userAgentPref ?? ""} placeholder="empty = app default" onchange={(e) => serviceEditor.saveText("userAgentPref", e.currentTarget.value, true)} />
            </label>
            <p class="desc">Per-service browser identity, overrides the global one. Reloads the service.</p>
          </div>

          {#if osKind === "win"}
            <div class="set-title">Windows browser privacy</div>
            {@const privacyNamespace = browserProfileNamespace(settingsServiceId, appSettings.serviceSandboxes)}
            <label class="download-setting-row setting-card-toggle">
              <span class="setting-copy">
                <strong>Reduce tracking prevention for sign-in compatibility</strong>
                <span class="desc">Off by default. Use only if an embedded sign-in challenge fails. Reduces privacy, not SmartScreen protection. Applies to {privacyNamespace.startsWith("sandbox:") ? "every service in this shared sandbox" : "this isolated service profile"}. Restart Tauridium after changing this setting.</span>
              </span>
              <span class="switch-control">
                <input class="switch-input" type="checkbox"
                  checked={ownValue(appSettings.trackingPreventionExceptions, privacyNamespace) === true}
                  disabled={serviceEditor.trackingPrivacyBusy || sandboxAssignmentBusy}
                  aria-label="Reduce Windows tracking prevention for this browser profile"
                  onclick={(event) => { event.preventDefault(); void saveTrackingException(settingsServiceId, ownValue(appSettings.trackingPreventionExceptions, privacyNamespace) !== true); }} />
                <span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>
              </span>
            </label>
          {/if}
          <div class="set-title">Proxy</div>
          <ServiceToggle
            label={"Use a proxy"}
            description={"Route this service through an HTTP/HTTPS proxy."}
            settingKey={"isProxyFeatureEnabled"}
            checked={settingsSvc.isProxyFeatureEnabled === true}
            onsave={serviceEditor.saveSetting}
          />
          {#if settingsSvc.isProxyFeatureEnabled}
            <div class="setrow">
              <div class="proxy-grid">
                <input placeholder="Host" value={settingsSvc.proxyHost ?? ""} onchange={(e) => serviceEditor.saveText("proxyHost", e.currentTarget.value)} />
                <input placeholder="Port" value={String(settingsSvc.proxyPort ?? "")} onchange={(e) => serviceEditor.saveText("proxyPort", e.currentTarget.value)} />
                <input placeholder="Username (optional)" value={settingsSvc.proxyUser ?? ""} onchange={(e) => serviceEditor.saveText("proxyUser", e.currentTarget.value)} />
                <input placeholder="Password (optional)" type="password" value={settingsSvc.proxyPassword ?? ""} onchange={(e) => serviceEditor.saveText("proxyPassword", e.currentTarget.value)} />
              </div>
            </div>
          {/if}

          {#if error}<p class="error">{error}</p>{/if}
          <div class="danger-zone">
            <div class="dz-row">
              <div>
                <strong>Clear cache & session</strong>
                <p class="dz-hint">Sign out of this service and wipe its cookies/storage from disk. The service stays in your list.</p>
              </div>
              <button class="danger sm" onclick={() => settingsSvc && handleClearCache(settingsSvc)}>
                Clear cache
              </button>
            </div>
            <div class="dz-row">
              <div>
                <strong>{settingsSvc.isEnabled === false ? "Enable service" : "Disable service"}</strong>
                <p class="dz-hint">{settingsSvc.isEnabled === false ? "Allow this web app to load again." : "Keep it in the list, but close it and prevent the web app from loading until re-enabled."}</p>
              </div>
              <button class:danger={settingsSvc.isEnabled !== false} class:secondary={settingsSvc.isEnabled === false} class="sm" onclick={() => settingsSvc && toggleServiceEnabled(settingsSvc)}>
                {settingsSvc.isEnabled === false ? "Enable" : "Disable"}
              </button>
            </div>
            <div class="dz-row">
              <div>
                <strong>Delete service</strong>
                <p class="dz-hint">Remove this service from your account and wipe its data.</p>
              </div>
              <button class="danger sm" onclick={() => settingsSvc && handleDelete(settingsSvc)}>
                Delete
              </button>
            </div>
          </div>
        </div>

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
  .error { color: #ff8a8a; font-size: 13px; margin: 4px 0; }
  .link { background: none; border: none; color: var(--link); cursor: pointer; font-size: 12px; text-decoration: underline; }
  .panel {
    width: min(560px, 90%); align-self: start; margin: 40px auto;
    background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 22px;
    display: flex; flex-direction: column; gap: 14px;
  }
  .panel-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  .head-actions { display: inline-flex; align-items: center; gap: 12px; }
  .primary.sm { padding: 6px 12px; font-size: 13px; }
  .panel-head h2 { margin: 0; font-size: 18px; }
  .recipe { color: var(--accent-soft); font-size: 12px; }
  .set-title { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted2); }
  .row-toggle { flex-direction: row; align-items: center; gap: 10px; color: var(--text2); font-size: 14px; cursor: pointer; }
  .row-toggle input { width: auto; }
  .setrow { display: flex; flex-direction: column; gap: 3px; }
  .desc { margin: 0 0 0 26px; color: var(--muted); font-size: 12px; line-height: 1.35; }
  .select {
    margin-left: auto; padding: 6px 9px; border-radius: 8px;
    border: 1px solid var(--border2); background: var(--input); color: var(--text); font-size: 13px;
  }
  .block { gap: 6px; }
  .num-row { display: flex; gap: 12px; }
  .num-row label { flex: 1; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
  .num { padding: 6px 8px; border-radius: 8px; border: 1px solid var(--border2); background: var(--input); color: var(--text); font-size: 13px; }
  .proxy-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .danger { margin-top: 6px; background: #3a2330; border: 1px solid #6e2b3e; color: #ff9aa8; border-radius: 8px; padding: 9px; cursor: pointer; }
  .danger:hover { filter: brightness(1.15); }
  .danger.sm { margin-top: 0; padding: 6px 12px; font-size: 13px; white-space: nowrap; align-self: center; }
  .danger-zone { margin-top: 16px; border: 1px solid #6e2b3e; border-radius: 10px; overflow: hidden; }
  .dz-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 14px; }
  .dz-row + .dz-row { border-top: 1px solid #6e2b3e; }
  .dz-row strong { font-size: 14px; }
  .dz-hint { margin: 3px 0 0; font-size: 12px; color: var(--muted); max-width: 380px; }
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
  .primary:focus-visible, .secondary:focus-visible, .select:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 2px;
  }
  .setting-copy { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .setting-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
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
  .workspace-avatar { width: 34px; height: 34px; display: grid; place-items: center; flex: none; border-radius: 8px; background: var(--hover); color: var(--text2); font-size: 13px; font-weight: 750; }
  .workspace-avatar-image { object-fit: contain; padding: 3px; box-sizing: border-box; }
  .workspace-icon-url-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 8px; width: 100%; }
  .pagination { display: flex; align-items: center; justify-content: center; gap: 10px; color: var(--muted); font-size: 12px; }
  .service-shortcut-policy { display: grid; grid-template-columns: minmax(0, 1fr) minmax(230px, 320px); align-items: start; gap: 8px 18px; }
  .service-shortcut-copy { min-width: 0; }
  .service-shortcut-policy .desc { margin-left: 0; }
  .service-shortcut-policy .select { width: 100%; min-width: 0; max-width: none; margin-left: 0; }
  .service-shortcut-effective { grid-column: 1 / -1; margin-top: 0; }
  .service-workspace-manager { display: flex; flex-direction: column; gap: 12px; padding: 14px; border: 1px solid var(--border); border-radius: 10px; background: color-mix(in srgb, var(--panel) 88%, var(--bg)); }
  .service-sandbox-manager { gap: 8px; }
  .service-sandbox-manager .service-workspace-overview { align-items: center; }
  .service-sandbox-help { margin: 0; }
  .service-download-manager { gap: 10px; }
  .download-override-toggle { width: fit-content; max-width: 100%; }
  .download-setting-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 12px; width: 100%; box-sizing: border-box; padding: 10px 0 0; border-top: 1px solid var(--border); }
  label.download-setting-row { cursor: pointer; }
  .download-setting-row .desc { margin-left: 0; }
  .download-inherited-copy { margin: 0; padding-top: 4px; }
  .service-workspace-overview { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
  .service-workspace-overview .setting-copy { min-width: 0; }
  .service-workspace-toolbar { display: flex; align-items: stretch; gap: 8px; }
  .service-workspace-search { min-width: 0; min-height: 40px; flex: 1 1 280px; box-sizing: border-box; }
  .service-workspace-search.service-sandbox-search { width: min(100%, 240px); max-width: 240px; min-height: 36px; flex: none; align-self: flex-start; margin: 0; }
  .service-workspace-filters { display: inline-grid; grid-template-columns: repeat(3, auto); align-items: stretch; flex: none; padding: 3px; border: 1px solid var(--border); border-radius: 9px; background: var(--input); }
  .service-workspace-filters button { min-height: 32px; padding: 5px 10px; border: 1px solid transparent; border-radius: 6px; background: transparent; color: var(--muted); cursor: pointer; font: inherit; font-size: 12px; font-weight: 650; white-space: nowrap; }
  .service-workspace-filters button:hover { background: var(--hover); color: var(--text2); }
  .service-workspace-filters button.active { border-color: var(--border2); background: var(--panel); color: var(--text); box-shadow: 0 1px 3px rgba(0, 0, 0, 0.14); }
  .service-workspace-filters button:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  .service-workspace-list { display: flex; flex-direction: column; gap: 4px; max-height: min(42vh, 460px); overflow-y: auto; overscroll-behavior: contain; margin: 0; padding: 4px; border: 1px solid var(--border); border-radius: 9px; background: var(--input); }
  .service-workspace-item { margin: 0; padding: 0; list-style: none; }
  .service-workspace-option { width: 100%; min-height: 54px; box-sizing: border-box; display: grid; grid-template-columns: 20px 34px minmax(0, 1fr) auto; align-items: center; gap: 10px; padding: 8px 10px; border: 1px solid transparent; border-radius: 7px; cursor: pointer; user-select: none; transition: background 0.12s ease, border-color 0.12s ease; }
  .service-workspace-option:hover { background: var(--hover); border-color: var(--border); }
  .service-workspace-option:focus-within { border-color: var(--accent); box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 62%, transparent); }
  .service-workspace-option.joined { border-color: color-mix(in srgb, var(--accent) 32%, var(--border)); background: color-mix(in srgb, var(--accent) 8%, var(--input)); }
  .service-workspace-option.busy { cursor: wait; opacity: 0.68; }
  .service-workspace-checkbox { width: 18px; height: 18px; margin: 0; accent-color: var(--accent); cursor: pointer; }
  .service-workspace-checkbox:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .service-workspace-checkbox:disabled { cursor: wait; }
  .service-workspace-avatar { width: 34px; height: 34px; border-radius: 8px; }
  .service-workspace-copy { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .service-workspace-copy strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text2); font-size: 13px; }
  .service-workspace-copy small { color: var(--muted); font-size: 11px; }
  .service-workspace-state { min-width: 74px; color: var(--muted); font-size: 11px; font-weight: 650; text-align: right; white-space: nowrap; }
  .service-workspace-option.joined .service-workspace-state { color: var(--text2); }
  .service-workspace-create-card { display: grid; grid-template-columns: minmax(0, 1fr) minmax(290px, 48%); align-items: center; gap: 14px; padding-top: 3px; border-top: 1px solid var(--border); }
  .service-workspace-create-card .setting-copy { padding-top: 9px; }
  .service-workspace-create { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: center; padding-top: 9px; }
  @media (max-width: 760px) {
    .setting-card-toggle { grid-template-columns: minmax(0, 1fr) auto; align-items: center; }
    .setting-actions { justify-content: flex-start; }
    .service-workspace-create, .service-workspace-create-card, .workspace-icon-url-row, .download-setting-row { grid-template-columns: 1fr; }
    .service-workspace-overview { flex-direction: column; }
    .service-workspace-toolbar { flex-direction: column; }
    .service-workspace-filters { width: 100%; grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .service-workspace-filters button { padding-inline: 6px; }
    .service-workspace-option { grid-template-columns: 20px 34px minmax(0, 1fr); }
    .service-workspace-state { display: none; }
    .service-shortcut-policy { grid-template-columns: 1fr; }
    .service-shortcut-effective { grid-column: auto; }
  }

</style>
