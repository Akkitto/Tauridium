# Tauridium Flatpak packaging

This directory is the canonical upstream packaging input for `dev.brani.tauridium`.
The application is built from source with network access disabled during module builds.

## Regenerate dependency sources

Run from the repository root:

```text
python3 tools/generate_flatpak_sources.py
```

`cargo-sources.json` and `node-sources.json` are deterministic derivatives of the
committed Cargo/npm lockfiles. `tools/generate_flatpak_sources.py` reproduces the
Cargo vendor layout and npm cacache layout used by the current Flatpak builder tools,
and `--check` fails when either committed source manifest is stale.

`tauri-cli-cargo-sources.json` is the pinned offline source set for
`tauri-cli 2.11.3`; regenerate it with the current `flatpak-cargo-generator.py`
against the `Cargo.lock` shipped in the `tauri-cli 2.11.3` crate before a
dependency/toolchain change. The exact flatpak-builder-tools revision used for a
Flathub submission should be recorded in the human-authored submission PR.

## Build and validation

Use the current Flathub Builder application and a clean checkout:

```text
flatpak run --command=flathub-build org.flatpak.Builder --install flatpak/dev.brani.tauridium.yml
flatpak run --command=flatpak-builder-lint org.flatpak.Builder manifest flatpak/dev.brani.tauridium.yml
flatpak run --command=flatpak-builder-lint org.flatpak.Builder appstream data/dev.brani.tauridium.metainfo.xml
flatpak run --command=flatpak-builder-lint org.flatpak.Builder repo repo
flatpak info --show-permissions dev.brani.tauridium
```

The source pin in `dev.brani.tauridium.yml` must equal the public immutable `v0.8.2`
tag commit. The file intentionally requests no host/home filesystem access and no
explicit `org.freedesktop.portal.*` bus permissions.
