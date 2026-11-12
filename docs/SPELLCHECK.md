# Spell checking

Tauridium uses each platform's own web engine spell checker. It does not check
text itself, and typed text is never sent to any service for checking.

## Platform status

| Platform | Per-service on/off | Languages | Personal dictionary |
|----------|--------------------|-----------|---------------------|
| Linux (WebKitGTK) | Tauridium | Tauridium | Tauridium |
| Windows 11 (WebView2) | Tauridium | Windows | Windows |
| macOS (WKWebView) | Tauridium | macOS | macOS |

Windows and macOS expose no way to choose spelling languages or manage the
dictionary per app, so Tauridium shows those controls as managed by the system
instead of offering settings that would do nothing. Use the website right-click
menu there to add words.

### Windows and macOS on/off switch

The engines have no native switch, so Tauridium sets the standard
`spellcheck="false"` attribute on editable fields of services where checking is off
and restores each field's own value when it is turned back on. It applies to the
top-level page of a service, not to embedded frames.

On macOS, WebKit underlines misspellings only when the app default
`WebContinuousSpellCheckingEnabled` is true, and treats a missing value as false.
Tauridium sets it once if you have never chosen a value, so a later choice from the
right-click menu is respected.

These two platforms have been implemented from engine documentation but have not
yet been tested on real systems.

## Linux

- Install a Hunspell dictionary for each language you write in (for example the
  `hunspell-en-us` package). Only installed dictionaries can be selected.
- With no language selected, the system language from the locale variables is used.
- Each service can override the on/off state and the languages in its own settings.
  Services that share a sandbox share one spell checker, so the latest change applies
  to all of them.
- When checking is off for a service, spelling items are also removed from its
  right-click menu.

### Personal dictionary

Words are stored once in `spelling-dictionary.json` in the Tauridium data directory
and apply in every language and service. Tauridium points the engine at a private word
list directory, `spelling/enchant`, inside that data directory and mirrors the
dictionary there. Words you add from the right-click menu are imported into the
dictionary. Your own `~/.config/enchant` files are never read or changed.

Personal words are included in full backups. They are not part of per-service or
workspace exports.
