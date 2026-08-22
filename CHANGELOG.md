# Changelog

## [0.6.4] - 2026-08-22

### Fixed

- Highlighted the currently active workspace in the quick workspace switcher with the same accent background and foreground treatment used by selected service items, including the **All services** state. Keyboard/hover navigation remains a separate neutral cursor state.

### Release quality

- Added focused 0.6.4 regression coverage for current-workspace semantics, the All services fallback, and coherent accent styling.

## [0.6.3] - 2026-08-22

### Fixed

- Fixed Windows 11 maximized/fullscreen startup restoration replaying the persisted window state more than once. The window-state plugin now owns the single startup restore, while tray/menu reveals simply show the already-live window without retriggering geometry or window-mode transitions.
- Made the **Collapsed icon spacing** slider automatically switch to collapsed sidebar mode while it is adjusted, and the **Expanded service spacing** slider automatically switch to expanded mode. The selected spacing and resulting sidebar state are persisted together.

### Release quality

- Added focused 0.6.3 regression coverage for single-pass window restoration, tray/menu reveal behavior, automatic sidebar-mode previews, and atomic spacing/sidebar-state persistence.

## [0.6.2] - 2026-08-22

### Added

- Added independent **Settings -> Appearance -> Sidebar** sliders for collapsed icon spacing and expanded service-row spacing. Both preserve the existing compact 2 px spacing as the minimum and can increase it up to 24 px with live preview.

### Fixed

- Made the green **Saved** toast consistent for immediately persisted Settings controls by centralizing feedback in the app-setting save path and covering direct-save exceptions including workspace downloads, workspace name/icon/membership changes, service/workspace ordering, custom accents, and sandbox assignment.
- Improved immediate-setting failure handling so a persistence failure restores the previous visual value, while failures in follow-up runtime application are reported without pretending the persisted setting was rolled back.

### Release quality

- Added focused 0.6.2 regression coverage for spacing defaults/ranges, live CSS application, minimum-density preservation, and Saved-toast coverage across central and direct persistence paths.

## [0.6.1] - 2026-08-22

### Added

- Added **Settings -> Appearance -> Sidebar** startup controls for choosing the default expanded/collapsed state and optionally restoring the most recently used sidebar state. Restore-last takes precedence, matching the existing startup-workspace preference model.

### Fixed

- Made collapsed service selection targets exact 42 x 42 px squares, always larger than every supported service icon size.
- Rebalanced the collapsed icon rail to 52 px with symmetric 5 px outer margins while preserving the existing icon center position, and removed visible scrollbar gutter width so service icons, the collapse control, and selection backgrounds stay precisely aligned.

### Release quality

- Added focused 0.6.1 regression coverage for startup-state precedence, settings persistence/validation, collapsed selection geometry, icon-size clearance, and centered rail layout.

## [0.6.0] - 2026-08-22

### Added

- Added a persistent, accessible sidebar collapse mode that turns the service list into a carefully aligned 64 px icon-only rail while preserving the configured expanded width.
- Added a dedicated sidebar collapse button, **View -> Toggle Sidebar**, and the default **Ctrl+Shift+B** keybinding, including service-webview shortcut capture and customizable keybinding support.

### Changed

- Kept account/workspace text and footer statistics out of collapsed mode, retained compact unread indicators and service tooltips, and kept icon sizing, drag-and-drop ordering, context menus, workspace filtering, themes, and sidebar list alignment working in both states.
- Fixed the `release` just recipe so `release-clean` is not declared twice as a dependency; the post-CI cleanliness check is now an explicit step before packaging.
- Normalized tracked Markdown typography with the supplied Unicode normalizer rules before release.

### Release quality

- Added focused 0.6.0 regression coverage for persistence, geometry, shortcut routing, accessibility, icon-only rendering, settings integration, and release-recipe semantics.

## [0.5.5] - 2026-08-22

### Changed

- Replaced the project README with the maintained concise project presentation and installation/development guidance.
- Reworked CI and tagged releases around canonical `just` recipes, with signed Windows x64/ARM64 MSI and NSIS installers, Linux x64/ARM64 AppImage/DEB/RPM packages, portable runtime ZIPs, deterministic source/documentation/build handoff archives, updater metadata, release notes, and SHA-256 checksums.

### Release quality

- Added release-asset validation, fail-closed updater signing, draft-first publishing, current pinned GitHub Actions, weekly GitHub Actions dependency updates, and focused 0.5.5 regression coverage for the release pipeline.

## [0.5.4] - 2026-08-22

### Fixed

- Fixed built-in default keybindings so they work immediately without requiring users to re-record the same shortcut, including reliable native handling of **Ctrl+,** for Settings and consistent matching across the shell and service webviews.
- Fixed service preloading so preloaded services remain live off-screen and switch in without a first-use reload; rapid switches during an in-flight preload now hand off the existing webview instead of racing creation.
- Fixed service hibernation lifecycle so inactive services are only destroyed by the explicit hibernation timer when both global hibernation and the per-service opt-in are enabled. With the default timer set to **Off**, inactive/preloaded services stay alive.

### Release quality

- Added focused 0.5.4 regression coverage for all default shortcuts, preload activation and cancellation, hidden-panel behavior, preload/switch races, and hibernation defaults/timer reconciliation.

## [0.5.3] - 2026-08-22

### Added

- Added **Settings -> Workspaces -> Startup workspace** controls for choosing a default startup workspace and optionally restoring the workspace that was active most recently.

### Changed

- Startup workspace selection now uses deterministic precedence: remembered workspace when enabled, configured default as fallback, then **All services**. Stale/deleted workspace references are cleaned safely, and selecting **All services** is remembered explicitly.

### Release quality

- Added focused 0.5.3 regression coverage for settings persistence and validation, startup precedence, stale-workspace fallback, deletion cleanup, and startup UI controls.

## [0.5.2] - 2026-08-21

### Changed

- Moved session sign-out from the sidebar account row into the native **Tauridium** application menu between **Show All** and **Exit**, with dedicated separators and session-aware enablement.
- Reused the reclaimed sidebar account-row space to display the active workspace name, using **All services** for the unfiltered scope and safe truncation for narrow sidebars.

### Release quality

- Added focused 0.5.2 regression coverage for native-menu ordering and sign-out routing, session-aware availability, sidebar removal, and active-workspace scope rendering.

## [0.5.1] - 2026-08-21

### Changed

- Condensed and reorganized README development/release guidance around Windows 11-first support, secondary Linux coverage, and best-effort untested macOS participation while preserving the existing introduction, Why, Features, Tech stack, and Licence sections.
- Added a compact root `AGENTS.md` with Tauridium's architecture, development direction, Git/release conventions, and non-negotiable quality gates for future AI-assisted development.
- Restored `.tauridium-source-manifest.json` to generated release metadata instead of tracked source and included `AGENTS.md` in documentation archives.

## [0.5.0] - 2026-08-21

### Changed

- Aligned Tauridium's current project authorship, repository/homepage metadata, badges, About links, application identity, and MIT licence presentation with the maintained fork.

