import { invoke } from "@tauri-apps/api/core";
import type { DownloadCompletion } from "../downloadToast";

interface Host {
  current: () => DownloadCompletion | null | undefined;
  pause: () => void;
}

/** Each notification renderer owns its actions; privileged paths stay native. */
export function createDownloadToastActions(host: Host) {
  let busy = $state(false);
  let resultId = $state<number | undefined>();
  let failure = $state("");
  let status = $state("");

  async function perform(action: "dismiss" | "show", expectedId?: number) {
    const current = host.current();
    if (!current || busy || (expectedId !== undefined && expectedId !== current.id)) return;
    if (action === "show" && (!current.canShowInFolder || current.count !== 1)) return;
    const id = current.id;
    host.pause();
    busy = true;
    resultId = id;
    failure = "";
    status = "";
    try {
      if (action === "dismiss") {
        await invoke("dismiss_download_toast", { id });
      } else {
        const outcome = await invoke<"shown" | "cancelled" | "folderOpened">("show_download_in_folder", { id });
        const message = outcome === "shown"
          ? "File shown in folder."
          : outcome === "cancelled"
            ? "Show in folder cancelled."
            : outcome === "folderOpened"
              ? "Folder opened. The file may not be selected."
              : null;
        if (!message) throw new Error("Invalid reveal result");
        if (host.current()?.id === id) status = message;
      }
    } catch (error) {
      if (host.current()?.id === id) {
        failure = action === "dismiss"
          ? "Unable to dismiss the notification. Please try again."
          : error === "missing"
            ? "This download is no longer at its saved location. It may have been moved or deleted."
            : error === "stale"
              ? "This download notification is no longer available. Dismiss it and try a newer notification."
              : "Unable to show the download. Check that a file manager is available, then try again.";
      }
    } finally {
      busy = false;
    }
  }

  return {
    dismiss: (expectedId?: number) => perform("dismiss", expectedId),
    show: () => perform("show"),
    get busy() { return busy; },
    get failure() { return resultId === host.current()?.id ? failure : ""; },
    get status() { return resultId === host.current()?.id ? status : ""; },
  };
}
