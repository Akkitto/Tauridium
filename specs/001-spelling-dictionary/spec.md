# Feature Specification: Spelling Check and Dictionary Support

**Feature Branch**: `001-spelling-dictionary`

**Created**: 2026-11-13

**Status**: Draft

**Input**: User description: "I'd like to implement dictionary and spelling support into this project"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See and fix misspellings while typing in a service (Priority: P1)

A user types a message, email or document in any service (chat, mail, notes). Misspelled words are visibly marked as they type. Right-clicking a marked word shows suggested corrections; choosing one replaces the word.

**Why this priority**: Core value. Without in-page checking and correction, nothing else matters.

**Independent Test**: Open a service with a text field, type a misspelled word, confirm it is marked, right-click it, pick a suggestion, and confirm the word is replaced.

**Acceptance Scenarios**:

1. **Given** spelling check is enabled and a service text field is focused, **When** the user types a misspelled word, **Then** the word is visibly marked as misspelled.
2. **Given** a marked word, **When** the user opens its context menu, **Then** up to several correction suggestions are listed.
3. **Given** the context menu is open, **When** the user chooses a suggestion, **Then** the misspelled word is replaced and the mark disappears.
4. **Given** a correctly spelled word, **When** the user types it, **Then** it is not marked.

---

### User Story 2 - Choose spelling languages (Priority: P1)

A user who writes in one or more languages selects which dictionaries are active. The default follows the user's system language. The selection applies to all services unless overridden for a specific service.

**Why this priority**: Spell checking is wrong and annoying in the wrong language; multilingual users are common.

**Independent Test**: Select a second language, type a correctly spelled word in that language, and confirm it is not flagged; restart and confirm the selection persisted.

**Acceptance Scenarios**:

1. **Given** a first launch, **When** the user focuses a text field, **Then** the system language dictionary is active without configuration.
2. **Given** the settings, **When** the user selects several languages, **Then** a word valid in any selected language is not flagged.
3. **Given** a global selection, **When** the user sets a different language set for one service, **Then** only that service uses it and the change shows the green "Saved" confirmation.
4. **Given** saved language choices, **When** the app restarts, **Then** the choices are unchanged.

---

### User Story 3 - Personal dictionary (Priority: P2)

A user adds names, jargon or abbreviations to a personal dictionary from the context menu so they stop being flagged. They can review and remove added words in settings.

**Why this priority**: Removes the biggest source of false positives and makes the feature tolerable long-term.

**Independent Test**: Add a flagged word via the context menu, confirm it is no longer flagged in any service and after restart, then remove it in settings and confirm it is flagged again.

**Acceptance Scenarios**:

1. **Given** a flagged word, **When** the user chooses "Add to dictionary", **Then** the word is unmarked in all services immediately.
2. **Given** the personal dictionary list in settings, **When** the user removes a word, **Then** it is flagged again.
3. **Given** a personal dictionary, **When** the user creates a backup or export and later restores it, **Then** the words are restored.

---

### User Story 4 - Turn checking on or off (Priority: P2)

A user disables spell checking globally or for a specific service (for example a code editor or terminal service) where it is noise.

**Why this priority**: Control over noise is expected; some services handle their own spell checking.

**Independent Test**: Disable checking for one service and confirm no marks appear there while other services still mark errors.

**Acceptance Scenarios**:

1. **Given** checking is disabled globally, **When** the user types misspellings anywhere, **Then** nothing is marked and no suggestions appear.
2. **Given** checking is enabled globally but disabled for one service, **When** the user types in that service, **Then** no marks appear there only.
3. **Given** a changed setting, **When** it is saved, **Then** the green "Saved" confirmation appears and the setting survives restart.

---

### User Story 5 - Look up a word in a dictionary (Priority: P3)

A user selects a word and chooses a lookup action to see its definition without leaving the app.

**Why this priority**: Fulfills the "dictionary" half of the request, but is useful independently of spell checking.

**Independent Test**: Select a word in a service page, choose the lookup action, and confirm a definition (or a clear "not found" message) is shown.

**Acceptance Scenarios**:

1. **Given** a selected word, **When** the user opens the context menu, **Then** a lookup action is offered.
2. **Given** the lookup action is chosen, **When** a definition exists, **Then** it is shown in a dismissible view.
3. **Given** no definition exists or no definition source is available, **When** the user looks up a word, **Then** a clear message explains why.

