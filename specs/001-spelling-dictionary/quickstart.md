# Quickstart: Validating Spelling Check and Dictionary Support

Prerequisites: toolchain via `just init`; on Linux, a system Hunspell/Enchant dictionary for at least one language.

## Automated gates

```text
just fmt-check
just lint
just check
just test
```

Includes new Rust unit tests (`spelling.rs`), Vitest `spelling.test.ts`, and `tools/test_spelling_*.py`.

## Manual validation (Windows 11 first, then Linux)

1. `just run`; open a service with a text box (a local test page is fine).
2. Type `teh`: it is marked within 1 second; right-click, choose a suggestion, the word is replaced (User Story 1).
3. Settings > Spelling: add a second language; type a valid word in it, not marked. A green `Saved` toast appears. Restart: choices persist (User Story 2).
4. Right-click a flagged name, Add to dictionary: it unmarks in a second service too. Remove it in Settings: marked again (User Story 3).
5. Disable spelling for one service only; confirm only that service stops marking (User Story 4).
6. Disconnect the network: repeat steps 2-4; behaviour is unchanged.
7. Create a backup, add a word, restore: the word added after the backup is gone and earlier words return.
8. Upgrade check: start with a profile from 1.0.9; no services, workspaces or sessions lost and defaults apply.
9. Password field: no marks appear.
10. (P3) Select a word and use the lookup action; verify definition or clear unavailable message.

Contracts: [contracts/spelling-commands.md](contracts/spelling-commands.md). Data shapes: [data-model.md](data-model.md).
