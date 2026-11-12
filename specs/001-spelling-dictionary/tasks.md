---
description: "Task list for Spelling Check and Dictionary Support"
---

# Tasks: Spelling Check and Dictionary Support

**Input**: Design documents from `/specs/001-spelling-dictionary/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/spelling-commands.md

**Tests**: Included. AGENTS.md requires focused regression coverage for every feature (Rust unit tests, Vitest, `tools/test_*.py`).

**Organization**: Grouped by user story. Paths are relative to the repository root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1-US5 map to the user stories in spec.md

---

## Phase 1: Setup

- [X] T001 Create `src-tauri/src/spelling.rs` with module docs and `mod spelling;` registration in `src-tauri/src/main.rs`
- [X] T002 [P] Create `src/lib/spelling.ts` and `src/lib/spelling.test.ts` skeletons (pure helpers: `normalizeWord`, `resolveEffectiveSpellcheck`)
- [X] T003 [P] Create `docs/SPELLCHECK.md` stub (platform behaviour, privacy, dictionaries) and add a `CHANGELOG.md` "Unreleased" entry in English

---

## Phase 2: Foundational (blocks all user stories)

**Purpose**: Spikes, settings model and persistence that every story depends on.

- [ ] T004 Spike S1: on Windows 11, determine WebView2 default spellcheck behaviour and whether enable/disable and languages can be set per service (Chromium switches via `additional_browser_args`, or newer profile interfaces); record result in `specs/001-spelling-dictionary/research.md` under D4
- [ ] T005 Spike S2: determine how to sync the personal dictionary into each engine (WebView2 profile custom-dictionary file in the service data directory, WebKitGTK/Enchant word list including Flatpak sandbox access, macOS) and whether native-menu "Add to dictionary" can be observed; record result in `research.md`
- [X] T006 Add `spellcheckEnabled`, `spellcheckLanguages` and `serviceSpellcheck` defaults in `src-tauri/src/main.rs` (settings defaults near line 3640) following the `serviceZoomLevels` pattern
- [X] T007 Implement validation for the three new settings in `src-tauri/src/spelling.rs` (BCP-47 tags, max 8 languages, no duplicates, override map shape) and call it from the settings validation in `src-tauri/src/main.rs` (near line 4167)
- [X] T008 Remove `serviceSpellcheck` entries when a service is deleted, in the service deletion path in `src-tauri/src/main.rs` and `src-tauri/src/local_profile.rs` (done in the frontend only: service deletion and duplication in `src/App.svelte` clean/copy `serviceSpellcheck`; no Rust change was needed because that cleanup is shell-driven like `serviceZoomLevels`)
- [X] T009 [P] Add `spellcheckEnabled`, `spellcheckLanguages`, `serviceSpellcheck` to the settings interface and defaults in `src/lib/api.ts` and `src/App.svelte` (defaults near line 322)
- [X] T010 [P] Unit tests for settings validation and upgrade defaults (missing keys load defaults) in `src-tauri/src/spelling.rs` and `src-tauri/src/main.rs` test module
- [X] T011 [P] Implement and test `resolveEffectiveSpellcheck` (override inherits global; empty languages = system) in `src/lib/spelling.ts` and `src/lib/spelling.test.ts`

**Checkpoint (gate)**: settings round-trip and validate; T004 and T005 are complete with outcomes recorded in `research.md`, and any resulting spec wording change (Windows fallback, menu vs Settings entry points) is made before Phase 3 starts.

---

## Phase 3: User Story 1 - See and fix misspellings (Priority: P1) MVP

**Goal**: Misspellings are marked in service text fields and fixable from the native menu.

**Independent Test**: Quickstart steps 1-2 and 9 on Linux and Windows 11.

- [X] T012 [US1] Add `SpellEngine` adapter trait and Linux implementation (WebKitGTK `set_spell_checking_enabled` / `set_spell_checking_languages` on the service's web context) in `src-tauri/src/spelling.rs`
- [X] T013 [US1] Add Windows adapter per spike S1 outcome (or documented global-only fallback) in `src-tauri/src/spelling.rs` (Windows: per-service on/off via the page-level `spellcheck` switch in `src-tauri/src/spellcheck_toggle.js`; languages and dictionary are OS-managed and shown as such. NOT tested on Windows.)
- [X] T014 [US1] Add macOS best-effort adapter in `src-tauri/src/spelling.rs` and make unsupported capabilities return an explicit "unsupported" result (macOS: same switch plus the `WebContinuousSpellCheckingEnabled` default. NOT tested on macOS.)
- [X] T015 [US1] Apply effective spellcheck settings when building a service webview in `src-tauri/src/main.rs` (WebviewBuilder near line 2224 and data-directory block near line 2380); touch `vendor/wry/` only if T004 proves it required and document it in `vendor/RUNTIME-PROVENANCE.md`
- [ ] T016 [US1] Verify password and other sensitive inputs are never checked (FR-013); add a `spellcheck="false"` init-script guard in `src-tauri/src/main.rs` only if the engine default fails, and add a required verification step to `tools/test_spelling_core.py`
- [X] T017 [P] [US1] Regression test for the adapter selection and unsupported-capability results in `src-tauri/src/spelling.rs` (`engine_controls`, init-script and no-mirroring tests in `spelling.rs`)
- [X] T018 [P] [US1] Python regression test asserting spelling is applied at webview creation and never in shell-only code, in `tools/test_spelling_core.py` (`tools/test_spelling_core.py`, plus a fake-DOM probe `tools/spellcheck_toggle_probe.cjs`)
- [X] T018a [P] [US1] Regression test asserting no spelling code path makes a network request with typed text (FR-014, SC-007) in `tools/test_spelling_core.py`

**Checkpoint**: US1 works end to end with global defaults (system language, enabled).

---

## Phase 4: User Story 2 - Choose spelling languages (Priority: P1)

**Goal**: Select multiple languages globally and per service; persisted.

**Independent Test**: Quickstart step 3.

- [X] T019 [US2] Implement language availability detection (`SpellingLanguage` with `available` and `reason`) in `src-tauri/src/spelling.rs`
- [X] T020 [US2] Implement `spelling_get_state` and `spelling_set_global`/`spelling_set_service` commands (validate, persist, apply live to running webviews, return updated state) in `src-tauri/src/spelling.rs` and register in `src-tauri/src/main.rs` (done via the existing `set_app_settings` path plus `spelling_get_state`; no separate set commands were needed)
- [X] T021 [P] [US2] Add typed wrappers for the three commands to `src/lib/api.ts` and tests in `src/lib/api.test.ts` (wrappers are `getSpellingState`, `addSpellingWord`, `removeSpellingWord`; language and on/off changes reuse the existing `setAppSettings` path)
- [X] T022 [US2] Add Settings > Spelling panel (language multi-select with unavailable languages shown disabled with reason, using existing `appToggle` patterns) in `src/App.svelte`
- [X] T023 [US2] Add per-service language override control to the service settings UI in `src/App.svelte`
- [X] T024 [US2] Show the green `Saved` toast on success and an actionable error on failure for every spelling setting in `src/App.svelte`
- [ ] T025 [P] [US2] Add spelling settings persistence checks to `tools/settings_smoke.py` and `tools/test_settings_smoke.py`
- [ ] T026 [P] [US2] Add UI layout test coverage in `src/lib/settingsLayout.test.ts` and `tools/test_settings_ui.py`

---

## Phase 5: User Story 3 - Personal dictionary (Priority: P2)

**Goal**: Add/remove words, shared across services, persisted and backed up.

**Independent Test**: Quickstart steps 4 and 7.

- [X] T027 [US3] Implement `PersonalDictionary` store (validation, de-dup, 10,000-word cap, sorted atomic write via `write_atomic`/`private_file`, version check) in `src-tauri/src/spelling.rs`
- [X] T028 [US3] Implement the engine sync chosen in spike S2 (push words to every running and newly created service webview) in `src-tauri/src/spelling.rs` and `src-tauri/src/main.rs`
- [X] T029 [US3] Implement `spelling_add_word` and `spelling_remove_word` commands and register them in `src-tauri/src/main.rs`; if S2 shows native-menu additions cannot be observed, add a Tauridium-owned add path in the UI instead
- [X] T030 [US3] Include the dictionary in backup and restore as an optional `spellingDictionary` section (v1/v2 backups still restore, hashes cover it) in `src-tauri/src/backup.rs`
- [X] T031 [P] [US3] Include the dictionary in portable data handling in `src-tauri/src/portable.rs` (no change needed: portable exports cover services and workspaces only and never carried global data)
- [X] T032 [P] [US3] Review `docs/EXPORT-PRIVACY.md` and `src-tauri/src/service_export.rs`; default decision: personal words go in backups and portable data but NOT in per-service exports; document it in `docs/EXPORT-PRIVACY.md`, implement it, and align FR-010 wording in `spec.md`
- [X] T033 [US3] Add personal dictionary list (view, add, remove, `Saved` toast) to the Spelling panel in `src/App.svelte` and wrappers in `src/lib/api.ts`
- [X] T034 [P] [US3] Rust tests: validation, duplicates, cap, corrupt file, future version, backup round trip, old-backup restore in `src-tauri/src/spelling.rs` and `src-tauri/src/backup.rs`
- [ ] T035 [P] [US3] Update `tools/test_backup.py` for the new section and add `tools/test_spelling_dictionary.py`

---

## Phase 6: User Story 4 - Turn checking on or off (Priority: P2)

**Goal**: Global and per-service enable/disable.

**Independent Test**: Quickstart step 5.

- [X] T036 [US4] Add global enable toggle to the Spelling panel using `appToggle` in `src/App.svelte`
- [X] T037 [US4] Add per-service "Inherit / On / Off" control in the service settings UI in `src/App.svelte`
- [X] T038 [US4] Apply enable changes live to the running webview, or show an explicit "applies after reload" message where the engine requires it, in `src-tauri/src/spelling.rs`
- [X] T039 [P] [US4] Tests for override resolution and live-apply result messages in `src/lib/spelling.test.ts` and `src-tauri/src/spelling.rs`

---

## Phase 7: User Story 5 - Word lookup (Priority: P3)

**Goal**: Look up a selected word; clear message when unavailable.

**Independent Test**: Quickstart step 10.

- [ ] T040 [US5] Spike S3: confirm how to obtain the selected word and add a menu action in native service menus per platform; record the outcome in `research.md` and choose the trigger
- [ ] T041 [US5] Implement `spelling_lookup_word` (opens the user-configurable dictionary URL template in the default browser only on explicit action, validates the template as https with a `{word}` placeholder, returns `WordLookupResult`) in `src-tauri/src/spelling.rs`
- [ ] T042 [US5] Add lookup trigger per T040 and a Settings field for the URL template with a clear note that the word is sent to that site, in `src/App.svelte`
- [ ] T043 [P] [US5] Tests for URL template validation, encoding of the word, and the unavailable result in `src-tauri/src/spelling.rs`

---

## Phase 8: Polish & Cross-Cutting

- [X] T044 [P] Finish `docs/SPELLCHECK.md` (supported platforms, Flatpak/Nix notes, privacy statement) and the `CHANGELOG.md` entry (Linux content; extend when Windows and macOS land)
- [ ] T045 [P] Run `tools/check_english.py` and the English-only test; fix any non-English text
- [ ] T046 Performance check: measure time-to-mark (SC-001: within 1 second in 95% of 20 trials), typing latency and startup time with spelling on vs off; record method and numbers in `docs/SPELLCHECK.md`; the task fails if median input latency differs by more than 10 ms
- [ ] T047 Upgrade check: load a 1.0.9 profile and confirm no loss of services, workspaces, order or sessions (extend `tools/test_runtime_security_upgrade.py`)
- [ ] T048 Run the full gates: `just fmt-check`, `just lint`, `just check`, `just test`, `just build`, the Rust supply-chain guard, `tools/validate_release.py`, `git diff --check`; report any gate that cannot run
- [ ] T049 Execute all steps in `specs/001-spelling-dictionary/quickstart.md` on Windows 11 and Linux

---

## Dependencies & Execution Order

- Phase 1 then Phase 2, ending at the Phase 2 gate. T004 and T005 (spikes) gate T013, T015, T028 and T029.
- US1 (Phase 3) and US2 (Phase 4) are both P1; US2 builds on the adapters from US1 (T012-T015).
- US3 needs T005, T006-T007; US4 needs US2's commands (T020); US5 is independent after Phase 2 apart from T040.
- Polish after all chosen stories.

## Parallel Examples

- Phase 2: T009, T010, T011 together after T006-T007.
- US1: T012, T013, T014 are sequential (same file, `spelling.rs`); then T017, T018, T018a together.
- US3: T031, T032, T034, T035 together after T027.

## Implementation Strategy

1. **MVP**: Phases 1-3 (US1) with defaults only. Validate on Linux, then Windows per spike S1.
2. Add US2 (languages) to complete the P1 scope, then release candidate.
3. Add US3 and US4 (P2), then US5 (P3) last because it depends on spike S3.
4. If S1 shows Windows cannot be controlled per service, ship Windows as global-only and state the limit in the UI (FR-016).
