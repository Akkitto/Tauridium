<p align="center">
  <img src="src-tauri/icons/icon.png" width="128" alt="Tauridium icon" />
</p>

<h1 align="center">Tauridium</h1>

<p align="center">
  <a href="https://github.com/Akkitto/Tauridium/releases/latest"><img src="https://img.shields.io/github/v/release/Akkitto/Tauridium?sort=semver" alt="Latest release" /></a>
  <a href="https://github.com/Akkitto/Tauridium/releases"><img src="https://img.shields.io/github/downloads/Akkitto/Tauridium/total?label=downloads%20total" alt="Total downloads (all releases)" /></a>
  <a href="https://github.com/Akkitto/Tauridium/releases/latest"><img src="https://img.shields.io/github/downloads/Akkitto/Tauridium/latest/total?label=downloads%20latest" alt="Downloads (latest release)" /></a>
  <img src="https://img.shields.io/badge/Maintained%3F-yes-green.svg" alt="Maintained: yes" />
  <a href="https://brani.dev"><img src="https://img.shields.io/badge/author-Daniel%20Braniewski-blue" alt="Author: Daniel Braniewski" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT" /></a>
  <img src="https://img.shields.io/badge/contributions-welcome-brightgreen.svg" alt="Contributions welcome" />
  <a href="https://github.com/Akkitto/Tauridium/commits"><img src="https://badgen.net/github/last-commit/Akkitto/Tauridium" alt="Latest commit" /></a>
</p>

Forget Franz, Ferdi, Ferdium and the rest. This is THE absolute best web app hub of all. I swear. Performant, beautiful and it just works™.

