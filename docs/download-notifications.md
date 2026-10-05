# Download completion notifications

In **Settings → Advanced → Downloads**, enable **Show download completion toasts**
to receive a notification at the bottom of Tauridium's window after each successful
website download. This global setting is **off by default**, including after upgrades,
and applies to every service and workspace.

Cancelled or failed downloads do not produce success toasts. Downloads that use a
Save dialog are included once they finish, as are automatically saved downloads.
Existing system notifications and destination selection are unchanged; this option
controls only Tauridium's in-window toasts, not updater or recipe downloads.

## Location details

- **Filename only** (default): display the downloaded filename without its local path.
- **Destination folder name**: add the final folder name, such as `Reports`.
- **Full file path**: add the complete destination supplied by the native download engine.
- **Partial file path**: add the filename and the nearest **1–10 parent folders**.
  The default is two: `…/Downloads/Reports/example.pdf` or
  `…\Downloads\Reports\example.pdf`. The ellipsis marks omitted ancestors;
  short paths that already fit are shown without inventing missing folders.

The settings include an example preview using fictional paths. Full and partial
paths can disclose local names to anyone viewing your screen. No destination is
invented if the engine reports a successful download without a path.

## Timing and interaction

Choose **8 seconds** (default), **15 seconds**, **30 seconds**, or **Until dismissed**.
The timer pauses while you hover over or keyboard-focus the toast, or when Tauridium
loses foreground focus. The notification never takes focus automatically. Use its
labelled dismiss button, or Escape while the notification has keyboard focus.

Multiple downloads queue rather than replacing one another. A waiting count is
shown. Extremely large bursts are bounded to 100 pending entries and combine the
overflow into an accurately counted summary without showing a misleading filename
or destination. Disabling the setting clears pending toasts. Changing location
detail removes old location text from queued toasts while preserving their filenames;
new downloads use the newly saved preference.

Notifications use the selected light/dark/OLED/system theme, remain inside the
window when resized, and support selectable, wrapped/scrollable long filenames
and paths. Settings persist across restarts and are preserved by full backups;
portable service/workspace exports do not include global preferences or local paths.

## Security and regression checks

The toast renders in a separate local Tauridium child webview, not inside a hosted
service. Local paths are never injected into website JavaScript, sent to the
Ferdium server, included in broadcast events, or read from disk for display.
Notification events target only that local renderer; remote service IPC remains
closed. Text is escaped, control/directional-spoofing characters are sanitized,
and navigation/popups are restricted.

`just test` covers settings migration and validation, backup preservation,
Unix/Windows/UNC paths, Unicode, unknown destinations, queue bounds and stale
callbacks, privacy changes, and pauseable timer cleanup. The opt-in
`just test-download-toast` additionally exercises real native downloads and
visible notifications in an isolated X11 production-app session; it needs Xvfb,
xdotool, ImageMagick and Tesseract. It does not access real service accounts or
the user's existing profile.

For a fully supplied headless environment, including a private D-Bus session per
temporary profile, run:

```sh
nix --extra-experimental-features 'nix-command flakes' run .#download-toast-smoke
```

This builds and tests the locked Nix production package. Linux CI runs this on
both supported architectures. Evidence goes to
`release/evidence/download-toast-smoke`; `-- --case filename` runs one case while
diagnosing a failure. Native Windows releases still require the Windows pipeline
and a WebView2 file-download smoke check.

The isolated Xvfb test selects X11/software rendering and disables WebKit's
DMA-BUF renderer only for its child processes: Xvfb has no real GPU buffers, and
that renderer can leave dynamically resized child views unpainted. It never
disables the WebKit sandbox or TLS checks. Installed Tauridium retains the user's
normal rendering environment; this smoke is not GPU/Wayland validation.
