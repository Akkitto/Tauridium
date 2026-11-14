# Contract: Ad blocking commands

Typed wrappers live in `src/lib/api.ts`; each command is allowlisted for the trusted shell only (`src-tauri/permissions/application.toml`). Errors are strings suitable for display.

Settings are changed through the existing `set_app_settings` command with the keys `adblockEnabled`, `adblockLists`, `adblockCustomLists`, `adblockAllowlist` and `serviceAdblock`; Rust validates them and re-applies blocking to running services. There are no separate setter commands.

| Command | Input | Output | Notes |
|---------|-------|--------|-------|
| `adblock_get_state` | none | `{ engine: { platform, supported, supportsCounters, coverageNote }, phase, error, catalog[], lists[] }`; `lists[]` = `{ id, name, url, custom, status, lastUpdated, ruleCount, lastError }` | `phase` is `unsupported`, `off`, `waiting`, `compiling`, `ready` or `error` |
| `adblock_update_lists` | none | state | Forces a refresh of every selected list; no-op error on unsupported platforms |
| `adblock_check_list` | `url: string` | `{ networkRules, cosmeticRules }` | Downloads and validates a custom list and caches it; the shell then saves the URL in settings |
| `adblock_normalize_sites` | `inputs: string[]` | `{ accepted: string[], rejected: { input, reason }[] }` | Normalises allowlist entries before they are saved |

Events to the shell: `adblock-lists-updated` (state changed in the background) and `adblock-error` (one message per failure episode).

There is no blocked-request counter command: WebKitGTK reports no event for requests blocked by a content filter.
