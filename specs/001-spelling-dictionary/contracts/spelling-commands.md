# Contract: Spelling Commands (Tauri IPC)

Typed wrappers live in `src/lib/api.ts`. All commands are callable only from the shell window, never from service webviews (follow `ipc_security.rs`). All errors are actionable strings.

| Command | Input | Output | Notes |
|---------|-------|--------|-------|
| `spelling_get_state` | none | `{ settings, serviceOverrides, words, languages: SpellingLanguage[] }` | Single load for the settings panel |
| `spelling_set_global` | `{ enabled?, languages? }` | updated settings | Validated, persisted, applied live; UI shows `Saved` |
| `spelling_set_service` | `{ serviceId, enabled?, languages? }` (null clears a field) | updated overrides | Same guarantees |
| `spelling_add_word` | `{ word }` | `{ words }` | Rejects invalid/duplicate with message |
| `spelling_remove_word` | `{ word }` | `{ words }` | |
| `spelling_lookup_word` | `{ word }` | `WordLookupResult` | P3, behind spike S3 |

## Settings keys (additive, upgrade-safe)

`spellcheckEnabled`, `spellcheckLanguages`, `serviceSpellcheck` added to the defaults and validation in `main.rs` and to the TypeScript settings interface. Existing profiles without them load with defaults.

## Backup contract

Backup payload gains an optional `spellingDictionary` section; readers treat absence as empty (schema v1/v2 backups still restore). Writers include it in new backups; integrity hashes cover it.