## [0.4.29] - 2026-08-21

### Added

- Added an **About** menu immediately after **Services** in the native application menu, with direct links to the project homepage, project source tree, and author homepage.
- Added a **Create service** action directly to **Settings -> Services -> Configured services**, reusing Tauridium's existing service creation flow.

### Fixed

- Fixed **Open links externally** being ignored for ordinary `target="_blank"` / `window.open` links such as Daily.Dev stories. Disabled/default now navigates the current service webview; enabled opens HTTP(S) links in the operating system's default browser. Sized authentication popups remain in-app, and `mailto:` continues to use the external handler.
- Replaced the Windows `cmd /C start` external-link launcher with direct `ShellExecuteW`, eliminating the transient command-prompt window when Tauridium intentionally opens an external link.
- Standardized green **Saved** feedback for per-service controls that persist and apply immediately without the main **Save changes** action, including icon inversion, download overrides, shortcut priority, sandbox assignment, workspace membership, and enable/disable state.

### Changed

- Restored Tauridium's original styled per-service right-click menu as the default. **Advanced -> Service context menu** can disable it and switch to the native system popup retained from 0.4.28, which reliably stays above embedded service webviews.

### Release quality

- Added focused 0.4.29 regression and release-invariant coverage for per-service external-link routing, Windows external launching without `cmd.exe`, immediate green Saved feedback, styled/native context-menu selection, native About quick links, and service creation from Settings.
- Retained exact Rust 1.97.1 formatter cleanliness, locked dependency metadata, English-only validation, clean-tree verification, source-manifest verification, and deterministic three-archive packaging requirements.

## [0.4.28] - 2026-08-21

### Added

- Added a per-service **Invert service icon colors** appearance preference for dark or black service icons that would otherwise disappear against the Black OLED theme. The setting is backup-backed, validated, copied on service duplication, cleaned on deletion, and applied consistently to sidebar, configured-service, and workspace icon-selection surfaces.

### Fixed

- Replaced the shell-rendered service right-click menu with a native Tauri popup menu so it remains above service child webviews even when opened at the far right edge of the sidebar. Mouse and keyboard context-menu invocation retain Settings, Reload, Duplicate, and Enable/Disable actions.
- Tightened the per-service **Sandbox assignment** search UI to a compact 240 px maximum width with normal control height, left alignment, and reduced manager spacing instead of stretching across the settings panel.
- Fixed false **Tauridium could not verify the service download settings** failures. Download preference verification now compares `directory` and `askEachDownload` semantically instead of relying on JSON object property order. Workspace download preference verification uses the same robust comparison.

### Release quality

- Added focused 0.4.28 regression and release-invariant coverage for service icon inversion lifecycle, native context-menu layering, compact Sandbox assignment layout, and property-order-independent download preference verification.
- Retained exact Rust 1.97.1 formatting, locked dependency metadata, English-only validation, clean-tree verification, source-manifest verification, and deterministic three-archive packaging requirements.

## [0.4.27] - 2026-08-21

### Fixed

- Fixed the frontend service-view API tests after the workspace-aware service request added `workspaceId`. The default `show_service` and `preload_service` payload expectations now require `workspaceId: null`, matching the production API contract.
- Added explicit coverage that `showService` forwards a non-null workspace ID when a workspace context is provided, protecting workspace-specific download preference resolution instead of weakening the assertion.

### Release quality

- Added focused 0.4.27 regression and release-invariant coverage for the service-view workspace request contract so the Windows-native Vitest gate cannot regress silently.

## [0.4.26] - 2026-08-21

### Fixed

- Fixed Cloudflare Turnstile compatibility for remote services such as Daily.Dev on Windows. Remote HTTP(S) service webviews now disable WebView2 Tracking Prevention so cross-site challenge storage/network access is not blocked, while local Tauridium application content keeps tracking prevention enabled. Windows services also use WebView2's native browser user agent by default instead of presenting the Chromium engine as Safari; explicit per-service/global user-agent overrides remain authoritative.
- Fixed per-service **Unread badge** being ignored by the sidebar. A disabled unread badge now hides that service's unread counter immediately and remains hidden after restart, matching the already-persisted/native badge behavior.
- Replaced the generic custom-ID checkbox wording with **Enable custom URL placeholders for this service** (or the corresponding global-enabled status), clearly identifying what the control enables.
- Successful workspace membership changes and sandbox assignments made from per-service settings now show a green **Saved** toast after persistence has been verified.
- Fixed the Windows `cargo check --locked` release gate after the 0.4.25 synchronous download-dialog addition by aligning Tauridium's direct `rfd` feature set with `tauri-plugin-dialog` (`default-features = false`, `common-controls-v6`), avoiding platform-dependent lockfile mutation.

### Release quality

- Added focused 0.4.26 regression and release-invariant coverage for Turnstile/WebView2 compatibility, native Windows user-agent behavior, lockfile-stable `rfd` features, sidebar badge preferences, customer-facing custom-ID wording, and verified green Saved toasts.
- Retained exact Rust 1.97.1 formatting, locked dependency metadata, English-only validation, clean-tree verification, source-manifest verification, and deterministic three-archive packaging requirements.

## [0.4.25] - 2026-08-21

### Added

- Added arbitrary HTTP(S) workspace icon fetching in **Settings -> Workspaces -> Workspace settings**. A direct image URL is used as-is after validation; a normal website URL uses Tauridium's existing favicon discovery. The fetched icon is stored as self-contained image data so full backups and portable workspace/sandbox exports remain independent of the source website.
- Added **Advanced -> Downloads** settings for a configurable default download directory and an **Ask where to save each download** toggle.
- Added per-service and per-workspace download overrides. Effective download behavior resolves in deterministic priority order: **service override -> active workspace override -> global Advanced defaults**.

### Fixed

- Fixed authenticated and opaque attachment downloads, including Proton Mail-style attachment URLs, losing their server/browser-suggested filename and extension. Tauridium now preserves the WebView engine's suggested destination filename first and only falls back to deriving a name from the URL when no usable suggestion exists.
- Download filenames are sanitized only for filesystem-invalid/control characters, retain useful extensions, handle Windows reserved device names, and use collision-safe destination paths when saving automatically.
- **Ask where to save each download** keeps the original authenticated WebView download rather than issuing a second HTTP request. The native Save dialog starts in the effective configured directory with the website/server-suggested filename.
- Reworked the synchronous Save-dialog path to use the underlying `rfd` native dialog directly from Wry's synchronous download callback, avoiding the main-thread deadlock that would occur if `tauri-plugin-dialog`'s blocking wrapper were dispatched back to the already-waiting main thread.
- Download workspace context is updated whenever an existing or preloaded service is shown, so workspace-specific overrides apply immediately without recreating the service session.
- Service duplication copies download overrides; deleting services/workspaces and order reconciliation remove stale download settings without disturbing unrelated settings.

### Release quality

