# Scoop packaging

This directory makes the Tauridium repository continuously testable against the requirements for
an official `ScoopInstaller/Extras` submission.

## Repository fixture

`tauridium.json.template` is an integration template, not the canonical public Scoop manifest. It
contains version and SHA-256 placeholders so the repository can validate field ordering, URLs,
architecture coverage, shortcut behavior, WebView2 notes, and autoupdate rules before Windows
release binaries exist.

For each tagged release, the Windows x64 and ARM64 jobs produce:

```text
tauridium-X.Y.Z-windows-x64-portable.zip
tauridium-X.Y.Z-windows-x64-portable.zip.sha256
tauridium-X.Y.Z-windows-arm64-portable.zip
tauridium-X.Y.Z-windows-arm64-portable.zip.sha256
```

The publish job downloads those exact staged assets, validates their hashes, and renders:

```text
tauridium-X.Y.Z-scoop.json
```

That rendered file has real SHA-256 values and deterministic GitHub Release URLs. It is suitable
for upstream review after being renamed to `tauridium.json` in the Extras bucket.

## What CI proves

Tagged releases must pass all of these Scoop-specific gates before publication:

1. Both Windows portable ZIPs are built from production-mode Tauridium binaries.
2. Each ZIP contains only root-level `tauridium.exe` and uses deterministic ZIP metadata.
3. Each portable executable reports the expected Tauridium version and compilation target through
   Tauridium's non-GUI `--build-info-file` probe.
4. Each ZIP's published `.sha256` sidecar matches the archive.
5. A clean, isolated Scoop root installs the local manifest on the matching Windows architecture.
6. The installed executable and Start Menu shortcut exist.
7. A simulated version update preserves application data outside Scoop's version directory.
8. Uninstall and reinstall succeed while external application data remains intact.
9. The final release manifest is generated from the hashes of both staged portable archives.
10. Scoop's own pinned `checkver.ps1` performs a local `checkver`/`autoupdate` cycle and must reproduce the expected portable URL and SHA-256; the final `$version` GitHub autoupdate URLs are also statically validated by `tools/scoop.py`.

The test uses a pinned Scoop release in GitHub Actions rather than relying on a mutable development
checkout.

## Official Extras submission

Do not add a `bucket/tauridium.json` file to this repository. The canonical manifest belongs in
[ScoopInstaller/Extras](https://github.com/ScoopInstaller/Extras).

Current Scoop contribution policy requires a new-package issue first. Wait for maintainer approval
before opening the package PR. For the initial package, use the PR title format required by Scoop
(for example `tauridium: Add version 0.7.0`), test install/uninstall/functionality/persistence and
autoupdate, then request the bucket's automated verification with `/verify` after the PR exists.

Upstream references:

- <https://github.com/ScoopInstaller/.github/blob/main/.github/CONTRIBUTING.md>
- <https://github.com/ScoopInstaller/Scoop/wiki/App-Manifests>
- <https://github.com/ScoopInstaller/Scoop/wiki/App-Manifest-Autoupdate>
