# Changelog

All notable changes to Tauridium are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/).

> Release notes **must be written in English**. The section of the tagged
> version is picked up **automatically** as the GitHub Release notes (see
> `.github/workflows/release.yml`), so fill in the section **before** pushing
> the `vX.Y.Z` tag. Entries for 0.1.0–0.1.8 were back-filled from the commit
> history, so they are more terse than the process going forward.

## [Unreleased]

## [0.3.10] - 2026-08-18

### Fixed
- Commit the exact Rust formatting required by Rust 1.94.0 for the 0.3.9 backup and local-recipe additions, so `just release` passes the non-mutating `cargo fmt -- --check` gate on Windows.
- Extend offline release regression coverage for the affected backup, settings, and custom-recipe source forms.

## [0.3.9] - 2026-08-18

### Fixed

- Fixed the native About action remaining visually hidden behind the active service child webview. The backend now hides service webviews before opening About, and the frontend About path repeats that safeguard defensively.
- Routed both the native About menu and the Settings About tab through one deterministic frontend `openAbout()` path.

### Added

- Added portable local-data backup export to a single Tauridium JSON backup file.
- Backups include app settings, local services/workspaces, and complete custom recipe content (`package.json`, `icon.svg`, and `webview.js`).
- Added backup restore with full preflight validation before persistent state is changed. Matching custom recipe ids are overwritten while unrelated existing custom recipes are retained.
- Backups deliberately exclude Ferdium login/session credentials, website cookies/storage, and remote recipe caches. The UI warns that local service configuration can still contain sensitive data such as proxy credentials.

### Tests

- Added regressions for child-webview hiding on About, backup command registration, portable backup contents/exclusions, preflight-before-write ordering, atomic backup writes, size limits, and GUI export/restore wiring.

## [0.3.8] - 2026-08-18

### Fixed

- Linux `just init` now probes for the Tauri v2 Cargo CLI, installs `tauri-cli` with Cargo when missing, and verifies `cargo tauri` before the later production build step.
- Replaced the platform-dependent predefined About menu item with a Tauridium-owned About action that shows the main window and opens an in-app About section.
- Added an About settings tab with version, project description, license, and project identity.

### Tests

- Added Linux bootstrap regressions covering an existing Tauri CLI, automatic installation, post-install re-probing, missing Cargo diagnostics, and `--native-only` behavior.
- Added regression coverage tying the native About menu action to the frontend About section.

## [0.3.7] - 2026-08-17

### Changed

- Runtime ZIP names now include a short suffix derived from the binary's actual Rust compilation target, for example `tauridium-0.3.7-run-win-x64.zip`, `tauridium-0.3.7-run-linux-x64.zip`, or `tauridium-0.3.7-run-macos-arm64.zip`.
- Runtime target identity is recorded at compile time and exposed through the existing non-GUI build-information probe; packaging does not infer the target from the host OS.
- Multiple explicitly supplied runtime binaries are grouped by compilation target and emitted as separate run ZIPs, allowing target artifacts to coexist in one release directory without collisions.
- Documentation checksums include every target-specific run ZIP produced by a multi-runtime packaging invocation.

### Tests

- Added coverage for Windows, Linux, musl, and macOS target suffixes, missing target provenance, and multi-target runtime grouping.


## [0.3.6] - 2026-08-17

### Fixed
- Replaced the false-positive runtime scan for the configured Tauri development URL with an executable build-provenance probe.
- Production runtime packaging now executes the freshly built binary with `--build-info-file` and requires `buildMode` to be `production`.
- Added compile-time Tauri build-mode metadata from `build.rs` so packaging validates the mode that actually controls startup behavior.
- Kept the raw Cargo release guard while allowing valid Tauri production executables to contain inert `build.devUrl` configuration bytes.
- Preserved the English-only tracked-source release gate and full Git-history source archives.

## [0.3.5] - 2026-08-17

### Fixed

- Fixed the Windows compile failure in the download-completion notification caused by an invalid Rust format string.
- Committed the exact remaining Rust formatting required by native `rustfmt 1.94.0` for `AppState` field alignment and the main-window lookup.
- Restored `just check` and the non-mutating `just release` formatting gate on the extracted Windows source release.

