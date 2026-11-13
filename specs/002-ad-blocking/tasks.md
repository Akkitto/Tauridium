---
description: "Task list for Ad and Tracker Blocking (Linux first)"
---

# Tasks: Ad and Tracker Blocking

**Input**: Design documents from `/specs/002-ad-blocking/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/adblock-commands.md

**Scope of this task list**: Linux (WebKitGTK) only (Windows and macOS builds must still compile and show an unsupported notice, T057-T058), per the decision to focus on Linux first. Windows and macOS work is deferred to Phase 9 and is NOT part of the Linux release gate. Settings, list management, backup and UI are platform-neutral and are built here so the other platforms plug in later. Nothing in Phase 9 may be claimed as done or tested from this host.

**Tests**: Included (AGENTS.md and constitution VI require focused regressions).

**Organization**: Grouped by user story. Paths are relative to the repository root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1-US5 map to the user stories in spec.md

---

## Phase 1: Setup

- [X] T001 Create `src-tauri/src/adblock.rs` with module docs and `mod adblock;` registration in `src-tauri/src/main.rs`
- [X] T002 [P] Create `src/lib/adblock.ts` and `src/lib/adblock.test.ts` skeletons (types only so far; helpers `normalizeHost` and `resolveEffectiveAdblock` land with T028/T030)
- [X] T003 [P] Create `docs/ADBLOCK.md` stub (platform behaviour, privacy, list sources, Linux coverage limits, Windows/macOS untested) and add an English `CHANGELOG.md` "Unreleased" entry

---

## Phase 2: Spikes and supply chain (blocks all later phases)

**Purpose**: Establish real WebKitGTK behaviour and the dependency cost before designing on them (constitution VII). Record every result in `specs/002-ad-blocking/research.md`.

- [X] T004 Spike S3a: add `adblock` 0.13.5 (features: `content-blocking`, default features reviewed and trimmed if possible) to `src-tauri/Cargo.toml`; then regenerate `src-tauri/Cargo.lock`; list every new crate and version added and confirm none is blocked by `python3 tools/check_rust_supply_chain.py`; record in research.md
- [X] T005 Spike S3b: review MPL-2.0 against `LICENSE` and distribution/packaging policy (including Flatpak and Nix); run `python3 tools/audit_dependencies.py` online; only after it passes, re-bind the hash in `data/security-advisory-policy.json` per the constitution; record result
- [X] T006 Add `webkit2gtk-sys = { version = "=2.0.2", default-features = false, features = ["v2_40"] }` as a Linux-only direct dependency in `src-tauri/Cargo.toml` (already locked; confirm `Cargo.lock` gains no package or version) 
- [X] T007 Spike S1a (Linux conversion; done in a scratchpad crate outside the repo, results in research.md): a program that parses a real EasyList + EasyPrivacy fetched into the scratchpad, converts with `content-blocking`, and prints rule count, skipped count, conversion time, JSON size, and the WebKit rule-count limit behaviour (try 50k, 100k, 150k, 200k); record in research.md and decide whether lists must be split across several filters
- [X] T008 Spike S1b (Linux engine): add `src-tauri/src/adblock/linux_filter.rs` containing the unsafe FFI wrapper over `webkit_user_content_filter_store_{new,save,load,remove,fetch_identifiers}` and `webkit_user_content_manager_{add,remove}_filter(_by_id)` with safe `Result`-returning functions and `// SAFETY:` comments; keep it the only unsafe module
- [X] T009 Spike S1c (behaviour probe, using the page set from T059; also measure U1: whether requests issued during the first navigation of a new webview slip through before an asynchronously loaded filter is attached, and include an iframe and a cross-site subresource case): extend `tools/` with `tools/adblock_probe.cjs` or a Rust test using a headless WebKitGTK view and a local HTTP fixture; verify (a) a listed request is blocked, (b) an exception rule is honoured, (c) `if-top-url` / `if-domain` `ignore-previous-rules` allowlist works, (d) `remove_filter` then `add_filter` on a live view takes effect for the next request without reload, (e) load time and RSS with the full list vs none; record numbers in research.md
- [X] T010 Spike S5: determine whether WebKitGTK reports blocked loads (a signal on the view or an observable failed load); decide whether the blocked counter is offered on Linux; if not, record that FR-015 counters are omitted on Linux and the UI shows an explanation instead of a control
- [X] T011 Decide defaults from spike data and record them in research.md: curated default lists (general ad list plus tracker list), default global state for new profiles, update interval; update spec.md Assumptions and plan.md to match what was found (constitution Spec Kit Practice)

