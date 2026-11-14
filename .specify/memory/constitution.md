<!--
Sync Impact Report
Version change: 1.0.0 -> 1.1.0
Modified principles:
  - III. Isolation by Default, Local First: added the typed-text privacy rule
  - VI. Tested and Reproducible: added real-engine verification and honest status reporting
Added principles: VII. Verified Platform Behaviour; VIII. Compatible Evolution
Added sections: Dependencies and Supply Chain; Spec Kit Practice (including one branch per spec)
Modified sections: Platform and Release Constraints (Linux first for this fork)
Removed sections: none
Templates:
  - .specify/templates/plan-template.md: OK (Constitution Check reads this file)
  - .specify/templates/spec-template.md: OK (no change needed)
  - .specify/templates/tasks-template.md: OK (no change needed)
Follow-up TODOs:
  - AGENTS.md (upstream guidance) still says "Windows 11 first". This fork's
    priority is Linux first; AGENTS.md was deliberately not edited.
Source of truth for detail: AGENTS.md, except platform priority (see below).
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
Svelte shell MUST orchestrate through typed commands (`src/lib/api.ts`), and every new
command MUST be allowlisted for the trusted shell only. Durable concerns (persistence,
validation) belong in dedicated Rust domain modules, not scattered through the UI.
`vendor/wry/` is intentionally patched and MUST NOT be replaced or updated casually.

### III. Isolation by Default, Local First
Service webviews MUST be isolated and persistent by default; shared sandboxes are
explicit opt-in. Local, accountless use is first-class; Ferdium server integration is
optional. Nothing a user types or stores in one service may leak to another or to an
external party without explicit user action. Text typed into a website MUST NOT be sent
anywhere for processing (for example spell checking); prefer the platform's own on-device
engine over a custom checker or a remote service.

### IV. Visible, Persistent Settings
Immediate per-service settings MUST visibly confirm successful persistence (for
example the green `Saved` toast) and MUST survive restart when designed to persist.
Per-service settings MUST also be cleaned up when a service is deleted and copied when
it is duplicated.

### V. Lean and Native
Tauridium MUST stay lighter and more reliable than Electron alternatives. Follow
existing UI patterns and native/platform abstractions; avoid unnecessary visual
churn, large margins, blocking work on interaction paths and platform-specific
flashes. Prefer the web engine's native behaviour over reimplementing it.

### VI. Tested and Reproducible (NON-NEGOTIABLE)
Bugs and features MUST ship with focused regressions; historical tests MUST NOT be
weakened. Clippy warnings are errors; Rust formatting is exact `rustfmt` from the
pinned toolchain; Svelte/TypeScript MUST be clean under `svelte-check` and Vitest.
The Rust supply-chain guard MUST run on every quality pass and blocked crate/version
indicators MUST NOT be bypassed. Behaviour that depends on a native engine MUST be
checked against that real engine where one is available, not only with unit tests.
Gates or platforms that cannot be run MUST be reported exactly, never claimed as
passed, and untested platform code MUST be labelled untested in docs and changelog.

### VII. Verified Platform Behaviour
Before designing around a platform capability, its real behaviour MUST be established
from engine documentation, source or a spike, and recorded in the feature's research.
A control the platform cannot honour MUST NOT be offered as a setting. Show that the
operating system manages it instead. Where an engine lacks a native control, prefer a
standard web mechanism (for example the `spellcheck` attribute) over private hacks, and
document its limits (such as top-level page only).

### VIII. Compatible Evolution
Persisted data changes MUST be additive and optional. Files written before a change
MUST still load and verify, and an absent value MUST be distinguishable from an empty
one, so an older backup cannot silently clear newer data. A change that alters an
integrity digest MUST leave the digest of data that lacks the new field unchanged.
Unknown future versions MUST be rejected without overwriting the file.

## Platform and Release Constraints

- Platform priority for this fork: **Linux first**, Windows 11 second, macOS
  best-effort. Windows 11 native releases are still expected to be stable, so Windows
  regressions block release. The upstream AGENTS.md says "Windows 11 first"; for Spec
  Kit feature work this constitution governs priority.
