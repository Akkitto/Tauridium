# Secure release activation and custody

Normal `just init`, `just ci`, `just build`, `just bundle-target TARGET` and local
unsigned packaging do not require a signing key. Never put keys in a source file,
`.env`, Cargo config, shell history, build cache, full-Git checkpoint intended for
sharing, or a builder environment. The native wrapper rejects signing credentials
before starting project/dependency build code. npm lifecycle hooks stay disabled.

## Owner activation before the next authorized release

This remediation does **not** create a release, version, tag, push, secret or remote
policy change. The owner must review and activate these controls on GitHub:

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
The application ZIP parser is maintained; the official pinned builder still has
upstream-only withdrawn/maintenance/private-PGP-signing findings. The supported
builder has no keys and only reviewed repository inputs; isolated updater signing
does not use those APIs. These controls are conditional assessments, not upstream
fixes. New/changed/expired findings fail and need review. A supplied offline database
snapshot is labeled a diagnostic, never the current online gate.

See [artifact inspection](ARTIFACT-SECURITY.md). Raw logs, profiles, screenshots/OCR,
scan corpora and full-Git recovery checkpoints stay private. Do not upload ignored
evidence directories recursively. Static scans and signatures cannot prove absence
of every secret or vulnerability; retain platform runtime and manual UX checks.
