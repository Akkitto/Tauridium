<script lang="ts">

  import type { AppSettings, DistributionInfo, MeUser } from "../lib/api";
  import { downloadDirectoryLabel } from "../lib/settingsMaps";
  import SettingsToggle from "./SettingsToggle.svelte";

  interface Props {
    appSettings: AppSettings;
    chooseGlobalDownloadDirectory: () => Promise<void>;
    distributionInfo: DistributionInfo;
    downloadToastExample: string | null;
    downloadToastSettingsBusy: boolean;
    me: MeUser;
    osKind: "mac" | "win" | "linux";
    refetchAllServiceIcons: () => Promise<void>;
    saveAppSetting: (key: keyof AppSettings, value: unknown) => Promise<void>;
    saveDownloadToastParentLevels: (event: Event) => void;
    saveDownloadToastSetting: <K extends "downloadToasts" | "downloadToastLocation" | "downloadToastParentLevels" | "downloadToastDuration">(key: K, value: AppSettings[K]) => Promise<void>;
    saveUnifiedTitleBar: (value: boolean) => Promise<void>;
    server: string;
    unifiedTitleBarAtStartup: boolean | null;
    unifiedTitleBarBusy: boolean;
    unifiedTitleBarFallback: boolean;
  }

  let {
    appSettings,
    chooseGlobalDownloadDirectory,
    distributionInfo,
    downloadToastExample,
    downloadToastSettingsBusy,
    me,
    osKind,
    refetchAllServiceIcons,
    saveAppSetting,
    saveDownloadToastParentLevels,
    saveDownloadToastSetting,
    saveUnifiedTitleBar,
    server,
    unifiedTitleBarAtStartup,
    unifiedTitleBarBusy,
    unifiedTitleBarFallback,
  }: Props = $props();

</script>

