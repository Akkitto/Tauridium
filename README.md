<p align="center">
  <img src="src-tauri/icons/icon.png" width="128" alt="Tauridium icon" />
</p>

<h1 align="center">Tauridium</h1>

<p align="center">
  <a href="https://github.com/Gizmo091/Tauridium/releases/latest"><img src="https://img.shields.io/github/v/release/Gizmo091/Tauridium?sort=semver" alt="Latest release" /></a>
  <a href="https://github.com/Gizmo091/Tauridium/releases"><img src="https://img.shields.io/github/downloads/Gizmo091/Tauridium/total?label=downloads%20total" alt="Total downloads (all releases)" /></a>
  <a href="https://github.com/Gizmo091/Tauridium/releases/latest"><img src="https://img.shields.io/github/downloads/Gizmo091/Tauridium/latest/total?label=downloads%20latest" alt="Downloads (latest release)" /></a>
  <img src="https://img.shields.io/badge/Maintained%3F-yes-green.svg" alt="Maintained: yes" />
  <img src="https://img.shields.io/badge/maintainer-Mathieu%20Vedie-blue" alt="Maintainer: Mathieu Vedie" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT" /></a>
  <img src="https://img.shields.io/badge/contributions-welcome-brightgreen.svg" alt="Contributions welcome" />
  <a href="https://github.com/Gizmo091/Tauridium/commits"><img src="https://badgen.net/github/last-commit/Gizmo091/Tauridium" alt="Latest commit" /></a>
</p>

<p align="center">
  <a href="https://www.buymeacoffee.com/mathieuvedie"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" height="32" /></a>
</p>