### Tests

- Added regression coverage for the valid quoted download-notification format string.
- Extended the offline native-rustfmt baseline guard with the exact formatting that failed in 0.3.4.
- Source ZIP packaging continues to include and validate the complete `.git` repository.

## [0.3.4] - 2026-08-17

### Fixed

- Fixed Windows release executables opening the development URL and failing with `ERR_CONNECTION_REFUSED` when no Vite development server is running.
- Production runtime builds now use `cargo tauri build --no-bundle --ci`, which packages the configured `frontendDist` instead of relying on `devUrl`.
- Added a release-profile build-script guard that rejects raw Cargo release builds when Tauri is still in development/custom-protocol-disabled mode.
- Translated all remaining non-English project prose, comments, UI labels, diagnostics, workflow text, and tests in the current tracked source tree to English.

### Tests

- Runtime packaging rejects binaries containing the configured development localhost URL.
- Added release regressions for the production Tauri build path and raw-release build guard.
- Added an English-only tracked-source audit and regression coverage; the gate includes vendored tracked text while preserving historical Git objects unchanged.
- Source ZIPs continue to include the complete `.git` repository and are validated after extraction.

## [0.3.3] - 2026-08-17

### Fixed

- Committed the exact Rust formatting required by native `rustfmt 1.94.0`, fixing `just release` failing at `fmt-check` immediately after extracting the 0.3.2 source release.
- Corrected formatting in the local-recipe additions in `src-tauri/src/main.rs` and `src-tauri/src/recipes.rs` without changing runtime behavior.

### Tests

- Added an offline regression for the exact native-rustfmt forms that drifted in 0.3.2, so packaging environments without a Rust toolchain still catch this known formatting regression.
- `just release` continues to enforce a real non-mutating `cargo fmt -- --check` gate when run in a Rust development environment.
- Source ZIP packaging continues to include the complete `.git` repository and validates extracted Git history, tags, clean status, and object integrity.

## [0.3.2] - 2026-08-17

### Fixed

- Fixed `just release` invalidating its own clean-worktree packaging gate by replacing the mutating release-time `cargo fmt` step with `cargo fmt -- --check`.
- Added explicit clean-worktree checks before and after release validation/build gates so packaging failures identify source changes at the point they occur.
- Release packaging now reports the exact dirty Git paths instead of only a generic clean-worktree error.
- Normalized Rust formatting in source areas that were rewritten by `cargo fmt` during the 0.3.1 Windows release attempt.

### Changed

- Cargo Clippy, check, test, build, and documentation recipes now use `--locked` so release validation cannot silently rewrite `Cargo.lock`.
- `just fmt` remains the explicit source-mutating formatter; `just release` is intentionally non-mutating.
- Source ZIPs continue to include the complete `.git` directory and are validated after extraction as clean Git repositories with release history and tags intact.

### Tests

- Added regression coverage for non-mutating release orchestration, locked Cargo gates, clean-worktree diagnostics, and exact dirty-path reporting.
- Preserved source-ZIP extraction checks for Git history, exact tag resolution, clean status, and `git fsck --full`.

## [0.3.1] - 2026-08-17

### Fixed

- Fixed Rust `E0505` in remote recipe catalog merging by owning the validated recipe id before mutating and moving the recipe value.
- Restored `cargo check`/Clippy compilability for the local-recipe feature introduced in 0.3.0.

### Changed

- Source release ZIPs now include the complete `.git` directory from the release checkout, including commit objects, refs, tags, index, and Git metadata needed for an immediately usable checkout after extraction.
- Source ZIP creation now requires a real Git checkout instead of silently producing a history-less source archive.
- `.tauridium-source-manifest.json` is ignored by Git so extracted official source ZIPs retain a clean worktree while preserving manifest verification.
- Packaged Git configuration normalizes `core.filemode=false` so extracted source ZIPs remain clean on Windows and extractors/filesystems that do not preserve Unix executable bits.

### Tests

- Added a regression for the remote-recipe borrow/move pattern that caused `E0505`.
- Added source-package regression coverage that extracts the ZIP and verifies Git commit history, exact release tag resolution, clean status, and `git fsck --full`.
- Added a release invariant requiring `.git` history packaging support.