- Added focused 0.4.25 Rust/Python regression and release-invariant coverage for workspace icon URL fetching, download-setting migration/validation, precedence, filename preservation and sanitization, authenticated-download handling, settings cleanup/duplication, and the non-deadlocking native Save-dialog architecture.
- Retained exact Rust 1.97.1 formatter cleanliness, locked dependency metadata, English-only validation, clean-tree verification, source-manifest verification, and deterministic three-archive packaging requirements.

## [0.4.24] - 2026-08-21

### Added

- Added per-workspace icon assignment in **Settings -> Workspaces -> Workspace settings**. Workspace icons are selected from the same resolved service-icon sources Tauridium already uses, including preferred website icons and custom/local recipe icons.
- Workspace icon assignments are stored in app settings, included automatically in full backups, and embedded directly in portable workspace and sandbox exports so the chosen icon travels with exported workspace data.

### Fixed

- Constrained the per-service **Search sandboxes...** field to the same compact control scale as **Search workspaces...** instead of stretching across the settings panel.
- Added an explicit accessible region role and label to the sidebar service drop area, eliminating the Svelte accessibility warning reported by the Windows-native 0.4.23 quality gate.
- Workspace icon settings now validate supported HTTP(S)/image-data sources, reject malformed or oversized values, clean stale entries when workspaces disappear, and fall back safely when an assigned image cannot load.

### Release quality

- Added focused 0.4.24 regression and release-invariant coverage for compact Sandbox search sizing, sidebar drag/drop accessibility, workspace icon validation and cleanup, resolved-icon assignment, workspace-surface fallbacks, portable export embedding, and backup inclusion.
- Retained the established exact Rust 1.97.1 formatter cleanliness, frontend/Rust checks and tests when dependencies are available, clean-tree validation, source-manifest verification, and deterministic three-archive packaging requirements.

## [0.4.23] - 2026-08-21

### Added

- Added Explorer-style **Shift+click service range selection** in the sidebar for drag-and-drop only. The active service does not change when creating the temporary drag group; a normal click clears the group and resumes ordinary service switching.
- Added a per-service **Sandbox assignment** manager to Service settings, using immediate radio-row selection with search, pagination, current-assignment status, and an explicit Isolated option.

### Improved

- The unused sidebar area below the last service is now a persistent **drop at end** target. Dragging below the current last row keeps the insertion indicator attached below that row instead of cancelling the drop.
- Multi-service drag-and-drop moves the selected range as one stable block while preserving relative service order and all hidden/workspace-filtered canonical slots. Drag-over remains purely local; only the completed drop performs the verified order persistence write.
- Assigning an active service to a sandbox from **Settings -> Sandbox** no longer navigates away from Settings or opens the service webview. The changed webview is closed and recreated only when the user actually returns to that service.
- Sandbox assignment writes are verified before the service webview is closed, with UI rollback on persistence failure and a distinct error if the saved assignment succeeds but the old webview cannot be closed.

### Release quality

- Added focused 0.4.23 regression and release-invariant coverage for trailing drop-at-end behavior, Shift-range selection, grouped canonical reordering, selected-row drag semantics, per-service sandbox assignment, and Settings navigation preservation.
- Retained the established exact Rust 1.97.1 formatter cleanliness, frontend/Rust checks and tests when dependencies are available, clean-tree validation, source-manifest verification, and deterministic three-archive packaging requirements.

## [0.4.22] - 2026-08-21

### Fixed

- Fixed **Settings -> Services -> Configured services** bypassing each service's icon preference and rendering the raw recipe/custom icon source instead of the resolved service icon. The list now uses the same icon-resolution path as the sidebar.
- Website-icon cache entries are used only while that service's **Use website icon** preference is enabled, so stale in-memory website icons cannot override a service after the preference is disabled.
- Enabling **Use website icon** now hydrates the preferred website icon immediately when automatic preferred-icon fetching is enabled, without requiring an application restart.
- Unified icon failure/fallback handling between the sidebar and Configured services so custom/local recipes and dynamically fetched icons degrade consistently to the service initial only when the selected icon actually fails.

### Release quality

- Added focused 0.4.22 regression and release-invariant coverage for per-service icon preference resolution, Configured services/sidebar parity, immediate preference hydration, and stale-cache suppression.
- Retained the established exact Rust 1.97.1 formatter cleanliness, frontend/Rust checks and tests when dependencies are available, clean-tree validation, source-manifest verification, and deterministic three-archive packaging requirements.

## [0.4.21] - 2026-08-21

### Fixed

- Fixed sidebar service drag-and-drop showing the forbidden/stop cursor on Windows instead of accepting a drop. The main Tauridium shell now disables Tauri's native WebView2 drag/drop interception so standard frontend HTML5 `dragstart`, `dragover`, and `drop` events reach the sidebar.
- Preserved the hardened 0.4.20 canonical ordering path unchanged: visible-service reordering still preserves hidden/filter-excluded slots, persists only once on drop, verifies the saved order, rolls back on failure, and serializes settings writes.

### Release quality

- Added dedicated 0.4.21 regression and release-invariant coverage requiring `dragDropEnabled: false` on the configured main webview and verifying that sidebar ordering continues to use HTML5 move semantics rather than Tauri native file-drop events.
- Retained the established exact Rust 1.97.1 formatter cleanliness, frontend/Rust checks and tests when dependencies are available, clean-tree validation, source-manifest verification, and deterministic three-archive packaging requirements.

## [0.4.20] - 2026-08-21

### Added

- Added **Advanced -> Sidebar service ordering -> Drag to reorder services**, enabled by default. Disabling it makes sidebar service rows non-draggable without changing the persisted canonical service order or the Settings -> Services ordering controls.

### Improved

- Hardened sidebar drag-and-drop with explicit before/after placement based on pointer position, matching drop indicators, native drag payloads, and safe cancellation when dragging is disabled or an order write is already in progress.
- Filtered workspace views and hidden disabled services retain their canonical global slots while visible services are reordered. Stale drag ids, duplicate order state, and invalid drop targets are safe no-ops.
- Service-order persistence is optimistic but single-flight, verified after the atomic backend write, rolled back on failure, and synchronized with the native Services menu without replacing unrelated in-memory settings.
- Serialized backend app-settings read/modify/write transactions across ordinary setting changes, service/workspace order persistence, and backup restore to prevent concurrent writes from losing ordering or unrelated settings.

### Release quality

- Added focused frontend helper, Rust settings-migration, and static integration regressions covering default-on migration, saved opt-out preservation, filtered-slot stability, stale/duplicate input safety, single-write persistence, backend serialization, and toggle gating.
- Retained exact Rust 1.97.1 formatter cleanliness, release invariants, clean-tree validation, source-manifest verification, and deterministic three-archive packaging requirements.

## [0.4.19] - 2026-08-21

### Fixed

- Corrected the native service-toast security regression test to validate the canonical `serde_json`-encoded JavaScript argument instead of expecting an extra backslash that is not part of valid JSON string encoding.
- Added an explicit assertion that the raw hostile test payload never appears verbatim in the generated one-shot overlay script, preserving the intended injection-safety guarantee while allowing the Windows Rust test suite to pass.

### Release quality