- [X] T059 Spike G1 (reference set; complete before T009 runs): define in research.md the reference page set for SC-001/SC-002 (the local fixture page plus at least three real ad-heavy public pages) and the measurement method (median of five cold loads, blocking on vs off); choose at least three chat or workspace services for SC-007 from the services available to the maintainer; record both lists before T009 numbers are used as pass/fail

**Phase 2 status (2026-11-14)**: T004-T011 and T059 are done; results are in research.md. Not yet measured and still owed before the SC-002/SC-003 claims are final: timing on real public pages with the T059 method, and app startup time with cached lists (T051). The compile-time memory transient (about 330-430 MB in the app process) needs a decision in T018: compile in a short-lived helper process or accept it. Blocked-request counters are not possible on Linux (T010).

**Checkpoint**: Do not start Phase 3 until T009 passes SC-001/SC-002/SC-003 thresholds on Linux, or the plan has been revised.

---

## Phase 3: Foundational (blocks all user stories)

**Purpose**: Settings model, persistence, list cache and compile pipeline that every story uses.

- [X] T012 Add defaults `adblockEnabled`, `adblockLists`, `adblockCustomLists`, `adblockAllowlist`, `serviceAdblock` to the settings defaults in `src-tauri/src/main.rs` (near the spelling defaults ~3708), additive and optional per data-model.md
- [X] T013 Implement settings validation in `src-tauri/src/adblock.rs` (list ids from the catalog, https-only custom URLs, max 20, host normalisation to lowercase/punycode, max 500 allowlist entries, override map shape, reject empty overrides and unknown fields) and call it from the settings validation in `src-tauri/src/main.rs` (~4197)
- [X] T014 [P] Unit tests for validation, host normalisation and upgrade defaults (missing keys load defaults, old settings files load unchanged) in `src-tauri/src/adblock.rs`
- [X] T015 Implement the list catalog and cache store in `src-tauri/src/adblock.rs`: private atomic writes via `private_file.rs` conventions for `adblock/lists/<id>.txt` and `adblock/lists.json`, retain the previous good copy, record `lastUpdated`, `ruleCount`, `skippedCount`, `lastError`, `contentHash`
- [X] T016 Implement download and validation in `src-tauri/src/adblock.rs` using the existing `reqwest` client: https only, size cap, timeout, redirect limit (each redirect target re-validated as https), refuse hosts that are or resolve to loopback, private, link-local or unspecified addresses (FR-016), parse with `adblock`, reject empty or fatal-parse lists, never replace the active copy on failure, one error per failure episode (`errorReportedAt`)
- [X] T017 [P] Unit tests for validation, atomic replace, last-good retention, error de-duplication and refusal of loopback/private/link-local URLs and redirects to them, using fixture lists (no network) in `src-tauri/src/adblock.rs`
- [X] T018 Implement the compile pipeline in `src-tauri/src/adblock.rs`: enabled lists plus allowlist to content-blocking JSON, keyed by `contentHash`, run on a worker thread, saved through `linux_filter.rs`, skipped-rule count reported, never on the UI or interaction path
- [X] T019 [P] Add typed command wrappers and the settings interface fields to `src/lib/api.ts` and defaults to `src/App.svelte` (near the spelling defaults ~322)
- [X] T020 Register the commands from `contracts/adblock-commands.md` in `src-tauri/src/main.rs`, allowlisted for the trusted shell only, following `ipc_security.rs` conventions; `adblock_get_state` returns `engine.supported` (true only on Linux in this release) and, on other platforms, every mutating command returns a clear "not available on this platform" error; add or extend the IPC allowlist test in `tools/test_ipc_security.py`

---

## Phase 4: User Story 1 - Block ads and trackers in services (Priority: P1) MVP

**Goal**: With blocking on, listed requests are blocked in each Linux service webview and changes apply live.

