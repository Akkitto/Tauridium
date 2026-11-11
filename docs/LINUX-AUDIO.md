# Linux audio and AppImage packaging

Tauridium 1.0.8 includes the GStreamer media framework, notification-audio
plugins and plugin scanner in its Linux x64 and ARM64 AppImages. WebKit needs
loadable plugins such as `appsrc` and `autoaudiosink`; shared libraries alone
are insufficient and can cause the service renderer to abort when audio starts.

The AppImage config enables Tauri's `bundleMediaFramework`. The existing
checksum-pinned Tauri bundler 2.10.4 embeds its media deployment script inside
the verified crate. This change introduces no floating media-script download.
The runtime hook uses the bundled plugin directory and scanner rather than
depending on a matching host GStreamer installation.

For development, run `just init`. Linux setup probes actual GStreamer factories,
including WAV/Ogg decoding and an available audio output backend. A host with
all development libraries but missing audio plugins is detected and repaired
through its supported package manager. Probes use a temporary registry and
respect distribution/Nix plugin locations. In `nix develop`, missing prerequisites
remain a Nix environment error; initialization does not install host packages.
The Nix package and Flatpak retain their existing media/runtime integration.

For an AppImage-only build and an account-free playback check:

```text
just bundle-appimage x86_64-unknown-linux-gnu
just appimage-audio x86_64-unknown-linux-gnu
```

Use `aarch64-unknown-linux-gnu` on a native ARM64 build machine. Official Linux
AppImages are built on Ubuntu 22.04, retaining the existing glibc compatibility
baseline. The test additionally needs `xvfb`, `xauth`, `pulseaudio`,
`pulseaudio-utils`, `dbus` and GStreamer's command-line tools. These test tools
are supplied explicitly by CI; they are not prerequisites for using the AppImage.

The production test opens a synthetic local service in an isolated display,
D-Bus session and temporary profile. It verifies bundled plugin/scanner ELF
architecture and confined lookup, plays generated WAV and Ogg notification
audio and a WebAudio oscillator, then measures actual PCM samples from its own
private PulseAudio null sink. Silence between phases and repeated playback are
required. The test uses no accounts, messages, existing audio server or real
speaker, changes no user audio configuration, and rejects signing credentials.
Its logs and profiles are private test evidence, excluded from public archives.

Both native architectures run this test before release signing. Windows keeps
its existing WebView2 media path. Service permissions, muting, autoplay policy
and application UI are unchanged. Codec support still depends on the supplied
GStreamer plugins and service/browser capabilities; this fix does not assert
that every calling protocol or DRM format is supported.

The missing-plugin diagnosis was reported in
[PR #25](https://github.com/Akkitto/Tauridium/pull/25). Its separate service
context-menu proposal is outside this audio patch.

References:

- [Tauri AppImage multimedia support](https://tauri.app/distribute/appimage/)
- [GStreamer tools and plugin search paths](https://gstreamer.freedesktop.org/documentation/tools/gst-launch.html)
- [Pinned bundler source](https://docs.rs/crate/tauri-bundler/2.10.4/source/src/bundle/linux/appimage/linuxdeploy.rs)
