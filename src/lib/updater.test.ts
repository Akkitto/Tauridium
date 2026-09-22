import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getVersion: vi.fn(),
  invoke: vi.fn(),
}));

vi.mock("@tauri-apps/api/app", () => ({ getVersion: mocks.getVersion }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: mocks.invoke }));

import { checkForUpdate, installUpdate } from "./updater";

describe("updater diagnostics", () => {
  beforeEach(() => {
    mocks.getVersion.mockReset();
    mocks.invoke.mockReset();
    vi.restoreAllMocks();
  });

  it("uses the backend-only native updater command", async () => {
    const update = { version: "0.8.1", body: "Fixes", date: null };
    mocks.invoke.mockResolvedValueOnce(update);

    await expect(checkForUpdate()).resolves.toEqual(update);
    expect(mocks.invoke).toHaveBeenCalledWith("check_native_update");
  });

  it("records update-check failures in the developer console and audit log", async () => {
    const error = new Error("Could not fetch a valid release JSON from the remote");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    mocks.invoke
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce(undefined);

    await expect(checkForUpdate()).rejects.toBe(error);

    expect(consoleError).toHaveBeenCalledWith(
      "[Tauridium updater] check failed: Could not fetch a valid release JSON from the remote",
      error,
    );
    expect(mocks.invoke).toHaveBeenNthCalledWith(2, "record_updater_error", {
      action: "check",
      message: "Could not fetch a valid release JSON from the remote",
    });
  });

  it("installs through the backend without exposing updater capability to the webview", async () => {
    mocks.invoke.mockResolvedValueOnce(undefined);

    await installUpdate({ version: "0.8.1" });

    expect(mocks.invoke).toHaveBeenCalledWith("install_native_update", {
      expectedVersion: "0.8.1",
    });
  });

  it("records install failures without replacing the original updater error", async () => {
    const error = new Error("signature verification failed");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    mocks.invoke
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce(undefined);

    await expect(installUpdate({ version: "0.8.1" })).rejects.toBe(error);

    expect(consoleError).toHaveBeenCalledWith(
      "[Tauridium updater] install failed: signature verification failed",
      error,
    );
    expect(mocks.invoke).toHaveBeenNthCalledWith(2, "record_updater_error", {
      action: "install",
      message: "signature verification failed",
    });
  });

  it("keeps the updater failure visible even if audit persistence also fails", async () => {
    const error = new Error("remote unavailable");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    mocks.invoke.mockRejectedValue(error);

    await expect(checkForUpdate()).rejects.toBe(error);

    expect(consoleError).toHaveBeenCalledTimes(2);
    expect(consoleError.mock.calls[1]?.[0]).toBe(
      "[Tauridium updater] Unable to persist updater failure to the audit log",
    );
  });
});