## [0.3.0] - 2026-08-17

### Added

- Added a built-in **Custom Website** recipe and a direct fallback action when recipe search has no match.
- Added locally managed recipes under Tauridium's OS configuration directory in `recipes/<recipe-id>/`.
- Added GUI import for recipe folders and individual `package.json` files.
- Added a lightweight local recipe creator with name, stable recipe id, service URL, description, custom-URL/team options, optional `icon.svg`, and optional `webview.js`.
- Added bundled NanoGPT, Chutes, and OpenCode Web recipes available without a Ferdium recipe catalog entry.
- Added source labels for bundled, custom, and remote recipes in the recipe picker.

### Changed

- Recipe discovery now merges remote recipes with bundled and user-owned recipes, keeping local recipes available when remote discovery is offline.
- Bundled recipe ids are reserved and cannot be shadowed by manually placed or imported custom recipes.
- Tauridium-local recipes create locally owned service records even while signed in to a Ferdium server, so custom recipes never depend on `/v1/service` accepting an unknown recipe id.
- Signed-in service lists overlay only explicitly local-recipe services; legacy accountless services are not duplicated into a server session.
- Imported recipe ids are normalized to their canonical local destination id.

### Security

- Local recipe ids are validated before filesystem access.
- Local recipe service URLs are restricted to HTTP(S).
- Recipe package writes use atomic replacement, with `package.json` written last as the discovery marker.
- The creator warns that optional `webview.js` executes inside the loaded service page and should only contain trusted code.

### Tests

- Added Rust unit coverage for bundled provider URLs, HTTP(S) validation, reserved ids, recipe companion-file persistence, local-service filtering, and signed-in/local service merging.
- Added frontend tests for custom-website commands, recipe persistence/import payloads, URL normalization, website-name derivation, URL detection, and recipe-id generation.
- Added release-invariant coverage for the local recipe commands, storage layout, no-match Custom Website UI, reserved built-in recipes, and bundled AI provider endpoints.

## [0.2.5] - 2026-08-17

### Fixed

- Fixed repeated Windows initialization falsely treating an already installed Node.js as missing when the parent PowerShell process still had a stale PATH.
- Reloaded persisted Machine/User PATH values before prerequisite discovery and after package-manager changes.
- Stopped treating a non-zero winget install exit code as authoritative when the requested executable is actually available after PATH refresh.
- Added post-install executable validation for Node.js, Python, Git, and rustup.
- Added a PowerShell Python resolver supporting py.exe, python.exe, and python3.exe so Scoop-installed Python works throughout Windows just recipes.

### Changed

- Windows prerequisite installation now prefers Scoop for Node.js LTS, Python, Git, and rustup.
- winget remains the fallback when Scoop is unavailable or does not produce a usable prerequisite.
- System-integrated MSVC Build Tools and WebView2 installation continue to use winget where an equivalent Scoop path is not reliable for the required Windows integration.

### Tests

- Added regression coverage for PATH refresh ordering, Scoop-first package-manager ordering, winget fallback, and the PowerShell Python resolver.
- Extended init-self-test to parse tools/python.ps1 in addition to tools/init.ps1.

## [0.2.4] - 2026-08-17

### Fixed

- Fixed `just init` aborting when `py.exe -3 --version` reports that no Python runtime is installed.
- Isolated expected native-command probe failures from `$ErrorActionPreference = "Stop"` under Windows PowerShell 5.1.
- Python bootstrap now reaches the `winget` installation branch when the Python launcher exists without an installed interpreter.
- Hardened Visual Studio, VBSCRIPT, Node.js, `winget show`, `cargo tauri`, and `cargo audit` capability probes against the same native-stderr failure mode.
- Preserved fatal handling for actual prerequisite installation and build failures.

### Tests

- Extended `just init-self-test` with a real native command that writes to stderr and exits non-zero, verifying the probe is safely contained.
- Added regression and release-invariant coverage for isolated native prerequisite probes.

## [0.2.3] - 2026-08-17

### Fixed

