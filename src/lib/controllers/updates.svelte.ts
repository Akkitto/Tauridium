import { checkForUpdate, installUpdate, type Update } from "../updater";
import { type DistributionInfo } from "../api";

export interface UpdatesHost {
  readonly distributionInfo: DistributionInfo;
}

/** Feature state is created once per application instance; host accessors stay live. */
export function createUpdatesController(host: UpdatesHost) {

  let updateInfo = $state<Update | null>(null);

  let updChecking = $state(false);

  let updInstalling = $state(false);

  let updStatus = $state("");

  async function checkUpdates(silent = false) {
    if (host.distributionInfo.updaterManagedExternally) {
      updateInfo = null;
      updStatus = "Updates are managed by Flatpak/Flathub.";
      return;
    }
    updChecking = true;
    if (!silent) updStatus = "";
    try {
      updateInfo = await checkForUpdate();
      if (!silent && !updateInfo) updStatus = "You're on the latest version.";
    } catch (e) {
      if (!silent) updStatus = `Update check failed: ${e}`;
    } finally {
      updChecking = false;
    }
  }

  async function doInstall() {
    if (!updateInfo) return;
    updInstalling = true;
    updStatus = "Downloading…";
    try {
      await installUpdate(updateInfo); // Download, install, and restart.
    } catch (e) {
      updStatus = `Update failed: ${e}`;
      updInstalling = false;
    }
  }

  return {
    checkUpdates,
    doInstall,
    get updChecking() { return updChecking; },
    get updInstalling() { return updInstalling; },
    get updStatus() { return updStatus; },
    get updateInfo() { return updateInfo; },
  };
}

export type UpdatesController = ReturnType<typeof createUpdatesController>;
