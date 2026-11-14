# Arch Linux packaging (local, unpublished)

Tauridium supports local Arch packages directly from this Git repository. Nothing
here registers or submits a package to AUR, hosts a pacman repository, creates an
account, publishes binaries, or installs anything automatically. AUR hosts recipes;
a custom pacman repository hosts built packages. These are different operations.

## Install directly from a checkout

Use an up-to-date Arch Linux x86_64 system and an ordinary user account. Install
`base-devel`, `git`, `python` and `namcap` using pacman first. Review the checkout
and recipe before executing it. No `just init`, Tauri CLI, signing key, WSL or AUR
account is needed for this source-package path.

```sh
git clone https://github.com/Akkitto/Tauridium.git
cd Tauridium
# Select a reviewed commit or a release tag containing this packaging support.
python3 tools/aur.py prepare
```

The command prints a directory under `release/aur/<commit>/tauridium`. Enter that
printed directory, review `PKGBUILD`, then run:

```sh
makepkg --verifysource
makepkg --printsrcinfo > .SRCINFO
namcap PKGBUILD
makepkg --syncdeps --install
```

`makepkg` requests elevation only for package dependencies and final pacman
installation. Never run makepkg itself as root. The output is a normal
`tauridium-*.pkg.tar.zst`; pacman owns the executable and desktop integration.
Source fetching follows Cargo/npm lockfiles; npm lifecycle scripts stay disabled.
Production compilation uses the system `rust` (at least the project's MSRV),
GTK/WebKitGTK and GStreamer packages, without invoking Tauri's installer bundler.

Preparation accepts only a clean commit and exports an explicit allowlist of
tracked build inputs. Git history/configuration, ignored files, credentials,
profiles, build caches and private evidence are excluded. A source snapshot is
bound to its full commit and SHA-256 in `SOURCE.json`. Untagged snapshots use
`pkgrel=0.1`; exact version tags use `pkgrel=1`. Preserve the preparation directory;
reruns require a fresh output (`--output PATH`) rather than overwriting it.

Only x86_64 is advertised. Linux ARM64 release payloads alone do not establish
Arch Linux ARM compatibility; validate that separately before expanding `arch`.
Arch derivatives are subject to their own dependency/repository compatibility.

## Install a verified binary payload

Starting with the packaging release, GitHub releases provide separate
`tauridium-X.Y.Z-linux-x64-system.zip` and ARM64 system-package payloads. They are
production builds with no native updater plugin or update commands. Standard
AppImages and native Windows releases retain their existing updater behaviour.
Do not substitute an ordinary runtime ZIP, DEB or AppImage for a managed payload.

Download the system ZIP for the checkout's version from the exact stable GitHub
release. Verify its SHA-256 against that release's `SHA256SUMS`, and verify its
GitHub artifact attestation against `Akkitto/Tauridium` and the protected release
workflow before preparing it. Hashes alone do not establish publisher identity.
Never treat an archive's self-reported metadata as proof of authenticity.

```sh
gh attestation verify /path/to/tauridium-X.Y.Z-linux-x64-system.zip --repo Akkitto/Tauridium
python3 tools/aur.py prepare-bin /path/to/tauridium-X.Y.Z-linux-x64-system.zip
```

Enter the printed `tauridium-bin` directory, review `PKGBUILD`, generate
`.SRCINFO` and run `makepkg --syncdeps --install` as above. The recipe uses a local
copy with an exact checksum, so neither an AUR account nor an upstream submission
is required. It declares `provides=tauridium` and conflicts with the source
package; it does not replace unrelated packages or install both variants.
The adapter never executes downloaded content. It rejects wrong targets,
versions, production/distribution policy, changed binary digests, unexpected
members and unsafe archive paths. Official release producers additionally probe
the trusted executable before exporting it.

For a future AUR submission, use independently verified, version-specific HTTPS
release sources and checksums; add maintainer ownership, a recipe licence, and a
fresh `makepkg --printsrcinfo`. Check name ownership/duplicates and current AUR
rules. Do not upload local source archives, binary packages or private evidence.
The current local recipe intentionally makes no registry-availability claim.

## Updates and removal

These builds show “Managed by your package manager” in Settings. Native update
checks/install commands are compiled out; no attempt is made to invoke pacman
from Tauridium. For direct-checkout installs, fetch/select the next reviewed
release, prepare/build it again and install the resulting package through pacman.
An AUR helper cannot discover this package until a recipe is actually submitted.

Use `sudo pacman -R tauridium` (or `tauridium-bin`) to remove an installed package.
No install/remove hooks delete user profiles, sessions, credentials or backups.
Application identity remains `dev.brani.tauridium`. Existing native user data is
reused; package removal and reinstall preserve it. Stop the running application
before switching package variants or testing upgrade behaviour.

## Optional owner-operated pacman repository

A custom binary repository is optional: direct checkout installation above is
fully supported. To host one later, build reviewed `.pkg.tar.zst` files on Arch,
sign each package with a dedicated owner-controlled OpenPGP package-signing key,
and create/update the database with `repo-add --sign --key KEYID`.
Host packages, detached signatures, database and database signature over HTTPS.
Distribute and verify the public-key fingerprint independently; clients should
require package/database signatures. Never disable `SigLevel` or bundle private
keys. Tauri's Minisign updater key is a different signing system and must not be
reused. This task does not provision a key, hosting, repository configuration or
publication; no pretend install URL is advertised.

## Maintainer gates

```sh
just aur-prepare
just aur-validate /path/to/prepared/directory
just system-package x86_64-unknown-linux-gnu
just aur-prepare-bin /path/to/tauridium-X.Y.Z-linux-x64-system.zip
```

Run actual makepkg builds, `namcap` on recipes/packages, clean Arch install,
upgrade, removal/reinstall, dependency/desktop checks and isolated WebKit/media
smoke tests. The production build probe verifies distribution policy and target;
it does not prove all desktop environments work. Keep `.SRCINFO` generated by
makepkg. Retest package dependencies when Arch rolls forward. Do not run a
Windows/Flatpak/Nix release under an Arch identity to bypass missing validation.

Primary references: [AUR rules](https://wiki.archlinux.org/title/AUR_submission_guidelines),
[PKGBUILD](https://man.archlinux.org/man/PKGBUILD.5.en),
[custom repositories](https://wiki.archlinux.org/title/Pacman/Tips_and_tricks#Custom_local_repository).