- Fixed Windows PowerShell 5.1 parse failure in `tools/init.ps1`.
- Removed Markdown-style backticks from PowerShell diagnostic strings.
- Fixed misleading parser errors reported near the Visual Studio `--config` override.
- Kept the initializer function-free and free of indirect bootstrap dispatch.

### Tests

- Added a regression that forbids PowerShell backticks in the Windows initializer.
- Added the same parser-safety invariant to release validation.
- Retained `just init-self-test` as the first native Windows bootstrap gate.

## [0.2.2] - 2026-08-17

### Fixed
- Replaced the Windows initializer's custom PowerShell function/script-block bootstrap dispatch with a linear execution path.
- Fixed `just init` failing with an invalid call-operator target for the MSVC bootstrap task.
- Fixed `just init-self-test` reporting `Test-MsvcBuildTools` as unavailable despite the helper being present in source.
- MSVC, WebView2, VBSCRIPT, Node.js, Python, Git, Rustup, Cargo tooling, and npm bootstrap handling now execute without user-defined PowerShell helper functions.

### Changed
- `just init-self-test` now validates the release identity, PowerShell parser acceptance, `.vsconfig`, and required Visual Studio components using only built-in PowerShell/.NET facilities.
- Windows bootstrap regression tests now reject reintroduction of custom function dispatch or the 0.2.1 MSVC script-block task.


## [0.2.1] - 2026-08-17

### Fixed
- Windows `just init` no longer dispatches the MSVC prerequisite bootstrap through the failing `Ensure-MsvcBuildTools` function lookup seen under Windows PowerShell.
- MSVC Build Tools prerequisite handling now runs through a directly invoked PowerShell script block while preserving the existing detection and installation behavior.

### Added
- `just init-self-test` validates Windows PowerShell bootstrap command/script-block availability without installing or changing system prerequisites.
- Native Windows CI now runs the bootstrap self-test before prerequisite initialization.
- Regression coverage prevents the MSVC bootstrap from returning to the failing named-function dispatch path.


## [0.2.0] - 2026-08-17

### Added
- First-class native Windows 11 development and release workflow using Windows PowerShell/PowerShell only; WSL, Bash, Git Bash, and Nushell are not required.
- Windows `just init` bootstrap for MSVC Build Tools, Windows 11 SDK, WebView2, Node.js LTS, Python 3.13, Git, rustup/MSVC, `cargo-tauri`, `cargo-audit`, rustfmt, Clippy, and MSI VBSCRIPT support.
- Checked-in `.vsconfig` covering x64 and ARM64 MSVC toolchains plus the Windows 11 SDK.
- `just init-native` and `-NoSystemChanges` support for Windows prerequisite-only and non-mutating diagnostics.
- Native Windows CI job running the full PowerShell development pipeline.
- Cross-platform Node release-version synchronizer used by release jobs instead of forcing Bash on Windows.
- Windows workflow regression tests covering shell selection, prerequisite bootstrap, CI, release synchronization, and Visual Studio configuration.

### Changed
- `justfile` now selects `powershell.exe` on Windows and `sh` on Unix using supported conditional shell settings.
- Windows Python tooling uses the standard `py -3` launcher; Windows cleanup uses native `Remove-Item`.
- Source ZIP permissions now come from Git index modes, making release archives deterministic across Windows and Unix hosts.
- Runtime executables are always packaged with executable ZIP permissions independent of host filesystem semantics.


## [0.1.18] - 2026-08-17

### Fixed
- `just release` now works from an extracted Tauridium source ZIP that intentionally contains no `.git` directory.
- Release packaging no longer unconditionally executes `git status`, `git ls-files`, or `git log` when Git metadata is absent.

### Added
- Source ZIPs now embed `.tauridium-source-manifest.json` with the exact packaged file list, SHA-256 digests, file modes, release version, Git commit/tree/tag, and Git-log snapshot.
- Extracted-source packaging verifies every manifest-listed source file before creating release archives, rejecting modified, stale, or incomplete source trees.
- Five regression tests cover no-Git source packaging, integrity rejection, manifest requirements, deterministic source contents, and Git-log reuse in documentation archives.
- Release validation now requires the source-manifest fallback and its regression coverage.

