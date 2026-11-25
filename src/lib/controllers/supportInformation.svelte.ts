import { copySupportInformation, getSupportInformation } from "../api";

/** Each mounted support panel owns its own request and presentation state. */
export function createSupportInformationController() {
  let text = $state("");
  let busy = $state(false);
  let status = $state("");
  let error = $state("");

  async function refresh() {
    if (busy) return;
    busy = true;
    error = "";
    status = "";
    try {
      text = await getSupportInformation();
    } catch {
      error = "Support information is temporarily unavailable. Please try again.";
    } finally {
      busy = false;
    }
  }

  async function copy() {
    if (busy) return;
    busy = true;
    error = "";
    status = "";
    try {
      // The native side creates and writes the report; arbitrary text is never sent.
      text = await copySupportInformation();
      status = "Support information copied.";
    } catch {
      error = "Unable to copy support information. Open the preview and copy it manually, or try again.";
    } finally {
      busy = false;
    }
  }

  return {
    refresh, copy,
    get text() { return text; },
    get busy() { return busy; },
    get status() { return status; },
    get error() { return error; },
  };
}
