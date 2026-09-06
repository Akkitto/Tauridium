# Installation

## Windows

Tauridium publishes native Windows installers and portable ZIP archives for x64 and ARM64.

### Scoop

The Tauridium repository is prepared for submission to the official
[Scoop Extras](https://github.com/ScoopInstaller/Extras) bucket. After the manifest has been
accepted upstream, installation is:

```powershell
scoop bucket add extras
scoop install tauridium
```

Until upstream acceptance, use the Windows installer or portable ZIP from
[GitHub Releases](https://github.com/Akkitto/Tauridium/releases/latest).

Release assets use stable names:

```text
tauridium-X.Y.Z-windows-x64-portable.zip
tauridium-X.Y.Z-windows-arm64-portable.zip
```

Each portable ZIP contains only `tauridium.exe`. The release also publishes a SHA-256 sidecar
for each portable ZIP, a combined `SHA256SUMS`, and a generated submission-ready Scoop manifest.

### Repeated launches and the existing application session

On Windows, Tauridium intentionally allows one durable application instance per logged-in desktop
session. Starting `tauridium.exe` again does not create another Tauridium window, service session,
or tray process. The short-lived secondary launch sends its activation context to the already
running primary process, waits for acknowledgement, and exits; the primary window is shown and
restored when necessary.

The coordination is crash-safe and startup-race-safe. If a second launch arrives before the
primary UI is ready, the activation is queued by the primary process. If the primary process has
terminated, Windows releases/abandons the operating-system ownership object so a later launch can
become the new primary. Tauridium does not use PID files, process-name scans, window-title matching,
or duplicate-process killing for instance ownership.

Launch arguments and the secondary process working directory are forwarded with the activation
request so the existing process receives the original launch context. Windows foreground
permission is transferred to the primary when the operating system permits it. The primary then uses
Windows' foreground API directly and respects refusal rather than using synthetic keyboard-input focus
workarounds; Windows remains in control of final foreground policy.

### Startup diagnostics

Normal Tauridium launches remain silent. For startup, tray-restoration, or repeated-launch debugging, run:

```powershell
.\tauridium.exe --startup-diagnostics
```

When possible, the release GUI-subsystem executable attaches to the invoking Windows console and
prints structured initialization/activation events there. The same events are persisted under:

```text
%LOCALAPPDATA%\Tauridium\diagnostics\startup-<timestamp>-<pid>.log
```

If another Tauridium instance is already running, the diagnostic secondary forwards this log path
through the session-local activation pipe. The existing primary appends its own window visibility,
minimized state, native restore/show fallback, foreground result, activation completion, and
acknowledgement events to the same file. After the primary has actually completed activation, the
secondary replays those primary-side lines to its console before exiting. Failed primary activation is
explicitly rejected rather than acknowledged, and pipe connection/wait retries include the Windows OS
error in diagnostics. This makes tray-only UI failures distinguishable from activation-transport failures
even when the original primary was started normally without a console.

Diagnostics intentionally record argument counts rather than command-line values and do not dump the
process environment, cookies, tokens, passwords, or other application credentials. A forwarded log
path is accepted only when it is a Tauridium `startup-*.log` file directly inside Tauridium's own
local diagnostics directory.

### Microsoft Edge WebView2 Runtime

Tauridium uses Tauri's native Windows WebView and therefore requires the Microsoft Edge WebView2
Runtime. Windows 11 and supported modern Windows 10 releases normally provide the Evergreen
runtime with the operating system. Tauridium deliberately does not bundle a fixed WebView2
runtime in its portable package so WebView2 remains serviced through Microsoft's normal update
mechanism.

If WebView2 has been removed from a Windows installation, install the current Evergreen WebView2
Runtime from Microsoft before starting Tauridium.

References:

- <https://v2.tauri.app/distribute/windows-installer/>
- <https://developer.microsoft.com/en-us/microsoft-edge/webview2/>

### Application data and Scoop upgrades

Tauridium does not store persistent user state beside `tauridium.exe`. Persistent settings,
services, workspaces, backups metadata, recipes, icon caches, audit data, and related application
state use Tauri's application-specific data/config directories. With the production identifier
`dev.brani.tauridium`, Windows resolves those locations below the current user's standard
application-data directories rather than the Scoop version directory.

Consequently, the official Scoop manifest intentionally has no `persist` entry: replacing
`~/scoop/apps/tauridium/<version>` during an upgrade does not replace Tauridium's user data.
Release CI tests install, update, uninstall, and reinstall the portable package with Scoop while
verifying that an external application-data marker survives.

Tauri path reference: <https://v2.tauri.app/reference/javascript/api/namespacepath/>

## Linux

Download the package matching the system architecture from
[GitHub Releases](https://github.com/Akkitto/Tauridium/releases/latest):

- DEB for Debian-based distributions
- RPM for RPM-based distributions
- AppImage for portable use

## Release integrity

Published release assets are immutable by version and are accompanied by `SHA256SUMS`. Verify the
hash of a downloaded asset before installation when release integrity needs to be checked manually.
