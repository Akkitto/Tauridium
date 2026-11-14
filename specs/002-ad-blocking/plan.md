# Implementation Plan: Ad and Tracker Blocking

**Branch**: `feat/ad-blocking` | **Date**: 2026-11-14 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-ad-blocking/spec.md`

## Summary

Block ad and tracker requests in service webviews using the `adblock` crate (brave/adblock-rust) as the single rule parser, with each platform enforcing the rules natively: WebKitGTK content filters on Linux (rules converted by the crate's `content-blocking` feature), a `*` WebResourceRequested handler backed by the in-memory `adblock::Engine` on Windows, and WKContentRuleList on macOS (best-effort, untested here). A new `adblock.rs` domain module owns settings validation, list download/validation/cache and the compiled engine; the shell only orchestrates through typed commands. Network blocking only; cosmetic filtering and scriptlets are a later spec. The Linux spike (S1) passed and Linux is implemented; the Windows spike (S2) and macOS are deferred. See [research.md](research.md), which records the measured results.

## Technical Context

**Language/Version**: Rust 1.97.1 (pinned), Svelte 5 + TypeScript

**Primary Dependencies**: New: `adblock` 0.13.5 (MPL-2.0; features `content-blocking` plus defaults trimmed per S1; not yet in `Cargo.lock`, its source is present in the local registry). Linux: direct dependency on `webkit2gtk-sys` 2.0.2 (already locked, `v2_40`) because the safe `webkit2gtk` crate does not wrap `UserContentFilterStore`/`UserContentFilter`. Windows: direct `webview2-com`/`windows` at the versions already locked through wry (S2 confirms). macOS: `objc2-web-kit` (new; deferred, best-effort). Existing: `reqwest` (rustls) for list downloads.

**Storage**: Additive optional settings in the existing validated app settings JSON (global switch, list selection, custom list URLs, global allowlist, `serviceAdblock` per-service map); list cache as private atomically written files under app data (`adblock/lists/<id>.txt` plus metadata); compiled platform artefacts (Linux filter store) under app data, rebuildable and excluded from backups.

**Testing**: `cargo test` unit tests in `adblock.rs` (settings validation, allowlist normalisation, list validation, conversion, matching); Vitest for `src/lib/adblock.ts`; Python regression tests under `tools/` (`test_adblock_core.py`, `adblock_smoke.py` in the style of `unread_badges_smoke.py`); a Linux WebKitGTK probe loading a local fixture page with a local ad-like request; a benchmark harness for S2 using a real EasyList.

**Target Platform**: Linux (WebKitGTK; native, AppImage, Flatpak, Nix) first, Windows 11 second (release gate needs a real Windows 11 run), macOS best-effort and labelled untested.

**Project Type**: Desktop app (Tauri shell UI + isolated native service webviews)

**Performance Goals**: Per-request match on Windows under 50 microseconds p99 on the UI thread for a full EasyList+EasyPrivacy engine (S2 sets the final number); no measurable startup regression; list compile and download never on interaction paths.

**Constraints**: Offline start from cache; no browsing data leaves the device; per-service isolation; PowerShell 5.1/7 tooling; vendored wry changes minimal and documented; supply-chain guard must pass.

**Scale/Scope**: Roughly 100k to 200k rules active; dozens of services; allowlist up to a few hundred entries.

## Constitution Check

| Principle | Status |
|-----------|--------|
| I. Correctness and data safety | PASS: list updates are atomic and keep the last good copy; no swallowed errors |
| II. Rust owns privileged work | PASS: downloads, cache and matching in Rust; new commands allowlisted for the trusted shell |
| III. Isolation, local first | PASS: per-service state; no browsing data sent anywhere (FR-016); only list URLs fetched |
| IV. Visible, persistent settings | PASS: `Saved` toast, restart persistence, cleanup on delete, copy on duplicate planned |
| V. Lean and native | PASS: Linux uses native filters (no per-request Rust hook); Windows latency is a later-release gate (S2) |
| VI. Tested and reproducible | PASS planned; Windows and macOS `cfg` paths are stubbed (T057), checked by T058, and reported as not run here unless run on real hosts |
| Platform constraints | PASS: Windows/macOS compile with an unsupported notice (T056-T058), so Windows releases are not regressed |
| VII. Verified platform behaviour | GATED: S1 and S2 must pass before dependent tasks; Linux native-API gap already found (research D2) |
| VIII. Compatible evolution | PASS: additive optional fields; digest unchanged when absent; unknown versions rejected |
| Dependencies and supply chain | GATED: `adblock` is a new crate tree; needs advisory audit, license review (MPL-2.0), `Cargo.lock` re-bind, Flatpak and Nix source regeneration |

Re-check after Phase 1: no unjustified violations. The only deviation is the direct `webkit2gtk-sys` FFI (unsafe), tracked below.

## Project Structure

### Documentation (this feature)

```text
specs/002-ad-blocking/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── adblock-commands.md
└── tasks.md             # created by /speckit-tasks
```

### Source Code (repository root)

```text
src-tauri/src/
├── adblock.rs           # NEW: settings validation, list store, engine build, platform adapters (cfg-gated)
├── main.rs              # register commands; attach blocking at webview creation (~2224-2450); apply on settings change (mirror apply_spelling_settings ~4574); defaults/validation (~3700, ~4197)
├── backup.rs            # optional adblock section, digest unchanged when absent
├── service_export.rs    # per-service override and allowlist entries
└── portable.rs          # include list cache metadata/settings as appropriate
src/
├── App.svelte           # Settings panel, list picker, per-service toggle (reuse spelling UI patterns)
└── lib/
    ├── api.ts           # typed adblock commands
    ├── adblock.ts       # NEW: pure helpers (effective setting, allowlist normalise)
    └── adblock.test.ts  # NEW
