<script lang="ts">

  import type { AppSettings, DistributionInfo } from "../lib/api";
  import SettingsToggle from "./SettingsToggle.svelte";

  interface Props {
    appSettings: AppSettings;
    distributionInfo: DistributionInfo;
    loginText: "when you sign in to your Mac" | "when you sign in to Windows" | "when you log in";
    saveAppSetting: (key: keyof AppSettings, value: unknown) => Promise<void>;
    trayWord: "menu bar" | "system tray";
  }

  let {
    appSettings,
    distributionInfo,
    loginText,
    saveAppSetting,
    trayWord,
  }: Props = $props();

</script>

<section class="settings-section" aria-labelledby="settings-general-startup">
                <div class="section-heading">
                  <h3 id="settings-general-startup">Startup</h3>
                  <p>Choose how Tauridium behaves when the desktop session starts and when its window closes.</p>
                </div>
                <div class="settings-list">
                  <SettingsToggle
                    label={"Launch at login"}
                    description={distributionInfo.portalAutostart
                      ? "Request desktop permission through the XDG Background portal. The desktop controls whether autostart is granted."
                      : `Start Tauridium automatically ${loginText}.`}
                    settingKey={"autostart"}
                    checked={appSettings.autostart}
                    onsave={saveAppSetting}
                  />
                  {#if distributionInfo.mode === "flatpak"}
                    <div class="setting-card info-card">
                      <div class="setting-copy"><span class="setting-label">Background/tray startup</span><span class="setting-description">Flatpak keeps the main window recoverable on desktops that do not expose status icons. Start in background and Close to tray are therefore disabled for this package.</span></div>
                      <span class="status-badge">Desktop-safe</span>
                    </div>
                  {:else}
                    <SettingsToggle
                      label={"Start in background"}
                      description={`Launch with the main window hidden while Tauridium remains available in the ${trayWord}.`}
                      settingKey={"startMinimized"}
                      checked={appSettings.startMinimized}
                      onsave={saveAppSetting}
                    />
                    <SettingsToggle
                      label={"Close to tray"}
                      description={`Hide Tauridium to the ${trayWord} when the window close button is used instead of quitting the app.`}
                      settingKey={"closeToSystemTray"}
                      checked={appSettings.closeToSystemTray}
                      onsave={saveAppSetting}
                    />
                  {/if}
                </div>
              </section>

<style>

  .setting-card:focus-visible {
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
  .info-card { min-height: 72px; }
  .status-badge {
    display: inline-flex; align-items: center; min-height: 24px; padding: 0 9px;
    border: 1px solid var(--border2); border-radius: 999px; background: var(--hover);
    color: var(--text2); font-size: 11px; font-weight: 700;
  }
  @media (max-width: 760px) {
    .setting-card { grid-template-columns: 1fr; gap: 10px; align-items: stretch; }
  }

</style>
