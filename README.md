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

Tauridium uses [`just`](https://github.com/casey/just) as the single development entry point.
**Windows 11 is the primary and most-tested platform; its native release binary is considered stable.**
Linux is supported secondarily and is not yet tested as completely.

### Windows 11

Use native Windows PowerShell 5.1 or PowerShell 7 (`pwsh.exe`); WSL, Bash, Git Bash,
and Nushell are not required. Install `just` with Scoop (preferred):

```powershell
scoop install just
```

If Scoop is unavailable:

```powershell
winget install --id Casey.Just --exact --source winget
```

Bootstrap and run:

```powershell
just init-self-test
just init
just run
```

`just init` validates the Windows 11 toolchain and prerequisites, including Node.js,
Python, Git, the pinned Rust/Tauri toolchain, MSVC/Windows SDK, and WebView2. Use
`just init-native` for native prerequisites only. To forbid system changes, run
`tools/init.ps1 -NoSystemChanges` from PowerShell.

### Linux

Linux is the second-most-tested platform, but coverage is not exhaustive. Install
Rust via rustup, Node.js 20+, Python 3, and `just`, then run:

```sh
just init
just run
```

`just init` can install missing Tauri native packages on supported Debian/Ubuntu,
Fedora/RHEL, Arch/Manjaro, Alpine, and openSUSE families. Set
`TAURIDIUM_INIT_SYSTEM_DEPS=0` to forbid automatic system-package changes.

### macOS

macOS is not a project focus and is not tested. Contributions and independent testing
are welcome; the project does not intentionally prevent anyone from making Tauridium
work there.

### Validate changes

```text
just fmt-check
just lint
just check
just test
just build
```

## Releases

Release notes come from [`CHANGELOG.md`](CHANGELOG.md). For `X.Y.Z`:

1. Move the relevant `Unreleased` entries into `## [X.Y.Z] - YYYY-MM-DD` in English.
2. Run `node tools/sync_version.mjs X.Y.Z` and commit the release state.
3. Create the annotated `vX.Y.Z` tag on that clean commit.
4. Run `just release`; only after it passes, push `master` and the tag.

A `v*` tag triggers the GitHub release workflow. CI covers formatting, Clippy, Rust and
frontend checks/tests/builds, and platform compile checks; Windows CI also exercises the
native PowerShell workflow.

Release packaging is deterministic. Source ZIPs contain the complete `.git` history plus
a SHA-256 source manifest. Native runtime ZIPs are target-qualified. If a native runtime
cannot be proven in the current environment, `just package-handoff` creates an explicit
`run-build-handoff` ZIP instead of pretending a binary was built.

## Licence

Copyright © 2026 [Daniel Braniewski](https://brani.dev)

Tauridium is free software released under the [MIT License](LICENSE). You may use, copy,
modify, merge, publish, distribute, sublicense, and/or sell copies subject to the complete
license terms. The software is provided **AS IS**, without warranty of any kind.