- Unix shells, WSL and Nushell MUST NOT be prerequisites for Windows development.
- Windows workflows MUST work in Windows PowerShell 5.1 and PowerShell 7; prefer Scoop,
  then WinGet.
- Customer-facing documentation and changelog entries MUST be English. Source and docs
  MUST NOT contain accented prose characters; write them as escapes (for example
  `\u{e5}`) where a string needs one. `tools/check_english.py` enforces this.
- Releases use SemVer, a concise `CHANGELOG.md`, `node tools/sync_version.mjs`, an
  annotated `vX.Y.Z` tag, and packaging only from the clean tagged commit. A full
  release delivers the source, run and doc archives; never fabricate a runtime, ship a
  dirty tree or release with formatter drift.
- Network-dependent bootstrap/build steps MUST fail clearly rather than silently
  change quality gates.
- `src-tauri/gen/schemas/` is generated by the build and committed. It MUST be
  regenerated, not hand-edited, and local differences from a platform build are not
  changes to keep.

## Dependencies and Supply Chain

- Dependencies MUST be locked and minimal. A direct dependency on a crate already in
  the lock, at its locked version and features, is preferred over a new crate.
- Any `Cargo.lock` change invalidates the hash in `data/security-advisory-policy.json`.
  Re-bind it only after confirming the lock gained no new package or version and after
  the online RustSec audit (`tools/audit_dependencies.py`) passes. Never edit the
  policy to bypass a finding or to make a test pass without that audit.
- Cross-platform code that cannot be compiled on the development host (for example
  macOS and Windows targets without their SDKs) MUST be kept small, use APIs confirmed
  in the vendored source, and be flagged as not compiled here.

## Development Workflow and Quality Gates

- Default branch is `master`; existing history and other contributors' identity MUST
  NOT be rewritten. Agent identity is set repository-locally, never globally.
- Commits use Capitalized Conventional Commits Dialect v1.3.2 (`Feat`, `Fix`, `Sec`,
  `Opt`, `Struct`, `Op`, `Build`, `CI`, `Dep`, `Test`, `Doc`, `Fmt`, `Proj`, `Prog`,
  `Gen`, `Release`, `Revert`), imperative, capitalized, no final period. Keep commits
  focused and order producers before consumers.
- Push feature branches to the contributor's fork remote, never to the upstream
  remote, unless explicitly told otherwise.
- Before shipping, run: `just fmt-check`, `just lint`, `just check`, `just test`,
  `just build`, plus `tools/validate_release.py`, a clean Git status and
  `git diff --check`. Lint and test cover the default, Flatpak and Nix feature sets.
- Prefer extending `tools/` workflows over parallel ad-hoc scripts. Behaviour of
  injected page scripts SHOULD be exercised against a minimal fake DOM in Node.

## Spec Kit Practice

- One branch per spec. A feature's spec directory (`specs/NNN-name`), its branch and its
  pull request correspond one-to-one; unrelated work goes on its own spec and branch.
- Record unknowns as spikes in `research.md` and resolve them before dependent tasks.
- When implementation reveals reality that differs from the spec (platform limits,
  deferred scope), update the spec and plan so they describe what was built.
- Mark a task done only when it is verified. Partial or unverified work MUST keep a
  note saying what was not tested.
- Spec Kit files (`specs/`, `.specify/`) are working material. Whether they go into a
  pull request upstream is the contributor's decision; keep feature code, tests, docs
  and changelog separable from them.

## Governance

This constitution supersedes other practices for Spec Kit work. Plans MUST pass the
Constitution Check against it; violations require an entry in Complexity Tracking
with justification. Amendments require a documented change to this file, a version
bump (MAJOR for removed or redefined principles, MINOR for added or materially
expanded guidance, PATCH for clarifications), and an updated Sync Impact Report.
AGENTS.md remains the detailed runtime guidance, with platform priority as the one
documented difference above. Compliance is reviewed in `/speckit-analyze` and during
code review.

**Version**: 1.1.0 | **Ratified**: 2026-11-13 | **Last Amended**: 2026-11-13
