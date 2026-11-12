# Phase 0 Research: Spelling Check and Dictionary Support

Findings come from reading this repo (`vendor/wry`, `src-tauri/src/main.rs`, `Cargo.toml`) and the locked Rust crates. Nothing here was run in a live Windows or macOS WebView; items needing that are explicit **spikes** that must be resolved before the dependent tasks start.

## Findings about the current code

- Service pages are native webviews created in [main.rs](../../src-tauri/src/main.rs) (`WebviewBuilder`, ~line 2224) with per-service data directories (Windows/Linux) or data-store identifiers (macOS).
- No spelling code exists anywhere (`grep -i spell` is empty), including in `vendor/wry`.
- The `prettyServiceContextMenu` setting only affects the *sidebar* service menu in the shell. Right-clicks inside service pages show the engine's native menu, which is where engines offer spelling suggestions.
- Settings are a validated JSON object with defaults and per-service maps (e.g. `serviceZoomLevels`), the established pattern to reuse.
- Linux: `webkit2gtk` 2.0.2 exposes `set_spell_checking_enabled` and `set_spell_checking_languages` on the web context; wry creates a `WebContext` per data directory, so per-service enable/languages is feasible.
- Windows: the `webview2-com` 0.39.1 bindings contain no spellcheck or custom-dictionary API.

## Decisions

### D1. Use native engine spellcheckers, not a custom in-page checker
- **Decision**: Drive WebKitGTK / WebView2 / WKWebView built-in checking.
- **Rationale**: Works in every editor type (textarea, contenteditable, rich editors), offline, no typed text handled by Tauridium, no overlay/performance risk, matches "lighter than Electron".
- **Alternatives**: Injected JS overlay with a bundled Hunspell-compatible checker (brittle across editors, heavy, privacy surface); Rust-side checker with custom context menu (cannot reliably replace native page menus).

### D2. Tauridium owns the state; engines are synced from it
- **Decision**: Settings in the existing app settings JSON; personal dictionary in a new private atomically-written file; both flow into backup/export/portable.
- **Rationale**: Engine-side stores differ per platform and are not backed up. A single source of truth keeps FR-009/FR-010 true on every platform.
- **Alternatives**: Rely on each OS/engine's own personal dictionary (not portable, not backed up, differs per service session).

### D3. Settings shape
- **Decision**: `spellcheck = { enabled, languages[] }` globally plus `serviceSpellcheck = { <serviceId>: { enabled?, languages? } }`; missing means inherit. Empty `languages` means system language.
- **Rationale**: Inheritance keeps upgrades trivially compatible and makes per-service overrides minimal.

### D4. Platform adapters
| Platform | Enable/disable | Languages | Personal dictionary sync | Status |
|----------|----------------|-----------|--------------------------|--------|
| Linux (WebKitGTK) | Web context API | Web context API (needs system Hunspell/Enchant dictionaries) | Spike S2 | Feasible |
| Windows (WebView2) | Spike S1 | Spike S1 | Spike S2 | **Unverified** |
| macOS (WKWebView) | Spike S1 | System-managed | System learn/ignore | Best-effort |

### D5. Word-definition lookup (P3)
- **Decision**: Deliver last, behind spike S3. Preferred first version: a "Look up" action that opens a user-configurable dictionary URL in the default browser only on explicit user action, with the privacy cost stated in the UI. Offline definitions would need a bundled licensed dataset; defer unless the user requires it.
- **Rationale**: No offline definition source exists today; bundling one affects size, licensing and the supply-chain gates.
- **Alternatives**: Bundled WordNet/Wiktionary data (size/licence/review burden); OS dictionary services (macOS only).

## Spikes (must resolve before dependent tasks)

- **S1 (blocks Windows work)**: On Windows 11, confirm what WebView2 does by default for `spellcheck` in service pages, which languages it uses, and whether it can be enabled/disabled/languaged per profile (candidates: Chromium command-line switches via `additional_browser_args`, profile settings via a newer `ICoreWebView2Profile` interface). Confirm the native menu shows suggestions.
- **S2 (blocks personal dictionary sync)**: Determine how to push Tauridium's words into each engine: WebView2 profile custom-dictionary file in the per-service data directory (Chromium convention, must be verified), WebKitGTK personal word list via Enchant (check Flatpak sandbox access), and macOS learn-word behaviour. Also determine how "Add to dictionary" chosen in the native menu is read back so Tauridium's store stays authoritative; if it cannot be observed, add a fallback Tauridium-owned way to add words.
- **S3 (blocks P3)**: Confirm a way to obtain the selected word from a native-menu action, or choose a different trigger (shortcut or shell-side entry).

If S1 shows Windows cannot be controlled per service, the fallback is a global-only toggle and language list on Windows, with the UI stating the limit (FR-016).

## Resolved clarifications

No `NEEDS CLARIFICATION` remains in the plan; spikes above are engineering unknowns, not requirement gaps. The spec note about offline definitions is handled by D5.
