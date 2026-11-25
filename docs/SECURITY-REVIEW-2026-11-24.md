# Dependency review: support information

The support-information action adds pinned **arboard 3.7.0**, with default image
features disabled, on Windows and macOS only. Linux reuses GTK's normal clipboard
selection on X11 and Wayland. The renderer receives two argument-free, main-only
support commands; no generic clipboard permission or clipboard-read API is added.
Only the native allowlisted report can be copied.

The application lock adds six package records: arboard 3.7.0, clipboard-win 5.4.3,
error-code 3.4.0, gethostname 1.1.0, x11rb 0.13.2 and x11rb-protocol 0.13.2.
No existing package version, source or checksum changes. An unrelated automatic
cssparser-macros dependency selection was restored to the existing syn 2.0.119.
The existing objc2-app-kit record gains the required objc2-core-graphics feature
edge for arboard's macOS platform bindings. Existing vault, notification and
assessed maintenance-warning parents retain their dependency records.

Application lock SHA-256: `8aa03df4d41d3ab77716f8e8c5800f89d2aff3bbc8484cfd22dff0d1ed147bec`.
Builder lock remains `bbc1542eebc53c9deac34dfa6d519af653e7030ad9469f49f145592238aafba6`.

The current online gate passed at `2026-11-24T22:37:16.952845+00:00` against
official RustSec database `10db6998b5d74ec438bcf0763125bd425a068a8f`.
It scanned both complete locks without target/severity filtering or advisory
ignores. The application has **zero known vulnerabilities** and five existing
explicit maintenance assessments. The SDK retains its one previously assessed RSA
advisory under enforced key-free builder controls and five existing total explicit
assessments. No new assessment or expiry extension was introduced; the existing
30 November 2026 review deadline remains enforced.

The exact-lock application binding is updated only for this reviewed delta.
Unknown findings, unsoundness, package/version/kind scope, source-integrity checks
and assessment expiry continue to fail closed.

References: [arboard platform behavior](https://docs.rs/arboard/3.7.0/arboard/struct.Clipboard.html),
[GTK text selection](https://docs.gtk.org/gtk3/method.Clipboard.set_text.html),
[WebView2 runtime version and channel names](https://learn.microsoft.com/en-us/microsoft-edge/webview2/reference/win32/webview2-idl).
