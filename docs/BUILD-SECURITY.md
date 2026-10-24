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
initializer verifies its locked local API and performs a real native transform
with node tools/check_esbuild.mjs. No npm command shim, installation script or
registry fallback is required. Missing, mismatched or unsupported local binaries
fail visibly rather than triggering a downloader.

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

data/build-toolchain.json pins the official stable Tauri CLI 2.12.3 and bundler
2.10.3 crate checksums. Upstream still requires ZIP 8, which is affected by
RUSTSEC-2026-0367/0368/0369. The shared `flatpak/prepare-tauri-cli.py` helper
verifies both immutable archives, extracts only bounded regular files, and
narrowly changes both ZIP requirements to 9.0.4. It binds the bundler as a local
dependency and assigns the distinct CLI identity `2.12.3+tauridium.2`. The exact
patched lock is separately hash-pinned; it is not represented as upstream's lock.
No Cargo registry source is edited. Patch preconditions fail closed on drift.

The second build revision also locks `rustls-webpki 0.103.16`,
`webpki-roots 1.0.10` and `webpki-root-certs 1.0.10`, fixing
[RUSTSEC-2026-0382](https://rustsec.org/advisories/RUSTSEC-2026-0382.html),
[RUSTSEC-2026-0381](https://rustsec.org/advisories/RUSTSEC-2026-0381.html) and
[RUSTSEC-2026-0383](https://rustsec.org/advisories/RUSTSEC-2026-0383.html).
Its distinct identity forces initialization to replace the earlier builder;
native, Nix and Flatpak producers all consume the same reviewed lock.
Both application and builder also use `tokio 1.53.3`, fixing the I/O-safety
finding [RUSTSEC-2026-0386](https://rustsec.org/advisories/RUSTSEC-2026-0386.html)
without selecting the separately affected Tokio 1.54.0 release.

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
