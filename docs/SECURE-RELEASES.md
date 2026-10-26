# Secure release activation and custody

Normal `just init`, `just ci`, `just build`, `just bundle-target TARGET` and local
unsigned packaging do not require a signing key. Never put keys in a source file,
`.env`, Cargo config, shell history, build cache, full-Git checkpoint intended for
sharing, or a builder environment. The native wrapper rejects signing credentials
before starting project/dependency build code. npm lifecycle hooks stay disabled.

## Owner activation before the next authorized release

For first-time owner key generation, backup, public-key migration and activation,
follow [the updater signing guide](UPDATER-SIGNING.md). Older installations with
the previous public key need a manual upgrade when its private key is unavailable.

A local release commit, tag or ZIP does **not** activate remote protections or
confirm signing-key scope. The owner must review and activate these controls on GitHub:

1. Pre-create `release-signing` and `release-publishing` environments. Require an
   appropriate reviewer and restrict deployment policies to **tags named `v*` only**.
   Disable administrator bypass in the UI. Prefer independent approval and prevent
   self-review when the maintainer team permits it. The read API cannot prove the
   administrator-bypass UI setting, so the preflight does not pretend to verify it.
2. Move `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` to
   **`release-signing` environment secrets only**. Remove any repository/organization
   scope copies accessible to builders. Keep the existing updater identity unless
   intentionally planning a separate key-rotation migration. Do not print/retrieve
   key values to verify their location. Set the repository variable
   `RELEASE_KEY_SCOPE_CONFIRMED=true` only after reviewing that scope.
3. Require the CI security, native Windows/Linux and Nix checks in the default-branch
   ruleset; protect release tags from unauthorized creation/replacement. Configure
   private vulnerability reporting and reviewed least-privilege collaborator access.
4. Review the exact tagged source and all required jobs before approving either
   protected environment. Use fresh GitHub-hosted runners, not shared/self-hosted
   runners retaining arbitrary jobs. Do not approve a substituted workflow.

Preflight checks reviewer/tag restrictions without creating environments. Missing
protection or scope confirmation fails closed. Repository/org secret locations and
branch rules remain owner responsibilities, not settings silently changed by scripts.

### Solo-maintainer configuration

For the present one-maintainer project, use **Akkitto** as the required reviewer
of both environments and leave **Prevent self-review** disabled. Keep administrator
bypass disabled. This is an intentional pause to inspect the exact source/jobs
before exposing a key or publishing bytes; it is not an independent second-person
review and cannot protect against a compromised owner account. Use a passkey/MFA
and review account recovery/access separately. Add independent review if a trusted
maintainer joins later, rather than configuring a nonexistent reviewer now.

In the default-branch ruleset require actual successful security, Linux, Windows
native and both Nix architecture jobs. Select their observed check contexts after
an authorized CI run; do not type an invented context that never runs. A solo
maintainer can require PRs with **zero** outside approvals, merge their own passing
PRs and retain an audit trail without locking themselves out. Preserve the existing
deletion/force-push restrictions; do not silently replace unrelated owner rules.

For tags matching `v*`, use an active no-bypass rule preventing updates/deletion.
If tag creation must be restricted, use a separate creation rule with the owner
allowed to create tags. Combining all three restrictions under one owner bypass
would also permit tag rewriting and defeat the immutable-tag rule.

Enable **Private vulnerability reporting** in GitHub repository security settings
and verify that the private Report a vulnerability entry is actually available.
Disabled public issues/discussions are not a replacement. The current integration
does not provide authenticated administration access; local documentation and
preflight code cannot activate these remote settings.

Check secret **names/scopes**, not values, using the GitHub UI or `gh secret list`
and `gh secret list --env release-signing`. If a key needs moving, enter it from
the owner's existing secure store into the environment; GitHub cannot return its
old secret value. Do not put a key on a command line or copy it into a builder.
Set `RELEASE_KEY_SCOPE_CONFIRMED=true` only after this review is complete.

## Workflow boundaries

The tag workflow uses these separate runners:

1. Key-free canonical native builds and deterministic source/docs handoff. No shared
   restored Rust/npm build caches in the release workflow.
2. Keyless exact same-run assembly and static full-container/secret inspection.
3. Protected signing with only the official SHA-256-pinned Minisign executable.
   No Cargo, npm, Tauri CLI, project hooks, archive/installer parsing or application
   execution. Python runs isolated (`-I`). Decoded keys are created mode 0600 inside
   private `/dev/shm` temporary directories; passphrases go over stdin, not argv or
   child environment. Passphrases preserve spaces and UTF-8, must be one line and
   at most 1022 UTF-8 bytes. Cleanup is not a claim of secure memory erasure.
4. Fresh keyless signature verification, metadata/Scoop/SBOM creation, whole-snapshot
   scanning and GitHub provenance attestation of the public checksummed subjects.