## [0.1.17] - 2026-08-17

### Fixed
- Frontend Tauri API tests now create the shared `invoke` mock with `vi.hoisted`, preventing Vitest from evaluating the mocked module factory before the mock variable is initialized.
- `just test` no longer fails with `ReferenceError: Cannot access 'invoke' before initialization`.

### Added
- Release validation now rejects the hoist-unsafe top-level `const invoke = vi.fn()` pattern in `src/lib/api.test.ts`.

## [0.1.16] - 2026-08-17

### Fixed
- `just init` no longer invokes esbuild's platform-native executable through Node.js.
- esbuild validation now uses `npm exec --offline -- esbuild --version`, which executes the local package binary correctly on each platform and cannot fall back to the registry.

### Added
- Regression coverage preventing the native esbuild binary from being passed to `node`.
- Release invariants requiring the platform-aware offline esbuild validation path.

## [0.1.15] - 2026-08-17

- Fixed stale/mixed release extraction being able to execute an older initializer silently.
- Added an initializer release-identity guard before any package-manager or npm mutation.
- Added an explicit `Tauridium initializer 0.1.15.` startup banner for immediate provenance.
- Hardened the libxdo compile/link probe with an explicit `stddef.h` include.
- Added `--native-only` for isolated native-prerequisite verification.
- Reworded native prerequisite failures so non-pkg-config probes are reported accurately.
- Added regressions for release identity, stale-overlay rejection, and native-only execution.

## [0.1.14] - 2026-08-17
### Fixed
- `just init` no longer falsely reports `xdo` missing on Debian/Ubuntu after `libxdo-dev` is already installed.
- Linux prerequisite validation now checks libxdo by compiling/linking against `xdo.h` and `-lxdo` instead of requiring nonexistent Debian `xdo.pc` metadata.

### Added
- Regression coverage for Debian-style libxdo installations without pkg-config metadata and for genuinely missing libxdo development files.
- Release invariants preventing `xdo` from being reintroduced as a mandatory pkg-config module.

## [0.1.13] - 2026-08-17
### Fixed
- Fresh `npm ci` no longer starts with the two high-severity transitive findings observed in 0.1.12; reviewed patched `nanoid` and `postcss` versions are locked reproducibly.
- `esbuild@0.25.12` install-script approval is committed in `package.json`, removing the manual `npm approve-scripts esbuild` bootstrap step.
- `just init` detects missing Linux GTK/WebKitGTK and related native `pkg-config` modules/build tools, then installs the Tauri v2 native prerequisites automatically on supported distributions.

### Changed
- `just init` now performs native-prerequisite verification, reproducible `npm ci`, a high-severity npm audit, and an `esbuild` execution check.
- Linux initialization supports Debian/Ubuntu, Fedora/RHEL, Arch/Manjaro, Alpine, and openSUSE package families and fails explicitly instead of guessing on unsupported distributions.
- Initializer regression tests run as part of `just test`.
- Rust source is normalized with Rust 1.97.1 `rustfmt`, keeping the release format gate clean on the supplied project toolchain.
- Set `TAURIDIUM_INIT_SYSTEM_DEPS=0` to forbid automatic system-package installation while still validating that the required native libraries are present.

## [0.1.12] - 2026-08-14
### Fixed
- Warning-free Rust release linting under `cargo clippy --all-targets --all-features -- -D warnings`.
- Service show/preload commands now use one typed request payload instead of over-wide command signatures.
- macOS-only UUID storage helper is compiled only where used, while remaining available to unit tests.
- Test module ordering, consuming dark-mode conversion naming, and needless app-handle borrows now follow Clippy guidance.

### Added
- Frontend regression coverage for the typed service-view command payload.
- Zero-argument `just package` and `just release` recipes that package the platform release executable automatically.

## [0.1.11] - 2026-08-14
### Added
- Accountless local mode with locally persisted services and workspaces.
- Local recipe discovery from the Ferdium Recipes repository with disk caching.
- Regression coverage for local persistence, CRUD, workspace cleanup, validation, IDs, and interrupted-write recovery.
### Changed
- Local sessions restore without contacting a Ferdium server.
- Server-backed mode and legacy server-session files remain compatible.
- Persistent file replacement recovers safely from interrupted Windows replacement.
- CI targets `master`, enforces warning-free Rust gates, and uses current stable action releases.

