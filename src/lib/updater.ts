import { getVersion } from "@tauri-apps/api/app";
import { invoke } from "@tauri-apps/api/core";

export interface Update {
  version: string;
  body?: string | null;
  date?: string | null;
}

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

// Native packages expose updater operations only through backend commands. Flatpak builds
// omit those commands entirely, so their UI never calls this path.
export async function checkForUpdate(): Promise<Update | null> {
  try {
    return await invoke<Update | null>("check_native_update");
  } catch (error) {
    await reportUpdaterError("check", error);
    throw error;
  }
}

export async function installUpdate(update: Update): Promise<void> {
  try {
    await invoke("install_native_update", { expectedVersion: update.version });
  } catch (error) {
    await reportUpdaterError("install", error);
    throw error;
  }
}