tools/
├── test_adblock_core.py # NEW regression tests
├── adblock_smoke.py     # NEW Linux webview probe
├── adblock_bench.*      # NEW S2 benchmark harness
└── generate_flatpak_sources.py  # updated output for new crates
flake.nix, data/security-advisory-policy.json, docs/ADBLOCK.md, CHANGELOG.md
```

**Structure Decision**: Single Tauri app layout; a new domain module `adblock.rs` mirrors `spelling.rs`, with per-OS adapters behind `#[cfg]` inside it (or a small `adblock/` directory if it grows). Unsafe FFI is confined to one Linux submodule.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Direct `webkit2gtk-sys` FFI (unsafe) | Safe `webkit2gtk` 2.0.2 does not expose `UserContentFilterStore`/`add_filter` | Injected-JS blocking cannot stop network requests; vendoring a patched webkit2gtk is heavier |
| Second WebResourceRequested handler on Windows | wry only registers the event for custom protocols | Platform-native rules do not exist on WebView2 |

## As built (Linux, 2026-11-14)

- `src-tauri/src/adblock.rs` holds settings validation, host normalisation and per-service resolution. `adblock/lists.rs` is the only module that touches the network (pinned, public-address-only downloads with manual redirects). `adblock/compile.rs` converts lists and the allowlist to WebKit rules and derives the filter id. `adblock/runtime.rs` runs the background updater and attaches filters. `adblock/linux_filter.rs` is the only `unsafe` module.
- Settings travel through the existing `set_app_settings` command; the four new commands are `adblock_get_state`, `adblock_update_lists`, `adblock_check_list` and `adblock_normalize_sites` (see `contracts/adblock-commands.md`).
- Linux-only items are gated with `#[cfg(any(target_os = "linux", test))]` so Windows and macOS build without dead code and report "unsupported". This was checked by simulating a non-Linux build of the module; a real Windows or macOS compile has not been run here (the Windows target needs an MSVC C compiler for `ring`).
- Compiled filters are about 37 MB each on disk for the default lists. A service with its own allowlist gets its own compiled filter; unused ones are removed.
- No navigation hold was added: the filter is attached synchronously after the webview is created, from a filter pre-loaded at startup.
- Real-world check by the maintainer: ad slots on dailymail.co.uk and forbes.com were blocked in the running app. Instagram feed ads are first-party and are not blocked; hiding them needs cosmetic filtering, which is a later release.
