import { check, type Update } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import { getVersion } from "@tauri-apps/api/app";

export type { Update };

// Current application version from tauri.conf.json / Cargo.toml.
export function appVersion(): Promise<string> {
  return getVersion();
}

// Check the update endpoint; return null when the application is current.
export function checkForUpdate(): Promise<Update | null> {
  return check();
}

// Download and install the update, then relaunch the application.
export async function installUpdate(update: Update): Promise<void> {
  await update.downloadAndInstall();
  await relaunch();
}
