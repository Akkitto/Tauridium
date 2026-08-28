import { getVersion } from "@tauri-apps/api/app";
import { invoke } from "@tauri-apps/api/core";
import { relaunch } from "@tauri-apps/plugin-process";
import { check, type Update } from "@tauri-apps/plugin-updater";

export type { Update };

type UpdaterAuditAction = "check" | "install";

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  return String(error);
}

async function reportUpdaterError(action: UpdaterAuditAction, error: unknown): Promise<void> {
  const message = errorMessage(error);
  console.error(`[Tauridium updater] ${action} failed: ${message}`, error);
  try {
    await invoke("record_updater_error", { action, message });
  } catch (auditError) {
    console.error("[Tauridium updater] Unable to persist updater failure to the audit log", auditError);
  }
}

// Current application version from tauri.conf.json / Cargo.toml.
export function appVersion(): Promise<string> {
  return getVersion();
}

// Check the update endpoint; return null when the application is current.
export async function checkForUpdate(): Promise<Update | null> {
  try {
    return await check();
  } catch (error) {
    await reportUpdaterError("check", error);
    throw error;
  }
}

// Download and install the update, then relaunch the application.
export async function installUpdate(update: Update): Promise<void> {
  try {
    await update.downloadAndInstall();
    await relaunch();
  } catch (error) {
    await reportUpdaterError("install", error);
    throw error;
  }
}
