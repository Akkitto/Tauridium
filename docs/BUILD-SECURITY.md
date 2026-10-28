# Build security

## JavaScript installation

Implicit dependency lifecycle scripts are disabled, including on npm 10. The
project .npmrc protects ordinary manual npm ci; both native initializers and the
Flatpak build also pass --ignore-scripts explicitly. Nix sets the corresponding
build environment policy and includes .npmrc in its source fileset. A caller's
unsafe npm_config_ignore_scripts=false cannot override the bootstrap CLI flag.

Unsupported allowScripts metadata is not used as a security boundary. The shared
tools/npm_policy.py validator rejects root installation hooks and unexpected
dependency hook metadata before installation. Only the locked optional macOS
fsevents install hook is recognized, and it is never executed. Vite 8 uses locked
Rolldown/Oxc and Lightning CSS native platform packages instead of esbuild.
The initializer first checks the supported Node.js runtime (22.12+, 24 or 26+),
then verifies both locked local native APIs with real TypeScript and CSS
transforms using node tools/check_frontend.mjs. Both JavaScript package versions
and the matching native platform-package versions must equal the lockfile.
External native-library overrides and WebAssembly fallbacks are refused. No npm
command shim, installation script or registry fallback is required. Missing,
mismatched or unsupported local binaries fail visibly rather than triggering a
downloader.

Explicit reviewed npm run build/check/test commands still work. This policy is
not a claim that a compiler or directly invoked build dependency is harmless:
source review, integrity-locked dependencies, current advisory gates and protected
signing custody remain separate requirements. Never put release credentials in a
generic build environment or upload an entire ignored output directory.

The real npm regression has a harmless, authored positive control proving a hook
would run when enabled, then verifies that both the explicit bootstrap flag and
the project default prevent execution. It does not execute untrusted third-party
code to perform the security scan.

## Svelte configuration merger

The latest Svelte Vite plugin still depends on vulnerable `deepmerge 4.3.1`.
The in-tree `4.3.1+tauridium.1` backport rejects prototype-control keys in both
merge loops and defines own data properties. Its verified upstream archive,
license, exact file hashes and retirement instructions are documented in
[`vendor/deepmerge/TAURIDIUM-PATCH.md`](../vendor/deepmerge/TAURIDIUM-PATCH.md).

Every frontend production build verifies the library actually resolved by the
plugin, its hashes, exploit regressions and normal configuration behavior.
Initialization and security CI also enforce the exact root-local override.
All implicit lifecycle scripts remain disabled, and registry advisory scanning
still fails at low severity. npm excludes local packages from its advisory
service; the separately enforced backport checks must not be replaced by a
clean registry audit. The daily/current dependency gate also queries npm for the
original upstream identity. It accepts only the verified backport assessment,
bound to the exact patch and a **15 November 2026** review deadline, and rejects
new or changed advisories and unavailable/malformed results. This preserves
future advisory detection for the local source. The patched build dependency is
not a shipped runtime module and does not alter service-webview permissions.

## Pinned native tooling

data/build-toolchain.json pins the official stable Tauri CLI 2.12.4 and bundler
2.10.4 crate checksums. Upstream has migrated to ZIP 9; the shared
`flatpak/prepare-tauri-cli.py` helper verifies both immutable archives, extracts
only bounded regular files and pins both ZIP dependencies to reviewed 9.1.2.
It binds the bundler as a local dependency and assigns the distinct CLI identity
`2.12.4+tauridium.1`. The exact patched lock is separately hash-pinned; it is not
represented as upstream's lock. No Cargo registry source is edited. Patch
preconditions fail closed on drift, and initialization rejects older builders.

The reviewed lock retains all prior security fixes while refreshing compatible
transitive dependencies. It includes `tokio 1.54.1`, the patched Rustls/WebPKI
stack and `zstd 0.14.3`, `zstd-safe 8.2.0`, `zstd-sys 2.1.2+zstd.1.5.7`.
These retain the fixes for the previously reviewed ZIP 8, Tokio I/O-safety,
WebPKI trust and Zstd wrapper/allocator advisories. The installed application
runtime does not contain the builder's Zstd stack. Whole-lock scanning covers
all platforms and warning kinds without new ignores or extended assessment
deadlines; native, Nix and Flatpak producers consume the same reviewed lock.

