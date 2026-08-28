import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  check: vi.fn(),
  getVersion: vi.fn(),
  invoke: vi.fn(),
  relaunch: vi.fn(),
}));

vi.mock("@tauri-apps/api/app", () => ({ getVersion: mocks.getVersion }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: mocks.invoke }));
vi.mock("@tauri-apps/plugin-process", () => ({ relaunch: mocks.relaunch }));
vi.mock("@tauri-apps/plugin-updater", () => ({ check: mocks.check }));

import { checkForUpdate, installUpdate } from "./updater";

describe("updater diagnostics", () => {
  beforeEach(() => {
    mocks.check.mockReset();
    mocks.getVersion.mockReset();
    mocks.invoke.mockReset();
    mocks.relaunch.mockReset();
    mocks.invoke.mockResolvedValue(undefined);
    vi.restoreAllMocks();
  });

  it("records update-check failures in the developer console and audit log", async () => {
    const error = new Error("Could not fetch a valid release JSON from the remote");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    mocks.check.mockRejectedValue(error);

    await expect(checkForUpdate()).rejects.toBe(error);

    expect(consoleError).toHaveBeenCalledWith(
      "[Tauridium updater] check failed: Could not fetch a valid release JSON from the remote",
      error,
    );
    expect(mocks.invoke).toHaveBeenCalledWith("record_updater_error", {
      action: "check",
      message: "Could not fetch a valid release JSON from the remote",
    });
  });

  it("records install failures without replacing the original updater error", async () => {
    const error = new Error("signature verification failed");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const update = {
      downloadAndInstall: vi.fn().mockRejectedValue(error),
    };

    await expect(installUpdate(update as never)).rejects.toBe(error);

    expect(mocks.relaunch).not.toHaveBeenCalled();
    expect(consoleError).toHaveBeenCalledWith(
      "[Tauridium updater] install failed: signature verification failed",
      error,
    );
    expect(mocks.invoke).toHaveBeenCalledWith("record_updater_error", {
      action: "install",
      message: "signature verification failed",
    });
  });

  it("keeps the updater failure visible even if audit persistence also fails", async () => {
    const error = new Error("remote unavailable");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    mocks.check.mockRejectedValue(error);
    mocks.invoke.mockRejectedValue(new Error("audit disk unavailable"));

    await expect(checkForUpdate()).rejects.toBe(error);

    expect(consoleError).toHaveBeenCalledTimes(2);
    expect(consoleError.mock.calls[1]?.[0]).toBe(
      "[Tauridium updater] Unable to persist updater failure to the audit log",
    );
  });
});
