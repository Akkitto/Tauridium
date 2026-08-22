<p align="center">
  <img src="src-tauri/icons/icon.png" width="128" alt="Tauridium icon" />
</p>

<h1 align="center">Tauridium</h1>

<p align="center">
  <a href="https://github.com/Akkitto/Tauridium/releases/latest"><img src="https://img.shields.io/github/v/release/Akkitto/Tauridium?sort=semver&style=plastic" alt="Release" /></a>
  <a href="https://github.com/Akkitto/Tauridium"><img src="https://img.shields.io/badge/project-source-2a2f33?style=plastic" alt="Source" /></a>
  <a href="https://www.rust-lang.org/"><img src="https://img.shields.io/badge/language-Rust-orange.svg?style=plastic" alt="Language: Rust" /></a>
  <a href="https://github.com/Akkitto/Tauridium/commits/master"><img src="https://img.shields.io/github/last-commit/Akkitto/Tauridium/master?style=plastic" alt="Last commit" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-informational?style=plastic" alt="License: MIT" /></a>
</p>

Forget Franz, Ferdi, Ferdium and the rest. This is THE absolute best web app hub of all. I swear. Performant, beautiful and it just works(TM).

Speedy Gonzales level desktop client for [Ferdium](https://ferdium.org) style web app service-workspace management & usage, built with **Tauri v2** (Rust + native WebView) instead of Electron. Use a Ferdium server for synchronised data, or run accountless with services and workspaces stored locally.

## Why

I got sick and tired of the official [Ferdium](https://ferdium.org) client having long-standing bugs in the most basic features, like re-ordering services, workspace ordering & switching and numerous other functionalities. It feels like vibe-coded slop, before LLM based coding was even possible.

If that wasn't bad enough, Electron made everything so extremely fat, that I had to disable a lot of web apps in the client, because Ferdium was slowing them down so much, to the point of unability of use. Then, I asked myself, what even the point of the desktop client is, if I cannot even use some of the most important web apps in it.

Within a fairly short amount of time, I pimped up Tauridium to be simply overall better, more reliable and bug-free for the most important features, I use sometimes, frequently and every day. All possible due to spec-driven AI Engineering, rather than blindfolded vibe-coding.

To my knowledge, this is, as of now, the only fully open source, fully free of cost web app hub desktop application, which does *NOT* rely on Electron or be otherwise super buggy and badly designed.

## Features

* Accountless local mode or optional Ferdium server synchronisation
* Isolated, persistent native WebView sessions per service
* Workspaces with configurable service organisation, ordering and icons
* Bundled recipes, custom recipes and arbitrary HTTP(S) websites
* Per-service behaviour including notifications, badges, hibernation, appearance, proxy, user agent and link handling
* Configurable themes, sidebar, keybindings and service interaction
* Shared sandboxes for deliberately sharing login/session state between compatible services
* Native notifications, tray operation, persistent window state and launch-at-login
* Browser-style downloads with global, workspace and service configuration
* Portable workspace exports, transactional backups and a local structured audit log

## Installation

### Windows

Install with [Scoop](https://scoop.sh/):

```powershell
scoop install tauridium
```

Alternatively, download the native installer or portable build from [GitHub Releases](https://github.com/Akkitto/Tauridium/releases/latest).

### Linux

Download the appropriate native package from [GitHub Releases](https://github.com/Akkitto/Tauridium/releases/latest):

* DEB for Debian-based distributions
* RPM for RPM-based distributions
* AppImage for portable installation

### Other

All officially provided platform packages and portable builds are available from [GitHub Releases](https://github.com/Akkitto/Tauridium/releases/latest).

macOS is currently not maintained.

## Development

[`just`](https://github.com/casey/just) is the development entry point.

### Windows

Install `just` with Scoop:

```powershell
scoop install just
```

Then bootstrap and run Tauridium:

```powershell
just init-self-test
just init
just run
```

### Linux

With `just` installed:

```sh
just init
just run
```

### Quality gates

```text
just fmt-check
just lint
just check
just test
just build
```

## Technology

* **Tauri v2 / Rust** - native application shell, WebViews and operating-system integration
* **Svelte 5 / TypeScript** - user interface
* **reqwest + rustls** - server communication outside the WebView
* **wry** - vendored and patched for recipe IPC compatibility

## Releases

See [`CHANGELOG.md`](CHANGELOG.md) for release history and [GitHub Releases](https://github.com/Akkitto/Tauridium/releases) for packaged releases.

Version tags trigger the release workflow after the repository quality gates pass.

## Licence

Copyright (c) 2026 [Daniel Braniewski](https://brani.dev)

Tauridium is free software released under the [MIT License](LICENSE). You may use, copy,
modify, merge, publish, distribute, sublicense, and/or sell copies subject to the complete
license terms. The software is provided **AS IS**, without warranty of any kind.