Speedy Gonzales level desktop client for [Ferdium](https://ferdium.org) style web app service-workspace management & usage, built with **Tauri v2** (Rust + native WebView) instead of Electron. Use a Ferdium server for synchronised data, or run accountless with services and workspaces stored locally.

## Why

I got sick and tired of the official [Ferdium](https://ferdium.org) client having long-standing bugs in the most basic features, like re-ordering services, workspace ordering & switching and numerous other functionalities. It feels like vibe-coded slop, before LLM based coding was even possible.

If that wasn't bad enough, Electron made everything so extremely fat, that I had to disable a lot of web apps in the client, because Ferdium was slowing them down so much, to the point of unability of use. Then, I asked myself, what even the point of the desktop client is, if I cannot even use some of the most important web apps in it.

Within a fairly short amount of time, I pimped up Tauridium to be simply overall better, more reliable and bug-free for the most important features, I use sometimes, frequently and every day. All possible due to spec-driven AI Engineering, rather than blindfolded vibe-coding.

To my knowledge, this is, as of now, the only fully open source, fully free of cost web app hub desktop application, which does *NOT* rely on Electron or be otherwise super buggy and badly designed.

## Features

- **Accountless local mode** - no Ferdium account, server, or token required
- **Local custom recipes** - add folders manually, import them through the GUI, or create them with the built-in lightweight recipe creator
- **Custom Website** fallback - add any HTTP(S) site even when no preset recipe exists
- Bundled local recipes for common AI, developer, observability, forge, router, and web services
- Optional Ferdium server sign-in - account, services and workspaces stay synced
- Each service in an **isolated, persistent session** (native WebView)
- **Native notifications** + dock unread badges
- **Close-to-tray**, run in background, launch at login
- **Persistent window state** - restores the main window's size, screen position, maximized state, and fullscreen state across tray hides and full restarts
- **Per-service settings** (name, custom URL, team, notifications, mute, badges,
  hibernation, dark mode, favicon, proxy, custom user agent…) - synced in server
  mode and persisted locally in accountless mode
- **App settings in tabs**: General / Services / Appearance / Keybinds / Sandbox / Privacy / Backup / Audit log / Advanced / Updates / About, using a consistent settings-card layout with responsive control alignment
- **Sidebar customization** aligned with Ferdium (icon size, service-list alignment, grayscale + dim level, fixed 160-420 px widths with Slim / Normal / Wide/custom presets, or a responsive percentage of the window)
- Theme (system / dark / **Black OLED** / light) + preset or custom accent colors using a native color picker and HSL sliders
- **Configurable keybindings** for navigation and application actions, including `Ctrl+D` workspace switching, `Ctrl+S` service search, `Ctrl+Shift+N` workspace creation, and optional two-stroke chords
- **Shared sandboxes** that let compatible services deliberately share one persistent webview data store/login session while unassigned services remain isolated; assignments can be changed globally or directly from each service settings page without navigating away from Settings, and one or all sandboxes can be exported with their services and referenced custom recipes
- Scalable Settings → Services management with direct **Create service**, search, workspace filtering, 100-row paging, and filtered reordering that preserves hidden global-order slots
- Optional Advanced setting for direct sidebar service drag-and-drop ordering (enabled by default), using the same verified canonical service order and preserving hidden/filter-excluded slots; Shift+click selects a contiguous temporary drag group, and the empty sidebar area below the last service remains a drop-at-end target; the main shell disables Tauri native drag/drop interception so standard HTML5 dragging reaches the frontend reliably on Windows/WebView2
- **Workspace icons** selectable from resolved service icons or fetched from an arbitrary HTTP(S) image/website URL; selected icons are stored self-contained and travel with backups and portable workspace/sandbox exports
- **Browser-style download controls** with a configurable global download directory, optional Save prompt for every download, server-suggested filename/extension preservation, and per-service/per-workspace overrides with service → workspace → global precedence
- Per-service **Open links externally** routing: disabled/default keeps ordinary new-window HTTP(S) links in that service webview, while enabled sends them directly to the operating system browser; Windows uses the shell API without a transient `cmd.exe` window
- The original styled per-service right-click menu is the default; **Advanced → Service context menu** can switch to the native always-in-front fallback when webview layering matters more than appearance
- **Portable workspace exports** for one or all workspaces, including referenced services, sandboxes, assignments, custom recipes, and self-contained workspace icons
- **Hardened backups** with integrity-verified transactional restore, selectable automatic-backup directory, startup/daily/weekly/monthly scheduling, count/age/combined/tiered retention, and pre-restore recovery points
- **Local structured audit log** for settings, backup/restore/retention/export operations, warnings, and failures, with secret-field redaction and bounded rotation

## Tech stack

- **Tauri v2** (Rust) - multi-webview, tray, native notifications
- **Svelte 5** + TypeScript - the shell UI
- **reqwest** (rustls) - server calls from Rust (no CORS, token kept out of JS)
- Vendored + patched **wry** - unfreezes `window.ipc` so Electron-style recipe
  IPC works (e.g. Synology Chat)

## Develop

Tauridium supports first-class native development on Linux, macOS, and Windows 11.
The project uses [`just`](https://github.com/casey/just) as the command runner.

### Windows 11 - PowerShell only

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
ARM64), then - once every build passes - publishes a GitHub Release with the
bundles attached.

Release notes come from [`CHANGELOG.md`](CHANGELOG.md): the workflow extracts the
section matching the tagged version and uses it as the GitHub Release body. So,
before tagging:

1. Move the relevant `## [Unreleased]` entries into a new `## [X.Y.Z] - DATE`
   section (**write them in English** - this is the project convention).
2. Bump the version in `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml` and
   `src-tauri/Cargo.lock`, then commit.
3. Tag and push:

```text
git tag -a v0.5.0 -m "Tauridium 0.5.0"
git push origin v0.5.0
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

Runtime ZIPs are target-qualified using the binary's actual Rust compilation target, so artifacts from different native builds can coexist in the same `release/` directory. Common examples are `tauridium-0.5.0-run-win-x64.zip`, `tauridium-0.5.0-run-win-arm64.zip`, `tauridium-0.5.0-run-linux-x64.zip`, `tauridium-0.5.0-run-linux-arm64.zip`, and `tauridium-0.5.0-run-macos-arm64.zip`. Source and documentation ZIP names remain target-neutral.

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

## Licence

Copyright © 2026 [Daniel Braniewski](https://brani.dev)

Tauridium is free software released under the [MIT License](LICENSE). You may use, copy,
modify, merge, publish, distribute, sublicense, and/or sell copies subject to the complete
license terms. The software is provided **AS IS**, without warranty of any kind.