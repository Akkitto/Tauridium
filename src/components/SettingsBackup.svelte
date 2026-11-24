<script lang="ts">

  import type { BackupsController } from "../lib/controllers/backups.svelte";
  import type { AppSettings, DistributionInfo } from "../lib/api";

  interface Props {
    backups: BackupsController;
    appSettings: AppSettings;
    distributionInfo: DistributionInfo;
    saveAppSetting: (key: keyof AppSettings, value: unknown) => Promise<void>;
  }

  let {
    backups,
    appSettings,
    distributionInfo,
    saveAppSetting,
  }: Props = $props();

</script>

<section class="settings-section" aria-labelledby="settings-backup-manual">
                <div class="section-heading"><h3 id="settings-backup-manual">Manual backup</h3><p>Export or restore Tauridium-owned configuration using a versioned, integrity-verified backup file.</p></div>
                <div class="settings-list">
                  <div class="setting-card">
                    <div class="setting-copy"><span class="setting-label">Tauridium data</span><span class="setting-description">Exports app settings, canonical service/workspace order, local services and workspaces, and complete custom recipes. Restore validates every component before committing. Ferdium login tokens, website cookies/storage, remote caches, and machine-specific monitor geometry are excluded.</span></div>
                    <div class="setting-actions"><button class="secondary sm" disabled={backups.backupBusy} onclick={backups.doRestoreBackup}>Restore backup…</button><button class="primary sm" disabled={backups.backupBusy} onclick={backups.doExportBackup}>Export backup…</button></div>
                  </div>
                  <p class="settings-note">Backups can contain sensitive local service configuration such as proxy credentials. Store them accordingly.</p>
                  {#if backups.backupStatus}<p class="settings-status">{backups.backupStatus}</p>{/if}
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-backup-automatic">
                <div class="section-heading"><h3 id="settings-backup-automatic">Automatic backup</h3><p>Create integrity-verified recovery copies on a schedule or on demand, then prune only after the new backup has been reread and verified.</p></div>
                <div class="settings-list">
                  <div class="setting-card" id="settings-option-automaticBackupSchedule">
                    <div class="setting-copy"><span class="setting-label">Schedule</span><span class="setting-description">Choose when Tauridium creates automatic backups while it is running.</span></div>
                    <select class="setting-control" aria-label="Automatic backup schedule" value={appSettings.automaticBackupSchedule} onchange={(e) => saveAppSetting("automaticBackupSchedule", e.currentTarget.value)}><option value="off">Off</option><option value="startup">On program startup</option><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select>
                  </div>
                  <div class="setting-card setting-card-stack" id="settings-option-automaticBackupDirectory">
                    <div class="setting-copy"><span class="setting-label">Output folder</span><span class="setting-description">{distributionInfo.automaticBackupsUsePrivateStorage ? "Flatpak stores scheduled backups in Tauridium's private application data so recurring writes do not require broad host filesystem access." : "Choose the folder used for scheduled and on-demand automatic backups. Leave unset to use Tauridium's managed configuration folder."}</span></div>
                    {#if distributionInfo.automaticBackupsUsePrivateStorage}
                      <div class="backup-location-row"><code>Tauridium private data/backups/automatic</code><span class="status-badge">Sandboxed</span></div>
                    {:else}
                      <div class="backup-location-row">
                        <code title={appSettings.automaticBackupDirectory || "Tauridium configuration/backups/automatic (default)"}>{appSettings.automaticBackupDirectory || "Tauridium configuration/backups/automatic (default)"}</code>
                        <div class="setting-actions"><button class="secondary sm" onclick={backups.chooseAutomaticBackupDirectory}>Choose folder…</button><button class="secondary sm" disabled={!appSettings.automaticBackupDirectory} onclick={backups.useDefaultAutomaticBackupDirectory}>Use default</button></div>
                      </div>
                    {/if}
                  </div>
                  <div class="setting-card" id="settings-option-automaticBackupRetentionMode">
                    <div class="setting-copy"><span class="setting-label">Retention strategy</span><span class="setting-description">Choose a simple count, age limit, both limits together, or tiered GFS-style history.</span></div>
                    <select class="setting-control" aria-label="Automatic backup retention strategy" value={appSettings.automaticBackupRetentionMode} onchange={(e) => saveAppSetting("automaticBackupRetentionMode", e.currentTarget.value)}>
                      <option value="count">Newest backup count</option>
                      <option value="age">Maximum age</option>
                      <option value="countAndAge">Count and maximum age</option>
                      <option value="tiered">Tiered history (GFS-style)</option>
                    </select>
                  </div>
                  {#if appSettings.automaticBackupRetentionMode === "count" || appSettings.automaticBackupRetentionMode === "countAndAge"}
                    <div class="setting-card" id="settings-option-automaticBackupRetention">
                      <div class="setting-copy"><span class="setting-label">Newest backups to keep</span><span class="setting-description">Always keep at least the newest verified automatic backup.</span></div>
                      <input class="setting-number" type="number" min="1" max="365" value={appSettings.automaticBackupRetention} aria-label="Automatic backup count retention" onchange={(e) => saveAppSetting("automaticBackupRetention", Math.max(1, Math.min(365, Number(e.currentTarget.value) || 1)))} />
                    </div>
                  {/if}
                  {#if appSettings.automaticBackupRetentionMode === "age" || appSettings.automaticBackupRetentionMode === "countAndAge"}
                    <div class="setting-card" id="settings-option-automaticBackupMaxAgeDays">
                      <div class="setting-copy"><span class="setting-label">Maximum backup age</span><span class="setting-description">Delete automatic backups older than this many days after a new verified backup exists. The newest verified backup is never removed solely because of age.</span></div>
                      <div class="number-with-unit"><input class="setting-number" type="number" min="1" max="3650" value={appSettings.automaticBackupMaxAgeDays} aria-label="Automatic backup maximum age in days" onchange={(e) => saveAppSetting("automaticBackupMaxAgeDays", Math.max(1, Math.min(3650, Number(e.currentTarget.value) || 1)))} /><span>days</span></div>
                    </div>
                  {/if}
                  {#if appSettings.automaticBackupRetentionMode === "tiered"}
                    <div class="setting-card info-card">
                      <div class="setting-copy"><span class="setting-label">Tiered history</span><span class="setting-description">Keeps one representative per recent day, then progressively one per week, calendar month, and calendar year for up to about five years. This is a GFS-style retention pattern; using one folder does not by itself satisfy a 3-2-1 backup strategy.</span></div>
                      <span class="status-badge">Daily → weekly → monthly → yearly</span>
                    </div>
                  {/if}
                  <div class="setting-actions" id="settings-option-automaticBackupNow"><button class="primary sm" disabled={backups.backupBusy || backups.automaticBackupRunning} onclick={backups.runAutomaticBackupNow}>Back up now</button></div>
                  <p class="settings-note">Retention cleanup runs only after the newly written backup has been staged, flushed, reread, parsed, and integrity-verified.</p>
                </div>
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
  .primary.sm { padding: 6px 12px; font-size: 13px; }
  .secondary { padding: 9px 12px; border: 1px solid var(--border2); border-radius: 8px; background: var(--input); color: var(--text2); font-weight: 600; cursor: pointer; }
  .secondary:hover { background: var(--hover); border-color: var(--accent); }
  .secondary:disabled { opacity: 0.55; cursor: default; }
  .secondary.sm { padding: 6px 10px; font-size: 12px; }
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
  .setting-card-stack { grid-template-columns: 1fr; align-items: stretch; gap: 10px; }
  .setting-copy { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .setting-label { color: var(--text2); font-size: 14px; line-height: 1.35; font-weight: 650; }
  .setting-description { max-width: 760px; color: var(--muted); font-size: 12.5px; line-height: 1.45; font-weight: 400; }
  .setting-control { min-width: 176px; max-width: 230px; margin-left: 0; }
  .setting-number { width: 96px; box-sizing: border-box; text-align: right; }
  .setting-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
  .settings-note, .settings-status { margin: 0 2px; color: var(--muted); font-size: 12px; line-height: 1.45; }
  .settings-status { color: var(--text2); }
  .info-card { min-height: 72px; }
  .status-badge {
    display: inline-flex; align-items: center; min-height: 24px; padding: 0 9px;
    border: 1px solid var(--border2); border-radius: 999px; background: var(--hover);
    color: var(--text2); font-size: 11px; font-weight: 700;
  }
  :global(.settings-panel) .primary, :global(.settings-panel) .secondary { min-height: 34px; display: inline-flex; align-items: center; justify-content: center; }
  :global(.settings-panel) .primary.sm, :global(.settings-panel) .secondary.sm { min-height: 30px; }
  .backup-location-row { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 8px; align-items: center; width: 100%; }
  .backup-location-row code { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .number-with-unit { display: inline-flex; align-items: center; gap: 8px; color: var(--muted); font-size: 12px; }
  @media (max-width: 760px) {
    .setting-card { grid-template-columns: 1fr; gap: 10px; align-items: stretch; }
    .setting-control { width: 100%; max-width: none; }
    .setting-number { width: 100%; text-align: left; }
    .setting-actions { justify-content: flex-start; }
    .backup-location-row { grid-template-columns: 1fr; }
  }

</style>