- Added dedicated 0.4.19 regression and release-invariant coverage for the service-toast encoding contract exposed by the Windows-native `cargo test` gate.
- Retained the established exact Rust 1.97.1 formatting, Clippy/check/test, frontend, clean-tree, source-manifest, and deterministic packaging requirements.

## [0.4.18] - 2026-08-21

### Added

- Added `Ctrl+Shift+N` as the default **Add workspace** shortcut across shell and focused-service shortcut handling, including the native application menu.
- Added bundled local recipes for **Woodpecker**, **Codeberg**, **SourceHut**, **Fritz!Box**, **Artifacts MMO**, **Lumo**, **Suno**, **Midjourney**, **Sora**, **Grafana**, **Graylog**, **Kibana**, and **Anytype**.
- Added website-workspace/namespace routing for Codeberg and SourceHut, while self-hosted Woodpecker, Fritz!Box, Grafana, Graylog, and Kibana recipes allow per-service custom instance URLs.

### Fixed

- Reload notifications now begin only after the replacement service webview reports that its page is ready, so `Ctrl+R` no longer destroys its own success toast during the reload.
- Service-visible notifications are mirrored through a native one-shot overlay above the service child webview while retaining the shell ARIA-live toast; hosted pages are not given a callable Tauridium notification API.
- Existing saved keybinding maps are merged with newly introduced defaults, preserving user customizations while supplying `Ctrl+Shift+N` on upgrade.
- The main window now starts hidden, restores persisted size/position/maximized/fullscreen state off-screen, and is shown only afterward, eliminating the visible windowed-to-fullscreen startup transition.

### Compatibility

- The Sora bundled recipe targets OpenAI's legacy Sora content-export endpoint because the Sora web/app product was discontinued in April 2026.

### Release quality

- Added 0.4.18 regression and release-invariant coverage for keybinding migration, post-ready reload notifications, native service toast overlays, all new bundled recipes and workspace routes, and hidden-before-restore fullscreen startup.
- Retained the established exact Rust 1.97.1 formatting, regression, release-invariant, clean-tree, source-manifest, and deterministic packaging gates.

## [0.4.17] - 2026-08-21

### Fixed

- Removed the large unused vertical gap between the per-service **Shortcut priority** explanation and its selector in Service Settings.
- Replaced the conflicting flex sizing with an explicit two-column grid so explanatory copy and the priority selector align predictably without reserving artificial height.

### UX and accessibility

- Aligned the shortcut heading, description, selector, and effective-behavior text to a compact shared layout with consistent spacing and no inherited description indent.
- Added a narrow-window fallback that stacks the selector directly below the explanatory copy while retaining full-width controls and keyboard focus behavior.

### Release quality

- Added dedicated 0.4.17 regression coverage preventing the former `flex-basis: 320px` spacing regression and enforcing the compact responsive layout.
- Retained the established formatting, regression, release-invariant, clean-tree, source-manifest, and deterministic packaging gates.

## [0.4.16] - 2026-08-20

### Changed

- Completely redesigned the per-service **Workspace membership** list in Service Settings around direct selection instead of narrow per-row Add/Remove buttons.
- Workspace rows are now fixed, consistently aligned selection targets with a checkbox, workspace identity, service count, and persistent **Included / Not included** state.
- Replaced the membership filter select with a three-way segmented **All / Included / Not included** control and clarified the interaction text and create action wording.

### UX and accessibility

- The entire workspace row is clickable, substantially increasing the target area and removing the conditional-column layout that caused Add/Remove controls to shift horizontally.
- Added explicit checkbox semantics and focus styling while preserving immediate persistence, search, filtering, pagination, and busy-state protection.
- Added a responsive narrow-window layout that stacks search/filter controls and hides only the redundant textual state while retaining the checkbox and workspace identity.

### Release quality

- Added dedicated 0.4.16 regression coverage for full-row click targets, stable row alignment, segmented filtering, scalable list behavior, and responsive layout.
- Retained the mandatory Rust 1.97.1 formatter, locked metadata, English-only, Git cleanliness, source-manifest, ZIP-integrity, and independently extracted-source validation gates.

## [0.4.15] - 2026-08-20

### Fixed

- Fixed Windows Rust 1.97.1 builds failing with `recursion limit reached while expanding $crate::json_internal!` while compiling the default application settings.

### Reliability

- Replaced the growing top-level `serde_json::json!` settings-default macro with direct `serde_json::Map` construction, preserving the existing JSON shape without raising the crate-wide macro recursion limit.
- Added regression coverage that prevents the large recursive settings macro from being reintroduced while preserving critical 0.4.14 defaults.
- Removed two stale `.searchrow` CSS selectors reported by `svelte-check`, keeping the frontend diagnostics clean.

## [0.4.14] - 2026-08-20

### Added

- Added a default-enabled **Capture Tauridium shortcuts inside services** Advanced setting so configured Tauridium shortcuts continue to work while a hosted service owns keyboard focus.
- Added a per-service **Shortcut priority** override with inheritance from the global policy, allowing hotkey-heavy websites to receive matching shortcuts instead.
- Added **Add Workspace** to the native Tauridium application menu directly below **Add Service**.

### Changed