{#if osKind === "win"}
                <section class="settings-section" aria-labelledby="settings-advanced-titlebar">
                  <div class="section-heading"><h3 id="settings-advanced-titlebar">Window title bar</h3><p>Keep application menus and the window title in one row, with Windows' native window controls.</p></div>
                  <div class="settings-list">
                    <label class="setting-card setting-card-toggle" id="settings-option-unifiedTitleBar">
                      <span class="setting-copy"><span class="setting-label">Unified title bar</span><span class="setting-description">Enabled by default on Windows. Disable to restore the classic title bar with the separate native menu bar used before 1.0.7. Quit and reopen Tauridium to apply this preference; closing to the tray does not restart the app.</span></span>
                      <span class="switch-control">
                        <input class="switch-input" type="checkbox" checked={appSettings.unifiedTitleBar} disabled={unifiedTitleBarBusy} aria-label="Unified title bar" onchange={(event) => saveUnifiedTitleBar(event.currentTarget.checked)} />
                        <span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>
                      </span>
                    </label>
                    {#if unifiedTitleBarAtStartup !== null && appSettings.unifiedTitleBar !== unifiedTitleBarAtStartup}
                      <p class="settings-note" role="status">Saved preference: {appSettings.unifiedTitleBar ? "unified" : "classic"}. Quit and reopen Tauridium to apply.</p>
                    {/if}
                    {#if unifiedTitleBarFallback}<p class="settings-note" role="status">The unified title bar could not be enabled for this session. Tauridium is using the classic layout so all window controls remain available.</p>{/if}
                  </div>
                </section>
              {/if}
              <section class="settings-section" aria-labelledby="settings-advanced-context-menu">
                <div class="section-heading"><h3 id="settings-advanced-context-menu">Service context menu</h3><p>Choose Tauridium's styled menu or the native system menu. Both stay above service webviews.</p></div>
                <div class="settings-list">
                  <SettingsToggle
                    label={"Use original service context menu"}
                    description={"Enabled by default. Keeps Tauridium's styled right-click menu above embedded services. Disable this to use the native system menu."}
                    settingKey={"prettyServiceContextMenu"}
                    checked={appSettings.prettyServiceContextMenu}
                    onsave={saveAppSetting}
                  />
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-advanced-sidebar-order">
                <div class="section-heading"><h3 id="settings-advanced-sidebar-order">Sidebar service ordering</h3><p>Control whether services can be rearranged directly from the sidebar.</p></div>
                <div class="settings-list">
                  <SettingsToggle
                    label={"Drag to reorder services"}
                    description={"Enabled by default. Drag a service to another position in the sidebar to update Tauridium's canonical service order. Workspace filtering and hidden disabled services keep their underlying slots stable. Disable this to make sidebar service rows non-draggable; the accessible move controls in Settings → Services remain available."}
                    settingKey={"sidebarServiceDragReorder"}
                    checked={appSettings.sidebarServiceDragReorder}
                    onsave={saveAppSetting}
                  />
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-advanced-shortcuts">
                <div class="section-heading"><h3 id="settings-advanced-shortcuts">Keyboard shortcut priority</h3><p>Control whether Tauridium shortcuts continue to work while a service website has keyboard focus.</p></div>
                <div class="settings-list">
                  <SettingsToggle
                    label={"Capture Tauridium shortcuts inside services"}
                    description={"Enabled by default. Matching configured Tauridium shortcuts are intercepted before the focused website. Normal typing remains untouched unless explicitly assigned as a Tauridium shortcut. Disable this if websites should receive matching shortcuts by default. Individual services can override this in Service Settings."}
                    settingKey={"captureServiceShortcuts"}
                    checked={appSettings.captureServiceShortcuts}
                    onsave={saveAppSetting}
                  />
                  <p class="settings-note">Changing this setting recreates open service webviews so the keyboard policy applies immediately while preserving their persistent sessions.</p>
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-advanced-downloads">
                <div class="section-heading"><h3 id="settings-advanced-downloads">Downloads</h3><p>Choose where websites save downloads. Tauridium preserves the filename suggested by the website or server, including attachment names and extensions.</p></div>
                <div class="settings-list">
                  {#if distributionInfo.downloadsRequireDestination}
                    <div class="setting-card info-card">
                      <div class="setting-copy"><span class="setting-label">Portal-selected destination</span><span class="setting-description">Flatpak asks where to save every download through the desktop file portal. Tauridium does not receive broad access to your home directory or Downloads folder.</span></div>
                      <span class="status-badge">Portal</span>
                    </div>
                  {:else}
                    <div class="setting-card" id="settings-option-downloadDirectory">
                      <div class="setting-copy">
                        <span class="setting-label">Default download directory</span>
                        <span class="setting-description" title={downloadDirectoryLabel(appSettings.downloadDirectory)}>{downloadDirectoryLabel(appSettings.downloadDirectory)}</span>
                      </div>
                      <div class="setting-actions">
                        <button class="secondary sm" onclick={chooseGlobalDownloadDirectory}>Choose folder…</button>
                        <button class="secondary sm" disabled={!appSettings.downloadDirectory} onclick={() => saveAppSetting("downloadDirectory", "")}>Use system Downloads</button>
                      </div>
                    </div>
                    <SettingsToggle
                      label={"Ask where to save each download"}
                      description={"Show a native Save dialog for every download. The dialog starts with the website/server-suggested filename and the effective download directory."}
                      settingKey={"askEachDownload"}
                      checked={appSettings.askEachDownload}
                      onsave={saveAppSetting}
                    />
                    <p class="settings-note">Priority: service override → active workspace override → these global defaults. Directory overrides are device-specific settings and full backups preserve them; portable workspace exports intentionally omit filesystem paths.</p>
                  {/if}
                  <label class="setting-card setting-card-toggle" id="settings-option-downloadToasts">
                    <span class="setting-copy"><span class="setting-label">Show download completion toasts</span><span class="setting-description">Show a non-interrupting notification at the bottom of the window after a website download succeeds. Applies to every service and workspace; off by default.</span></span>
                    <span class="switch-control"><input class="switch-input" type="checkbox" checked={appSettings.downloadToasts} disabled={downloadToastSettingsBusy} aria-label="Show download completion toasts" onchange={(event) => saveDownloadToastSetting("downloadToasts", event.currentTarget.checked)} /><span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span></span>
                  </label>
                  <fieldset class="download-toast-options" disabled={!appSettings.downloadToasts || downloadToastSettingsBusy}>
                    <legend>Download notification details</legend>
                    <label class="setting-card" id="settings-option-downloadToastLocation">
                      <span class="setting-copy"><span class="setting-label">Saved location</span><span class="setting-description">Filename only keeps local paths private. Folder name shows just the destination folder; full and partial paths include the filename.</span></span>
                      <select class="select setting-control" value={appSettings.downloadToastLocation} aria-label="Download notification saved location" onchange={(event) => { const value = event.currentTarget.value; if (value === "none" || value === "directory" || value === "full" || value === "partial") void saveDownloadToastSetting("downloadToastLocation", value); }}>
                        <option value="none">Filename only</option><option value="directory">Destination folder name</option><option value="full">Full file path</option><option value="partial">Partial file path</option>
                      </select>
                    </label>
                    {#if appSettings.downloadToastLocation === "partial"}
                      <label class="setting-card" id="settings-option-downloadToastParentLevels">
                        <span class="setting-copy"><span class="setting-label">Parent folders to show</span><span class="setting-description">Show the nearest 1–10 parent folders and the filename. Omitted ancestors are marked with an ellipsis; 2 shows, for example, Downloads/Reports/example.pdf.</span></span>
                        <input class="num setting-control" type="number" min="1" max="10" step="1" value={appSettings.downloadToastParentLevels} aria-label="Download notification parent folders" onchange={saveDownloadToastParentLevels} />
                      </label>
                    {/if}
                    <label class="setting-card" id="settings-option-downloadToastDuration">
                      <span class="setting-copy"><span class="setting-label">Display time</span><span class="setting-description">The timer pauses while hovered, keyboard-focused, or Tauridium is in the background. Multiple downloads queue; every toast can be dismissed.</span></span>
                      <select class="select setting-control" value={appSettings.downloadToastDuration} aria-label="Download notification display time" onchange={(event) => { const value = Number(event.currentTarget.value); if (value === 0 || value === 8 || value === 15 || value === 30) void saveDownloadToastSetting("downloadToastDuration", value); }}>
                        <option value={8}>8 seconds</option><option value={15}>15 seconds</option><option value={30}>30 seconds</option><option value={0}>Until dismissed</option>
                      </select>
                    </label>
                    <div class="download-toast-preview"><span>Example: Download complete — example.pdf</span>{#if downloadToastExample}<code>{appSettings.downloadToastLocation === "directory" ? "Folder" : "Saved to"}: {downloadToastExample}</code>{/if}</div>
                  </fieldset>
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-advanced-browser">
                <div class="section-heading"><h3 id="settings-advanced-browser">Browser identity</h3><p>Advanced compatibility controls for services that depend on browser identification.</p></div>
                <div class="settings-list">
                  <div class="setting-card setting-card-stack" id="settings-option-userAgentPref">
                    <div class="setting-copy"><span class="setting-label">Custom user agent</span><span class="setting-description">Override the browser identity sent to newly opened services. Restart Tauridium to apply it everywhere.</span></div>
                    <input class="setting-text-input" value={appSettings.userAgentPref} aria-label="Custom user agent" placeholder="Leave empty to use the app default" onchange={(e) => saveAppSetting("userAgentPref", e.currentTarget.value)} />
                  </div>
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-advanced-service-icons">
                <div class="section-heading"><h3 id="settings-advanced-service-icons">Service icons</h3><p>Control durable website-icon discovery and refresh.</p></div>
                <div class="settings-list">
                  <SettingsToggle
                    label={"Fetch preferred website icons automatically"}
                    description={"For services with Use website icon enabled, fetch the website icon once and keep it in Tauridium's persistent cache. Services that do not prefer website icons are never fetched automatically."}
                    settingKey={"fetchMissingServiceIcons"}
                    checked={appSettings.fetchMissingServiceIcons}
                    onsave={saveAppSetting}
                  />
                  <div class="setting-card" id="settings-option-refetchIcons">
                    <div class="setting-copy"><span class="setting-label">Refetch preferred website icons</span><span class="setting-description">Refresh only services whose Use website icon preference is enabled. Recipe-icon services are left untouched.</span></div>
                    <button class="secondary sm" onclick={refetchAllServiceIcons}>Refetch all…</button>
                  </div>
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-advanced-url-templates">
                <div class="section-heading"><h3 id="settings-advanced-url-templates">Custom URL placeholders</h3><p>Opt in to reusable values inside service Custom URLs.</p></div>
                <div class="settings-list">
                  <SettingsToggle
                    label={"Enable custom URL placeholders for all services"}
                    description={"Allow {{custom_id_1}} and {{custom_id_2}} replacement in every service Custom URL. Disabled by default; individual services can opt in instead."}
                    settingKey={"customUrlTemplatesEnabled"}
                    checked={appSettings.customUrlTemplatesEnabled}
                    onsave={saveAppSetting}
                  />
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-advanced-feedback">
                <div class="section-heading"><h3 id="settings-advanced-feedback">Feedback</h3></div>
                <div class="settings-list">
                  <SettingsToggle
                    label={"Show reload notifications"}
                    description={"Show a brief toast after a service is reloaded from a keybinding or the service context menu."}
                    settingKey={"reloadToasts"}
                    checked={appSettings.reloadToasts}
                    onsave={saveAppSetting}
                  />
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-advanced-account">
                <div class="section-heading"><h3 id="settings-advanced-account">{me.local ? "Account" : "Server"}</h3></div>
                <div class="settings-list">
                  <div class="setting-card info-card">
                    <div class="setting-copy"><span class="setting-label">{me.local ? "Local mode" : me.email}</span><span class="setting-description">{me.local ? "Services and workspaces are stored on this device without a Ferdium account." : `Connected to ${server}. Sign out to change the server.`}</span></div>
                    <span class="status-badge">{me.local ? "Local" : "Connected"}</span>
                  </div>
                </div>
              </section>

<style>

  button, input, select { font-family: inherit; }
  label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); }
  input {
    padding: 9px 11px; border-radius: 8px; border: 1px solid var(--border2);
    background: var(--input); color: var(--text); font-size: 14px;
  }
  .select {
    margin-left: auto; padding: 6px 9px; border-radius: 8px;
    border: 1px solid var(--border2); background: var(--input); color: var(--text); font-size: 13px;
  }
  .num { padding: 6px 8px; border-radius: 8px; border: 1px solid var(--border2); background: var(--input); color: var(--text); font-size: 13px; }
  .secondary { padding: 9px 12px; border: 1px solid var(--border2); border-radius: 8px; background: var(--input); color: var(--text2); font-weight: 600; cursor: pointer; }
  .secondary:hover { background: var(--hover); border-color: var(--accent); }
  .secondary:disabled { opacity: 0.55; cursor: default; }
  .secondary.sm { padding: 6px 10px; font-size: 12px; }
  .setting-card:focus-visible, .secondary:focus-visible, .select:focus-visible, .setting-text-input:focus-visible {
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
  .settings-note { margin: 0 2px; color: var(--muted); font-size: 12px; line-height: 1.45; }
  .info-card { min-height: 72px; }
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
  :global(.settings-panel) .secondary { min-height: 34px; display: inline-flex; align-items: center; justify-content: center; }
  :global(.settings-panel) .secondary.sm { min-height: 30px; }
  .download-toast-options { display: grid; gap: 10px; min-width: 0; margin: 0; padding: 0; border: 0; }
  .download-toast-options > legend { padding: 0 0 8px; color: var(--muted); font-size: 12px; }
  .download-toast-options:disabled { opacity: .6; }
  .download-toast-options .select {
    appearance: none; padding-right: 30px;
    background-image: linear-gradient(45deg, transparent 50%, var(--text) 50%), linear-gradient(135deg, var(--text) 50%, transparent 50%);
    background-position: calc(100% - 14px) 50%, calc(100% - 10px) 50%;
    background-size: 4px 4px; background-repeat: no-repeat;
  }
  .download-toast-preview { display: grid; gap: 5px; padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px; font-size: 12px; color: var(--muted); }
  .download-toast-preview code { overflow-wrap: anywhere; white-space: pre-wrap; color: var(--text); }
  @media (max-width: 760px) {
    .setting-card { grid-template-columns: 1fr; gap: 10px; align-items: stretch; }
    .setting-card-toggle { grid-template-columns: minmax(0, 1fr) auto; align-items: center; }
    .setting-control { width: 100%; max-width: none; }
    .setting-actions { justify-content: flex-start; }
  }

</style>
