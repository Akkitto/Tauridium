# Data Model: Spelling Check and Dictionary Support

## SpellcheckSettings (app settings, global)

| Field | Type | Rules |
|-------|------|-------|
| `spellcheckEnabled` | boolean | Default `true` |
| `spellcheckLanguages` | string[] | BCP-47 tags (e.g. `en-US`); max 8; no duplicates; empty = system language |

## ServiceSpellcheckOverride (app settings, map keyed by service id)

Setting `serviceSpellcheck`: `{ [serviceId]: { enabled?: boolean, languages?: string[] } }`

- Keys must be existing valid service ids; entries for deleted services are removed on service deletion.
- Absent field inherits the global value. An empty object is dropped.
- Effective settings: `enabled = override.enabled ?? global.enabled`; `languages = override.languages ?? global.languages`.

## PersonalDictionary (file `spelling-dictionary.json`, private, atomic writes)

```json
{ "version": 1, "words": ["Tauridium", "Kubernetes"] }
```

- Words are trimmed, 1-64 characters, no whitespace or control characters; compared case-sensitively but stored de-duplicated case-insensitively for lowercase entries; max 10,000 words.
- Unknown future `version` is rejected with an actionable error (same approach as `LocalProfile`).
- Sorted on write for deterministic backups.

## SpellingLanguage (runtime, not persisted)

| Field | Type |
|-------|------|
| `tag` | string |
| `displayName` | string |
| `available` | boolean |
| `reason` | string, only when unavailable |

## WordLookupResult (runtime, P3)

`{ status: "found" | "notFound" | "unavailable", word, definitions?: string[], message?: string }`

## State transitions

- Add word: validated, de-duplicated, saved, then pushed to all running service webviews.
- Remove word: saved, then removed from running webviews; takes effect for new sessions on next create if live removal is unsupported.
- Settings change: validated and saved, then applied live where the engine allows, otherwise at next webview creation (UI states which).
- Restore from backup: dictionary and settings replaced atomically; invalid data rejected without touching current state.
