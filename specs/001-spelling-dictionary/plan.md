# Implementation Plan: Spelling Check and Dictionary Support

**Branch**: `001-spelling-dictionary` | **Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-spelling-dictionary/spec.md`

## Summary

Add spelling check, language selection and a personal dictionary to service webviews by driving each platform's **native** WebView spellchecker (WebKitGTK on Linux, WebView2/Chromium on Windows, WKWebView on macOS) instead of building an in-page checker. Rust owns the durable state (new `spelling.rs` module: settings validation plus a personal dictionary file, both included in backups) and applies it to each service webview at creation and live on change. The Svelte shell provides a Settings panel and per-service overrides. Because service pages use the engine's own context menu, "fix" and "Add to dictionary" come from the native menu; Tauridium keeps its dictionary as the source of truth and syncs it into each engine. Word-definition lookup (P3) is gated behind a spike and shipped last.

## Technical Context

**Language/Version**: Rust 1.97.1 (pinned), Svelte 5 + TypeScript

**Primary Dependencies**: Existing only: tauri 2.12.4 (vendored), wry 0.57 (vendored/patched), webkit2gtk 2.0.2 (Linux), webview2-com 0.39.1 (Windows). No new crates planned.

**Storage**: App settings (existing validated JSON settings, same pattern as `serviceZoomLevels`) plus a new private `spelling-dictionary.json` written atomically; both added to backup, export and portable handling

**Testing**: `cargo test` (unit tests in `spelling.rs`, settings validation tests in `main.rs`), Vitest for `src/lib/api.ts` and a new `src/lib/spelling.ts`, Python regression tests under `tools/` following the existing `test_patch_*` convention, `tools/settings_smoke.py` for persistence

**Target Platform**: Windows 11 (first), Linux (WebKitGTK; native, AppImage, Flatpak, Nix), macOS best-effort

**Project Type**: Desktop app (Tauri shell UI + isolated native service webviews)

**Performance Goals**: No perceptible typing lag; no startup regression (spelling applied during webview creation only; dictionary load is a small local file)

**Constraints**: Offline-capable; no typed text leaves the device; per-service isolation preserved; Windows PowerShell 5.1 and 7 compatible tooling; vendored wry changes minimal and documented

**Scale/Scope**: Dozens of services, personal dictionary up to ~10,000 words, ~5 languages selected

## Constitution Check

`.specify/memory/constitution.md` is still the unfilled template, so the binding gates are the engineering rules in [AGENTS.md](../../AGENTS.md):

| Gate | Status |
|------|--------|
| Rust owns privileged/persistent work; Svelte orchestrates via typed commands | PASS: `spelling.rs` + typed commands in `api.ts` |
| Isolated per-service sessions preserved | PASS: dictionary is app-level data, no page data crosses services |
| Immediate settings show green `Saved` toast and survive restart | PASS: planned in UI tasks and `settings_smoke` coverage |
| Backup/export/upgrade compatibility | PASS: additive, optional fields; backup schema handled without breaking v1/v2 |
| No new dependencies / vendored wry only changed with care | PASS for default plan; spike S2 may need a small documented wry patch |
| No swallowed errors; actionable diagnostics | PASS: unavailable languages surfaced, not dropped |
| Windows 11 first | PASS, but gated by spike S1 (see research) |
| English docs + CHANGELOG entry | PASS: planned |

Re-check after Phase 1: no violations. No Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/001-spelling-dictionary/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── spelling-commands.md
└── tasks.md             # created by /speckit-tasks
```

### Source Code (repository root)

```text
src-tauri/src/
├── spelling.rs          # NEW: settings validation, personal dictionary store, language availability, engine adapters
├── main.rs              # register commands; apply spelling in webview builder (~line 2224-2410); settings defaults/validation (~3640-4170)
├── backup.rs            # include dictionary in backup/restore
├── portable.rs          # include dictionary in portable data
└── service_export.rs    # per-service override handling in exports
src/
├── App.svelte           # Settings panel + per-service override controls (reuse appToggle pattern)
└── lib/
    ├── api.ts           # typed spelling commands
    ├── spelling.ts      # NEW: pure helpers (normalize word, resolve effective settings)
    └── spelling.test.ts # NEW
tools/
└── test_spelling_*.py   # NEW regression tests following existing convention
docs/SPELLCHECK.md       # NEW: platform behaviour, privacy, dictionaries
CHANGELOG.md
```

**Structure Decision**: Follow the existing single Tauri app layout. A new domain module `spelling.rs` mirrors `local_profile.rs`/`backup.rs` (persistence and validation in Rust, thin UI). Engine-specific code sits behind `#[cfg]` adapters inside `spelling.rs`.

## Complexity Tracking

None.