A lightweight desktop client for [Ferdium](https://ferdium.org), built with
**Tauri v2** (Rust + native WebView) instead of Electron. Use a Ferdium server
for synchronized data, or run accountless with services and workspaces stored locally.

> ⚡️ **This project is vibe-coded.** It was built end-to-end in a
> pair-programming session with an AI assistant (Claude / Claude Code). The
> architecture, code, icon and CI/CD were shaped conversationally rather than
> from a formal spec — treat it accordingly. 🤖

The name is a nod to the lineage **Franz → Ferdi → Ferdium**, with the `-ium`
suffix kept and **Tauri** baked in.

## Why

Ferdium is great, but Electron makes it heavy. Tauridium renders each service in
its own **isolated native WebView** (per-service persistent sessions). Server mode
uses the Ferdium REST API; accountless mode keeps service/workspace state local.

## Features

- **Accountless local mode** — no Ferdium account, server, or token required
- **Local custom recipes** — add folders manually, import them through the GUI, or create them with the built-in lightweight recipe creator
- **Custom Website** fallback — add any HTTP(S) site even when no preset recipe exists
- Bundled AI recipes for **NanoGPT**, **Chutes**, and **OpenCode**
- Optional Ferdium server sign-in — account, services and workspaces stay synced
- Each service in an **isolated, persistent session** (native WebView)
- **Native notifications** + dock unread badges
- **Close-to-tray**, run in background, launch at login
- **Persistent window state** — restores the main window's size, screen position, maximized state, and fullscreen state across tray hides and full restarts
- **Per-service settings** (name, custom URL, team, notifications, mute, badges,
  hibernation, dark mode, favicon, proxy, custom user agent…) — synced in server
  mode and persisted locally in accountless mode
- **App settings in tabs**: General / Services / Appearance / Keybinds / Sandbox / Privacy / Backup / Audit log / Advanced / Updates / About, using a consistent settings-card layout with responsive control alignment
- **Sidebar customization** aligned with Ferdium (icon size, service-list alignment, grayscale + dim level, fixed 160–420 px widths with Slim / Normal / Wide/custom presets, or a responsive percentage of the window)
- Theme (system / dark / **Black OLED** / light) + preset or custom accent colors using a native color picker and HSL sliders
- **Configurable keybindings** for navigation and application actions, including `Ctrl+D` workspace switching, `Ctrl+S` service search, and optional two-stroke chords
- **Shared sandboxes** that let compatible services deliberately share one persistent webview data store/login session while unassigned services remain isolated; one or all sandboxes can be exported with their services and referenced custom recipes
- Scalable Settings → Services management with search, workspace filtering, 100-row paging, and filtered reordering that preserves hidden global-order slots
- **Portable workspace exports** for one or all workspaces, including referenced services, sandboxes, assignments, and custom recipes
- **Hardened backups** with integrity-verified transactional restore, selectable automatic-backup directory, startup/daily/weekly/monthly scheduling, count/age/combined/tiered retention, and pre-restore recovery points
- **Local structured audit log** for settings, backup/restore/retention/export operations, warnings, and failures, with secret-field redaction and bounded rotation

## Accountless local mode

On the sign-in screen, choose **Use Tauridium without an account**. Tauridium
stores services and workspaces in `local_profile.json` under its OS application-data
directory and restores that local session without contacting a Ferdium server.

Remote recipe discovery still uses the public
[`ferdium/ferdium-recipes`](https://github.com/ferdium/ferdium-recipes) repository
and is cached locally. Tauridium's bundled recipes and user-owned local recipes remain
available without that catalog, so accountless mode can add those recipes offline; the
actual service website still needs whatever network connectivity that site requires.

## Local recipes

Open **Add a service** to use any of these paths:

- search the normal recipe catalog; when nothing matches, choose **Add a custom website**;
- choose **Custom website** directly and enter any HTTP(S) URL;
- choose **Recipe creator** to save a reusable local recipe;
- choose **Import folder…** for an existing recipe folder;
- choose **Import package.json…** for a recipe package file;
- place recipe folders manually in the local recipe directory shown by the Add Service UI, then press **Refresh**.

The on-disk layout is deliberately small and Ferdium-compatible at its core:

```text
<Tauridium OS config>/recipes/<recipe-id>/
  package.json     # required; config.serviceURL must be HTTP(S)
  icon.svg         # optional
  webview.js       # optional
```

`package.json` needs a `config.serviceURL`; `config.hasCustomUrl` and
`config.hasTeamId` are optional booleans. Tauridium validates recipe ids before
filesystem access, reserves its bundled recipe ids, and writes GUI-created recipes
atomically. A local `webview.js` runs inside the service page and can access its DOM,
so only use scripts you trust.

Bundled local recipes include **Custom Website**, **NanoGPT**, **Chutes**, and
**OpenCode**. OpenCode defaults to `https://opencode.ai/go`. Set its website-specific
workspace ID to use `https://opencode.ai/workspace/{teamId}/go`, or override the URL
with a custom URL when needed.

Local recipes are owned by Tauridium even during a Ferdium-server session. They are
therefore not sent to the server as unknown recipe ids and are merged into the service
list locally. Ordinary accountless-mode services are not implicitly overlaid after a
server login.

## Window state

Tauridium persists the main window's normal size, screen position, maximized state, and fullscreen state in `window-state.json` under the OS application-config directory. The state is saved before hiding to the tray and before quitting, then restored before the window is shown again and on the next launch.

Visibility is intentionally excluded from persisted window state so **Start minimized** remains an independent explicit setting. Persistence is limited to the main Tauridium window; service child webviews are not treated as desktop windows. If saved coordinates no longer intersect an available monitor, the window-state restore logic falls back instead of restoring the window off-screen.

## Backups

Open **Settings → Backup** to export Tauridium-owned local state to one portable
`tauridium-backup-YYYY-MM-DD.json` file. The backup contains app settings, local
services/workspaces, and complete custom recipes including optional `icon.svg` and
`webview.js` files.

**Restore backup…** validates the backup schema, settings, local profile, and every recipe
before writing persistent state. Restoring replaces local settings/services/workspaces and
overwrites custom recipes with matching ids; unrelated existing custom recipes are retained.
The app reloads after a successful restore.

Ferdium login/session credentials, website cookies/storage, remote recipe caches, and monitor-specific `window-state.json` geometry are intentionally excluded. Window geometry remains local to each installation so restoring a portable backup on a different display setup cannot import stale monitor coordinates. A backup can still contain sensitive local service configuration (for example proxy credentials), so store backup files accordingly.

## About and project links

**Settings → About** presents Tauridium's application identity, installed version, project
summary, MIT license, maintainer and contributor credits, and the main open-source project
destinations. Source, release, issue, license, contributor, Tauri, and Ferdium links open in
the operating system's default browser rather than inside a service webview.

## Tech stack

- **Tauri v2** (Rust) — multi-webview, tray, native notifications
- **Svelte 5** + TypeScript — the shell UI
- **reqwest** (rustls) — server calls from Rust (no CORS, token kept out of JS)
- Vendored + patched **wry** — unfreezes `window.ipc` so Electron-style recipe
  IPC works (e.g. Synology Chat)

## Develop

Tauridium supports first-class native development on Linux, macOS, and Windows 11.
The project uses [`just`](https://github.com/casey/just) as the command runner.

### Windows 11 — PowerShell only

No WSL, Git Bash, Bash, or Nushell is required. Run the workflow from Windows
PowerShell 5.1 or PowerShell 7 (`pwsh.exe`). `just` executes Windows recipes with
the built-in `powershell.exe`, so a fresh Windows 11 machine can bootstrap before
PowerShell 7 or any Unix shell exists.

If `just` is not installed yet, prefer Scoop:

```powershell
scoop install just
```

If Scoop is unavailable, use WinGet as the fallback:

```powershell
winget install --id Casey.Just --exact --source winget
```

Validate the bootstrap itself, then initialize and run Tauridium:

```powershell
just init-self-test
just init
just run
```

On Windows, `just init` verifies Windows 11 and reloads the persisted Machine/User
PATH before prerequisite discovery so tools installed by a previous bootstrap run
are immediately visible. Scoop is the preferred package manager for Node.js LTS,
Python 3, Git, and rustup; WinGet is the fallback. System-integrated Microsoft C++
Build Tools, the Windows 11 SDK, and WebView2 Runtime use the Windows/WinGet path.
After every package-manager change, the initializer reloads PATH and validates the
required executable instead of treating a package-manager exit code alone as the
source of truth. Python-dependent Windows recipes use `tools/python.ps1`, which
resolves a usable Python 3 through `py.exe`, `python.exe`, or `python3.exe`. The
initializer also installs `cargo-tauri` and `cargo-audit` when absent, ensures
`rustfmt`/Clippy are present, checks the VBSCRIPT optional feature needed for MSI
bundling, runs reproducible `npm ci`, audits high-severity npm advisories, and
verifies esbuild locally. The checked-in `.vsconfig` covers both x64 and ARM64
MSVC tools. The Windows initializer is deliberately function-free and executes
prerequisite handling linearly for compatibility with Windows PowerShell 5.1.
Expected failures from native capability probes are isolated from strict
PowerShell error handling so a missing tool can reach its installation branch
instead of aborting initialization.

Use `just init-native` to validate/install only the native Windows prerequisites.
Use `powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/init.ps1 -NoSystemChanges` when system changes
must be forbidden; the initializer will fail with the missing prerequisite instead.

Windows prerequisites follow Tauri's documented requirements:
https://v2.tauri.app/start/prerequisites/

### Linux / macOS

Requirements: Rust (stable), Node 20+, Python 3, and `just`. On Linux, `just init`
detects and installs missing Tauri v2 native prerequisites for supported
Debian/Ubuntu, Fedora/RHEL, Arch/Manjaro, Alpine, and openSUSE families. It
also verifies the Tauri v2 Cargo CLI and installs `tauri-cli` with Cargo when
`cargo tauri` is unavailable. It invokes `sudo` only when system packages are
actually missing.

```sh
just init
just run
```

`just init` performs reproducible `npm ci`, checks for high-severity npm
advisories, verifies the reviewed `esbuild` install-script policy, and executes the
local esbuild binary through `npm exec --offline` as a bootstrap smoke test. Set
`TAURIDIUM_INIT_SYSTEM_DEPS=0` to forbid automatic Linux system-package changes.
Debian/Ubuntu `libxdo-dev` is validated by compiling/linking a tiny probe because
Debian does not ship `xdo.pc`; the remaining native libraries are checked through
`pkg-config`.

### Tests

The same commands work from PowerShell on Windows and the native shell on Unix:

```text
just check
just test
```

## Build

```text
cargo tauri build              # release bundle for your platform
cargo tauri build --debug      # faster debug bundle
```

On macOS, signing locally with your own identity avoids repeated Keychain
prompts (WebView session stores are Keychain-encrypted; a stable signature makes
"Always Allow" stick):

```bash
APPLE_SIGNING_IDENTITY="Apple Development: …" cargo tauri build --debug
```

## Releases

Pushing a `v*` tag triggers GitHub Actions, which runs the tests, builds for
**macOS** (universal), **Linux** (x86_64 / ARM64) and **Windows** (x86_64 /
ARM64), then — once every build passes — publishes a GitHub Release with the
bundles attached.

Release notes come from [`CHANGELOG.md`](CHANGELOG.md): the workflow extracts the
section matching the tagged version and uses it as the GitHub Release body. So,
before tagging:

1. Move the relevant `## [Unreleased]` entries into a new `## [X.Y.Z] - DATE`
   section (**write them in English** — this is the project convention).
2. Bump the version in `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml` and
   `src-tauri/Cargo.lock`, then commit.
3. Tag and push:

```text
git tag -a v0.4.12 -m "Tauridium 0.4.12"
git push origin v0.4.12
```

If no matching `CHANGELOG.md` section exists, the workflow falls back to generic
notes (and logs a warning).

Continuous integration (`cargo fmt -- --check` · Clippy · Rust tests · release build ·
svelte-check · Vitest · frontend build) runs on every push and pull request. A dedicated Windows
job executes the full local workflow under `pwsh`, including `just init-native`,
`just check`, `just test`, `just build`, and `just package`.

For a local validated release, run:

```text
just release
```

Runtime ZIPs are target-qualified using the binary's actual Rust compilation target, so artifacts from different native builds can coexist in the same `release/` directory. Common examples are `tauridium-0.4.12-run-win-x64.zip`, `tauridium-0.4.12-run-win-arm64.zip`, `tauridium-0.4.12-run-linux-x64.zip`, `tauridium-0.4.12-run-linux-arm64.zip`, and `tauridium-0.4.12-run-macos-arm64.zip`. Source and documentation ZIP names remain target-neutral.

`tools/package_release.py --build-handoff` emits an explicit `run-build-handoff` ZIP when a native runtime cannot be proven in the current environment. It never labels that archive as a validated executable. `tools/package_release.py` also accepts repeated `--runtime` arguments and groups supplied binaries by their reported compilation target, emitting one run ZIP per target instead of overwriting a generic runtime archive.

The release recipe is deliberately non-mutating: it requires a clean Git worktree before
validation, checks Rust formatting without rewriting source files, runs Cargo gates with the
existing lockfile, verifies the worktree is still clean after the build, then packages the
release. Use `just fmt` separately when source formatting should actually be changed.

Official source ZIPs include both the complete `.git` directory and
`.tauridium-source-manifest.json`. Extracting a source ZIP therefore yields a normal Git
checkout with the release commit/tag/history available to `git log`, while the manifest
independently verifies every packaged tracked source file by SHA-256. Source packaging
requires a real, clean Git checkout so release archives cannot silently omit history.

## Install

Grab the asset for your platform from the
[latest release](../../releases/latest).

**macOS** builds are **unsigned** (no paid Apple Developer account), so Gatekeeper
blocks them on first launch (*"Tauridium can't be opened…"*). Open the `.dmg`,
drag Tauridium to Applications, then either:

- **macOS ≤ 14**: right-click the app → **Open** → confirm; or
- **macOS 15+**: try to open it, then **System Settings → Privacy & Security →
  Open Anyway**; or
- run once in Terminal: `xattr -cr /Applications/Tauridium.app`

**Linux**: `.deb` / `.rpm` / `.AppImage` (x86_64 and ARM64).
**Windows**: `.msi` or `-setup.exe` (x64 and ARM64).

## Known limitations

- **Passkeys / biometric sign-in (Touch ID, security keys) don't work.** This is
  a WebKit limitation: WebAuthn is disabled in an embedded `WKWebView` unless the
  app holds Apple's restricted *Web Browser* entitlement (granted only to real
  browsers). It affects every service, not just Google. **Workaround:** on the
  login screen pick "try another way" and use a **password + an authenticator
  code (TOTP) or a phone prompt** instead of a passkey. See
  [tauri-apps/tauri#7926](https://github.com/tauri-apps/tauri/issues/7926).
- **The native right-click "Download Image" doesn't work.** WKWebView handles
  that context-menu item through an internal path that isn't exposed to the app.
  Downloads triggered from within a service (in-page download buttons, e.g.
  WhatsApp or ChatGPT) do work and save to your Downloads folder. **Workaround:**
  use the service's own download button instead of the right-click menu.

## Status & caveats

- Vibe-coded personal project — expect rough edges.
- **Windows 11, Linux, and macOS are first-class development/build targets.**
  Platform-specific packaging and signing constraints still apply.
- macOS builds are **unsigned** (see [Install](#install)) — proper Developer ID
  signing + notarization needs a paid Apple Developer account, wired in CI and
  ready to activate via secrets.
- Not affiliated with Ferdium.

### Bootstrap identity

`just init` prints its Tauridium release version before making system changes and aborts when the platform initializer and `package.json` come from different releases. Extract each release into a new empty directory rather than overlaying an older tree. On Windows use `just init-native`; on Linux use `python3 tools/init.py --native-only` to validate/install only native Tauri prerequisites.
