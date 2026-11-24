<script lang="ts">  import type { AuthController } from "../lib/controllers/auth.svelte";

  import { DEFAULT_SERVER } from "../lib/api";

  interface Props {
    auth: AuthController;
    booting: boolean;
    error: string | null;
  }

  let {
    auth,
    booting,
    error,
  }: Props = $props();

</script>

{#if booting}
  <main class="login">
    <div class="card"><p class="sub">Restoring session…</p></div>
  </main>
{:else if auth.reconnecting}
  <main class="login">
    <div class="card">
      <h1>Tauridium</h1>
      <p class="notice">⚠️ Can't reach the server — it may be temporarily down.</p>
      <p class="sub">Retrying automatically in {auth.reconnectIn}s…</p>
      <button class="primary" onclick={auth.retryNow}>Retry now</button>
      <button class="link" onclick={auth.cancelReconnect}>
        {auth.hasPendingCredentials ? "Cancel" : "Sign in with a different account"}
      </button>
    </div>
  </main>
{:else}
  <main class="login">
    <form class="card" onsubmit={auth.handleLogin}>
      <h1>Tauridium</h1>
      <p class="sub">Lightweight Ferdium client — use a server or keep everything local</p>
      <label>
        Email
        <input type="email" bind:value={auth.email} autocomplete="username" required />
      </label>
      <label>
        Password
        <input
          type="password"
          bind:value={auth.password}
          autocomplete="current-password"
          required
        />
      </label>
      <button type="button" class="gear" onclick={() => (auth.showServer = !auth.showServer)}>
        ⚙︎ Server {auth.showServer ? "▲" : "▼"}
      </button>
      {#if auth.showServer}
        <label>
          Server URL
          <input type="url" bind:value={auth.server} placeholder={DEFAULT_SERVER} />
        </label>
        <label class="login-option">
          <input type="checkbox" bind:checked={auth.allowInsecureServer} />
          Allow non-loopback HTTP on a trusted development network (exposes account credentials).
        </label>
      {/if}
      <label class="login-option">
        <input type="checkbox" bind:checked={auth.rememberSession} />
        Remember using OS credential store
      </label>
      <p class="local-note">Unchecked: account token stays in memory for this run only. No plaintext fallback is used if the OS store is unavailable.</p>
      {#if error}<p class="error">{error}</p>{/if}
      <button class="primary" type="submit" disabled={auth.loading}>
        {auth.loading ? "Signing in…" : "Sign in"}
      </button>
      <div class="local-separator"><span>or</span></div>
      <button class="local-mode" type="button" disabled={auth.loading} onclick={auth.handleLocalSession}>
        Use Tauridium without an account
      </button>
      <p class="local-note">Services and workspaces stay on this device. No Ferdium server is used.</p>
    </form>
  </main>
{/if}

<style>

  button, input { font-family: inherit; }
  .login { display: grid; place-items: center; height: 100vh; }
  .login-option { display: flex; align-items: flex-start; gap: 0.5rem; }
  .login-option input[type="checkbox"] { width: auto; margin: 0.2rem 0 0; flex: none; }
  .card {
    background: var(--card); padding: 28px; border-radius: 14px; width: 320px;
    display: flex; flex-direction: column; gap: 12px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
  }
  .card h1 { margin: 0; font-size: 24px; }
  .sub { margin: 0 0 6px; color: var(--muted); font-size: 13px; }
  label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); }
  input {
    padding: 9px 11px; border-radius: 8px; border: 1px solid var(--border2);
    background: var(--input); color: var(--text); font-size: 14px;
  }
  .primary {
    padding: 10px 14px; border: none; border-radius: 8px; background: var(--accent);
    color: var(--accent-fg); font-weight: 700; cursor: pointer;
  }
  .primary:disabled { opacity: 0.6; cursor: default; }
  .local-separator {
    display: flex; align-items: center; gap: 10px; color: var(--muted2); font-size: 11px;
  }
  .local-separator::before, .local-separator::after {
    content: ""; flex: 1; height: 1px; background: var(--border);
  }
  .local-mode {
    padding: 10px 14px; border: 1px solid var(--border2); border-radius: 8px;
    background: var(--input); color: var(--text); font-weight: 700; cursor: pointer;
  }
  .local-mode:hover { background: var(--hover); }
  .local-mode:disabled { opacity: 0.6; cursor: default; }
  .local-note { margin: -3px 0 0; color: var(--muted2); font-size: 11px; line-height: 1.4; }
  .gear { align-self: flex-start; background: none; border: none; color: var(--muted); cursor: pointer; font-size: 12px; padding: 0; }
  .error { color: #ff8a8a; font-size: 13px; margin: 4px 0; }
  .link { background: none; border: none; color: var(--link); cursor: pointer; font-size: 12px; text-decoration: underline; }
  .notice {
    margin: 0; padding: 9px 11px; border-radius: 8px; font-size: 12px; line-height: 1.4;
    background: rgba(217, 119, 6, 0.12); border: 1px solid rgba(217, 119, 6, 0.35); color: var(--text2);
  }
  .primary:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 2px;
  }

</style>
