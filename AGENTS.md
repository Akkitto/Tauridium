# AGENTS.md

## Mission

Tauridium is a fast, native-WebView desktop hub for web services and workspaces. Keep it
lighter and more reliable than Electron alternatives while preserving a polished desktop
experience. Local/accountless use is first-class; Ferdium server integration is optional.

Platform priority is **Windows 11 first**, Linux second, and macOS best-effort. Windows 11
native releases are expected to be stable. Linux support is real but less exhaustively
tested. Do not make Unix shells, WSL, or Nushell prerequisites for Windows development.

## Architecture

- `src/`: Svelte 5 + TypeScript shell UI. Keep UI state predictable and responsive.
- `src/lib/api.ts`: typed frontend boundary to Tauri commands.
- `src-tauri/src/main.rs`: application/window/webview lifecycle and native commands.
- `src-tauri/src/{local_profile,backup,portable,audit,recipes,icons}.rs`: durable domain
  concerns; keep persistence and validation here rather than scattering them through UI.
- `vendor/wry/`: intentionally vendored/patched WebView layer. Do not replace/update it
  casually; preserve Tauridium IPC/session behavior and review upstream changes.
- `tools/`: bootstrap, validation, regression tests, versioning, and deterministic release
  packaging. Prefer extending these workflows over creating parallel ad-hoc scripts.

Service webviews are isolated and persistent by default. Shared sandboxes are explicit
opt-in state. Rust should own privileged filesystem/network/secret-sensitive operations;
the Svelte shell should orchestrate through typed commands. Preserve local data, service
and workspace order, sessions, backups, exports, and upgrade compatibility.

## Engineering rules

- Correctness, reliability, data safety, performance, and coherent UX outrank shortcuts.
- Implement features completely: persistence, validation, backup/export implications,
  cleanup/migration, UI feedback, and regression coverage when applicable.
- Immediate per-service settings must visibly confirm successful persistence (for example,
  the green `Saved` toast) and must survive restart when designed to persist.
- Never hide failures with lint suppressions, unsafe casts, swallowed errors, or weakened
  assertions. Fix root causes and keep diagnostics actionable and non-spammy.
- Keep dependencies locked and minimal. Network-dependent bootstrap/build steps must fail
  clearly rather than silently changing quality gates.
- Rust formatting is exact native `rustfmt` from pinned **Rust 1.97.1**. Clippy warnings
  are errors. Keep Svelte/TypeScript clean under `svelte-check` and Vitest.
- Windows workflows must work in Windows PowerShell 5.1 and PowerShell 7. Prefer Scoop for
  installable prerequisites; use WinGet when Scoop is unsuitable/unavailable.
- Follow existing UI patterns and native/platform abstractions. Avoid unnecessary visual
  churn, large margins, blocking work on interaction paths, and platform-specific flashes.
- Customer-facing documentation and changelog entries are English unless explicitly asked
  otherwise.

## Git and changes

- Default branch: `master`.
- Preserve existing history; do not rewrite another contributor's commits or Git identity.
- Set agent identity repository-locally, never globally. For OpenAI release work use:
  `OpenAI Release Builder <release@openai.invalid>`.
- Use the project's capitalized commit taxonomy (`Feat`, `Fix`, `Perf`, `Test`, `Fmt`,
  `Doc`, `Build`, `CI`, `Dep`, `Struct`, `Prog`, `Proj`, `Revert`, `Misc`).
- Keep commits focused. Release identity/tagging belongs in a final release commit when
  practical.

## Required validation

Before shipping, run the strongest gates the environment can genuinely execute:

```text
just fmt-check
just lint
just check
just test
just build
```

Also require `tools/validate_release.py`, clean Git status, and `git diff --check`.
Add focused regressions for bugs/features instead of weakening historical tests. If a
native/dependency-backed gate cannot run because the environment lacks required packages
or network access, state that exactly; never claim it passed.

## Releases

Use SemVer: patches for fixes/polish, feature releases for meaningful new capability.
Keep `CHANGELOG.md` concise and English, synchronize versions with
`node tools/sync_version.mjs X.Y.Z`, commit, annotate `vX.Y.Z`, and package only from the
clean tagged release commit.

A complete release normally delivers three artifacts in the same handoff:

- `tauridium-X.Y.Z-src.zip`: tracked source + real `.git` history + generated SHA-256
  source manifest.
- `tauridium-X.Y.Z-run-<target>.zip`: verified native runtime for the actual Rust target;
  otherwise use the explicit `run-build-handoff` archive.
- `tauridium-X.Y.Z-doc.zip`: release documentation, checksums, manifest, and evidence.

Packaging must be deterministic and ZIP-integrity-checked. Never fabricate a runtime,
ship a dirty tree, release with formatter drift, or stop after only part of the expected
artifact set when the full release is feasible.
