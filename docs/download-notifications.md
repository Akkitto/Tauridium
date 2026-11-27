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

## Show in folder

Each individual completed download with a known destination offers **Show in folder**.
It opens the system file manager at the containing folder and selects the file where
supported. It never opens or executes the downloaded file. On Windows this uses the
native Explorer selection API. Linux uses FileManager1; Flatpak uses the desktop
portal's file-descriptor-based OpenDirectory request without additional sandbox
permissions. macOS uses Finder's reveal action.

The button works with **Filename only**: enabling it does not display the full path.
Only the current download's numeric notification ID crosses the command boundary;
the destination stays in the bounded native queue, is never persisted as download
history, and is removed when dismissed, cleared or folded into an overflow summary.
Unknown destinations and multi-download summaries have no reveal button.

Revealing keeps the notification available. The timer pauses during the request,
and repeated clicks are blocked while it is pending. If the file has been moved or
deleted, the toast explains this and remains available to dismiss or retry. A
cancelled portal request is neutral. If no compatible file manager/portal is
available, the toast offers a clear error; Tauridium does not open the downloaded
file as a fallback. Some portal backends open the containing folder without
selecting a file. The opt-in notification setting remains off by default.

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
callbacks, privacy changes, pauseable timer cleanup, native-only reveal identity,
metadata-only portal descriptors, and private-bus selection/cancellation/error handling. The opt-in
`just test-download-toast` additionally exercises real native downloads and
visible notifications in an isolated X11 production-app session; it needs Xvfb,
xdotool, ImageMagick, Tesseract, Thunar, xclip and GIO. The supplied Nix fixture
also verifies that the actual downloaded file is selected in its parent folder
and that moving it produces a recoverable error. It does not access real service accounts or
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
and its WebView2 download/Explorer selection and moved-file smoke check.

The isolated Xvfb test selects X11/software rendering and disables WebKit's
DMA-BUF renderer only for its child processes: Xvfb has no real GPU buffers, and
that renderer can leave dynamically resized child views unpainted. It never
disables the WebKit sandbox or TLS checks. Installed Tauridium retains the user's
normal rendering environment; this smoke is not GPU/Wayland validation.

Native integration references: [Explorer selection](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shopenfolderandselectitems),
[FileManager1](https://www.freedesktop.org/wiki/Specifications/file-manager-interface/),
and [OpenDirectory portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.OpenURI.html).
