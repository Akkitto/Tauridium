import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createAuthController, type AuthHost } from "./auth.svelte";
import { login, startLocalSession, type MeUser } from "../api";

vi.mock("../api", () => ({
  DEFAULT_SERVER: "https://example.invalid", login: vi.fn(),
  startLocalSession: vi.fn(), restoreSession: vi.fn(),
}));
vi.mock("@tauri-apps/plugin-dialog", () => ({ message: vi.fn() }));

const user: MeUser = { id: "synthetic", email: "example@example.invalid", firstname: "Test", lastname: "User" };
function host(): AuthHost {
  return { me: null, error: null, loadAfterAuth: vi.fn(async () => undefined) };
}
describe("Authentication controller lifecycle", () => {
  beforeEach(() => { vi.resetAllMocks(); vi.useFakeTimers(); });
  afterEach(() => vi.useRealTimers());

  it("retains private retry credentials only until success and clears the password", async () => {
    const owner = host(), auth = createAuthController(owner);
    auth.email = user.email;
    auth.password = "synthetic-test-password";
    vi.mocked(login).mockRejectedValueOnce("transient:offline").mockResolvedValueOnce(user);
    await auth.handleLogin(new Event("submit", { cancelable: true }));
    expect(auth.reconnecting).toBe(true);
    expect(auth.hasPendingCredentials).toBe(true);
    expect(auth).not.toHaveProperty("pendingCreds");
    await vi.advanceTimersByTimeAsync(30000);
    expect(login).toHaveBeenCalledTimes(2);
    expect(owner.me).toEqual(user);
    expect(owner.loadAfterAuth).toHaveBeenCalledOnce();
    expect(auth.hasPendingCredentials).toBe(false);
    expect(auth.password).toBe("");
    expect(auth.reconnecting).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("cancels retry timers without affecting another application instance", async () => {
    vi.mocked(login).mockRejectedValue("transient:offline");
    const first = createAuthController(host()), second = createAuthController(host());
    await first.handleLogin(new Event("submit"));
    expect(second.reconnecting).toBe(false);
    expect(second.hasPendingCredentials).toBe(false);
    first.cancelReconnect();
    await vi.advanceTimersByTimeAsync(60000);
    expect(login).toHaveBeenCalledOnce();
    expect(first.hasPendingCredentials).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("stops account retries before starting a local session", async () => {
    vi.mocked(login).mockRejectedValue("transient:offline");
    vi.mocked(startLocalSession).mockResolvedValue({ ...user, local: true });
    const owner = host(), auth = createAuthController(owner);
    auth.password = "synthetic-test-password";
    await auth.handleLogin(new Event("submit"));
    await auth.handleLocalSession();
    expect(auth.hasPendingCredentials).toBe(false);
    expect(auth.password).toBe("");
    expect(auth.loading).toBe(false);
    expect(owner.me?.local).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });
});