## [0.1.10] - 2026-07-10
### Fixed
- **Doubled keystrokes in Discord's channel search.** On macOS, WKWebView
  dispatched two native `textInput` events per keystroke, so Draft.js-based
  fields (Discord's channel search) inserted every character twice. The
  duplicate is now de-duplicated (at most one insertion per keydown).
- **Doubled accented characters in Discord's message composer.** Dead keys /
  IME composition with accented characters inserted the character twice in the Slate composer.
  The redundant legacy `textInput` is now neutralized in Slate editors only, so
  Draft.js accent input (search) keeps working.
### Added
- **In-app downloads.** Downloads triggered from within a service (e.g.
  WhatsApp's image download button, ChatGPT image downloads) now save to your
  Downloads folder, with a completion notification.
- **Developer Tools in release builds.** "Toggle Developer Tools" (⌘⌥I) now
  works in the packaged app, not just in `cargo tauri dev`.
### Known limitations
- The native right-click **"Download Image"** context-menu item does not work:
  WKWebView handles it through an internal path that is not exposed to the app.
  Use a service's in-page download button instead.

## [0.1.9] - 2026-07-09
### Fixed
- **Links in conversations are clickable again.** `target="_blank"` links and
  `window.open` calls no longer responded to clicks on macOS. They now open in
  your default browser, while sign-in popups (sized OAuth windows) open in an
  in-app window so the session is preserved and the service webview stays in
  place.

## [0.1.8] - 2026-07-06
### Added
- Per-service dark mode via Dark Reader.
- Reorder services by drag & drop, plus ⌘1–9 shortcuts to switch services.
- Per-service loading / error indicator with retry.
- Per-service "Clear cache", and data-store purge when a service is removed.
- Auto-reconnect screen when the Ferdium server is unreachable.
### Fixed
- No longer signs out on reload after a transient network error.
- Service-switch race condition.
- Batch of robustness quick-wins from a code review.

## [0.1.7] - 2026-07-03
### Fixed
- Removing a workspace or service now uses a native dialog (the browser
  `window.confirm` does not work in WKWebView, so the confirmation was broken).
### Changed
- Warn about passkey / WebAuthn limitations under WKWebView (docs and UI).

## [0.1.6] - 2026-07-03
### Added
- Service preloading; reload a service or the whole app.
### Changed
- Settings descriptions adapted to the host OS.
### Fixed
- Cleaned up wry warnings.

## [0.1.5] - 2026-07-03
### Added
- Show the app version in the sidebar footer.

## [0.1.4] - 2026-07-02
### Added
- Auto-updater (`tauri-plugin-updater`) with an Updates tab — first release with
  automatic updates.
- Google compatibility (user-agent / spoofing), cross-platform session
  isolation, and service hibernation (inspired by Ferx).

## [0.1.3] - 2026-07-02
### Changed
- Documented how to open unsigned macOS builds past Gatekeeper.

## [0.1.2] - 2026-07-02
### Added
- macOS code signing + notarization wiring (enabled only when Apple secrets are
  present).
### Fixed
- Release pipeline: conditional macOS signing no longer breaks the build when no
  signing secrets are set; the release is created in a single job (fixes the
  build-matrix race that produced duplicate releases); bundles are named after
  the tag.

## [0.1.1] - 2026-07-01
### Changed
- Maintenance re-tag to exercise the release pipeline; no functional changes.

## [0.1.0] - 2026-07-01
Initial release — a lightweight Ferdium client built with Tauri v2.
### Added
- Render each Ferdium service in its own isolated child webview.
- Sidebar with unread badges and workspaces (selector + management).
- Native notifications and a dock-badge pipeline.
- Close-to-tray: menubar icon, window hidden instead of quitting.
- App settings: theme (system / dark / light), autostart, start in background.
- Per-service settings, plus add / remove services.
- Tabbed settings with an English UI.
- Multi-platform release pipeline on tag (macOS, Linux, Windows) with tests on
  every push.