- Renamed the native application-menu items **Settings...** to **Settings** and **Add Service...** to **Add Service**.
- Redesigned Service Settings workspace membership as a coherent searchable, filterable, paginated manager with joined-state badges and explicit **Add**/**Remove** actions, plus a separate **Create & add** card.
- Service-webview shortcut capture supports all configured single-stroke and two-stroke Tauridium bindings rather than only the developer-tools shortcut.

### Reliability and UX

- Shortcut capture intercepts only configured Tauridium shortcut sequences; normal typing remains untouched unless explicitly assigned as a shortcut.
- Per-service shortcut overrides are copied on service duplication, removed when the service is deleted, persisted in portable application settings, and applied by recreating the affected service webview.
- Global shortcut-policy or keybinding changes recreate open service webviews so the effective keyboard policy applies consistently without changing persistent sessions.
- Consolidated the Rust shortcut action list so validation, service-webview injection, and native dispatch share one authoritative action set.
- Routed service-webview shortcuts through a private per-webview navigation nonce that Tauridium intercepts and cancels natively, avoiding any remote Tauri IPC capability while remaining compatible with Tauri 2.11+ remote-origin ACL enforcement.

### Release quality

- Added dedicated 0.4.14 regressions for global/per-service shortcut priority, single-stroke and chord capture, override lifecycle, native menu wording and Add Workspace routing, and scalable Service Settings workspace management.
- Retained mandatory Rust 1.97.1 formatting, locked Cargo metadata, strict frontend TypeScript validation, English-only, Git cleanliness, source-manifest, ZIP-integrity, and independently extracted-source validation gates.

## [0.4.13] - 2026-08-20

### Changed

- Removed the workspace strip above the sidebar service list so the sidebar dedicates its vertical space to services; workspace switching remains available through the configurable quick switcher and Navigate shortcuts.
- Added a dedicated **Settings -> Workspaces** tab with Services-style search, 100-row pagination, creation, portable export, verified custom ordering, deletion, and per-workspace settings.
- Workspace settings now open in place of the long workspace list and provide searchable, paginated service membership management plus rename, export, and delete actions.
- Added quick-switch workspace ordering modes for **Custom**, **Custom - reverse**, **Alphabetical - A to Z**, **Alphabetical - Z to A**, **Most recently used**, and **Least recently used**, while keeping **All services** pinned first.

### Reliability and UX

- Kept quick-switch ordering independent from Tauridium's canonical custom workspace order so alphabetical/recent modes cannot mutate persisted workspace ordering.
- Preserved filtered workspace reordering semantics by moving only visible workspace slots while hidden search results retain their canonical positions.
- Serialized workspace recency persistence to avoid rapid-switch write races, pruned usage history for deleted workspaces, and included the new ordering/history settings in portable application settings and backups.
- Added discard confirmation for an unsaved workspace rename and clamped workspace-list pagination after deletions or external workspace changes.

### Release quality

- Expanded the offline regression suite with dedicated 0.4.13 coverage for sidebar removal, scalable workspace management, filtered canonical reordering, all six quick-switch ordering modes, recency persistence/pruning, in-place workspace settings, and portable settings coverage.
- Retained mandatory Rust 1.97.1 formatting, locked Cargo metadata, English-only, Git cleanliness, source-manifest, ZIP-integrity, and independently extracted-source validation gates.

## [0.4.12] - 2026-08-20

### Fixed

- Removed the stale `is_local_recipe` field from the website-icon Tauri request model after the frontend stopped sending or using it, clearing the Windows-native Clippy `dead_code` release blocker without a lint suppression.

### Release quality

- Added dedicated 0.4.12 regressions and release invariants that require the icon request model and frontend payload to contain only runtime-used fields and reject reintroducing the stale field.
- Retained the mandatory Rust 1.97.1 formatter, locked metadata, English-only, Git cleanliness, source-manifest, and extracted-source validation gates.

## [0.4.11] - 2026-08-20

### Fixed

- Fixed the Service Settings workspace-membership status badge failing `svelte-check` because the nullable `settingsSvc` value was captured inside an array callback. The already-narrowed service ID is now captured once for the Service Settings block and reused throughout workspace membership rendering.
- Applied the same stable service ID to workspace membership checkboxes, avoiding the same reactive nullability hazard in adjacent UI.

### Release quality

- Added dedicated 0.4.11 regressions and release invariants that reject callback use of nullable `settingsSvc.id`, non-null assertions, and TypeScript suppression comments for this flow.
- Retained mandatory Rust 1.97.1 formatter, locked metadata, English-only, Git cleanliness, source-manifest, and extracted-source validation gates.

## [0.4.10] - 2026-08-20

### Fixed

- Restricted automatic and bulk website-icon fetching to services whose **Use website icon** preference is enabled, with the same rule enforced in the Rust backend so forced refreshes cannot bypass it.
- Routed native **Ctrl+R** reload actions through the frontend reload path so the configurable reload notification is shown consistently.
- Restored the configured service-webview devtools shortcut on Windows by bridging the active service webview to Tauridium's native devtools command; Windows opens devtools directly instead of relying on unsupported toggle/close behavior.
- Made service-name edits dirty immediately on the first input event, and kept service/template forms dirty when persistence fails instead of incorrectly showing them as saved.
- Added an unsaved-changes confirmation before closing Service Settings.
- Preserved website-icon preference, assigned custom-recipe icons, and persistent cached website icons when duplicating services.

### Added

- Added searchable, scrollable per-service workspace membership management to Service Settings, including transactional **Create & add** behavior with rollback if membership persistence fails.
- Added explicit shortcut guidance that uppercase key labels do not imply Shift unless **Shift** is shown in the binding.

### Changed

- Newly created custom-recipe and Custom Website services now prefer a fetched website icon by default.
- Improved alignment and responsive spacing of accent-color presets and the **Custom...** button.
- Moved **Only favorites in unread count** immediately after **Indirect message badge**.
- Changing keybindings now recreates service webviews so service-focused shortcut bridges immediately use the latest configured binding.

### Release quality

- Added dedicated 0.4.10 regressions for icon-preference scoping, custom-recipe defaults, duplicate cache semantics, reload notifications, devtools shortcut bridging, Shift wording, immediate dirty-state behavior, failed-save preservation, unsaved-close confirmation, workspace management, setting order, and accent-picker layout.
- Added a frontend API contract test for persistent service-icon cache copying and a Rust unit test for single-stroke devtools shortcut injection versus unsupported chords.
- Retained mandatory Rust 1.97.1 formatting, locked metadata, English-only, Git cleanliness, source-manifest, and extracted-source release gates.

## [0.4.9] - 2026-08-20

### Fixed

- Fixed the sidebar service context-menu **Settings** action so it captures the selected service before clearing reactive menu state, eliminating the runtime null dereference reported against 0.4.8.
- Added a narrowly scoped remote-service compatibility shim for hosted applications that detect Tauri internals and call `plugin:webview|internal_toggle_devtools`; only that devtools command becomes a harmless no-op, while Tauridium's remote-service capability/ACL boundary remains closed.
- Kept duplication of Tauridium-local **Custom Website** services on the local profile path instead of accidentally attempting remote Ferdium API creation in account mode.

### Added

- Added **Duplicate** to the service context menu between **Reload** and the enable/disable action. Copies preserve service configuration, workspace memberships, sandbox assignment, custom URL template data, enabled state, and canonical ordering next to the source service, with rollback of partial changes on failure.
- Added collision-safe duplicate names (`Name Copy`, `Name Copy 2`, and so on).

### Changed

- Shortened the context-menu state action to **Enable** / **Disable**.
- Increased context-menu placement bounds for the additional action while preserving keyboard navigation.

### Release quality

- Added dedicated 0.4.9 regressions for the context-menu null-state bug, requested menu order/labels, duplication and rollback behavior, local custom-website ownership, menu geometry, and remote-service capability isolation.
- Added strict isolated TypeScript validation of the complete `App.svelte` script; it caught and fixed an additional nullable duplicate-selection path before release.
- Executed the remote compatibility shim in an isolated JavaScript runtime to verify that the devtools command is neutralized, unrelated commands still forward, and reinjection remains idempotent.

## [0.4.8] - 2026-08-20

### Fixed

- Fixed the native Services-menu selection handler so TypeScript narrows a missing service before passing it to the service-selection path.
- Made custom URL template editing type-safe with a key-aware generic setter instead of an unsafe record cast.
- Fixed the configured-services icon error handler to pass the complete service object expected by persistent website-icon fallback logic.
- Made the service context-menu container explicitly programmatically focusable, clearing Svelte's `a11y_interactive_supports_focus` warning while preserving keyboard focus on the first enabled menu action.

### Release quality

- Added dedicated 0.4.8 regressions and release invariants for all four Windows-native `svelte-check` diagnostics reported against 0.4.7.
- Performed an isolated strict TypeScript compilation pass for the complete `App.svelte` script and Tauridium frontend modules as additional release evidence, alongside the existing Svelte and Vitest release gates.
- Retained the mandatory Rust 1.97.1 formatter, locked Cargo metadata, English-only, Git cleanliness, and source-package integrity gates.

## [0.4.7] - 2026-08-19

### Changed

- Replaced each sidebar service cogwheel with a full-width service row and a right-click / Shift+F10 context menu containing **Settings**, **Reload**, and the state-aware **Enable Service** / **Disable Service** action. Disabled services stay listed with reduced emphasis, are closed immediately, and are never selected or preloaded until re-enabled.
- Added the matching enable/disable control to each service Settings danger zone between **Clear cache & session** and **Delete service**.
- Changed the bundled OpenCode recipe title to **OpenCode**, its default URL to `https://opencode.ai/go`, and added workspace routing through `https://opencode.ai/workspace/{teamId}/go`.
- Clarified the service **Team / workspace ID** field with an explicit website-specific OpenCode example.
- Added opt-in custom URL placeholders `{{custom_id_1}}` and `{{custom_id_2}}`, disabled globally by default and enableable globally or per service.

### Added

- Added persistent website-icon discovery for services without usable preset icons, enabled by default, with positive and negative caching to avoid repeated network fetches. Service Settings can explicitly refetch one icon; Advanced Settings can refetch all icons after confirmation.
- Added optional reload toast notifications for service reloads triggered by keybindings or the service context menu.
- Added package/build metadata plumbing for About-page repository, license, description, and configurable maintainer metadata.

### Reliability and release quality

- Added regression coverage for disabled-service lifecycle behavior, context-menu accessibility/navigation, OpenCode workspace routing, custom URL placeholder validation, persistent icon caching/refetch behavior, reload toasts, and build metadata.
- Hardened icon caching to create its cache directory atomically before first write and to keep preset-icon failure fallback separate from initial automatic icon probes.
- Preserved disabled service Settings while toggling the currently active service off, instead of unexpectedly navigating away from the Settings view.
- Retained the mandatory Rust 1.97.1 formatter and locked release-validation gates.

## [0.4.6] - 2026-08-19

### Fixed

- Fixed tiered automatic-backup retention when multiple backups have identical filesystem modification times. Tauridium now uses the fixed-width timestamp embedded in its validated automatic-backup filename as the deterministic tie-breaker, so the newer same-day recovery point is retained instead of an older one.
- Applied the same deterministic newest-filename policy to count retention when mtimes tie, while preserving explicit protection of the just-created integrity-verified backup against anomalous future mtimes.

### Release quality

- Added Rust regression coverage for the exact Windows-native tiered-retention failure and equal-mtime count retention.
- Added 0.4.6 offline release regressions that require descending embedded-timestamp tie-breaking and reject a return to pathname-ascending selection.
- Verified the exact production retention function independently with Rust 1.97.1 and Clippy `-D warnings` without lint suppression.

## [0.4.5] - 2026-08-19

### Fixed

- Moved audit-log capacity and rotation invariants from runtime unit-test assertions into compile-time const assertions, eliminating the Rust 1.97.1 `clippy::assertions_on_constants` failures reported by the Windows-native release gate without suppressing Clippy.
- Removed the redundant runtime assertion of the fixed audit rotation count so the remaining Rust test verifies rotated-path behavior rather than literal constant values.

### Release quality

- Added 0.4.5 regression coverage that requires the compile-time invariant form and rejects `allow`/`expect` suppression of `clippy::assertions_on_constants`.
- Verified the exact const-assertion pattern independently with the supplied Rust 1.97.1 `clippy-driver -D warnings`, in addition to the mandatory formatter and offline release suites.

## [0.4.4] - 2026-08-19

### Fixed

- Made backup restore transactional only for Tauridium-owned data. Operating-system autostart synchronization now runs after the verified restore commits, is state-aware/idempotent, and can only add a non-fatal restore warning; rollback no longer invokes the external autostart integration.
- Hardened autostart state inspection so an unreadable operating-system integration is reported distinctly instead of blindly issuing another enable/disable mutation.
- Prevented long automatic-backup directory paths and relative sidebar widths on very wide displays from overflowing or disagreeing with backend geometry limits.

### Added

- Added a native directory picker for the automatic-backup output location, with an explicit return-to-managed-default action.
- Added count, maximum-age, combined count-and-age, and tiered GFS-style automatic-backup retention. Tiered retention keeps progressively representative daily, weekly, monthly, and yearly recovery points while always preserving the newest verified backup.
- Added a Settings **Audit log** tab with searchable/filterable structured events for application and service settings, service/workspace ordering, manual and automatic backups, restores, retention, portable exports, warnings, failures, export, and clear operations. Secret-like detail fields are recursively redacted; local JSONL history is bounded by rotation and synchronized against concurrent in-process access.
- Added integrity-protected portable sandbox exports for one sandbox or all sandboxes, including assigned services, relevant workspace membership, sandbox assignments, and referenced custom recipes.
- Added matching portable workspace exports for one workspace or all workspaces, including their services, referenced sandboxes/assignments, and referenced custom recipes. Portable bundles reject dangling service/workspace/sandbox relationships.
- Added percentage-based sidebar sizing alongside fixed pixel widths. Relative sizing follows window resize events through animation-frame-throttled updates and remains bounded to preserve useful service content.

### Changed

- Increased the Settings card to use substantially more available desktop width. Settings tabs now distribute across the available width and wrap to additional rows instead of horizontally scrolling.
- Renamed **Service position** to **Service list alignment**.
- Audit-log export now includes every event still present in the bounded retained log generations rather than applying the UI read cap.

### Backup and release quality

- Automatic retention runs only after the new backup has been staged, flushed, reread, parsed, and integrity-verified; retention cleanup failures do not invalidate the newly verified backup. The just-created verified backup is explicitly protected from pruning even when a pre-existing file has an anomalous future filesystem timestamp.
- Retention now considers only filenames matching Tauridium's exact generated `tauridium-auto-backup-YYYY-MM-DD-HHMMSS-mmm.json` shape with valid calendar/time fields, preventing unrelated look-alike files from becoming deletion candidates.
- Expanded Rust backup tests for corrupted/truncated files, integrity tampering, stale staging files, replacement safety, deterministic retention boundaries, future timestamps, protected-new-backup semantics, strict automatic-backup filename validation, warning propagation, supported retention modes, and tiered history.
- Added portable-export integrity/atomicity and referential-integrity tests, audit redaction/rotation tests, autostart idempotence coverage, and 0.4.4 cross-layer release invariants.
- Hardened source-ZIP packaging to preserve required empty `.git` directories after refs are packed, so a freshly extracted release remains a directly usable Git repository even after repository garbage collection.
- Added a packed-refs extraction regression that verifies the packaged repository resolves `HEAD`, its exact release tag, and passes `git fsck --full`.
- Retained the mandatory native Rust 1.97.1 formatter gate and existing tagged-release compilation/lint/test gates.

## [0.4.3] - 2026-08-19

### Fixed

- Preserved full HSL conversion precision in the custom accent-color picker so opening the picker and applying an unchanged color no longer mutates the stored RGB value through integer HSL quantization.
- Corrected the frontend color round-trip regression to require exact preservation of representative preset, dark, light, black, and white colors.
- Kept hue, saturation, and lightness labels rounded for human-readable UI while retaining precise internal slider state.

### Release quality

- Added dedicated 0.4.3 static release regressions for color-conversion precision, exact frontend round trips, and readable slider labels.
- Verified the corrected TypeScript conversion directly with 10,000 deterministic RGB/HSL round trips in addition to the repository regression suite.
- Re-ran the pinned Rust 1.97.1 formatter and available source-side release gates before tagging and packaging.

## [0.4.2] - 2026-08-19

### Fixed

- Replaced the quick switcher `<section role="dialog">` with a dialog-compatible generic container so `svelte-check` no longer reports the Svelte accessibility warning found by the Windows-native quality gate.
- Exercised the macOS/shared-session `storage_identifier` helper in Rust unit tests, eliminating the Windows test-target dead-code warning that becomes a Clippy error under `-D warnings` while increasing sandbox identity coverage.
- Rewrote shared-sandbox membership collection from `filter_map(bool.then(...))` to Clippy-preferred `filter` plus `map` without changing ordering or behavior.
- Replaced the single-element accent-color validation loop with direct validation, removing the `clippy::single_element_loop` failure without weakening input validation.

### Release quality

- Added patch regressions that preserve the corrected quick-switcher dialog markup and the exact Rust structures required to avoid the three Windows-native Clippy failures.
- Extended cross-platform release-version synchronization to the README tag and target-qualified runtime examples, with release validation rejecting stale examples.
- Re-ran the full offline regression suite and pinned Rust 1.97.1 formatter gate before tagging and packaging.

## [0.4.1] - 2026-08-19

### Fixed

- Restored the missing `[unix]` guard on the Unix `package-handoff` recipe. `just` no longer rejects the entire `justfile` as a duplicate `package-handoff` definition before commands such as `just init-self-test` can run on Windows.
- Added a generalized release invariant that rejects duplicate `just` recipes unless every definition is explicitly and disjointly guarded by `[unix]` or `[windows]`, preventing this parser failure class from recurring.

### Release quality

- Enforced `--locked` for Cargo check, Clippy, and Rust-test gates in branch CI and tagged-release validation.
- Strengthened the tagged-release gate so offline Python regressions, `svelte-check`, frontend tests, Cargo check, Clippy with warnings denied, Rust tests, and native Rust 1.97.1 formatting must pass before the draft release is created.
- Re-ran project-owned whitespace/line-ending checks, Python syntax compilation, TypeScript syntax parsing, structured configuration parsing, release invariants, and the full offline regression suite while leaving vendored third-party formatting unchanged.

## [0.4.0] - 2026-08-19

### Added

- Added a true-black **Black OLED** theme with near-black elevated surfaces, retained focus treatment, and existing system/dark/light modes.
- Added accent presets plus saved custom accent colors with a native color input and keyboard-accessible hue, saturation, and lightness sliders.
- Added a 160-420 px sidebar-width slider, Slim/Normal/Wide presets, and persisted custom width presets.
- Added **Keybinds** settings for application/navigation actions. Defaults include `Ctrl+D` for the workspace switcher and `Ctrl+S` for service search; two-stroke chords are recordable and exact conflicts are surfaced.
- Added searchable keyboard-driven quick workspace/service switchers with bounded result rendering for large installations.
- Added **Sandbox** settings. Compatible services can share a Tauridium-owned persistent webview data store/session; isolated services retain their existing per-service store. Shared stores can be cleared as a group and are not deleted when only one member service is removed.
- Added an explicit `package-handoff` / `--build-handoff` release path that produces a clearly named source-only runtime build handoff when no native executable can be validated.

### Changed

- Configured Services now scales through search, workspace filtering, and 100-row paging. Filtered reordering uses the canonical global order and preserves hidden service slots.
- Workspace selection now consistently activates an eligible service in the selected workspace rather than leaving a hidden active service selected.
- Accent foreground selection now uses WCAG relative-luminance contrast between black and white foregrounds.
- Shared-sandbox identity is derived authoritatively by the Rust backend from persisted settings rather than trusted from a frontend webview request.
- Version synchronization now updates Tauri, npm, Cargo/Cargo.lock, and initializer release identities together.

### Backup and reliability

- OLED/theme state, custom accent presets, custom sidebar presets, keybindings, sandbox definitions, and service-to-sandbox assignments are all stored in `appSettings`; the existing integrity-protected backup payload exports/restores the complete object.
- Deleting a shared sandbox clears its shared data, removes assignments transactionally through app settings, and reopens an affected active service in isolated storage.
- Clearing a shared service cache closes every service using that sandbox before deleting the shared store, preventing live webviews from retaining stale session state.

### Tests

- Added 0.4.0 offline regressions for appearance persistence, scalable service management, keybinding/chord defaults, backend-authoritative sandbox identity, and backup coverage.
- Added Rust unit tests for malformed new settings and deterministic shared/isolated storage identity.
- Rust 1.97.1 native `rustfmt` remains a mandatory implementation, pre-tag, packaging, and extracted-source gate.

## [0.3.19] - 2026-08-19

### Fixed

- Corrected the automatic-backup monthly scheduling regression test: monthly backups use calendar-month semantics rather than a fixed 30-day interval.
- Added explicit month-boundary coverage, including exact due-time checks, 31st-to-month-end clamping, and leap-year February behavior.

### Tests

- Added offline release coverage that requires the calendar-month implementation and the native Vitest regression cases, so the same mismatch is caught even when frontend dependencies are unavailable in a packaging environment.
- The pinned Rust 1.97.1 formatter remains a mandatory pre-tag and packaging gate.

## [0.3.18] - 2026-08-19

### Added

- Added a dedicated Backup settings tab with manual export/restore, automatic backup schedules for startup/daily/weekly/monthly operation, and configurable retention.
- Added repository-pinned Rust 1.97.1 tooling and a package-time rustfmt gate so release packaging cannot bypass the exact formatter used by Tauridium.

### Changed

- Manual backup filenames now include local date, time, seconds, and milliseconds so multiple backups on the same day do not collide.
- Standardized user-facing local-mode terminology to the concise label `Local`.
- Service settings opened from Settings -> Services now return to that Settings section when closed.

### Fixed

- Appearance and other unrelated settings changes no longer invoke the autostart integration; autostart is updated only when the `autostart` setting itself changes.

### Reliability

- Automatic backups are serialized one at a time, integrity-verified before retention pruning, restricted to Tauridium-owned filenames, and retained independently from manual and pre-restore safety backups.
- Release packaging now requires a successful `cargo fmt -- --check` under the repository-pinned Rust 1.97.1 toolchain.

## [0.3.17] - 2026-08-18

### Fixed

- Committed the exact Rust formatting required by native `rustfmt 1.94.0` for the 0.3.16 service-ordering and backup-reliability additions, allowing the non-mutating Windows `fmt-check` release gate to proceed.
- Kept all 0.3.16 service/sidebar/order and backup behavior unchanged; this patch is release-hygiene only.

### Tests

- Extended the offline native-rustfmt baseline with every formatter drift reported by the Windows toolchain in `backup.rs`, `local_profile.rs`, and `main.rs`.
- Updated backup/release invariants to assert the formatted staging-verification code while preserving the same fsync, read-back validation, SHA-256 verification, and atomic-replace requirements.

## [0.3.16] - 2026-08-18

### Changed

- Rebuilt Settings -> Services around the actual configured service list, with reliable names/fallback labels, live counts, service metadata, direct settings access, and explicit reorder controls.
- Rebuilt the native Services menu from the same canonical ordered service list: it now shows the actual service names/count, has no phantom numbered entries, routes clicks by stable service id, and reserves `Ctrl/Cmd+1...9` for the first nine services only.
- Removed the sidebar Add Service and Settings buttons to dedicate more vertical space to services. Add Service and Settings now live in the Tauridium application menu; Settings reopens on the previously selected Settings section.
- Refined workspace and Settings tab styling into compact, rounded, scrollable controls while keeping native application-menu behavior intact.

### Fixed

- Made the sidebar service list dynamically scroll only when its contents exceed the available window height; larger windows continue to show the complete list without unnecessary scrolling.
- Replaced best-effort multi-request service reordering with one Tauridium-owned canonical order persisted atomically in application settings. Workspace order now uses the same verified persistence model.
- Reconcile saved order state against the actual service/workspace ids after load, creation, deletion, and workspace refresh so stale ids are removed and new items are appended deterministically.
- Preserve hidden service slots when reordering inside a filtered workspace so workspace/filter views cannot corrupt the global order.

### Backup reliability

- Upgraded portable backups to schema 2 with SHA-256 payload integrity metadata while retaining migration support for schema-1 backups and rejecting unsupported future schemas.
- Validate app settings, local-profile ids/workspace membership, and every custom recipe before the first restore mutation. Duplicate ids and broken workspace references are rejected.
- Restore custom recipes through staging/rollback directories and retain unrelated existing recipes while replacing matching backup ids.
- Create an automatic integrity-protected pre-restore recovery backup before any persistent mutation; restore aborts if that safety snapshot cannot be written.
- Roll back recipes, local profile, autostart, app settings, and in-memory profile state if a later restore component fails.
- Stage every backup beside its destination, flush it to durable storage, parse it back, re-run schema/SHA-256 validation, and only then atomically replace any existing backup; failed verification leaves the previous backup untouched.
- Keep backup writes size-limited and private (`0600`) on Unix; continue excluding session credentials, website storage, remote caches, and machine-specific monitor geometry.

### Tests

- Added ordering/sidebar regressions for canonical persistence, filtered drag/drop, dynamic scrolling, service naming, Tauridium menu actions, and last-Settings-tab behavior.
- Expanded backup quality gates for schema migration, SHA-256 integrity, tamper detection, unsupported schemas, oversized files, structural validation, duplicate recipes, staged restore, recovery snapshots, and all-component rollback.

## [0.3.15] - 2026-08-18

### Fixed

- Repaired the Cargo lockfile introduced in 0.3.14: `errno` had been downgraded to 0.3.13 while retaining the checksum for 0.3.14, causing Cargo to abort before compilation with a checksum mismatch.
- Restored the previously resolved `errno` 0.3.14 package and its matching checksum instead of carrying an unnecessary transitive-dependency downgrade.

### Tests

- Added lockfile regression coverage for the exact `errno` version/checksum pair so future dependency additions cannot silently recreate this corruption.
- Kept the window-state plugin pinned to 2.4.1 and retained all 0.3.14 window-state lifecycle behavior.

All notable changes to Tauridium are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/).

> Release notes **must be written in English**. The section of the tagged
> version is picked up **automatically** as the GitHub Release notes (see
> `.github/workflows/release.yml`), so fill in the section **before** pushing
> the `vX.Y.Z` tag. Entries for 0.1.0-0.1.8 were back-filled from the commit
> history, so they are more terse than the process going forward.

## [Unreleased]

## [0.3.14] - 2026-08-18

### Added
- Persist and restore the main Tauridium window's normal size, screen position, maximized state, and fullscreen state across tray hides and complete application restarts.
- Store window state in `window-state.json` under Tauridium's OS application-config directory using the official Tauri window-state plugin.

### Fixed
- Save the current main-window state immediately before close-to-tray, tray-toggle hiding, and tray Quit so reopening reproduces the last visible window geometry reliably.
- Restore persisted geometry before showing Tauridium again from the tray. Visibility itself is intentionally not persisted, keeping the existing start-minimized setting authoritative.
- Scope persisted state to the main window only and rely on Tauri's monitor-aware restore behavior so stale coordinates from a removed monitor do not strand Tauridium off-screen.

### Tests
- Added regressions for the pinned window-state dependency, persisted state flags, main-window-only filtering, close-to-tray saves, tray Quit saves, and restore-before-show ordering.

## [0.3.13] - 2026-08-18

### Fixed
- Committed the exact `rustfmt 1.94.0` formatting required for `open_external_url`, allowing the non-mutating Windows `fmt-check` release gate to pass.
- Removed three obsolete Settings tab CSS selectors (`.tabs`, `.tab`, `.tab.on`) left behind by the Settings redesign, eliminating the corresponding `svelte-check` unused-selector warnings.

### Tests
- Extended the offline native-rustfmt baseline guard with the exact external-URL formatting reported by the Windows toolchain.
- Added regression coverage requiring the obsolete Settings tab selectors to remain absent.

## [0.3.12] - 2026-08-18

### Fixed
- Fixed malformed Svelte markup in the About page MIT License button that prevented `App.svelte` from parsing and caused `svelte-check` to fail.
- Restored frontend compilability of the Settings/About redesign introduced in 0.3.11.

### Tests
- Added regression coverage requiring every About project-link `onclick` handler to be a complete Svelte expression.

## [0.3.11] - 2026-08-18

### Changed

- Redesigned every application Settings tab around a consistent settings-card layout with clear section hierarchy, supporting descriptions, and right-aligned controls.
- Increased the Settings content width, normalized typography and control sizing, improved keyboard focus treatment, and added responsive stacking for narrower windows.
- Reworked Appearance, Services, Advanced, Updates, and account/server presentation so labels, controls, status text, and action groups align consistently.
- Rebuilt About as a standard open-source application identity surface with the Tauridium icon, version, short purpose, repository, releases, issue reporting, license/copyright, maintainer/contributor credits, and Tauri/Ferdium references.
- About project links now open through Tauridium's native external-link command in the system default browser.

### Tests

- Added Settings/About regressions covering the seven settings sections, card-layout structure, responsive alignment, About metadata, bundled icon, and native external-link wiring.


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
- Reorder services by drag & drop, plus ⌘1-9 shortcuts to switch services.
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
- Auto-updater (`tauri-plugin-updater`) with an Updates tab - first release with
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
Initial release - a lightweight Ferdium client built with Tauri v2.
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
