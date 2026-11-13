# Feature Specification: Ad and Tracker Blocking

**Feature Branch**: `feat/ad-blocking`

**Created**: 2026-11-14

**Status**: Implemented for Linux; Windows and macOS deferred

**Input**: User description: "I want to implement a new spec branch for adblock in Tauridium, using the brave/adblock-rust engine. Network blocking first; cosmetic filtering and scriptlets as a later release. Needs filter list management, global switch, per-service override and site allowlist, backup/export, UI, tests and supply-chain updates. Linux and Windows spikes must confirm feasibility and performance before commitment; macOS is best-effort."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Block ads and trackers in services (Priority: P1)

A user enables ad and tracker blocking. Requests that the active filter lists identify as advertising or tracking are stopped before they load in service webviews, so pages load with fewer third-party requests and without the blocked content.

**Why this priority**: Core value. Without actual request blocking, nothing else in this feature matters.

**Independent Test**: With blocking on, open a service page known to load a listed ad or tracker host and confirm that request is blocked while the rest of the page loads; turn blocking off and confirm the request succeeds again.

**Acceptance Scenarios**:

1. **Given** blocking is enabled and filter lists are loaded, **When** a service page requests a resource matching a list rule, **Then** the request is blocked and the page continues to load.
2. **Given** blocking is enabled, **When** a service page requests a resource that matches no rule, **Then** it loads normally.
3. **Given** blocking is disabled, **When** any page loads, **Then** no request is blocked by this feature.
4. **Given** a rule marked as an exception in the lists, **When** a matching request is made, **Then** it is not blocked.
5. **Given** a service was already open, **When** the user changes the blocking setting, **Then** the change applies to that running service without restarting the app.

---

### User Story 2 - Turn blocking off quickly for one service or site (Priority: P1)

Blocking will sometimes break a site, especially chat and workspace apps. A user can switch blocking off for a single service in one step, can override the global default per service, and can add sites to an allowlist so they are never blocked.

**Why this priority**: The feature is not safe to ship without a fast, obvious escape hatch for broken services.

**Independent Test**: Break a service with blocking on, switch that service's blocking off from its settings, confirm it works and shows the green "Saved" confirmation, restart, and confirm the choice persisted while other services stay blocked.

**Acceptance Scenarios**:

1. **Given** a global default, **When** the user sets a different value for one service, **Then** only that service uses it and the change shows the green "Saved" confirmation.
2. **Given** a per-service override, **When** the user removes it, **Then** the service follows the global default again.
3. **Given** a site on the allowlist, **When** a service loads pages from that site, **Then** requests for that site's pages are not blocked.
4. **Given** saved blocking choices and allowlist, **When** the app restarts, **Then** they are unchanged.
5. **Given** a service is deleted or duplicated, **When** the action completes, **Then** its blocking settings are removed or copied accordingly.

---

### User Story 3 - Choose and maintain filter lists (Priority: P1)

A user picks which filter lists are active from a curated set and can add a custom list. Lists are downloaded, validated, cached on disk and refreshed periodically. The app works when offline using the cached copy.

**Why this priority**: Blocking quality depends entirely on the lists, and a start that fails offline or on a bad download would harm the app's reliability.

**Independent Test**: Enable a list, confirm it downloads and activates; disconnect the network, restart, and confirm blocking still works from cache; supply a corrupt list and confirm the previous good copy stays active with one clear message.

**Acceptance Scenarios**:

1. **Given** a first launch with no cache, **When** blocking is enabled, **Then** the default lists are fetched and become active, and the user sees their status.
2. **Given** cached lists and no network, **When** the app starts, **Then** blocking works from the cache and startup is not delayed waiting for the network.
3. **Given** a downloaded list that is invalid or empty, **When** validation fails, **Then** the previously active copy remains in use and a single actionable message is shown.
4. **Given** repeated update failures, **When** time passes, **Then** the user is not shown repeated identical errors.
5. **Given** the user adds a custom list address, **When** it is valid, **Then** it is downloaded and used; **When** invalid, **Then** it is rejected with an explanation.
6. **Given** lists are out of date, **When** the update interval elapses, **Then** lists refresh in the background without interrupting service pages.

---

### User Story 4 - Keep blocking settings in backups and exports (Priority: P2)

