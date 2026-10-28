# Reviewed deepmerge security backport

This is upstream **deepmerge 4.3.1** with Tauridium's minimal security backport,
identified explicitly as **4.3.1+tauridium.1**. The original MIT license and type
definitions are retained. `dist/cjs.js` is the published, self-contained CommonJS
runtime, including upstream's bundled mergeability helper. It is used unchanged
except for the security changes below. Upstream `license.txt` is stored as `LICENSE`.

Source: <https://registry.npmjs.org/deepmerge/-/deepmerge-4.3.1.tgz>.
Its original SHA-512 integrity and every included implementation/metadata file's
SHA-256 are recorded in `TAURIDIUM-PATCH.json`. The source archive was verified
against the existing registry lock before extracting these bounded regular files.

## Reason and changes

[GHSA-gcqx-w48m-w2h4](https://github.com/advisories/GHSA-gcqx-w48m-w2h4), reviewed
on 27 October 2026, reports prototype poisoning of returned objects. The issue
is reproducible with null-prototype targets, primitive/null defaults and an own
`__proto__` key on the target. Checking only global `Object.prototype` misses it.
There is no published upstream patched version as of 28 October 2026.

Both the target-copy and source-copy loops now reject the string keys
`__proto__`, `constructor` and `prototype` before reading their values. All
assignments define own writable/enumerable/configurable data properties rather
than invoking inherited setters. Other merging, array replacement hooks, symbol
keys and object/function handling retain upstream behavior. No install scripts,
external dependencies or automatic source patching are introduced.

## Enforcement and retirement

The root development dependency selects this in-tree package, and npm's
`$deepmerge` override makes the Svelte plugin resolve that same copy. Bootstraps
validate its source hashes and exact local-link policy before installation.
`tools/check_deepmerge.mjs` independently checks actual plugin resolution, hashes,
exploit regressions and ordinary Svelte configuration behavior. It runs before
every production frontend build, during initialization and in security CI.

`npm audit --audit-level=low` remains mandatory for all registry dependencies.
**npm does not audit local packages**; a clean registry audit is not evidence that
this source backport is safe. Its explicit provenance, integrity checks and
mandatory behavioral regressions provide that separate evidence. No advisory
ignore, severity downgrade, old-version rollback or purported upstream fix is used.

Nix includes the backport and mandatory build probe in its explicit source set.
Flatpak carries them in the immutable source and caches registry packages only;
its offline-source generator accepts this exact local link and rejects others.
Canonical LF bytes are preserved on Windows for the integrity-bound files.

Replace this backport only after a reviewed maintained upstream dependency
removes the affected code or provides the fix. Regenerate the npm lock, Flatpak
sources and measured Nix npm hash together, preserve equivalent exploit coverage,
and verify Windows, native Linux, Nix and offline Flatpak builds.
