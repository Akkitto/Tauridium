# Nix and NixOS

Tauridium 0.9.0 includes a locked, source-built Nix flake for x86_64-linux and
aarch64-linux. This is the project's package, **not a claim of acceptance into
nixpkgs**. Windows uses the existing native/Scoop workflows; do not install Nix
or WSL merely to develop Tauridium on Windows.

## Try, install, update and remove

After the release tag has been pushed, try the immutable release:

```sh
nix --extra-experimental-features 'nix-command flakes' run github:Akkitto/Tauridium/v0.9.1
```

Install in your profile for a stable desktop launcher and session autostart:

```sh
nix --extra-experimental-features 'nix-command flakes' profile add github:Akkitto/Tauridium/v0.9.1#tauridium
nix profile list
```

Tagged references are intentionally immutable: upgrading a profile pinned to
v0.9.1 cannot discover a newer tag. Replace that reference when choosing the next
release. For automatic tracking of the development branch, use
`github:Akkitto/Tauridium/master#tauridium` instead, understanding that it follows
unreleased commits; `nix profile upgrade <name>` then updates it. Obtain the exact
entry name from `nix profile list`. `nix profile remove <name>` removes the package
but not application data. Disable autostart before uninstalling. These profile
commands use current Nix's `add`/`remove` interface; older Nix versions may use
`install`. Use Nix 2.35 or later for the documented profile commands.

On non-NixOS Linux, install/configure Nix's host desktop/OpenGL integration using
your distribution's supported approach. A source build does not turn a Linux ZIP
or AppImage into a NixOS package. Use the wrapped Nix executable, not the unwrapped
ELF inside the store. The flake does not change your Nix daemon configuration.

## Declarative NixOS and Home Manager

Add the input to your configuration flake (and commit its generated flake.lock):

```nix
inputs.tauridium.url = "github:Akkitto/Tauridium/v0.9.1";
```

In a NixOS module where the input is passed through `specialArgs`:

```nix
{ pkgs, tauridium, ... }:
{
  environment.systemPackages = [ tauridium.packages.${pkgs.stdenv.hostPlatform.system}.default ];
}
```

Pass it from your configuration's `outputs = { nixpkgs, tauridium, ... }: ...`:
`specialArgs = { inherit tauridium; };`. For Home Manager, use the same package
expression in `home.packages` and pass `tauridium` through `extraSpecialArgs`.
An overlay is also available: `nixpkgs.overlays = [ tauridium.overlays.default ];`
then `environment.systemPackages = [ pkgs.tauridium ];` (or `home.packages`). Do
not assume stock nixpkgs already contains this package. The overlay retains the
flake's tested dependency/compiler lock rather than picking an older channel's
compiler below Tauridium's MSRV. It does not require following your system's
nixpkgs input. Keep the Tauridium lockfile when updating the configuration.

Use your normal desktop/session configuration, D-Bus, audio and graphics drivers.
No system service or root GUI is necessary. If screen sharing/file dialogs need
desktop portals, configure the portal backend appropriate to your desktop using
NixOS `xdg.portal`; the package does not choose conflicting desktop-wide backends.
Tray availability depends on your desktop's StatusNotifier/AppIndicator support.

Update the Tauridium input reference and lockfile, then use your normal
`nixos-rebuild switch`/`home-manager switch`. Review changes before activation.
Nix generations provide package rollback; keep backups of application data too.

## Distribution behavior and migration

- Nix builds disable the native self-updater at compile time. Updates settings
  show “Managed by Nix”. The package never tries to modify its store executable.
- This is not a Flatpak sandbox. Ordinary dialogs, notifications, downloads,
  sessions, backups, shortcuts and tray behavior remain native Linux behavior.
- Data stays in Tauridium's existing user XDG locations (`dev.brani.tauridium`),
  not in the store. Export/back up before changing distribution; no app data is
  deleted by install, update or uninstall. Flatpak data may live in its sandbox
  directory; use portable exports/backups to migrate rather than moving files
  blindly or sharing a live profile between running instances.
