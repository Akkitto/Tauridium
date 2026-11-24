<script lang="ts">

  import type { UpdatesController } from "../lib/controllers/updates.svelte";
  import type { DistributionInfo } from "../lib/api";

  import { managedUpdateText } from "../lib/distribution";

  interface Props {
    updates: UpdatesController;
    appVer: string;
    distributionInfo: DistributionInfo;
  }

  let {
    updates,
    appVer,
    distributionInfo,
  }: Props = $props();

</script>

<section class="settings-section" aria-labelledby="settings-updates-version">
                <div class="section-heading"><h3 id="settings-updates-version">Updates</h3><p>{distributionInfo.updaterManagedExternally ? managedUpdateText(distributionInfo.mode).description : "Keep Tauridium current using signed releases published through the project repository."}</p></div>
                <div class="settings-list">
                  <div class="setting-card">
                    <div class="setting-copy"><span class="setting-label">Current version</span><span class="setting-description">Tauridium {appVer ? `v${appVer}` : "version information is loading"}.</span></div>
                    {#if distributionInfo.updaterManagedExternally}
                      <span class="status-badge">{managedUpdateText(distributionInfo.mode).badge}</span>
                    {:else if updates.updateInfo}
                      <button class="primary" disabled={updates.updInstalling} onclick={updates.doInstall}>{updates.updInstalling ? "Installing…" : `Update to v${updates.updateInfo.version}`}</button>
                    {:else}
                      <button class="secondary" disabled={updates.updChecking} onclick={() => updates.checkUpdates(false)}>{updates.updChecking ? "Checking…" : "Check for updates"}</button>
                    {/if}
                  </div>
                  {#if distributionInfo.updaterManagedExternally}
                    <p class="settings-status">{managedUpdateText(distributionInfo.mode).status}</p>
                  {:else}
                    {#if updates.updateInfo}<p class="settings-status">Version {updates.updateInfo.version} is available. Tauridium will restart after installation.</p>{/if}
                    {#if updates.updStatus}<p class="settings-status">{updates.updStatus}</p>{/if}
                  {/if}
                </div>
              </section>

<style>

  button { font-family: inherit; }
  .primary {
    padding: 10px 14px; border: none; border-radius: 8px; background: var(--accent);
    color: var(--accent-fg); font-weight: 700; cursor: pointer;
  }
  .primary:disabled { opacity: 0.6; cursor: default; }
  .secondary { padding: 9px 12px; border: 1px solid var(--border2); border-radius: 8px; background: var(--input); color: var(--text2); font-weight: 600; cursor: pointer; }
  .secondary:hover { background: var(--hover); border-color: var(--accent); }
  .secondary:disabled { opacity: 0.55; cursor: default; }
  .setting-card:focus-visible, .primary:focus-visible, .secondary:focus-visible {
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
  .settings-status { margin: 0 2px; color: var(--muted); font-size: 12px; line-height: 1.45; }
  .settings-status { color: var(--text2); }
  .status-badge {
    display: inline-flex; align-items: center; min-height: 24px; padding: 0 9px;
    border: 1px solid var(--border2); border-radius: 999px; background: var(--hover);
    color: var(--text2); font-size: 11px; font-weight: 700;
  }
  :global(.settings-panel) .primary, :global(.settings-panel) .secondary { min-height: 34px; display: inline-flex; align-items: center; justify-content: center; }
  @media (max-width: 760px) {
    .setting-card { grid-template-columns: 1fr; gap: 10px; align-items: stretch; }
  }

</style>
