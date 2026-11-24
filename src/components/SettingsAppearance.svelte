<script lang="ts">

  import type { AppearanceController } from "../lib/controllers/appearance.svelte";
  import type { AppSettings, Service } from "../lib/api";
  import { renderTitleTemplate } from "../lib/title-template";
  import { serviceLabel } from "../lib/ui";
  import SettingsToggle from "./SettingsToggle.svelte";

  interface Props {
    appearance: AppearanceController;
    activeService: Service | null;
    activeWorkspaceName: string;
    appSettings: AppSettings;
    dockWord: "Dock" | "taskbar";
    previewServiceSpacing: (key: "collapsedServiceSpacing" | "expandedServiceSpacing", value: number, collapsed: boolean) => void;
    saveAppSetting: (key: keyof AppSettings, value: unknown) => Promise<void>;
    saveRestoreLastSidebarStateOnStartup: (enabled: boolean) => Promise<void>;
    saveServiceSpacing: (key: "collapsedServiceSpacing" | "expandedServiceSpacing", collapsed: boolean) => Promise<void>;
    syncSidebarWidth: () => void;
  }

  let {
    appearance,
    activeService,
    activeWorkspaceName,
    appSettings = $bindable(),
    dockWord,
    previewServiceSpacing,
    saveAppSetting,
    saveRestoreLastSidebarStateOnStartup,
    saveServiceSpacing,
    syncSidebarWidth,
  }: Props = $props();

</script>