A user's blocking setting, per-service overrides, selected lists, custom lists and allowlist travel with backups and are restored with them. (Built: they are part of the app settings that backups already carry. Service exports do not carry per-service settings of any kind, so blocking overrides are not exported either.)

**Why this priority**: Constitution requires settings to survive backup and restore; losing an allowlist would silently re-break sites.

**Independent Test**: Configure blocking, create a backup, restore it on a clean profile, and confirm settings and allowlist match; restore a backup made before this feature and confirm it still verifies and does not erase newer settings.

**Acceptance Scenarios**:

1. **Given** configured blocking, **When** the user creates a backup and restores it, **Then** all blocking settings and the allowlist are restored.
2. **Given** a backup or export created before this feature, **When** it is loaded, **Then** it verifies and loads unchanged.
3. **Given** a backup that lacks blocking data, **When** it is restored over a profile with blocking settings, **Then** the existing settings are not cleared.
4. **Given** a backup made before this feature, **When** it is restored over a profile that has blocking settings, **Then** those settings are kept rather than reset.

---

### User Story 5 - See what blocking is doing (Priority: P3)

A user can see per-service how many requests were blocked in the current session, and the state of each filter list (last updated, rule count, errors).

**Why this priority**: Builds trust and helps diagnose breakage, but not required for blocking to work.

**Independent Test**: Open the lists panel and confirm update times and status match reality. A blocked-request counter is shown only where the platform can report it; it cannot on Linux.

**Acceptance Scenarios**:

1. **Given** a platform that can report blocked requests, **When** requests are blocked in a service, **Then** that service's blocked count increases. On Linux, the web engine reports no such event, so no counter is offered and the interface says why.
2. **Given** the lists panel, **When** it is opened, **Then** each list shows its status, last update time and rule count.

---

### Edge Cases

- The filter lists are very large: startup, page load and interaction MUST NOT visibly slow compared with blocking off.
- A list rule cannot be expressed by the platform's native blocking mechanism: the unsupported rule is skipped, and the user is told coverage differs on that platform.
- Network is unavailable at first launch with no cache: blocking is reported as inactive for lack of lists, not as an error loop.
- The user toggles blocking repeatedly while pages are loading: no crash, no stale state, final state matches the setting.
- A service uses a shared sandbox: blocking follows each service's own setting, not the sandbox's.
- A request is for the app's own shell or internal pages: never blocked.
- Embedded frames and cross-site requests inside a service: blocked consistently with top-level requests.
- Allowlist entries are malformed, duplicated or overly broad: they are validated and normalised, with clear feedback.
- A backup from a newer, unknown version is loaded: it is rejected without overwriting existing data.
- Cosmetic filtering and scriptlets are not part of this release: lists that contain such rules are still accepted, and those rules are ignored without error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST block requests from service pages that match the active filter lists, and MUST honour exception rules in those lists.
- **FR-002**: System MUST provide a global blocking switch and a per-service override with three states: follow global, force on, force off.
- **FR-003**: System MUST apply a changed blocking setting to already running services without requiring an app restart.
- **FR-004**: System MUST let the user maintain an allowlist of sites for which blocking is not applied, and MUST validate and normalise entries.
- **FR-005**: System MUST offer a curated set of filter lists and allow adding a custom list by address.
- **FR-006**: System MUST download, validate and cache lists on disk, refresh them periodically in the background, and keep the previous good copy when an update fails.
- **FR-007**: System MUST start and block from cached lists with no network, and MUST NOT delay startup or service loading while waiting for downloads.
- **FR-008**: System MUST report list failures with one clear, actionable message and MUST NOT repeat the same error unprompted.
- **FR-009**: System MUST NOT cause visible slowdown of page loading or interaction, measured against a real large list on each supported platform, and MUST NOT perform blocking-related disk or network work on interaction paths.
- **FR-010**: System MUST persist global settings, per-service overrides, selected and custom lists, and the allowlist across restarts, and each immediate setting change MUST show the green "Saved" confirmation.
- **FR-011**: System MUST include blocking settings in backups and service exports, MUST keep integrity digests of data lacking these fields unchanged, and MUST keep older backups and exports loading and verifying without clearing newer data.
- **FR-012**: System MUST remove a service's blocking settings when it is deleted and copy them when it is duplicated.
- **FR-013**: System MUST keep each service's blocking independent of other services, including services that share a sandbox.
- **FR-014**: System MUST never block the app's own shell or internal pages.
- **FR-015**: System MUST show per-list status (last update, rule count, last error) in the interface, and per-service blocked-request counts on platforms that can report them. Linux cannot, so no counter is shown there.
- **FR-016**: System MUST NOT send browsing activity, visited addresses or blocked-request details to any external party; only list downloads from the configured list addresses are permitted, and list addresses that resolve to loopback, private or link-local network addresses MUST be refused.
- **FR-017**: System MUST disclose in the interface and documentation where a platform cannot honour a given rule type or setting, and MUST NOT offer a control the platform cannot honour.
- **FR-018**: System MUST label any platform behaviour that could not be tested in this project as untested in documentation and changelog.
- **FR-019**: System MUST leave cosmetic filtering and scriptlet injection out of this release while ensuring the list handling and settings do not preclude adding them later.

