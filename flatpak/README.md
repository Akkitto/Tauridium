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
just flatpak-test
just flatpak-lint
```

This exports a fresh build/repository under ignored, private `release/flatpak/`.
It does not install over the user's existing app. The source is a checksum-bound
exact Git tree/blob archive, not `git archive` or an ignored-file directory sweep.
Neither tracked nor producer-local export attributes/filters can omit or rewrite
committed files. Relative module patches and executable modes are preserved.
The Nix development shell supplies the native builder; otherwise
install `flatpak-builder` or the current `org.flatpak.Builder` application.

The builder publishes `release/flatpak/latest.json` only after a successful export.
Test/lint select that exact current-HEAD candidate, reject incomplete/stale/changed
outputs, and never fall back to a root `repo` or installed app. An explicit candidate
directory can be passed as the recipe's single argument. Run the recipes on separate
lines: optional arguments in `just` can otherwise consume a following recipe name.
The shared `tools/flatpak_policy.py` contract validates metadata before publishing a
successful candidate seal and again before every test/run/lint action. It requires
the reviewed GNOME 51 runtime/SDK architecture pair, exact application/context/session
bus settings, no added system-bus policy or runtime environment, and only the known
Debug/Build metadata. Unknown groups, application fields, inherited defaults or
extension injection fail closed. A future legitimate policy/runtime change must
update the explicit contract and regression tests; matching hashes alone are not
permission approval. Existing reviewed generated Debug/Build groups remain accepted.

`flatpak-test` is a headless production/distribution identity check. `flatpak-lint`
validates the selected manifest/source binding, exported repository, actual sandbox
permissions, installed AppStream metadata and desktop file offline. It does not
claim online Flathub approval. For manual GUI testing, use `just flatpak-run`: this
runs the candidate read-only with temporary XDG data, no owner app profile and no
real credential-vault access. Closing it discards that temporary test profile.

`just flatpak-flathub-lint` runs the official online Flathub policy checks against
the same candidate. Network, reverse-domain ownership/reachability, or submission
policy failures are real failures, not suppressed exceptions. For example the
existing `dev.brani.tauridium` ID's domain can be challenge-blocked to automated
clients. Resolve such publication conditions with the domain owner/Flathub; do not
change the application ID casually because existing profiles depend on it.

Publication is a different operation. Before submitting the publication reference,
verify that its immutable tag/commit and all three offline source manifests agree:

```text
just flatpak-publication-check
```

The publication reference targets the immutable 1.0.0 source commit. Its pin was
materialized after tagging to avoid a self-referential commit; the tagged source
archive therefore retains the preparatory placeholder. Use this post-tag upstream
reference for publication, or `just flatpak-build` for local tagged-source testing.
This check rejects unresolved pins or incompatible source/offline inputs; do not
move an existing published release tag. Verify the matching offline inputs before
running submission checks. The
following explicit Flathub command installs an application and is **not** the local
non-installing QA workflow above:

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