---

### Edge Cases

- A language dictionary is unavailable or cannot be loaded: the user sees an actionable message, and checking continues with the remaining languages.
- A service's sessions are isolated: personal-dictionary words still apply across all services, and no typed text is shared between services.
- A text field is a password or similar sensitive field: no checking or marking occurs.
- Very long text or rapid typing must not noticeably slow typing.
- Words with mixed case, numbers, URLs, email addresses and code-like tokens are not flagged unnecessarily.
- Duplicate or empty personal-dictionary entries are rejected or de-duplicated with feedback.
- Offline use: checking and personal dictionary work without network access.
- Upgrading from a version without the feature keeps all existing data intact and defaults sensibly.
- Language set contains a language the platform cannot support: it is shown as unavailable rather than silently dropped.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The app MUST mark misspelled words in editable text fields inside service pages.
- **FR-002**: The app MUST offer correction suggestions for a misspelled word in its context menu and replace the word when one is chosen.
- **FR-003**: Spell checking MUST work fully offline.
- **FR-004**: The system language MUST be the default spelling language.
- **FR-005**: Users MUST be able to select one or more spelling languages globally.
- **FR-006**: Users MUST be able to override the language set and the on/off state per service.
- **FR-007**: Users MUST be able to enable or disable spell checking globally and per service.
- **FR-008**: Users MUST be able to add a word to a personal dictionary from the context menu, and view and remove words in settings.
- **FR-009**: Personal dictionary words MUST apply across all services and persist across restarts.
- **FR-010**: The personal dictionary and spelling settings MUST be included in backups, exports and portable data, and MUST be restored from them.
- **FR-011**: Every spelling setting changed from the UI MUST show visible confirmation of successful persistence, and failures MUST show an actionable error.
- **FR-012**: Users MUST be able to look up a selected word and see a definition or a clear not-found/unavailable message.
- **FR-013**: Checking MUST NOT apply to password or other sensitive input fields.
- **FR-014**: Typed text MUST NOT be sent to any external service for spell checking.
- **FR-015**: Existing local data, service and workspace order, sessions, and upgrade compatibility MUST be preserved.
- **FR-016**: The feature MUST behave consistently on Windows 11 and Linux, and on macOS on a best-effort basis; where a platform cannot support a capability, the UI MUST say so.
- **FR-017**: Spell checking MUST NOT cause noticeable typing lag or increase startup time.
- **FR-018**: User-facing text and documentation MUST be in English, and the changelog MUST describe the feature.

### Key Entities

- **Spelling Settings**: Global enabled state and selected languages, with optional per-service overrides.
- **Spelling Language**: A dictionary a user can enable, with availability status.
- **Personal Dictionary**: The user's set of added words, shared by all services.
- **Word Lookup Result**: A definition, or a not-found/unavailable state, for a selected word.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A misspelled word is marked within 1 second of typing it, in 95% of attempts.
- **SC-002**: A user can fix a misspelling through the context menu in 2 clicks or fewer.
- **SC-003**: A user can add a word to the personal dictionary in 2 clicks or fewer, and it stays unmarked after restart.
- **SC-004**: Typing latency in a service with checking on is not perceptibly different from checking off in side-by-side testing.
- **SC-005**: 100% of spelling settings changes show confirmation and persist across restart.
- **SC-006**: A backup then restore round trip preserves 100% of personal dictionary words and spelling settings.
- **SC-007**: Spell checking and personal dictionary work with the network disconnected.
- **SC-008**: Upgrading with existing data results in zero lost services, workspaces or sessions.

## Assumptions

- "Dictionary support" means two things: spelling dictionaries per language, and word-definition lookup. Lookup scope is minimal in this iteration.
- Spell checking is on by default and follows the system language, matching common desktop expectations.
- Dictionaries are available offline; how they are obtained is a planning decision.
- Word lookup may be limited where no offline definition source exists, in which case it shows the unavailable message.
- Grammar checking, autocorrect, and text prediction are out of scope.
- Spellchecking of the app's own shell UI fields (e.g. service name inputs) is out of scope; only service page content is in scope.
- Service webviews remain isolated; settings and the personal dictionary are app-level, not tied to any service account.