The same narrow source preparation disables RPM's OpenPGP feature and replaces
the unused signing branch with explicit credential rejection plus unsigned RPM
construction. All payload compression formats remain enabled. This removes the
OpenPGP/ML-DSA stack rather than retaining a build-only vulnerability exception.
The remaining whole-lock RSA advisory belongs to macOS certificate key generation,
not the affected decryption API; its precise expiring assessment is still printed.

Native initialization, Nix and Flatpak all use that same preparation and lock.
An unpatched CLI with the upstream version is not reused. Nix retains the
nixpkgs Tauri hook and never installs into the user's Cargo directory. Flatpak
removes cargo-tauri during final cleanup; the builder is not a runtime dependency.
This security migration can be retired after a reviewed stable upstream release
provides the fixes. Do not replace it with prerelease Tauri 3 or advisory ignores.

tools/generate_flatpak_sources.py regenerates and exactly checks the CLI's offline
source manifest as well as the application's Cargo/npm sources. A source-count or
nonempty-file check is not sufficient. Tool updates must review the new published
lock, advisories, checksums and all three producer paths together.

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
in the development environment. On Linux, `just init` can install the archive- and
executable-checksum-pinned official x64/ARM64 binary into ignored
`release/tools/minisign-VERSION-ARCH/`; later signature checks independently verify
that cache before using it. This avoids assuming Ubuntu 22.04 has a Minisign apt
package, does not require root for this tool, and never downloads signing keys.
Existing invalid caches are rejected, not overwritten. On macOS install it with
brew install minisign.
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

## Complete archive and candidate inspection

Public ZIPs support only stored and deflate compression. Validation accounts for
every physical record and independently decodes each complete compressed span,
including empty directories. Actual output, full CRC, end-of-stream and exact
compressed-byte consumption must all agree; declared sizes and `testzip()` alone
are not sufficient. Byte, record, nesting and decoder-time budgets fail closed.
Unsupported codecs are rejected, never inspected only as compressed bytes.

A source archive has one Git root and one manifest at that same root. Multiple
roots, overwritten relative inventories and ambiguous manifests are rejected.
All approved reachable history is inspected, including deleted containers. A
bounded traversal of historical trees retains evidence obligations across every
alias/rename, including nested containers: a deleted evidence ZIP/gzip containing
a renamed PNG still receives OCR without needing an outer archive named evidence.
Historical private-configuration paths are rejected just like current paths.
Raw loose/packed Git storage is validated by its own complete format, checksums
and strict native pack verification before decoded objects are inspected. Literal
ZIP bytes inside typed Git storage are not mistaken for an executable ZIP
preamble. Extra data is rejected even when outer storage hashes are recomputed.
Private full-Git checkpoints are never public input.

Flatpak candidates must satisfy the complete reviewed metadata policy at both
sealing and consumption. They also reject any `build/usr` entry, including a
dangling symlink: Flatpak would otherwise use that custom runtime instead of the
GNOME runtime named in metadata. Read-only execution does not establish runtime
identity. Candidate tests do not install over the owner's application or profile.

## Windows public-signature verification tool

The native Windows initializer checks Minisign before compiling the Tauri CLI.
Scoop and WinGet remain preferred; runners without them use the official pinned
portable ZIP with separate native x64 and ARM64 members. The policy binds the
archive and executable SHA-256 and checks the PE machine type before execution.
The archive used to establish these pins was verified against the existing
upstream publisher key. Later cache discovery rechecks regular-file, reparse,
checksum and architecture constraints; damaged caches are rejected and preserved.

The cache is ignored build tooling, never an application runtime payload.
`tools/minisign.ps1 -Portable` selects this path explicitly. `-NoSystemChanges`
forbids fetching a missing tool while allowing an already verified cache.
Real Windows x64/ARM64 jobs exercise missing-tool refusal, installation, reuse,
fresh-process discovery and synthetic signature/tampering controls. Their result
explicitly gates the required Windows native check; a dependency skip cannot make
the required check pass. Release builders run the same check before compilation.
The protected Linux signer and owner signing-secret boundaries remain unchanged.