5. Protected hash-only publication. No complex artifact parsing under a write token.
   Upload a private draft, verify **every** remote name/size/SHA-256, then publish.
   Existing drafts/releases are never overwritten, deleted or repurposed. Interrupted
   uploads leave a private draft for owner review; they are not automatically retried
   over existing assets. No pipeline can make a multi-file GitHub upload transactional.
   Private drafts are discovered through the authenticated release listing; GitHub's
   by-tag endpoint returns published releases only. Verification, promotion and the
   final remote check stay bound to the same numeric release ID. For owner-reviewed
   recovery, compare the complete draft against the exact approved sealed snapshot
   and provenance before promoting that ID; do not replace uploaded assets or tags.

Each boundary checks the preceding job's independent output digest against a bounded
`TRANSFER.json` exact inventory, version and commit. That transport seal and release
notes are not extra release assets. `ARTIFACTS.json`, `SHA256SUMS`, version-bound
Minisign signatures and attestations cover the actual public snapshot. An unsigned
fallback remains available for local builds, **not** for protected updater publication.
Checksums alone are not publisher authentication. Updater signatures are not Windows
Authenticode; Windows installers are not represented as Authenticode-signed.

The CycloneDX build-input inventory includes optional/other-platform/build dependencies;
it deliberately does not claim all components are reachable in the installed runtime.
Consumers can use `gh attestation verify FILE --repo Akkitto/Tauridium` for future
attested files, and verify hashes/signatures before using installers.

## Continuing checks

`just audit` checks npm at all advisory severities and audits both actual Rust locks
against a fresh RustSec database. Security CI is required by normal CI/release and
also scheduled daily. Exact version/lock-scoped assessments in
`data/security-advisory-policy.json` expire and are printed, never silently ignored.
The application and patched stable builder both use maintained ZIP 9. The shared
builder preparation removes RPM's unused OpenPGP/ML-DSA stack entirely. Whole-lock
scanning still reports an RSA advisory from the macOS-only certificate generator:
its reviewed API use generates ephemeral keys, not the affected RSA decryption.
That precise expiring assessment and upstream maintenance warnings remain visible;
this is not an upstream RSA fix or a claim of zero findings. New/changed/expired
findings fail and need review. A supplied offline database
snapshot is labeled a diagnostic, never the current online gate.

The application lock is also SHA-256-bound. The exact `zbus_names 4.3.2`,
`zvariant 5.12.0` and `zvariant_derive 5.12.0` maintenance findings have a separate
short review deadline of **15 November 2026**; they remain visible in every fresh
audit. Upstream merged them into zbus 6, while
the current notification, portal and OS-vault parents require zbus 5. The
[review and coordinated migration plan](ZBUS-MAINTENANCE-REVIEW.md) explains the
temporary exact-scope decision. It is not a vulnerability exclusion or an upstream
fix. Lock changes, new versions/kinds and expiry fail closed; do not just extend it.

See [artifact inspection](ARTIFACT-SECURITY.md). Raw logs, profiles, screenshots/OCR,
scan corpora and full-Git recovery checkpoints stay private. Do not upload ignored
evidence directories recursively. Static scans and signatures cannot prove absence
of every secret or vulnerability; retain platform runtime and manual UX checks.

### Recurring owner review

- Daily: monitor the security workflow's fresh npm/RustSec results and actual
  scanner controls. An unpushed workflow does not run; enable notification delivery
  and investigate failures rather than treating a schedule as an operational proof.
- Weekly: review dependency update PRs and the pinned Tauri CLI/scanner/toolchain
  upstream releases. Reassess builder findings before their 15 November 2026 expiry;
  reassess the three D-Bus maintenance findings by the same date. Other maintenance assessments expire
  15 January 2027. Do not extend them without evidence.
- Monthly, and before a security release: review Nix inputs, GNOME SDK/platform,
  WebKitGTK/WebView2, native libraries and vendored compatibility patches. Prepare
  lock updates in a disposable private checkout; inspect the diff, then run actual
  Nix package/install/VM checks and the local Flatpak build. No automatic merge,
  floating source pin or unreviewed candidate build belongs under signing keys.
- Before publication: review exact source, required checks, protections, key scope,
  signatures/attestations and final remote draft bytes. Validate Windows transport,
  real vault migration/cleanup, Settings, sign-in, file drops, downloads and Scoop.

Native Windows unit gates now run before release bundling on both Windows targets.
They include private-DACL checks, silent/partial/non-reading pipe peers, large
overlapped transfers and a real Credential Manager migration/removal using only a
new synthetic session. Cross-Clippy cannot establish that these tests passed on
Windows; GUI/sign-in behavior also needs native execution. Pipe cancellation must
finish before its borrowed buffers are dropped; bounded peer waits are not a claim
of bounded kernel teardown on a malfunctioning OS.

Windows activation also reserves the first pipe instance exclusively before UI
startup, retains that endpoint between clients, and checks object ownership plus
peer process user/session before sending launch context or granting foreground
permission. The client requests identification-only SQOS. Native tests cover
preexisting/extra endpoint rejection, reconnect reservation, actual owner checks,
identification level and cancelled idle-listener shutdown. Native execution is
still required: compiling these tests in WSL is not proof they passed on Windows.
