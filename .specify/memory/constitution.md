<!--
Sync Impact Report
Version change: (unfilled template) -> 1.0.0
Modified principles: none (all new; derived from AGENTS.md)
Added sections: Core Principles I-VI, Platform and Release Constraints,
  Development Workflow and Quality Gates, Governance
Removed sections: none
Templates:
  - .specify/templates/plan-template.md: OK (Constitution Check reads this file)
  - .specify/templates/spec-template.md: OK (no change needed)
  - .specify/templates/tasks-template.md: OK (no change needed)
Follow-up TODOs: none
Source of truth for detail: AGENTS.md. If they conflict, AGENTS.md is
amended to match this file, or this file is amended through Governance.
-->
# Tauridium Constitution

## Core Principles

### I. Correctness and Data Safety First
Correctness, reliability, data safety, performance and coherent UX outrank shortcuts.
Features MUST be implemented completely: persistence, validation, backup/export
implications, cleanup/migration, UI feedback and regression coverage where applicable.
Local data, service and workspace order, sessions, backups, exports and upgrade
compatibility MUST be preserved. Failures MUST NOT be hidden by lint suppressions,
unsafe casts, swallowed errors or weakened assertions; diagnostics MUST be actionable
and non-spammy.

### II. Rust Owns Privileged Work
Rust MUST own privileged filesystem, network and secret-sensitive operations. The
Svelte shell MUST orchestrate through typed commands (`src/lib/api.ts`). Durable
concerns (persistence, validation) belong in dedicated Rust domain modules, not
scattered through the UI. `vendor/wry/` is intentionally patched and MUST NOT be
replaced or updated casually.

### III. Isolation by Default, Local First
Service webviews MUST be isolated and persistent by default; shared sandboxes are
explicit opt-in. Local, accountless use is first-class; Ferdium server integration
is optional. Nothing a user types or stores in one service may leak to another or to
an external party without explicit user action.

### IV. Visible, Persistent Settings
Immediate per-service settings MUST visibly confirm successful persistence (for
example the green `Saved` toast) and MUST survive restart when designed to persist.

### V. Lean and Native
Tauridium MUST stay lighter and more reliable than Electron alternatives. Follow
existing UI patterns and native/platform abstractions; avoid unnecessary visual
churn, large margins, blocking work on interaction paths and platform-specific
flashes. Dependencies MUST be locked and minimal.

### VI. Tested and Reproducible (NON-NEGOTIABLE)
Bugs and features MUST ship with focused regressions; historical tests MUST NOT be
weakened. Clippy warnings are errors; Rust formatting is exact `rustfmt` from the
pinned toolchain; Svelte/TypeScript MUST be clean under `svelte-check` and Vitest.
The Rust supply-chain guard MUST run on every quality pass and blocked crate/version
indicators MUST NOT be bypassed. Gates that cannot run MUST be reported exactly,
never claimed as passed.

## Platform and Release Constraints

- Platform priority: Windows 11 first, Linux second, macOS best-effort. Unix shells,
  WSL and Nushell MUST NOT be prerequisites for Windows development.
- Windows workflows MUST work in Windows PowerShell 5.1 and PowerShell 7; prefer Scoop,
  then WinGet.
- Customer-facing documentation and changelog entries MUST be English.
- Releases use SemVer, a concise `CHANGELOG.md`, `node tools/sync_version.mjs`, an
  annotated `vX.Y.Z` tag, and packaging only from the clean tagged commit. A full
  release delivers the source, run and doc archives; never fabricate a runtime, ship a
  dirty tree or release with formatter drift.
- Network-dependent bootstrap/build steps MUST fail clearly rather than silently
  change quality gates.

## Development Workflow and Quality Gates

- Default branch is `master`; existing history and other contributors' identity MUST
  NOT be rewritten. Agent identity is set repository-locally, never globally.
- Commits use Capitalized Conventional Commits Dialect v1.3.2 (`Feat`, `Fix`, `Sec`,
  `Opt`, `Struct`, `Op`, `Build`, `CI`, `Dep`, `Test`, `Doc`, `Fmt`, `Proj`, `Prog`,
  `Gen`, `Release`, `Revert`), imperative, capitalized, no final period.
- Before shipping, run: `just fmt-check`, `just lint`, `just check`, `just test`,
  `just build`, plus `tools/validate_release.py`, a clean Git status and
  `git diff --check`.
- Prefer extending `tools/` workflows over parallel ad-hoc scripts.

## Governance

This constitution supersedes other practices for Spec Kit work. Plans MUST pass the
Constitution Check against it; violations require an entry in Complexity Tracking
with justification. Amendments require a documented change to this file, a version
bump (MAJOR for removed or redefined principles, MINOR for added or materially
expanded guidance, PATCH for clarifications), and an updated Sync Impact Report.
AGENTS.md remains the detailed runtime guidance; the two MUST be kept consistent.
Compliance is reviewed in `/speckit-analyze` and during code review.

**Version**: 1.0.0 | **Ratified**: 2026-11-13 | **Last Amended**: 2026-11-13
