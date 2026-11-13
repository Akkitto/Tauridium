# Data Model: Ad and Tracker Blocking

All additions are optional. Absent means "use default"; an empty list is different from absent.

## App settings (existing JSON, additive)

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `adblockEnabled` | bool | false for upgraded profiles | Global switch |
| `adblockLists` | string[] | curated defaults (decided in S1/S3) | Ids from the curated catalog |
| `adblockCustomLists` | string[] | [] | `https://` URLs, max 20, deduplicated |
| `adblockAllowlist` | string[] | [] | Normalised hostnames (lowercase, punycode, no scheme/port/path, optional leading `*.`), max 500 |
| `serviceAdblock` | map<serviceId, override> | {} | Override: `{ enabled?: bool, allowlist?: string[] }`; empty override rejected; unknown fields rejected |

Validation: reject unknown versions and malformed values without overwriting the file; ids must be existing service ids on write and are cleaned on service delete; copied on duplicate.

## Filter list (cache metadata, private file `adblock/lists.json`)

`id`, `source` (catalog or custom URL), `enabled`, `etag`/`lastModified`, `lastUpdated`, `ruleCount`, `skippedCount`, `lastError` (string or null), `errorReportedAt`, `contentHash`. Content in `adblock/lists/<id>.txt`, written atomically; previous good copy retained until the new one validates.

State: `missing -> downloading -> active`; `active -> updating -> active | active(with lastError)`; invalid downloads never replace `active`.

## Compiled artefacts (rebuildable, not backed up)

- Linux/macOS: native rule list saved under app data keyed by `contentHash` of the enabled lists plus allowlist.
- Windows: in-memory `Engine` snapshot swapped atomically.

## Blocked count

Per service, in-memory, per session. Not persisted, not exported.

## Backup and export

New optional `adblock` section in backups (settings, custom lists, allowlist; not list contents or compiled artefacts) and per-service override in service exports. When the section is absent the integrity digest input is byte-identical to today's, and restoring a backup without it does not clear existing settings.