### Key Entities

- **Blocking Settings**: The global on/off state, selected lists, custom list addresses, update interval and the global allowlist.
- **Service Blocking Override**: A per-service state (follow global, on, off) plus optional per-service allowlist entries.
- **Filter List**: A named source of rules with an address, enabled state, cached copy, last update time, rule count and last error.
- **Allowlist Entry**: A normalised site pattern for which blocking is not applied.
- **Blocked Count**: A per-service, per-session tally of blocked requests.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a page with known listed ad and tracker requests, at least 90% of those requests are blocked on Linux with the default lists. Windows 11 is measured the same way when Windows support ships.
- **SC-002**: Page load time and interaction responsiveness with blocking on and default lists are no worse than 10% slower than with blocking off on the reference page set defined in research.md (a local fixture page with listed requests, plus at least three real ad-heavy public pages), measured as median of five cold loads on Linux, and are typically faster on ad-heavy pages.
- **SC-003**: App startup time with cached lists is within 5% of startup with blocking off, and startup with no network completes without waiting on the network.
- **SC-004**: A user can switch blocking off for a broken service in at most three actions from that service (open its menu, choose Settings, choose Off), and the service works as soon as its page is reloaded.
- **SC-005**: 100% of blocking settings and allowlist entries survive restart and backup-and-restore, and 100% of pre-feature backups and exports still load and verify.
- **SC-006**: A corrupt or unreachable list update never leaves the user without working blocking when a previous good copy exists, and produces at most one visible error per failure episode.
- **SC-007**: At least three chat or workspace services (chosen in research.md and tested with the accounts available) remain fully usable with default settings, or have a documented one-step workaround.

## Assumptions

- The brave/adblock-rust engine is the filter engine; its choice is a project decision, and its limits relative to browser extensions (for example scriptlet coverage) are accepted.
- This release delivers blocking on **Linux only**. On Windows 11 and macOS the settings controls are hidden and replaced by a "not available on this platform yet" notice, and the build must still compile and run there unchanged. Windows 11 blocking is the next release and needs a real Windows 11 test run; macOS is best-effort and will ship labelled untested.
- Linux and macOS use the engine's native content-blocking mechanism, which cannot express every rule, so their coverage may differ from Windows. This difference is documented, not hidden.
- Whether each platform's feasibility and performance targets are achievable is established by a Linux spike and a Windows spike recorded in the plan's research. If a spike fails, scope or platform support is revised before dependent work begins.
- The Windows spike requires testing on real Windows 11, which the development machine cannot do; it is a gate for the Windows release, not for this Linux release.
- Default lists are EasyList (ads) and EasyPrivacy (trackers), downloaded at runtime and never bundled. Custom lists can be added.
- Blocking is off by default for upgraded and new profiles; the setting is always visible and one step to change.
- Blocked counts, where available, are session-only and are not persisted or exported.
- Cosmetic filtering and scriptlets are a later release and a separate spec.
- New dependencies follow the project's supply-chain rules, including the Rust supply-chain guard and Flatpak and Nix source updates.
- Existing patterns for global settings with per-service overrides, applying changes to running services, and backward-compatible backup digests (as used by spell checking) are reused.
