<script lang="ts">

  import type { AppSettings } from "../lib/api";
  import { DEFAULT_KEYBINDINGS } from "../lib/ui";
  import { KEYBINDING_SETTINGS } from "../lib/settingsSearch";
  import { bindingStrokes } from "../lib/ui";

  interface Props {
    appSettings: AppSettings;
    beginRecording: (action: "quickWorkspaceSwitch" | "quickServiceSwitch" | "openSettings" | "addService" | "addWorkspace" | "toggleSidebar" | "nextService" | "previousService" | "nextWorkspace" | "previousWorkspace" | "reloadService" | "reloadApp" | "zoomIn" | "zoomOut" | "resetZoom" | "toggleDevtools") => void;
    keybindingConflicts: Map<string, string[]>;
    recordingAction: "quickWorkspaceSwitch" | "quickServiceSwitch" | "openSettings" | "addService" | "addWorkspace" | "toggleSidebar" | "nextService" | "previousService" | "nextWorkspace" | "previousWorkspace" | "reloadService" | "reloadApp" | "zoomIn" | "zoomOut" | "resetZoom" | "toggleDevtools" | null;
    recordingStrokes: string[];
    saveAppSetting: (key: keyof AppSettings, value: unknown) => Promise<void>;
    saveKeybinding: (action: "quickWorkspaceSwitch" | "quickServiceSwitch" | "openSettings" | "addService" | "addWorkspace" | "toggleSidebar" | "nextService" | "previousService" | "nextWorkspace" | "previousWorkspace" | "reloadService" | "reloadApp" | "zoomIn" | "zoomOut" | "resetZoom" | "toggleDevtools", binding: string) => Promise<void>;
  }

  let {
    appSettings,
    beginRecording,
    keybindingConflicts,
    recordingAction,
    recordingStrokes,
    saveAppSetting,
    saveKeybinding,
  }: Props = $props();

</script>

<section class="settings-section" aria-labelledby="settings-keybindings-main">
                <div class="section-heading"><h3 id="settings-keybindings-main">Keybindings</h3><p>Customize application navigation. Bindings may be a single shortcut or a two-stroke chord such as Ctrl+K Ctrl+S. Letter keys are shown as uppercase key labels; Shift is required only when <strong>Shift</strong> is explicitly present. Press Delete while recording to clear a binding.</p></div>
                <div class="settings-list keybinding-list">
                  {#each KEYBINDING_SETTINGS as [action, label, description] (action)}
                    {@const binding = appSettings.keybindings[action] ?? ""}
                    {@const conflict = keybindingConflicts.get(bindingStrokes(binding).join(" "))}
                    <div class="setting-card keybinding-card" id={`settings-option-keybinding-${action}`}>
                      <div class="setting-copy"><span class="setting-label">{label}</span><span class="setting-description">{description}{#if conflict}<span class="keybinding-conflict"> Conflicts with another action.</span>{/if}</span></div>
                      <div class="keybinding-control">
                        <kbd>{recordingAction === action ? (recordingStrokes.length ? `${recordingStrokes.join(" ")} …` : "Press shortcut…") : (binding || "Unassigned")}</kbd>
                        <button class="secondary sm" aria-pressed={recordingAction === action} onclick={() => beginRecording(action)}>{recordingAction === action ? "Recording" : "Record"}</button>
                        <button class="link" disabled={!binding} onclick={() => saveKeybinding(action, "")}>Clear</button>
                      </div>
                    </div>
                  {/each}
                </div>
                <div class="setting-actions" id="settings-option-keybindingDefaults"><button class="secondary" onclick={() => saveAppSetting("keybindings", { ...DEFAULT_KEYBINDINGS })}>Restore defaults</button></div>
              </section>

<style>

  button { font-family: inherit; }
  .link { background: none; border: none; color: var(--link); cursor: pointer; font-size: 12px; text-decoration: underline; }
  .secondary { padding: 9px 12px; border: 1px solid var(--border2); border-radius: 8px; background: var(--input); color: var(--text2); font-weight: 600; cursor: pointer; }
  .secondary:hover { background: var(--hover); border-color: var(--accent); }
  .secondary:disabled { opacity: 0.55; cursor: default; }
  .secondary.sm { padding: 6px 10px; font-size: 12px; }
  .setting-card:focus-visible, .secondary:focus-visible {
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
  .setting-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
  :global(.settings-panel) .secondary { min-height: 34px; display: inline-flex; align-items: center; justify-content: center; }
  :global(.settings-panel) .secondary.sm { min-height: 30px; }
  .keybinding-list { gap: 7px; }
  .keybinding-card { min-height: 72px; }
  .keybinding-control { display: flex; align-items: center; justify-content: flex-end; gap: 7px; flex-wrap: wrap; }
  .keybinding-control kbd { min-width: 120px; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 6px 8px; border: 1px solid var(--border2); border-bottom-width: 2px; border-radius: 6px; background: var(--bg); color: var(--text2); font: 12px ui-monospace, SFMono-Regular, Consolas, monospace; text-align: center; }
  .keybinding-conflict { color: #ff9b9b; font-weight: 650; }
  @media (max-width: 760px) {
    .setting-card { grid-template-columns: 1fr; gap: 10px; align-items: stretch; }
    .setting-actions { justify-content: flex-start; }
    .keybinding-control { justify-content: flex-start; }
    .keybinding-control kbd { flex: 1; max-width: none; }
  }

</style>
