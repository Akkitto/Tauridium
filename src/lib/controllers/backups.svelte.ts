import { backupTimestamp, automaticBackupDue } from "../ui";
import { open, save as saveDialog } from "@tauri-apps/plugin-dialog";
import { closeServices, setAppSettings, exportBackup, restoreBackup, createAutomaticBackup, type AppSettings, type BackupSummary } from "../api";

export interface BackupsHost {
  appSettings: AppSettings;
  readonly confirmAsk: (message: string) => Promise<boolean>;
  error: string | null;
  readonly saveAppSetting: (key: keyof AppSettings, value: unknown) => Promise<void>;
}

/** Feature state is created once per application instance; host accessors stay live. */
export function createBackupsController(host: BackupsHost) {

  // Portable backup/export state.
  let backupBusy = $state(false);

  let backupStatus = $state("");

  let automaticBackupStartupHandled = false;

  let automaticBackupRunning = $state(false);

  function backupFileName(): string {
    return `tauridium-backup-${backupTimestamp()}.json`;
  }

  function automaticBackupFileName(): string {
    return `tauridium-auto-backup-${backupTimestamp()}.json`;
  }

  async function maybeRunAutomaticBackup(startup: boolean) {
    if (automaticBackupRunning) return;
    const schedule = host.appSettings.automaticBackupSchedule ?? "off";
    const now = Date.now();
    const due = automaticBackupDue(
      schedule,
      host.appSettings.lastAutomaticBackupAt ?? 0,
      now,
      startup,
      automaticBackupStartupHandled,
    );
    if (schedule === "startup" && startup) automaticBackupStartupHandled = true;
    if (!due) return;
    automaticBackupRunning = true;
    try {
      const summary = await createAutomaticBackup(automaticBackupFileName());
      host.appSettings = await setAppSettings({ lastAutomaticBackupAt: now });
      backupStatus = backupSummaryText("Automatic backup created", summary);
    } catch (err) {
      backupStatus = `Automatic backup failed: ${err}`;
    } finally {
      automaticBackupRunning = false;
    }
  }

  function backupSummaryText(action: string, summary: BackupSummary): string {
    const integrity = summary.integrityVerified
      ? "integrity verified"
      : summary.sourceSchema < summary.schema
        ? `migrated from legacy schema ${summary.sourceSchema}`
        : "legacy integrity metadata unavailable";
    const recovery = summary.recoveryBackupPath ? ` Recovery snapshot: ${summary.recoveryBackupPath}` : "";
    const warnings = summary.warnings?.length ? ` Warning: ${summary.warnings.join(" ")}` : "";
    return `${action}: schema ${summary.schema}, ${integrity}; ${summary.customRecipeCount} custom recipes, ${summary.serviceCount} local services, ${summary.workspaceCount} local workspaces.${recovery}${warnings}`;
  }

  async function chooseAutomaticBackupDirectory() {
    try {
      const selected = await open({
        directory: true,
        multiple: false,
        title: "Choose automatic backup folder",
        defaultPath: host.appSettings.automaticBackupDirectory || undefined,
      });
      const path = Array.isArray(selected) ? selected[0] : selected;
      if (path) await host.saveAppSetting("automaticBackupDirectory", path);
    } catch (err) {
      host.error = `Unable to choose automatic backup folder: ${err}`;
    }
  }

  async function useDefaultAutomaticBackupDirectory() {
    await host.saveAppSetting("automaticBackupDirectory", "");
  }

  async function doExportBackup() {
    backupBusy = true;
    backupStatus = "";
    host.error = null;
    try {
      if (!(await host.confirmAsk("This backup contains private service configuration, possibly proxy credentials, personal URLs and executable recipe scripts. Keep it private; it is a recovery backup, not a public sharing bundle. Continue?"))) return;
      const path = await saveDialog({
        title: "Export Tauridium backup",
        defaultPath: backupFileName(),
        filters: [{ name: "Tauridium backup", extensions: ["json"] }],
      });
      if (!path) return;
      const summary = await exportBackup(path);
      backupStatus = backupSummaryText("Backup exported", summary);
    } catch (err) {
      host.error = `Backup export failed: ${err}`;
    } finally {
      backupBusy = false;
    }
  }

  async function runAutomaticBackupNow() {
    if (automaticBackupRunning || backupBusy) return;
    automaticBackupRunning = true;
    backupBusy = true;
    backupStatus = "";
    try {
      const now = Date.now();
      const summary = await createAutomaticBackup(automaticBackupFileName());
      host.appSettings = await setAppSettings({ lastAutomaticBackupAt: now });
      backupStatus = backupSummaryText("Automatic backup created", summary);
    } catch (err) {
      backupStatus = `Automatic backup failed: ${err}`;
    } finally {
      automaticBackupRunning = false;
      backupBusy = false;
    }
  }

  async function doRestoreBackup() {
    backupStatus = "";
    host.error = null;
    try {
      const selected = await open({
        directory: false,
        multiple: false,
        title: "Restore Tauridium backup",
        filters: [{ name: "Tauridium backup", extensions: ["json"] }],
      });
      const path = Array.isArray(selected) ? selected[0] : selected;
      if (!path) return;
      const confirmed = await host.confirmAsk(
        "Restore this Tauridium backup? Local app settings and local services/workspaces will be replaced. Custom recipes with matching ids will be overwritten; other custom recipes are retained. Backups can contain sensitive local service configuration such as proxy credentials. Only restore a trusted backup: included recipe scripts can read or change signed-in service pages.",
      );
      if (!confirmed) return;
      backupBusy = true;
      await closeServices();
      const summary = await restoreBackup(path);
      backupStatus = backupSummaryText("Backup restored", summary);
      window.setTimeout(() => window.location.reload(), 150);
    } catch (err) {
      host.error = `Backup restore failed: ${err}`;
    } finally {
      backupBusy = false;
    }
  }

  return {
    maybeRunAutomaticBackup,
    get automaticBackupRunning() { return automaticBackupRunning; },
    get backupBusy() { return backupBusy; },
    get backupStatus() { return backupStatus; },
    chooseAutomaticBackupDirectory,
    doExportBackup,
    doRestoreBackup,
    runAutomaticBackupNow,
    useDefaultAutomaticBackupDirectory,
  };
}

export type BackupsController = ReturnType<typeof createBackupsController>;