<section class="settings-section" aria-labelledby="settings-appearance-app">
                <div class="section-heading">
                  <h3 id="settings-appearance-app">App appearance</h3>
                  <p>Choose the color scheme and accent used by Tauridium's own interface.</p>
                </div>
                <div class="settings-list">
                  <div class="setting-card" id="settings-option-theme">
                    <div class="setting-copy">
                      <span class="setting-label">Theme</span>
                      <span class="setting-description">Follow the operating system appearance or force Light, Dark, or true-black Black OLED mode.</span>
                    </div>
                    <select class="select setting-control" aria-label="Theme" bind:value={appSettings.theme} onchange={() => saveAppSetting("theme", appSettings.theme)}>
                      <option value="system">Use system setting</option>
                      <option value="dark">Dark</option>
                      <option value="oled">Black OLED</option>
                      <option value="light">Light</option>
                    </select>
                  </div>
                  <div class="setting-card setting-card-stack accent-setting-card" id="settings-option-accentColor">
                    <div class="setting-copy">
                      <span class="setting-label">Accent color</span>
                      <span class="setting-description">Used for selected navigation, primary actions, and active-service emphasis.</span>
                    </div>
                    <div class="accent-picker-control">
                      <div class="swatches" role="group" aria-label="Accent color presets">
                        {#each ["#ffc131", "#4f46e5", "#2563eb", "#0891b2", "#16a34a", "#d97706", "#dc2626", "#db2777", "#7c3aed"] as c (c)}
                          <button class="swatch" class:on={appSettings.accentColor === c} style="background:{c}" aria-label={`Use accent color ${c}`} aria-pressed={appSettings.accentColor === c} onclick={() => saveAppSetting("accentColor", c)}></button>
                        {/each}
                        {#each appSettings.customAccentColors as c (c)}
                          <span class="custom-swatch-wrap">
                            <button class="swatch" class:on={appSettings.accentColor === c} style="background:{c}" aria-label={`Use custom accent color ${c}`} aria-pressed={appSettings.accentColor === c} onclick={() => saveAppSetting("accentColor", c)}></button>
                            <button class="swatch-remove" aria-label={`Remove custom accent ${c}`} title="Remove preset" onclick={() => appearance.removeCustomAccent(c)}>×</button>
                          </span>
                        {/each}
                      </div>
                      <button class="secondary sm accent-custom-button" onclick={appearance.openCustomColorPicker}>Custom…</button>
                    </div>
                  </div>
                  {#if appearance.customColorOpen}
                    <div class="setting-card setting-card-stack color-picker-card" id="settings-option-customAccent">
                      <div class="setting-copy"><span class="setting-label">Custom accent</span><span class="setting-description">Use the platform color picker or adjust hue, saturation, and lightness with keyboard-accessible sliders.</span></div>
                      <div class="color-picker-preview-row">
                        <input type="color" value={appSettings.accentColor} aria-label="Custom accent native color picker" oninput={(event) => appearance.setCustomColorFromNative(event.currentTarget.value)} />
                        <code>{appSettings.accentColor}</code>
                        <span class="color-preview" style={`background:${appSettings.accentColor}`} aria-hidden="true"></span>
                      </div>
                      <label class="slider-field"><span>Hue <strong>{Math.round(appearance.colorHue)}°</strong></span><input type="range" min="0" max="359" value={appearance.colorHue} oninput={(event) => { appearance.colorHue = Number(event.currentTarget.value); appearance.previewCustomColor(); }} /></label>
                      <label class="slider-field"><span>Saturation <strong>{Math.round(appearance.colorSaturation)}%</strong></span><input type="range" min="0" max="100" value={appearance.colorSaturation} oninput={(event) => { appearance.colorSaturation = Number(event.currentTarget.value); appearance.previewCustomColor(); }} /></label>
                      <label class="slider-field"><span>Lightness <strong>{Math.round(appearance.colorLightness)}%</strong></span><input type="range" min="10" max="90" value={appearance.colorLightness} oninput={(event) => { appearance.colorLightness = Number(event.currentTarget.value); appearance.previewCustomColor(); }} /></label>
                      <div class="setting-actions"><button class="secondary sm" onclick={appearance.cancelCustomColorPicker}>Cancel</button><button class="secondary sm" onclick={() => appearance.applyCustomColor(false)}>Use color</button><button class="primary sm" onclick={() => appearance.applyCustomColor(true)}>Use & save preset</button></div>
                    </div>
                  {/if}
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-appearance-titles">
                <div class="section-heading">
                  <h3 id="settings-appearance-titles">Native titles</h3>
                  <p>Show workspace context in operating-system window and app-icon labels.</p>
                </div>
                <div class="settings-list">
                  <SettingsToggle
                    label={"Workspace in window title"}
                    description={"Show the selected workspace in the native title bar, for example Tauridium ~ Engineering."}
                    settingKey={"showWorkspaceInWindowTitle"}
                    checked={appSettings.showWorkspaceInWindowTitle}
                    onsave={saveAppSetting}
                  />
                  <SettingsToggle
                    label={"Workspace in taskbar title"}
                    description={`Use workspace context for a separately addressable ${dockWord} or app-icon label when the operating system exposes one. Windows taskbar buttons always mirror the native window title; independent taskbar titles are unsupported on Windows.`}
                    settingKey={"showWorkspaceInTaskbarTitle"}
                    checked={appSettings.showWorkspaceInTaskbarTitle}
                    onsave={saveAppSetting}
                  />
                  <SettingsToggle
                    label={"Custom title templates"}
                    description={"Enable variable-based title formats for the window title and taskbar/app-icon title. The two workspace-title toggles still decide which destinations use the custom format."}
                    settingKey={"customTitleTemplatesEnabled"}
                    checked={appSettings.customTitleTemplatesEnabled}
                    onsave={saveAppSetting}
                  />
                  {#if appSettings.customTitleTemplatesEnabled}
                    <div class="setting-card setting-card-stack" id="settings-option-windowTitleTemplate">
                      <div class="setting-copy">
                        <span class="setting-label">Window title template</span>
                        <span class="setting-description">Available variables: {"{app}"}, {"{workspace}"}, {"{service}"}. Unknown text is preserved literally.</span>
                      </div>
                      <input
                        class="input setting-text-input"
                        aria-label="Window title template"
                        maxlength="240"
                        bind:value={appSettings.windowTitleTemplate}
                        onchange={() => saveAppSetting("windowTitleTemplate", appSettings.windowTitleTemplate)}
                      />
                      <span class="settings-note">Preview: {renderTitleTemplate(appSettings.windowTitleTemplate, { app: "Tauridium", workspace: activeWorkspaceName, service: activeService ? serviceLabel(activeService) : "No service" })}</span>
                    </div>
                    <div class="setting-card setting-card-stack" id="settings-option-taskbarTitleTemplate">
                      <div class="setting-copy">
                        <span class="setting-label">Taskbar title template</span>
                        <span class="setting-description">Used where the OS exposes a separate taskbar/app-icon label. Windows taskbar buttons always mirror the native window title.</span>
                      </div>
                      <input
                        class="input setting-text-input"
                        aria-label="Taskbar title template"
                        maxlength="240"
                        bind:value={appSettings.taskbarTitleTemplate}
                        onchange={() => saveAppSetting("taskbarTitleTemplate", appSettings.taskbarTitleTemplate)}
                      />
                      <span class="settings-note">Preview: {renderTitleTemplate(appSettings.taskbarTitleTemplate, { app: "Tauridium", workspace: activeWorkspaceName, service: activeService ? serviceLabel(activeService) : "No service" })}</span>
                    </div>
                    <p class="settings-note">Variables: <code>{"{app}"}</code> application name, <code>{"{workspace}"}</code> selected workspace (or All services), <code>{"{service}"}</code> active service (or No service).</p>
                  {/if}
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-appearance-sidebar">
                <div class="section-heading">
                  <h3 id="settings-appearance-sidebar">Sidebar</h3>
                  <p>Adjust service density and placement without changing individual service configuration.</p>
                </div>
                <div class="settings-list">
                  <SettingsToggle
                    label={"Collapse sidebar"}
                    description={"Use the compact icon-only rail now. The expanded width is preserved and restored when reopened. Default shortcut: Ctrl+Shift+B."}
                    settingKey={"sidebarCollapsed"}
                    checked={appSettings.sidebarCollapsed}
                    onsave={saveAppSetting}
                  />
                  <div class="setting-card" id="settings-option-sidebarStartupCollapsed">
                    <div class="setting-copy">
                      <span class="setting-label">Default sidebar state</span>
                      <span class="setting-description">Used at startup when restoring the last sidebar state is disabled.</span>
                    </div>
                    <select
                      class="select setting-control"
                      aria-label="Default sidebar state"
                      value={appSettings.defaultSidebarCollapsed ? "collapsed" : "expanded"}
                      onchange={(event) => saveAppSetting("defaultSidebarCollapsed", event.currentTarget.value === "collapsed")}
                    >
                      <option value="expanded">Expanded</option>
                      <option value="collapsed">Collapsed</option>
                    </select>
                  </div>
                  <label class="setting-card setting-card-toggle" id="settings-option-restoreLastSidebarState">
                    <span class="setting-copy">
                      <span class="setting-label">Restore last sidebar state on startup</span>
                      <span class="setting-description">Start with the sidebar state used most recently. When enabled, this takes precedence over the default sidebar state.</span>
                    </span>
                    <span class="switch-control">
                      <input
                        class="switch-input"
                        type="checkbox"
                        checked={appSettings.restoreLastSidebarStateOnStartup}
                        aria-label="Restore last sidebar state on startup"
                        onchange={(event) => saveRestoreLastSidebarStateOnStartup(event.currentTarget.checked)}
                      />
                      <span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>
                    </span>
                  </label>
                  <div class="setting-card setting-card-stack" id="settings-option-sidebarWidth">
                    <div class="setting-copy"><span class="setting-label">Expanded sidebar width</span><span class="setting-description">Use a fixed pixel width or keep the expanded sidebar proportional to the Tauridium window. Collapsed mode uses a fixed 52 px rail for consistent icon alignment.</span></div>
                    <select class="select setting-control" aria-label="Sidebar width mode" value={appSettings.sidebarWidthMode} onchange={(event) => saveAppSetting("sidebarWidthMode", event.currentTarget.value)}>
                      <option value="pixels">Fixed pixels</option>
                      <option value="percent">Relative to window</option>
                    </select>
                    {#if appSettings.sidebarWidthMode === "pixels"}
                      <div class="sidebar-width-control">
                        <input class="range" type="range" min="160" max="420" step="2" value={appSettings.sidebarWidth} aria-label="Sidebar width in pixels" oninput={(event) => appearance.previewSidebarWidth(Number(event.currentTarget.value))} onchange={() => saveAppSetting("sidebarWidth", appSettings.sidebarWidth)} />
                        <output>{Math.round(appSettings.sidebarWidth)} px</output>
                      </div>
                      <div class="preset-row" role="group" aria-label="Sidebar width presets">
                        <button class="secondary sm" class:on={appSettings.sidebarWidth === 180} onclick={() => saveAppSetting("sidebarWidth", 180)}>Slim · 180</button>
                        <button class="secondary sm" class:on={appSettings.sidebarWidth === 240} onclick={() => saveAppSetting("sidebarWidth", 240)}>Normal · 240</button>
                        <button class="secondary sm" class:on={appSettings.sidebarWidth === 320} onclick={() => saveAppSetting("sidebarWidth", 320)}>Wide · 320</button>
                        {#each appSettings.customSidebarWidths as width (width)}
                          <span class="preset-chip"><button class="secondary sm" class:on={appSettings.sidebarWidth === width} onclick={() => saveAppSetting("sidebarWidth", width)}>{width} px</button><button class="preset-remove" aria-label={`Remove ${width} pixel sidebar preset`} onclick={() => appearance.removeSidebarPreset(width)}>×</button></span>
                        {/each}
                        <button class="secondary sm" disabled={[180, 240, 320, ...appSettings.customSidebarWidths].includes(Math.round(appSettings.sidebarWidth))} onclick={appearance.saveCurrentSidebarPreset}>Save current preset</button>
                      </div>
                    {:else}
                      <div class="sidebar-width-control">
                        <input class="range" type="range" min="10" max="40" step="1" value={appSettings.sidebarWidthPercent} aria-label="Sidebar width as percentage of window" oninput={(event) => { appSettings.sidebarWidthPercent = Number(event.currentTarget.value); syncSidebarWidth(); }} onchange={() => saveAppSetting("sidebarWidthPercent", appSettings.sidebarWidthPercent)} />
                        <output>{Math.round(appSettings.sidebarWidthPercent)}%</output>
                      </div>
                      <p class="settings-note">Relative mode recalculates the service viewport while the window is resized. Updates are animation-frame throttled to avoid unnecessary layout work.</p>
                    {/if}
                  </div>
                  <div class="setting-card setting-card-stack" id="settings-option-collapsedIconSpacing">
                    <div class="setting-copy"><span class="setting-label">Collapsed icon spacing</span><span class="setting-description">Increase the vertical space between icon-only service targets. The current compact 2 px spacing is the minimum.</span></div>
                    <div class="sidebar-width-control">
                      <input class="range" type="range" min="2" max="24" step="1" value={appSettings.collapsedServiceSpacing} aria-label="Collapsed service icon spacing" oninput={(event) => previewServiceSpacing("collapsedServiceSpacing", Number(event.currentTarget.value), true)} onchange={() => saveServiceSpacing("collapsedServiceSpacing", true)} />
                      <output>{Math.round(appSettings.collapsedServiceSpacing)} px</output>
                    </div>
                  </div>
                  <div class="setting-card setting-card-stack" id="settings-option-expandedServiceSpacing">
                    <div class="setting-copy"><span class="setting-label">Expanded service spacing</span><span class="setting-description">Increase the vertical space between service rows in the expanded sidebar. The current compact 2 px spacing is the minimum.</span></div>
                    <div class="sidebar-width-control">
                      <input class="range" type="range" min="2" max="24" step="1" value={appSettings.expandedServiceSpacing} aria-label="Expanded service item spacing" oninput={(event) => previewServiceSpacing("expandedServiceSpacing", Number(event.currentTarget.value), false)} onchange={() => saveServiceSpacing("expandedServiceSpacing", false)} />
                      <output>{Math.round(appSettings.expandedServiceSpacing)} px</output>
                    </div>
                  </div>
                  <div class="setting-card" id="settings-option-iconSize">
                    <div class="setting-copy"><span class="setting-label">Service icon size</span><span class="setting-description">Change icon size while preserving consistent sidebar spacing.</span></div>
                    <select class="select setting-control" aria-label="Service icon size" bind:value={appSettings.iconSize} onchange={() => saveAppSetting("iconSize", appSettings.iconSize)}>
                      <option value={18}>Very small</option><option value={21}>Small</option><option value={24}>Normal</option><option value={28}>Large</option><option value={34}>Very large</option>
                    </select>
                  </div>
                  <div class="setting-card" id="settings-option-serviceListAlignment">
                    <div class="setting-copy"><span class="setting-label">Service list alignment</span><span class="setting-description">Align the service list to the top, center, or bottom of the sidebar.</span></div>
                    <select class="select setting-control" aria-label="Service list alignment" bind:value={appSettings.sidebarServicesLocation} onchange={() => saveAppSetting("sidebarServicesLocation", appSettings.sidebarServicesLocation)}>
                      <option value="top">Top</option><option value="center">Center</option><option value="bottom">Bottom</option>
                    </select>
                  </div>
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-appearance-icons">
                <div class="section-heading"><h3 id="settings-appearance-icons">Service icons</h3><p>Reduce visual noise while keeping the active service easy to identify.</p></div>
                <div class="settings-list">
                  <SettingsToggle
                    label={"Grayscale inactive icons"}
                    description={"Show service icons in grayscale until they are hovered or active."}
                    settingKey={"grayscaleServices"}
                    checked={appSettings.grayscaleServices}
                    onsave={saveAppSetting}
                  />
                  {#if appSettings.grayscaleServices}
                    <div class="setting-card" id="settings-option-inactiveIconDimming">
                      <div class="setting-copy"><span class="setting-label">Inactive icon dimming</span><span class="setting-description">Control how strongly inactive grayscale icons are dimmed.</span></div>
                      <div class="range-control"><input class="range" type="range" min="0" max="100" value={appSettings.grayscaleDim} aria-label="Inactive icon dimming" onchange={(e) => saveAppSetting("grayscaleDim", Number(e.currentTarget.value))} /><span>{appSettings.grayscaleDim}%</span></div>
                    </div>
                  {/if}
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
  .primary.sm { padding: 6px 12px; font-size: 13px; }
  .select {
    margin-left: auto; padding: 6px 9px; border-radius: 8px;
    border: 1px solid var(--border2); background: var(--input); color: var(--text); font-size: 13px;
  }
  .range { margin-left: auto; width: 130px; accent-color: var(--accent); }
  .swatches { margin-left: auto; display: inline-flex; gap: 7px; }
  .swatch {
    width: 22px; height: 22px; border-radius: 999px; border: none; padding: 0; cursor: pointer;
  }
  .swatch.on { outline: 2px solid var(--text); outline-offset: 2px; }
  .secondary { padding: 9px 12px; border: 1px solid var(--border2); border-radius: 8px; background: var(--input); color: var(--text2); font-weight: 600; cursor: pointer; }
  .secondary:hover { background: var(--hover); border-color: var(--accent); }
  .secondary:disabled { opacity: 0.55; cursor: default; }
  .secondary.sm { padding: 6px 10px; font-size: 12px; }
  .setting-card:focus-visible, .primary:focus-visible, .secondary:focus-visible, .select:focus-visible, .setting-text-input:focus-visible, .swatch:focus-visible {
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
  :global(.settings-panel) .swatches { margin-left: 0; justify-content: flex-end; flex-wrap: wrap; max-width: 250px; }
  .accent-setting-card { align-items: stretch; }
  .accent-picker-control { display: flex; align-items: center; justify-content: space-between; gap: 14px; width: 100%; }
  .accent-picker-control .swatches { flex: 1 1 auto; justify-content: flex-start; max-width: none; }
  .accent-custom-button { flex: 0 0 auto; min-width: 92px; }
  :global(.settings-panel) .swatch { width: 24px; height: 24px; border: 1px solid rgba(255,255,255,0.18); }
  .range-control { display: flex; align-items: center; gap: 10px; color: var(--muted); font-size: 12px; min-width: 180px; }
  :global(.settings-panel) .range { width: 140px; margin-left: 0; }
  .custom-swatch-wrap { position: relative; display: inline-flex; align-items: center; }
  .swatch-remove { position: absolute; top: -8px; right: -8px; width: 18px; height: 18px; display: grid; place-items: center; padding: 0; border: 1px solid var(--border2); border-radius: 999px; background: var(--panel); color: var(--muted); cursor: pointer; font-size: 12px; line-height: 1; }
  .swatch-remove:hover, .preset-remove:hover { color: var(--text); background: var(--hover); }
  .color-picker-card { gap: 12px; }
  .color-picker-preview-row { display: grid; grid-template-columns: 48px minmax(100px, 1fr) 38px; align-items: center; gap: 10px; }
  .color-picker-preview-row input[type="color"] { width: 48px; height: 38px; padding: 2px; border-radius: 8px; cursor: pointer; }
  .color-picker-preview-row code { color: var(--text2); font: 12px ui-monospace, SFMono-Regular, Consolas, monospace; }
  .color-preview { width: 34px; height: 34px; border: 1px solid var(--border2); border-radius: 8px; }
  .slider-field { display: grid; grid-template-columns: 112px minmax(140px, 1fr); align-items: center; gap: 10px; color: var(--muted); }
  .slider-field > span { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; }
  .slider-field strong { color: var(--text2); font-variant-numeric: tabular-nums; }
  .slider-field input[type="range"] { width: 100%; margin: 0; accent-color: var(--accent); }
  .sidebar-width-control { display: grid; grid-template-columns: minmax(160px, 1fr) 72px; align-items: center; gap: 12px; }
  .sidebar-width-control .range { width: 100%; margin: 0; }
  .sidebar-width-control output { color: var(--text2); font-size: 12px; font-variant-numeric: tabular-nums; text-align: right; }
  .preset-row { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }
  .preset-chip { min-height: 30px; display: inline-flex; align-items: center; gap: 6px; padding: 4px 8px; border: 1px solid var(--border2); border-radius: 999px; background: var(--input); color: var(--text2); }
  .preset-chip button { min-height: 24px; }
  .preset-chip .secondary { border: none; background: transparent; padding: 2px 4px; color: var(--text2); }
  .preset-remove { min-width: 24px; padding: 0; border: none; background: transparent; color: var(--muted); cursor: pointer; }
  @media (max-width: 760px) {
    .setting-card { grid-template-columns: 1fr; gap: 10px; align-items: stretch; }
    .setting-card-toggle { grid-template-columns: minmax(0, 1fr) auto; align-items: center; }
    .setting-control { width: 100%; max-width: none; }
    .setting-actions { justify-content: flex-start; }
    :global(.settings-panel) .swatches { justify-content: flex-start; max-width: none; }
    .range-control { min-width: 0; }
    :global(.settings-panel) .range { flex: 1; width: auto; }
    .color-picker-preview-row { grid-template-columns: 48px minmax(0, 1fr); }
    .color-preview { display: none; }
    .slider-field { grid-template-columns: 1fr; gap: 5px; }
    .sidebar-width-control { grid-template-columns: 1fr auto; }
  }

</style>
