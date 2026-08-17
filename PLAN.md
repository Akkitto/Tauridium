# Tauridium — Design Plan

> Goal: a **lightweight alternative Ferdium client** (Tauri v2, Rust + native webview)
> replacing the Electron client while **remaining connected to the Ferdium server**
> (`api.ferdium.org` or self-hosted): same account and synchronized services/workspaces.
> Primary original target: **macOS** (Darwin), with Windows now supported as a first-class platform.

## 1. Principle: do not reinvent Ferdium; provide a lighter client

- Keep the **Ferdium server** as the source of truth for accounts, services, workspaces, and recipes.
- Replace only the **Electron client** with a **Tauri** client.
- Maximize reuse where licensing permits:
  - **ferdium-app** is **Apache-2.0**: port the relevant server API and model logic
    (service, recipe, workspace, URL calculation) from TS/Electron into Tauridium.
  - **ferdium-recipes** recipes are **MIT**: reuse the catalog metadata and `webview.js`
    integrations through a compatible **`Ferdium` shim**.
- Do not retain the Electron runtime or the embedded local Node server; Tauridium talks
  directly to the remote Ferdium server with JWT authentication.

## 2. Ferdium server API surface

Base: `https://<server>/v1/`. Authentication: `POST /v1/auth/login` returns a **JWT**,
which is then sent as `Authorization: Bearer <jwt>`.

| Method | Route | Use |
|---|---|---|
| POST | `/v1/auth/login` | login (email/password) → JWT |
| GET/PUT | `/v1/me` | user account |
| GET | `/v1/me/services` | user service list |
| POST / PUT | `/v1/service[/:id]` | create/update a service |
| GET | `/v1/icon/:id` | service icon |
| GET | `/v1/workspace` | workspace list |
| POST / PUT | `/v1/workspace[/:id]` | create/update a workspace |
| GET | `/v1/recipes/download/:recipe` | download a recipe package |
| GET | `/v1/recipes/search` · `/recipes/popular` | search/popular recipes |

Architecture note: the Electron client routes through a small local Node server using
`X-Ferdium-Local-Token`. Tauridium bypasses that hop and talks directly to the remote
server using the JWT.

## 3. Tauri v2 technical model

| Component | Status | Implication |
|---|---|---|
| Multiple webviews in one window (`Window::add_child`) | ✅ `unstable` API | Create sequentially/lazily |
| Per-service session isolation | ✅ via `data_store_identifier` | One stable UUID per service |
| Native notifications | ✅ notification plugin | Recipe shim forwards notifications |
| Unified dock badge / unread count | custom | Aggregate service counts |
| Recipe `webview.js` expecting Electron integration | compatibility layer | `Ferdium` shim and per-service adaptation |

## 4. Target architecture

```text
┌──────────────────────────── Tauri window ──────────────────────────────┐
│  Shell UI: workspace/service sidebar and unread state                  │
│  ┌──────┐  ┌───────────────────────────────────────────────────────┐   │
│  │ side │  │ Active service webview                                │   │
│  │ bar  │  │ - data_store_identifier = UUID(serviceId)             │   │
│  │      │  │ - recipe user agent                                   │   │
│  │      │  │ - Ferdium shim + webview.js (badges/notifs → IPC)     │   │
│  └──────┘  └───────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
   Rust core: windows/webviews, sessions, native notifications, dock badge, disk cache
   Sync layer: JWT login, services, workspaces, recipe download, service URL calculation
   ▲ synchronizes with ▼
   ╔════════════════ Ferdium server (api.ferdium.org or self-hosted) ═════════════════╗
```

## 5. Stack

- **Backend**: Rust + **Tauri v2** (`unstable` webview support), notification and updater plugins.
- **Shell UI + sync layer**: **TypeScript + Vite + Svelte**.
- **Persistence**: session/settings files plus recipe and service caches; stronger credential storage
  can be introduced where platform support warrants it.
- **Sessions**: `data_store_identifier` derived from each `serviceId`.

## 6. Delivery phases

### Phase 0 — Risk-reduction spike ✅ COMPLETE
Validated multiple webviews, `data_store_identifier` isolation, and persistence.
Key finding: WKWebView ignores `data_directory`; use `data_store_identifier` on macOS.

### Phase 1 — Server connection vertical slice ✅ COMPLETE
- Login using server URL + credentials.
- Restore JWT session and query `/v1/me`, services, and workspaces.
- Display synchronized services/workspaces in the sidebar.

### Phase 2 — Service rendering ✅ COMPLETE
- Each service renders in an isolated child webview.
- Resolve URLs from recipe configuration and service overrides.
- Cache recipes from `ferdium/ferdium-recipes`.
- Apply service/browser compatibility shims where required.
- Vendor the necessary Wry patch for mutable IPC compatibility.

### Phase 3 — Notifications and badges ✅ IMPLEMENTED
- Compatible recipe `webview.js` runtime and badge plumbing.
- Native notifications.
- Aggregate unread state and dock badge where supported.

### Phase 4 — Parity and usability ✅ IN PROGRESS
- Service/workspace editing.
- Per-service dark mode.
- Shortcuts, startup behavior, reload/debug controls, and offline resilience.

### Phase 5 — Local recipes ✅ COMPLETE (0.3.0)
- Built-in **Custom Website** fallback when no preset matches.
- Merged remote, bundled, and user recipe catalogs.
- Local `recipes/<id>/package.json` directory under Tauridium's OS configuration directory.
- GUI folder/package import and lightweight recipe creator with optional `icon.svg`/`webview.js`.
- Bundled NanoGPT, Chutes, and OpenCode Web recipes.
- Services created from Tauridium-local recipes remain local even while signed into a server.

### Phase 6 — Production runtime integrity ✅ COMPLETE (0.3.5)
- Production runtimes are built through `cargo tauri build`, never raw `cargo build --release`.
- Raw release-profile Cargo builds fail fast if Tauri is in development mode.
- Packaged release workflows use `frontendDist`, while `devUrl` remains development-only.
- Current tracked project text is English-only and guarded by an automated audit.

## 7. Known difficult areas

| Area | Approach |
|---|---|
| Recipes whose `webview.js` expects Node/Electron APIs | compatible `Ferdium` shim and targeted adaptation |
| Final service URL calculation | port Ferdium model behavior and test overrides |
| Multi-webview lifecycle races | sequential creation, lazy loading, in-flight guards |
| Authentication/keychain | progressively strengthen platform credential storage |
| External OAuth/popups | preserve shared service session and route normal external links to the system browser |

## 8. Sources

- Pake — https://github.com/tw93/pake
- Ferdium app — https://github.com/ferdium/ferdium-app
- Ferdium server — https://github.com/ferdium/ferdium-server
- Ferdium recipes — https://github.com/ferdium/ferdium-recipes
- Tauri — https://v2.tauri.app/
