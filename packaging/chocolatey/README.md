# Local Chocolatey package

Tauridium provides a self-contained `tauridium` Chocolatey package for Windows
x64 and ARM64 (Windows 10 version 1709 or newer, including Windows 11). It is prepared from the application's repository and installed
from a local folder. No Chocolatey Community Repository submission, API key,
account or hosted feed is required. GitHub repository URLs are source/download
locations; the folder containing the generated `.nupkg` is the Chocolatey source.

## Build and install

Use a reviewed checkout, Chocolatey, Python and `just` on Windows. Native commands
work with Windows PowerShell 5.1 and PowerShell 7; WSL is not required.

```powershell
just chocolatey-pack 1.0.12
# Review the package and scripts before this elevated installation:
choco install tauridium --version 1.0.12 --source "$PWD\release\chocolatey\packages"
```

The recipe fetches both official MSI/signature pairs from fixed version-specific
GitHub release URLs, checks their exact sizes/SHA-256 and publisher signatures
using the pinned native Minisign verifier, then prepares an allowlisted staging
tree. It invokes actual `choco pack`, verifies its payload and NuGet identity,
and normalizes ZIP timestamps, generated NuGet identifiers and host/tool stamps.
Repeat generation must produce identical bytes or fails while preserving the
existing output. Only the two MSIs, their public signatures, fixed install/removal
scripts, release metadata, license and verification notes are packaged. No
producer Git, profiles, credentials, caches or logs enter the package.

The generated package includes both architectures and selects the actual native
Windows architecture through `IsWow64Process2`, including under emulated
Chocolatey/PowerShell. Runtime-information helpers alone can report the emulated
x64 view on ARM64. x86 and forced-x86
requests fail. Embedded bytes, MSI architecture, version, manufacturer, upgrade
family and machine installation scope are checked before installation. There
are no package-source dependencies; WebView2 still has to be present or provided
by the native installer's Microsoft bootstrap. An entirely offline operating
system without WebView2 is not claimed supported.

Normal package use does not require Minisign/Python/just; those are preparation
tools. A copied package is executable installation code: verify its provenance
and inspect its source before trusting it with administrator rights. SHA-256
inside a modified package alone cannot authenticate its publisher. The embedded
MSI signatures are Tauridium updater signatures, not Windows Authenticode.

## Upgrade and remove

Keep the old and new generated packages in the same local source folder:

```powershell
choco upgrade tauridium --version NEW_VERSION --source C:\Packages
choco uninstall tauridium
```

Quit Tauridium, including its tray process, before either operation. Package
scripts refuse running instances and never kill them. Installation is
machine-wide, and the application is not launched elevated by the installer.
Scope, launch and reboot arguments are owned by the package. Custom installer
arguments, global argument overrides and package parameters are refused before
MSI execution. If a command fails, correct the cause and retry from the reviewed
local package; the installed application and its data are preserved.
A conflicting per-user NSIS installation must be removed using its own
uninstaller first; preserve your application data. Package scripts do not migrate
or delete an unrelated installation, user profile, sessions, backups, credentials
or the shared WebView2 runtime.

Tauridium's native updater remains available. Chocolatey Community does not
promise automatic synchronization of its recorded package version after a
self-update. A matching/newer local package reconciles that version through
`choco upgrade`; installing an older package over a newer MSI is refused.
Removal identifies only the verified machine-wide Tauridium MSI upgrade family,
so a legitimate MSI self-update changing its ProductCode remains removable.
Multiple or conflicting registrations fail for manual review.

## New release intake

After the ordinary protected release is public:

```text
just chocolatey-intake VERSION COMMIT RELEASE_RUN_ID
```

The command resolves the immutable tag and checks the exact successful protected
release workflow. It verifies both architecture MSI/signature pairs before
writing a new review candidate in `release/chocolatey/candidates/`. Review and
commit it as `packaging/chocolatey/releases/VERSION.json`; do not replace an
existing lock or public release asset silently. Then run the normal pack recipe.
Preparation and cryptographic verification also run on Linux through
`just chocolatey-prepare VERSION`; creating/testing actual `.nupkg` requires
Windows and Chocolatey.

## Acceptance and publication boundary

`tools/test_chocolatey_install.ps1` is restricted to disposable GitHub-hosted
Windows runners. It exercises real pack/repack, native MSI install, actual
previous-release upgrade, native MSI updater path followed by Chocolatey
reconciliation, repeated installation, responsive production GUI, safe
running-process/conflicting-registration rejection, removal/reinstallation,
architecture/version probes and synthetic data preservation. Both native x64
and ARM64 must pass. Package contents are scanned as decoded data, including
embedded MSIs, by the existing pinned artifact security gate. Raw profiles,
screenshots and logs are not uploaded.

CI and release preflight require those keyless checks. The `.nupkg` output is a
local package and short-lived workflow artifact, separate from the existing
strict public application asset inventory. Nothing is submitted upstream or
published to a Chocolatey feed by any of these commands. A hosted feed and future
community submission remain separate work.

Official references: [package creation](https://docs.chocolatey.org/en-us/create/create-packages/),
[embedded installer helper](https://docs.chocolatey.org/en-us/create/functions/install-chocolateyinstallpackage/),
[uninstall helper](https://docs.chocolatey.org/en-us/create/functions/uninstall-chocolateypackage/).

Native-machine API reference: [Microsoft IsWow64Process2](https://learn.microsoft.com/en-us/windows/win32/api/wow64apiset/nf-wow64apiset-iswow64process2).
