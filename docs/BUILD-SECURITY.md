# Build security

## JavaScript installation

Implicit dependency lifecycle scripts are disabled, including on npm 10. The
project .npmrc protects ordinary manual npm ci; both native initializers and the
Flatpak build also pass --ignore-scripts explicitly. Nix sets the corresponding
build environment policy and includes .npmrc in its source fileset. A caller's
unsafe npm_config_ignore_scripts=false cannot override the bootstrap CLI flag.

Unsupported allowScripts metadata is not used as a security boundary. The shared
tools/npm_policy.py validator rejects root installation hooks and unexpected
dependency hook metadata before installation. The locked esbuild and optional
macOS fsevents install hooks are recognized in the lockfile but never executed.
esbuild uses the native executable in its locked optional platform package; the
initializer verifies it with npm exec --offline -- esbuild --version. Missing or
unsupported platform binaries fail visibly rather than triggering a downloader.

Explicit reviewed npm run build/check/test commands still work. This policy is
not a claim that a compiler or directly invoked build dependency is harmless:
source review, integrity-locked dependencies, current advisory gates and protected
signing custody remain separate requirements. Never put release credentials in a
generic build environment or upload an entire ignored output directory.

The real npm regression has a harmless, authored positive control proving a hook
would run when enabled, then verifies that both the explicit bootstrap flag and
the project default prevent execution. It does not execute untrusted third-party
code to perform the security scan.

## Pinned native tooling

data/build-toolchain.json identifies supported Tauri CLI 2.12.3 and the SHA-256
digests of its published crate and Cargo.lock. Native initialization reuses only
that exact CLI; a different installed version is replaced with a locked install.
Nix builds the same checksum-pinned published crate and dependency bundle, retains
the nixpkgs Tauri hook, and never installs tools into the user's Cargo directory.
Flatpak builds from the same crate/lock and removes cargo-tauri during final
cleanup; the build-only executable is not a runtime dependency.

tools/generate_flatpak_sources.py regenerates and exactly checks the CLI's offline
source manifest as well as the application's Cargo/npm sources. A source-count or
nonempty-file check is not sufficient. Tool updates must review the new published
lock, advisories, checksums and all three producer paths together. Prerelease Tauri
3 tooling is not an acceptable substitute for the supported Tauri 2 builder.

## Updater signature verification

Canonical native `just build`, `just bundle` and `just bundle-target` commands
invoke the pinned CLI through `tools/tauri_build.py`. Bundles are always produced
without automatic updater signing. A nonempty signing-credential environment is
rejected before build code starts; unset it and use the separate isolated
`tools/sign_release.py` custody step. No owner signing key belongs in a build
shell, dotenv file, Cargo/npm hook, generic CI environment or checkout. Direct
raw `cargo tauri build` is not the supported release-signing workflow.

The helper preserves existing Cargo flags and remaps repository/home paths in
compiler output using whitespace-safe encoded flags. This reduces accidental
local-path disclosure; it is not a claim that a local workstation is an OS-level
security boundary against malicious code running as its owner. CI compilation
and protected signing must use different fresh jobs/runners.

Signature presence or nonempty text is never proof of signing. The native
collector verifies the exact staged artifact bytes before replacement. Signed
updater-set classification and manifest creation reverify every required pair
against the public key in the checked-in Tauri configuration, including the
global signature over the trusted comment. The trusted version must exactly
match the release; an older signed binary cannot be relabeled as a newer update.
Prehashed Minisign envelopes are required. An arbitrary public-key sidecar is
never a trust anchor, and missing verification tools fail closed.

Native initialization supplies Minisign through the Linux package manager or,
on Windows, Scoop with the verified WinGet package as fallback. Nix supplies it
in the development environment. On macOS install it with brew install minisign.
The verifier also finds normal Windows package-manager links when the parent
terminal has not yet refreshed PATH. It never executes downloaded application
artifacts to verify them.

Regression tests generate only ephemeral synthetic keys outside the repository.
They cover real Tauri CLI output, independent Minisign verification, wrong keys,
tampered bytes, altered signed-version comments, dummy/oversized signatures,
complete-set classification and preservation of existing output on rejection.

Protected release signing uses the official checksum-pinned standalone Minisign,
not the build SDK. See [secure release activation](SECURE-RELEASES.md) for owner
environment/secret-scope requirements, hash-sealed job boundaries, expiring
upstream builder-only advisory assessments and the distinction between updater
signatures and Windows Authenticode. `just audit` uses the pinned current scanner
and actual application/builder locks; daily and required CI enforce the same gate.

Dependency-update PRs are proposed weekly for npm, Cargo and Actions. They still
require source review, tests, regenerated Flatpak offline sources and correct Nix
hashes; automated dependency PRs do not authorize automatic merging or release.
