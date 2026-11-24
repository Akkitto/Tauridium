import { message as showMessage } from "@tauri-apps/plugin-dialog";
import { login, startLocalSession, restoreSession, DEFAULT_SERVER, type MeUser } from "../api";

export interface AuthHost {
  error: string | null;
  readonly loadAfterAuth: () => Promise<void>;
  me: MeUser | null;
}

/** Feature state is created once per application instance; host accessors stay live. */
export function createAuthController(host: AuthHost) {

  let server = $state(DEFAULT_SERVER);

  let email = $state("");

  let password = $state("");

  let showServer = $state(false);

  let rememberSession = $state(true);

  let allowInsecureServer = $state(false);

  let loading = $state(false);

  // Automatically reconnect when the server is unreachable (Ferdium outage, network issue, etc.).
  const RECONNECT_SECS = 30;

  let reconnecting = $state(false);

  let reconnectIn = $state(RECONNECT_SECS);

  let pendingCreds = $state<{ server: string; email: string; password: string; rememberSession: boolean; allowInsecureServer: boolean } | null>(
    null,
  );

  let reconnectAttempt: (() => Promise<boolean>) | null = null;

  let reconnectTimer: ReturnType<typeof setInterval> | null = null;

  function stopReconnect() {
    if (reconnectTimer) {
      clearInterval(reconnectTimer);
      reconnectTimer = null;
    }
    reconnectAttempt = null;
    reconnecting = false;
  }

  // Start a reconnection loop that calls attempt every RECONNECT_SECS.
  // attempt returns true when finished (success OR definitive error), so stop;
  // false means the server is still unreachable, so retry later.
  function startReconnect(attempt: () => Promise<boolean>) {
    stopReconnect();
    reconnectAttempt = attempt;
    reconnecting = true;
    reconnectIn = RECONNECT_SECS;
    reconnectTimer = setInterval(async () => {
      reconnectIn -= 1;
      if (reconnectIn <= 0) {
        reconnectIn = RECONNECT_SECS;
        if (await attempt()) stopReconnect();
      }
    }, 1000);
  }

  async function retryNow() {
    const fn = reconnectAttempt;
    if (!fn) return;
    reconnectIn = RECONNECT_SECS;
    if (await fn()) stopReconnect();
  }

  function cancelReconnect() {
    pendingCreds = null;
    stopReconnect();
  }

  // Try to restore the session. true = finished (connected OR expired session ->
  // login screen); false = server unreachable (retry later).
  async function attemptRestore(): Promise<boolean> {
    try {
      host.me = await restoreSession();
      await host.loadAfterAuth();
      await showSessionWarning();
      return true;
    } catch (e) {
      if (!String(e).startsWith("transient:") && String(e) !== "No saved session") host.error = String(e);
      return !String(e).startsWith("transient:");
    }
  }

  // Try login with pending credentials. false means the server is unreachable.
  async function attemptLogin(): Promise<boolean> {
    if (!pendingCreds) return true;
    try {
      host.me = await login(pendingCreds.server, pendingCreds.email, pendingCreds.password, pendingCreds.rememberSession, pendingCreds.allowInsecureServer);
      pendingCreds = null;
      password = "";
      host.error = null;
      await host.loadAfterAuth();
      await showSessionWarning();
      return true;
    } catch (e) {
      if (String(e).startsWith("transient:")) return false;
      host.error = String(e); // Rejected credentials: stop and display the error.
      pendingCreds = null;
      return true;
    }
  }

  async function handleLogin(e: Event) {
    e.preventDefault();
    loading = true;
    host.error = null;
    pendingCreds = { server, email, password, rememberSession, allowInsecureServer };
    const done = await attemptLogin();
    loading = false;
    if (!done) startReconnect(attemptLogin); // Server unreachable: reconnect automatically.
  }

  async function handleLocalSession() {
    loading = true;
    host.error = null;
    pendingCreds = null;
    stopReconnect();
    try {
      host.me = await startLocalSession();
      password = "";
      await host.loadAfterAuth();
      await showSessionWarning();
    } catch (e) {
      host.error = String(e);
      host.me = null;
    } finally {
      loading = false;
    }
  }

  async function showSessionWarning() {
    if (typeof host.me?.sessionSecurityWarning === "string") {
      await showMessage(host.me.sessionSecurityWarning, { title: "Tauridium — session security", kind: "warning" });
    }
  }

  return {
    attemptRestore,
    startReconnect,
    stopReconnect,
    get reconnecting() { return reconnecting; },
    get reconnectIn() { return reconnectIn; },
    retryNow,
    cancelReconnect,
    get hasPendingCredentials() { return pendingCreds !== null; },
    handleLogin,
    get email() { return email; },
    set email(value: typeof email) { email = value; },
    get password() { return password; },
    set password(value: typeof password) { password = value; },
    get showServer() { return showServer; },
    set showServer(value: typeof showServer) { showServer = value; },
    get server() { return server; },
    set server(value: typeof server) { server = value; },
    get allowInsecureServer() { return allowInsecureServer; },
    set allowInsecureServer(value: typeof allowInsecureServer) { allowInsecureServer = value; },
    get rememberSession() { return rememberSession; },
    set rememberSession(value: typeof rememberSession) { rememberSession = value; },
    get loading() { return loading; },
    handleLocalSession,
  };
}

export type AuthController = ReturnType<typeof createAuthController>;
