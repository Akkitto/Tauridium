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
`tauri-cli 2.12.3`; regenerate it with `tools/generate_flatpak_sources.py`
against the verified `flatpak/tauri-cli.Cargo.lock` shipped in that exact crate before a
dependency/toolchain change. The exact flatpak-builder-tools revision used for a
Flathub submission should be recorded in the human-authored submission PR.

The AppIndicator dependency is vendored from Flathub `shared-modules` revision
`cb9ec602a1ece1c76d5a4f8aa1d87c4a6bf99c3e`. Update the complete
`intltool` and `libayatana-appindicator` module directories together rather than
editing their upstream files independently.

## Build and validation

For local development use a clean, committed checkout and build its exact HEAD:

```text
just flatpak-build
```

This exports a fresh build/repository under ignored, private `release/flatpak/`.
It does not install over the user's existing app. The source is a checksum-bound
Git archive, not an ignored-file directory sweep; relative module patches are
preserved. The Nix development shell supplies the native builder; otherwise
install `flatpak-builder` or the current `org.flatpak.Builder` application.

Publication is a different operation. Before submitting the publication reference,
verify that its immutable tag/commit and all three offline source manifests agree:

```text
just flatpak-publication-check
```

The unchanged 0.9.5 publication pin is historical while security changes are
unreleased. This check deliberately rejects incompatible old source/new inputs;
do not move an existing release tag. After an authorized release, update the
publication pin and offline inputs together, then run the Flathub checks:

```text
flatpak run --command=flathub-build org.flatpak.Builder --install flatpak/dev.brani.tauridium.yml
flatpak run --command=flatpak-builder-lint org.flatpak.Builder manifest flatpak/dev.brani.tauridium.yml
flatpak run --command=flatpak-builder-lint org.flatpak.Builder appstream data/dev.brani.tauridium.metainfo.xml
flatpak run --command=flatpak-builder-lint org.flatpak.Builder repo repo
flatpak info --show-permissions dev.brani.tauridium
```

The source pin must equal the exact public immutable version tag being submitted,
not an unrelated old release. The file requests no host/home filesystem access and no
explicit `org.freedesktop.portal.*` bus permissions.
