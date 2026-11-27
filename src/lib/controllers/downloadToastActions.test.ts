import { beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import type { DownloadCompletion } from "../downloadToast";
import { createDownloadToastActions } from "./downloadToastActions.svelte";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

function fixture() {
  let current: DownloadCompletion | null = {
    id: 10, filename: "example.txt", count: 1, location: null, locationLabel: "", canShowInFolder: true,
  };
  const pause = vi.fn();
  const actions = createDownloadToastActions({ current: () => current, pause });
  return { actions, pause, get current() { return current; }, set current(value) { current = value; } };
}

describe("Download actions use native completion identity and preserve privacy", () => {
  beforeEach(() => vi.resetAllMocks());

  it("pauses expiry synchronously and acknowledges only after the native operation succeeds", async () => {
    const pending = Promise.withResolvers<string>();
    const f = fixture();
    vi.mocked(invoke).mockImplementation(() => {
      expect(f.pause).toHaveBeenCalledOnce();
      return pending.promise;
    });
    const showing = f.actions.show();
    expect(f.actions.busy).toBe(true);
    expect(f.actions.status).toBe("");
    expect(invoke).toHaveBeenCalledExactlyOnceWith("show_download_in_folder", { id: 10 });
    await f.actions.show();
    await f.actions.dismiss();
    expect(invoke).toHaveBeenCalledTimes(1);
    pending.resolve("shown");
    await showing;
    expect(f.actions.status).toBe("File shown in folder.");
    expect(f.actions.busy).toBe(false);
    expect(f.current?.id).toBe(10); // Revealing never dismisses or advances the queue.
  });

  it("never accepts a renderer path or reveals unknown, aggregate or stale completions", async () => {
    const f = fixture();
    f.current = null;
    await f.actions.show();
    f.current = { id: 20, filename: "unknown", count: 1, location: "/private/UI_ONLY", locationLabel: "", canShowInFolder: false };
    await f.actions.show();
    f.current.canShowInFolder = true;
    f.current.count = 2;
    await f.actions.show();
    await f.actions.dismiss(19);
    expect(invoke).not.toHaveBeenCalled();
    expect(f.pause).not.toHaveBeenCalled();
    f.current.count = 1;
    vi.mocked(invoke).mockResolvedValue("shown");
    await f.actions.show();
    expect(invoke).toHaveBeenCalledExactlyOnceWith("show_download_in_folder", { id: 20 });
    expect(JSON.stringify(vi.mocked(invoke).mock.calls)).not.toContain("UI_ONLY");
  });

  it.each([
    ["missing", "moved or deleted"],
    ["stale", "no longer available"],
    [new Error("PRIVATE_NATIVE_PATH_CANARY"), "file manager"],
    ["/private/PRIVATE_NATIVE_PATH_CANARY", "file manager"],
  ])("keeps failures actionable and path-free, then permits retry (%s)", async (error, expected) => {
    const f = fixture();
    vi.mocked(invoke).mockRejectedValueOnce(error).mockResolvedValueOnce("shown");
    await f.actions.show();
    expect(f.actions.failure).toContain(expected);
    expect(f.actions.failure).not.toContain("PRIVATE_NATIVE_PATH_CANARY");
    expect(f.actions.status).toBe("");
    expect(f.actions.busy).toBe(false);
    expect(f.current?.id).toBe(10);
    await f.actions.show();
    expect(f.actions.failure).toBe("");
    expect(f.actions.status).toBe("File shown in folder.");
  });

  it("treats a user's portal cancellation as a neutral result", async () => {
    const f = fixture();
    vi.mocked(invoke).mockResolvedValue("cancelled");
    await f.actions.show();
    expect(f.actions.failure).toBe("");
    expect(f.actions.status).toBe("Show in folder cancelled.");
  });

  it("distinguishes a folder opened without confirmed selection", async () => {
    const f = fixture();
    vi.mocked(invoke).mockResolvedValue("folderOpened");
    await f.actions.show();
    expect(f.actions.failure).toBe("");
    expect(f.actions.status).toBe("Folder opened. The file may not be selected.");
    expect(f.current?.id).toBe(10);
  });

  it("rejects unexpected native responses without claiming success", async () => {
    const f = fixture();
    vi.mocked(invoke).mockResolvedValue("unexpected");
    await f.actions.show();
    expect(f.actions.failure).toContain("file manager");
    expect(f.actions.status).toBe("");
  });

  it.each([true, false])("does not attach a late response to the next queued file (%s)", async (success) => {
    const f = fixture(), pending = Promise.withResolvers<string>();
    vi.mocked(invoke).mockReturnValue(pending.promise);
    const showing = f.actions.show();
    f.current = { ...f.current!, id: 11, filename: "next.txt" };
    if (success) pending.resolve("shown"); else pending.reject("missing");
    await showing;
    expect(f.actions.failure).toBe("");
    expect(f.actions.status).toBe("");
    expect(f.actions.busy).toBe(false);
  });

  it("dismisses only the expected completion and keeps unrelated owners independent", async () => {
    const first = fixture(), second = fixture();
    vi.mocked(invoke).mockResolvedValue(undefined);
    await first.actions.dismiss(10);
    expect(invoke).toHaveBeenCalledExactlyOnceWith("dismiss_download_toast", { id: 10 });
    expect(second.pause).not.toHaveBeenCalled();
    expect(second.actions.busy).toBe(false);
    expect(second.actions.status).toBe("");
  });
});