- Nix autostart writes only an owned
  `$XDG_CONFIG_HOME/autostart/dev.brani.tauridium.desktop` (default
  `~/.config/autostart/`). It uses `Exec=tauridium` and honors the saved
  start-minimized setting. It does not persist a store path that can disappear
  after garbage collection. Install into a profile/system configuration first;
  transient `nix run` alone does not make the command available next login.
- Disable previous native autostart before enabling Nix autostart: the old
  `tauridium.desktop` is not deleted automatically. Custom files, symlinks and
  Home Manager-managed entries are rejected by the app's toggle with guidance.
  To manage autostart declaratively, create the same desktop entry via Home
  Manager's `xdg.configFile` and control it in the configuration instead of the
  app. Keep `Exec=tauridium` and `TryExec=tauridium`; don't hard-code an unwrapped
  store executable.
- Native file drag-and-drop depends on WebKitGTK. Packaging does not claim to
  fix upstream WebKit bug 323277. Tauridium's Linux file-chooser fallback remains
  available; see the drag-and-drop documentation for its limitations.

## Build and develop from this repository

```sh
just nix-build
just nix-check
just nix-smoke
just nix-nixos-test
just nix-dev
# Inside the shell:
just init
just ci
```

All Nix recipes opt into flakes explicitly. `nix develop` provides Rust 1.97.1
with exact rustfmt/clippy and Node 24, GTK3/WebKitGTK 4.1 and project tools. Entering
the shell does not download node_modules or change global toolchains. `just init`
verifies those tools, then installs locked JS dependencies and audits them. The
source derivation uses nixpkgs Rust (currently 1.98.1, above the 1.97.1 MSRV); the
exact developer formatter remains 1.97.1. No default Windows command needs Nix.

The package uses fixed-output Cargo/npm fetches and an explicit source fileset;
node_modules, target, `.git`, release assets and local credentials are excluded.
It preserves the vendored Tauri/Wry patches and builds a production custom
protocol frontend offline. `wrapGAppsHook3` supplies GTK3/WebKit/GIO/GStreamer,
tray-library and external URL launcher paths. No global WebKit sandbox/TLS
disabling workaround is installed.

`nix-check` builds/tests the package, metadata and runtime build identity.
`nix-smoke` launches the actual wrapped application in private D-Bus/Xvfb and XDG
directories, retaining a screenshot, OCR text and build information under ignored
`release/evidence/nix-smoke`. It does not use your accounts or app profile.
`nix-nixos-test` installs the package declaratively in an isolated NixOS VM and
runs that graphical smoke as an ordinary user. It permits software emulation
without KVM, which is slower; it never activates a host NixOS configuration.
CI runs native builds/smokes for both architectures and a NixOS VM on x86_64.
See the release validation report for executed results versus pending remote CI.

## Maintaining or proposing upstream packaging

`packaging/nix/package.nix` is callPackage-compatible. Its default Rust platform
comes from nixpkgs. The repository flake provides source; an upstream nixpkgs
submission must use an immutable release source (`fetchFromGitHub` with a real
hash), adapt the fileset/source argument, add a real consenting maintainer and
follow the contribution process. Preserve local vendor patches and the Nix
distribution feature. Do not submit placeholder hashes or self-updater behavior.

To update inputs, explicitly use `nix flake update`, review/commit flake.lock,
then execute all Nix/native gates. After changing Cargo.lock/package-lock.json,
update the corresponding content hash using the hash mismatch from the actual
fixed-output fetch; both lockfiles and hashes are reviewable together. Do not
run unconstrained dependency updates during a release build.

Authoritative packaging references: [Nixpkgs manual](https://nixos.org/manual/nixpkgs/unstable/),
[cargo-tauri hook](https://github.com/NixOS/nixpkgs/tree/nixos-unstable/pkgs/by-name/ca/cargo-tauri),
[rust-overlay](https://github.com/oxalica/rust-overlay),
[WebKit bug 323277](https://bugs.webkit.org/show_bug.cgi?id=323277).