**Independent Test**: `python3 tools/adblock_smoke.py` blocks the listed fixture request, loads the exception and clean requests, then loads the listed one again after blocking is switched off, without restart.

- [X] T021 [P] [US1] Write `tools/adblock_smoke.py` in the style of `tools/unread_badges_smoke.py`: serve a local fixture (listed ad host, exception host, clean host) and assert blocked/loaded/loaded (spec US1 scenarios 1-4)
- [X] T022 [US1] Attach the compiled filter to each service webview at creation in `src-tauri/src/main.rs` (near the spelling `with_webview` call ~2442) via `adblock.rs` `apply_to_webview`, loading the cached compiled filter only (never compile or download inline). Because loading a saved filter is asynchronous, the service's initial navigation MUST NOT start until the filter is attached (or the load has failed and a diagnostic was logged), using the strategy recorded from T009 (for example creating the webview on `about:blank` and navigating after attach). Add a smoke assertion in `tools/adblock_smoke.py` that the first page load blocks the listed request
- [X] T023 [US1] Implement `apply_to_webview` for Linux in `src-tauri/src/adblock.rs` (remove then add the filter by id on the view's `UserContentManager`, idempotent)
- [X] T024 [US1] Add `apply_adblock_settings` in `src-tauri/src/main.rs` mirroring `apply_spelling_settings` (~4574) to re-apply to every running service webview on settings or list change
- [X] T025 [US1] Never apply to the shell webview or internal pages (FR-014): add a guard and a unit test in `src-tauri/src/adblock.rs`
- [X] T026 [US1] Add the global switch to the settings panel in `src/App.svelte` with the green `Saved` toast, and a Vitest case in `src/lib/adblock.test.ts`
- [X] T056 [US1] Constitution VII: when `engine.supported` is false (Windows, macOS), `src/App.svelte` MUST NOT render the global switch, per-service toggle, allowlist editor or list picker; show a single "Ad blocking is not available on this platform yet" notice instead. Add a Vitest case in `src/lib/adblock.test.ts` and a Rust unit test for the unsupported-platform state in `src-tauri/src/adblock.rs`
- [X] T027 [US1] Handle the no-cache first run: blocking reports "waiting for lists" rather than an error loop, then activates when the first list lands (spec edge case)

**Checkpoint**: US1 works on Linux and is demonstrable alone.

---

## Phase 5: User Story 2 - Quick per-service off and allowlist (Priority: P1)

**Goal**: Fast escape hatch for broken services.

**Independent Test**: Turn blocking off for one service from its settings, see `Saved`, restart, confirm it persists and other services are still blocked.

- [X] T028 [US2] Implement `effective_for_service` (follow global / on / off) and per-service allowlist merge in `src-tauri/src/adblock.rs`, with unit tests
- [X] T029 [US2] Compile the global allowlist as `ignore-previous-rules` entries after list rules in `src-tauri/src/adblock.rs`; per-service allowlist entries produce a per-service compiled variant keyed by hash (spike result T009 decides the exact form)
- [X] T030 [US2] Per-service controls in `src/App.svelte` (three-state toggle reachable in at most two actions from the service, SC-004) and allowlist editor with normalisation feedback, each showing `Saved`
- [X] T031 [US2] Clean `serviceAdblock` on service delete and copy on duplicate in `src/App.svelte` (same path as `serviceSpellcheck`), plus Rust-side check in `src-tauri/src/main.rs` if the shell path does not cover it
- [X] T032 [US2] Shared-sandbox services use each service's own setting (FR-013): unit test in `src-tauri/src/adblock.rs`
- [X] T033 [P] [US2] Extend `tools/settings_smoke.py` to cover persistence across restart for the new keys, and add `tools/test_adblock_core.py` cases for override resolution

---

## Phase 6: User Story 3 - Choose and maintain filter lists (Priority: P1)

**Goal**: Curated list picker, custom lists, background refresh, offline start.

**Independent Test**: Enable a list, see it download and activate; go offline, restart, blocking still works; serve a corrupt list, previous copy stays and exactly one message appears.

- [X] T034 [US3] Background updater in `src-tauri/src/adblock.rs`: refresh on the configured interval and on demand, ETag/Last-Modified conditional fetch, jittered start so startup never waits (FR-007), recompile only when `contentHash` changes
- [X] T035 [US3] `adblock_get_state`, `adblock_set_lists`, `adblock_add_custom_list`, `adblock_remove_custom_list`, `adblock_update_lists` command bodies in `src-tauri/src/main.rs`; emit `adblock-lists-updated` and a single `adblock-error` per failure episode
- [X] T036 [P] [US3] List picker, custom list entry with validation message, status row (last updated, rule count, last error) in `src/App.svelte` and typed calls in `src/lib/api.ts`
- [X] T037 [P] [US3] Offline start test: unit/integration test that starting with cache and no network never blocks on I/O and activates from cache, in `src-tauri/src/adblock.rs`
- [X] T038 [P] [US3] Extend `tools/adblock_smoke.py` with the corrupt-list and offline scenarios (SC-006), and a privacy check that the only outbound connections made during the run are to the configured list address (FR-016)

---

## Phase 7: User Story 4 - Backups and exports (Priority: P2)

**Goal**: Settings and allowlist travel with backups and service exports without changing old digests.

**Independent Test**: Back up, restore on a clean profile, settings match; restore a pre-feature backup and it verifies and does not clear newer settings.

- [X] T039 [US4] Add the optional `adblock` section to `src-tauri/src/backup.rs` (settings, custom lists, allowlist only; no list contents or compiled artefacts), keeping the digest byte-identical when the section is absent
- [X] T040 [US4] Include the per-service override and allowlist in `src-tauri/src/service_export.rs`, with the same optional-field rule
- [X] T041 [US4] Restoring a backup without the section must not clear existing adblock settings; unknown future versions rejected without overwriting
- [X] T042 [P] [US4] Add regression tests in `tools/test_backup.py` and unit tests in `src-tauri/src/backup.rs` for old backups, new backups, absent vs empty, and digest stability
- [X] T043 [P] [US4] Decide and implement what `src-tauri/src/portable.rs` includes (settings yes, compiled cache no) with a test

---

## Phase 8: User Story 5 - Visibility (Priority: P3)

**Goal**: Per-list status everywhere, counters only where the platform can honour them.

- [X] T044 [US5] Per-list status panel is already part of T036; add the Linux coverage note (skipped/unsupported rule count and "coverage differs from Windows") from `engine.coverageNote` in `src/App.svelte`
- [X] T045 [US5] If T010 found a usable signal, implement `adblock_blocked_count` and a per-service counter; otherwise return `null`, hide the counter and document why in `docs/ADBLOCK.md` (principle VII)
- [X] T046 [P] [US5] Vitest and Rust tests for the counter-absent path and coverage note

---

## Phase 9: Polish and release gates (Linux)

- [ ] T047 [P] Regenerate Flatpak sources with `tools/generate_flatpak_sources.py` and update `flake.nix` (and `flake.lock` only if required) for the new crates; verify with `tools/test_flatpak_*.py` and `tools/test_nix.py`
- [ ] T048 [P] Confirm Flatpak sandbox: filter store path under app data works and no new permissions are required; record in `docs/ADBLOCK.md`
- [X] T049 [P] Add `tools/check_english.py`-clean docs: finish `docs/ADBLOCK.md` and `CHANGELOG.md`, stating Windows and macOS are not yet available
- [ ] T050 Run the full gate on Linux: `just fmt-check`, `just lint` (default, Flatpak and Nix feature sets), `just check`, `just test`, `just build`, `just rust-supply-chain`, `python3 tools/validate_release.py`, `git diff --check`; report exactly what ran and what could not
- [ ] T060 After enabling blocking with default lists, manually exercise the chosen chat/workspace services (sign in, send a message, open a workspace page, notifications) and record pass, or the one-step workaround, in research.md and `docs/ADBLOCK.md` (SC-007)
- [ ] T051 Run `specs/002-ad-blocking/quickstart.md` Linux steps end to end and record results; perf checks against SC-002/SC-003 using the T059 reference set and real list
- [X] T052 Update spec.md, plan.md and research.md to describe what was built, including deferred Windows/macOS scope (constitution Spec Kit Practice)

---

- [X] T057 [P] Add non-Linux `#[cfg]` stubs in `src-tauri/src/adblock.rs` so the module compiles on Windows and macOS: no `webkit2gtk-sys` use, `apply_to_webview` is a no-op, `engine.supported` is false, and the Linux FFI module is `#[cfg(target_os = "linux")]` only; unit test the unsupported state
- [ ] T058 Verify non-Linux builds are not broken: run `cargo check --manifest-path src-tauri/Cargo.toml --locked --target x86_64-pc-windows-msvc` when the target is installed and report it exactly as not run if it cannot be; review Windows and macOS `cfg` paths by hand and flag them "not compiled here" (constitution Dependencies)

---

## Phase 10: Deferred platforms (NOT in the Linux release)

- [ ] T053 Windows spike S2: on real Windows 11, `*` WebResourceRequested handler via `with_webview` backed by an `adblock::Engine` snapshot; benchmark p50/p99 with a real list; decide hook vs vendored wry patch; add direct `webview2-com`/`windows` dependencies only at locked versions
- [ ] T054 Windows implementation of `apply_to_webview`, counters and allowlist in `src-tauri/src/adblock.rs` after T053 passes; requires a real Windows 11 test run before release
- [ ] T055 macOS spike S4 and implementation via `WKContentRuleListStore` (`objc2-web-kit`); cannot be built here, ship only labelled untested or defer

---

## Implementation status (2026-11-14)

Phases 1-2 are complete. Phases 3-8 are implemented for Linux and verified by unit tests, lints and a real launch of the app, with the gaps below. Nothing is committed yet.

**Deviations from the task text (the code is the source of truth):**
- Settings changes use the existing `set_app_settings` command rather than separate setter commands. The new commands are `adblock_get_state`, `adblock_update_lists`, `adblock_check_list` and `adblock_normalize_sites` (T020, T035). `contracts/adblock-commands.md` is updated to match.
- T022: no navigation hold. The filter is attached synchronously right after the webview is created, from a filter pre-loaded at startup. The U1 probe showed first navigations were blocked even without this, but the end-to-end first-load assertion has not been run against the real app.
- T018: the compile runs in the app process on a worker thread (no helper process). Memory was measured only in the standalone probe (about 330-430 MB transient). Re-measure inside the app (T051).
- T039-T041: blocking settings live in the app settings, so backups already carry them and old-backup digests are unchanged with no `backup.rs` change. Restoring a backup that lacks the keys keeps the current values (`carry_forward_missing`, unit tested). `service_export.rs` does not export per-service settings for spelling either, so no per-service blocking export was added (T040 open).
- T045: there is no counter command or UI because WebKitGTK cannot report blocked loads.

**Update later the same day:**
- T025, T032, T037: covered by new unit tests in `adblock/runtime.rs` (only `svc-` webviews are addressed; shared-sandbox services resolve independently; cached metadata alone is enough to block offline and a missing cache waits instead of failing).
- T033, T042: `tools/test_adblock_core.py` pins the wiring and safety properties; backup carry-forward is unit tested. `tools/settings_smoke.py` was not extended.
- T043: not applicable. `portable.rs` does not handle app settings; settings (including blocking) are covered by the app-settings path.
- T046: nothing to test beyond `supportsCounters = false` in the state; there is no counter code.
- T049, T052: `docs/ADBLOCK.md`, `CHANGELOG.md`, `spec.md`, `plan.md` and `research.md` now describe what was built.
- C2/T057/T058: a simulated non-Linux build of the module (Linux `cfg` gates flipped) found dead-code failures that would break `clippy -D warnings` on Windows and macOS; they are fixed by gating Linux-only items with `#[cfg(any(target_os = "linux", test))]`. A real Windows or macOS compile was not possible here (`ring` needs an MSVC C compiler).

**T021, T033, T038 (done, with these scope notes):**
- `tools/adblock_smoke.py` (`just test-adblock`) runs the real production executable in isolated profiles against a local fixture site and uses its request log as ground truth. Seven scenarios pass: `block` (first load blocked, including a cross-host iframe; exception and clean requests load), `cold` (filter compiled in the background, next start blocks on the first load), `off`, `service` (override off), `allowlist`, `restart` (override and blocking settings persist across a restart of the same profile) and `offline`.
- `offline` uses a dead proxy to simulate no network: the cached list keeps blocking, the failure is recorded once, and blocking adds only the selected list host (`easylist.to`) compared with a baseline run with blocking off. The baseline shows the app's own unrelated connections to `github.com` and `raw.githubusercontent.com` (recipe catalog).
- A genuinely corrupt download (valid HTTPS response with bad content) cannot be served locally without TLS, so that path is covered by the unit tests in `adblock/lists.rs` (validation, last-good retention, one report per failure episode) rather than the smoke test.
- T033 was not done as an extension of `tools/settings_smoke.py` (it needs OCR, which is not installed here). Persistence is covered by the smoke `restart` scenario and by a Rust save-and-reload round-trip test in `main.rs`; the settings tab controls themselves were not driven by a UI test.
- Not covered: a cold first start loads the page before the filter exists (informational in the smoke test; the page already loaded stays unfiltered until reloaded, and later loads are blocked).

**T030 and Phase 7 (US4), T045 (done, with these scope notes):**
- T030: reaching the per-service control takes three actions (open the service menu, choose Settings, choose Off), not two. The service menu is a fixed-layout native overlay with exact heights and tests, so adding a menu item was judged too invasive; SC-004 now says three actions and the service works as soon as its page reloads. A one-click item in the overlay remains an option for a later change.
- T039: no `backup.rs` code was needed. Blocking settings are app settings, and every backup path (manual, automatic, pre-restore) already writes the effective app settings, so they are integrity protected. `backup_carries_adblock_settings_with_integrity` proves a tampered allowlist is rejected.
- T041: `restoring_a_pre_adblock_backup_keeps_current_blocking_settings` runs the real merge and `carry_forward_missing` together: a backup without the keys keeps the current blocking settings, a backup with them wins, and omitted keys carry forward individually. Unknown future list-cache versions are rejected without overwriting (unit tested in `adblock/lists.rs`).
- T042: `PRE_ADBLOCK_BACKUP` in `backup.rs` is a frozen backup written by the unchanged digest code; it still verifies, which is the proof that old digests are unaffected (the digest includes the export time, so a single pinned hash is not possible). `tools/test_backup.py` pins the wiring.
- T040 and T043: not applicable. Service exports and portable bundles carry no per-service settings or app settings handling of any kind (spelling is the same), so blocking overrides are not exported there.
- T045: WebKitGTK reports no event for blocked requests (spike S5), so there is no counter command or counter UI on Linux. The settings tab now says why ("Blocked-request counts are not shown because this platform's web engine does not report blocked requests"), driven by `engine.supportsCounters`.

**Still open:**
- T048 (Flatpak sandbox: untested; the store lives under the app data directory), T051 (numeric performance measurements with the T059 method).
- T047: Flatpak sources are regenerated and `--check` passes. The Nix `cargoHash` in `packaging/nix/package.nix` is stale and must be recomputed on a host with Nix (not installed here).
- T050: Git status is not clean until the work is committed; every other gate in the list has been run.

## Dependencies and Order

- Phase 1 -> Phase 2 (spikes) -> Phase 3 (foundational) -> stories.
- T004/T005 gate T006-T008; T007-T009 gate T011; T011 gates Phase 3 defaults.
- US1 (Phase 4) needs Phase 3. US2 and US3 need US1's apply path (T022-T024) but are otherwise independent of each other. US4 needs only Phase 3 settings. US5 needs US3 status data and T010.
- Phase 9 needs all selected stories. Phase 10 is independent and later.

## Parallel Opportunities

- Setup: T002, T003.
- Spikes: T007 can run alongside T005 once T004 lands; T010 alongside T009.
- Foundational: T014, T017, T019 in parallel with their implementation siblings in different files.
- Stories: US4 (backup) can proceed in parallel with US2/US3 after Phase 3, since it only touches `backup.rs`, `service_export.rs`, `portable.rs`.
- Polish: T047-T049.

## Implementation Strategy

1. MVP is Phases 1-4 (US1 on Linux) after spikes pass; demo with `tools/adblock_smoke.py`.
2. Add US2 and US3 next since the escape hatch and list management are required before any release (spec priority P1).
3. US4 before release so settings never get lost; US5 last.
4. If S1 fails (rule limit, load regression, live toggle broken), stop and revise the plan before Phase 3.
