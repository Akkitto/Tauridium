# WinGet

Tauridium's proposed community package ID is `Akkitto.Tauridium`. It uses the
official per-user NSIS installers for native x64 and ARM64. This directory holds
reviewed release locks and integration fixtures. Canonical manifests belong in
`microsoft/winget-pkgs`, under `manifests/a/Akkitto/Tauridium/<version>/`.
Catalog publication requires the upstream submission and indexing to complete.

## Prepare a published release

Run from the Tauridium repository. The same `just` commands work on native Windows
and Linux. The adapter revalidates the official hash-pinned Minisign cache and
bootstraps the verifier if missing. An arbitrary executable on `PATH` is never
used for WinGet signature verification. No private signing key or registry
submission credential is needed.

```text
just winget-fetch 1.0.3
just winget-prepare 1.0.3
```

The reviewed release lock pins the exact installer and signature sizes/SHA-256
values for both architectures. Downloads use official HTTPS endpoints and a
bounded redirect allowlist. Both version-bound Minisign signatures are verified
against Tauridium's configured public key before manifests are generated. A
signature is an updater signature, not Windows Authenticode.

Assets are placed in ignored `release/winget/assets/<version>/`. Manifests are
generated in ignored `release/winget/manifests/<version>/`, with a schema header,
stable version URL, deterministic UTF-8/CRLF bytes and no private data. Outputs
are reverified and reused when repeated unchanged. Changed hashes, manifest bytes,
symlinks or unexpected manifest files fail without replacing the existing evidence.
To regenerate changed manifests, preserve the previous directory and prepare again.

## Accept a new version

1. Finish the ordinary protected release and confirm its public assets. Record
   the exact tag commit and successful release workflow run ID. Never change old
   assets or move an existing tag to update a registry.
2. Generate a review candidate, supplying the real version/commit/run values:

   ```text
   just winget-intake VERSION COMMIT RELEASE_RUN_ID
   ```

   This checks the public stable release, resolves its tag, verifies the exact
   commit and successful release workflow, then downloads and verifies both
   signed installers. Output is `release/winget/candidates/VERSION.json`.
   GitHub API/network errors stop preparation. No unpublished fallback is used.
3. Review and copy that candidate to `packaging/winget/releases/VERSION.json`.
   Confirm the exact hashes against the protected release inventory and verify
   artifact attestations with `gh attestation verify FILE --repo Akkitto/Tauridium`.
   The release is not advertised as GitHub-enforced immutable. A versioned URL
   alone does not authenticate bytes.
4. Update the acceptance harness's current/previous version defaults to an actual
   published pair. Keep the previous lock for the real upgrade test. Validate
   native installer identity and self-update/manager coexistence before changing
   publisher, scope or installer family.
5. Run the native acceptance mode on both architectures and the Python regression
   suite. Review actual installation results, not only generated YAML.
6. Prepare manifests with the commands above. Re-run native `winget validate`
   for the final exact files. Copy only the three YAML files into the single
   upstream package/version folder. Complete catalog acceptance after indexing.

The adapter deliberately does not automatically push registry changes from a
release job. It does not add artifacts to the sealed application release or put
new credentials into the protected updater signing environment.

## Acceptance phases

The manifest format is 1.12.0, explicitly accepted by the registry and present in
Microsoft's released client schemas. The registry's current PR template also
mentions 1.28, while the pinned released client still provides 1.12 schemas.
Actual client validation determines compatibility.

The `WinGet acceptance` workflow has two explicit modes on native x64 and ARM64
Windows. The harness refuses ordinary developer machines and changes installation
state only on disposable GitHub-hosted runners.

- **native** runs on relevant PRs and master updates. It verifies release hashes,
  both updater signatures using the pinned verifier, and real `winget validate`.
  It tests direct signed-installer installation, actual previous-release upgrade,
  unique per-user registration, production version/architecture, data-preserving
  uninstall/reinstall, responsive GUI startup, second-instance activation and
  the updater's NSIS `/UPDATE` path. Native checks do not establish catalog availability.
- **catalog** is required after upstream acceptance/indexing. It fails if the
  expected public version is unavailable or the selected catalog installer URL/hash
  differs from the reviewed lock. It exercises actual WinGet upgrade from the
  older native installation, fresh installation, uninstall/reinstall and recognition
  after the native updater's installer path. It uses the official community source.

After the implementation is merged and the package is indexed, run:

```text
gh workflow run winget.yml --repo Akkitto/Tauridium --ref master -f mode=catalog
```

Unsigned local-manifest installation can stop at a Windows SmartScreen reputation
prompt in a headless runner. Microsoft's client marks approved trusted-source
installers differently after repository scans. The harness does not disable
SmartScreen, change trust zones, remove download security marks, bypass hashes or
pretend a direct installation is a completed catalog test. See the client's
[download trust handling](https://github.com/microsoft/winget-cli/blob/v1.29.380/src/AppInstallerCLICore/Workflows/DownloadFlow.cpp).

A missing/outdated WinGet client is registered from checksum-pinned Microsoft
packages in `client.json`. For manual local-manifest testing use a disposable
Windows desktop VM or upstream `Tools/SandboxTest.ps1`, retaining normal security
prompts. `LocalManifestFiles` requires administrator policy approval. Do not change
it on an owner's managed workstation merely to run a test. Check WebView2-present
and clean-runtime bootstrap cases, tray/second launch and ordinary-user operation.
Keep profiles and evidence private.

Tauridium's native updater remains available. NSIS and WinGet must retain the
same per-user installed-version identity. Measured ARP metadata is display name
`Tauridium`, publisher `brani` and uninstall key `Tauridium`. Never add another
installer family/scope without independently testing its upgrade paths.

## Submit and maintain

- Search the exact ID/name and open/closed PRs before opening a submission. Use a
  sparse checkout, never recursively scan the full upstream manifest collection.
- Follow upstream `AGENTS.md`, contributor guidance, current schema recommendation
  and PR template. One PR contains one version's three manifest files, with no
  tooling or documentation changes. Use `New package: Akkitto.Tauridium version
  VERSION` initially and the upstream update convention afterward.
- Use the owner's normal GitHub fork/PR authorization. If Microsoft requests a
  contributor agreement, the accountable owner signs it. Do not claim it is signed
  or check unperformed tests in the PR checklist.
- Follow validation/review through catalog availability. After publication, verify
  `winget show --id Akkitto.Tauridium --exact --source winget`, then clean native
  `install`, `upgrade` and `uninstall`. Update user documentation only after the
  corresponding availability claim is true.
- If interrupted, inspect the existing PR/version before retrying. Fix the pending
  manifest through its normal review process. Preserve existing releases and data.

Primary references: [manifest schema](https://github.com/microsoft/winget-pkgs/blob/master/doc/manifest/README.md),
[submission](https://learn.microsoft.com/en-us/windows/package-manager/package/repository),
[first contribution](https://github.com/microsoft/winget-pkgs/blob/master/doc/FirstContribution.md),
[Tauri WebView2 provisioning](https://v2.tauri.app/distribute/windows-installer/#webview2-installation-options).
