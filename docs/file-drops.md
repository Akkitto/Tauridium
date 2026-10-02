# File drops into services

Drop files onto the service's own attachment area, message composer, upload target, or
file input. Tauridium lets the native browser deliver the original files to the page,
including multiple files and filenames with spaces or non-ASCII characters. The service
controls accepted file types, attachment limits, and whether a particular area accepts drops.

### Linux engine limitation

WebKitGTK currently has an open upstream regression where an operating-system file drop
arrives with an empty `DataTransfer.files` list. This was reproduced with WebKitGTK 2.52.6
in the Tauridium production build. Disabling Tauri's interception cannot repair that engine
behavior. See [WebKit bug 323277](https://bugs.webkit.org/show_bug.cgi?id=323277) and
[the proposed upstream fix](https://github.com/WebKit/WebKit/pull/73114).

On affected Linux systems, use the service's attachment button and file picker. Do not
downgrade WebKit or disable its security protections to restore drops. The native-drop
smoke test deliberately fails when files are missing; a successful build does not prove
file uploads work.

On Windows, run Tauridium with normal user privileges, as you would File Explorer.
Windows blocks drag-and-drop from ordinary applications into an elevated application.

## Reproducible checks

Serve the tracked fixture with `python3 -m http.server 8765 --bind 127.0.0.1 --directory tools/fixtures`
(on Windows, use `py -3` in place of `python3`). Add a Custom Website service with URL
`http://127.0.0.1:8765/file-drop.html`. The fixture displays filenames and sizes and reads
the actual bytes delivered by the browser. Its POST report endpoint is used only by the
automated harness.

Check a single file, multiple files, a zero-byte file, a binary file, and a filename with
spaces and non-ASCII characters. Test both the green drop zone and native file input,
then repeat after switching services, reloading, and restarting Tauridium. Repeat at
50%, 100%, and 200% service zoom. In Proton Mail, repeat in an open draft and verify the
attachment names and downloaded contents without sending the message.

The opt-in Linux production-app test is `just test-file-drop`. It requires an isolated
X11 display at least 1600×1000 (for example Xvfb), `xdotool`, and Python GTK3 bindings.
It creates temporary local profiles and files, performs real OS drags, and checks trusted
DOM events, original names, sizes, and content hashes. It covers multiple services,
preloading, zoom, reloads, restart, cancellation, and native file inputs. It does not
access the user's Tauridium profile or require third-party credentials.
