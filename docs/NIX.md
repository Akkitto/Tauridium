# Nix and NixOS

Tauridium 0.9.0 includes a locked, source-built Nix flake for x86_64-linux and
aarch64-linux. This is the project's package, **not a claim of acceptance into
nixpkgs**. Windows uses the existing native/Scoop workflows; do not install Nix
or WSL merely to develop Tauridium on Windows.

## Try, install, update and remove

After the release tag has been pushed, try the immutable release:

```sh
nix --extra-experimental-features 'nix-command flakes' run github:Akkitto/Tauridium/v0.9.3
```

Install in your profile for a stable desktop launcher and session autostart:

```sh
nix --extra-experimental-features 'nix-command flakes' profile add github:Akkitto/Tauridium/v0.9.3#tauridium
nix profile list
```

Tagged references are intentionally immutable: upgrading a profile pinned to
v0.9.3 cannot discover a newer tag. Replace that reference when choosing the next
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

Choose the smallest integration that fits your existing configuration. Tauridium
exports `packages`, `apps` and an overlay, **not** a NixOS service module or a
Home Manager module. You supply your own installation module; no `services.tauridium`
or `programs.tauridium.enable` option is required or exported.

| Consumption pattern | Installation expression | Input forwarding |
| --- | --- | --- |
| Direct package in an inline module | `tauridium.packages.${system}.default` | None when captured from `outputs` |
| Direct package in an imported NixOS module | Same package in `environment.systemPackages` | `nixosSystem.specialArgs` |
| Direct package in an imported standalone Home Manager module | Same package in `home.packages` | `homeManagerConfiguration.extraSpecialArgs` |
| Home Manager embedded in NixOS | Same package in the user's `home.packages` | `home-manager.extraSpecialArgs` |
| Overlay | `pkgs.tauridium` | Register the overlay on the package set actually used by that module |

Both `.default` and `.tauridium` name the same package. Available systems are
`x86_64-linux` and `aarch64-linux`; choose your host architecture, not the machine
editing the configuration. These outputs are native Linux packages, not a
cross-compilation interface or Windows/macOS packages.

### Shared flake input and dependency policy

Add this input to your existing configuration flake:

```nix
inputs.tauridium.url = "github:Akkitto/Tauridium/v0.9.3";
```

Bind it in your existing `outputs` function, for example
`outputs = inputs@{ nixpkgs, tauridium, ... }: ...;`, then update and commit your
configuration's `flake.lock` after the tag is published. Do not replace unrelated
inputs or your existing host/user settings.

Keep Tauridium's own tested nixpkgs/compiler lock. Neither direct consumption nor
the overlay requires `tauridium.inputs.nixpkgs.follows = "nixpkgs"`; adding it
replaces the tested dependency set and may select a compiler below Tauridium's
MSRV. The overlay deliberately returns Tauridium's locked package rather than
rebuilding it with your configuration's `pkgs`. Updating your system nixpkgs alone
therefore does not update Tauridium's dependencies. Review changes to both locks.

### Direct package: capture the input inline

Inside `outputs`, the input is already in lexical scope. This is the simplest
pattern when you do not need a separate installation module:

```nix
nixosConfigurations.desktop = nixpkgs.lib.nixosSystem {
  system = "x86_64-linux"; # Or aarch64-linux.
  modules = [
    ./configuration.nix # Your existing complete host configuration.
    ({ pkgs, ... }: {
      environment.systemPackages = [
        tauridium.packages.${pkgs.stdenv.hostPlatform.system}.default
      ];
    })
  ];
};
```

For a Home Manager inline module, replace `environment.systemPackages` with
`home.packages`. Do not add `tauridium` to that inline function's argument list:
doing so shadows the captured input and asks the module system to supply it.

### Imported NixOS module: `specialArgs`

In your configuration flake's `outputs`:

```nix
nixosConfigurations.desktop = nixpkgs.lib.nixosSystem {
  system = "x86_64-linux";
  specialArgs = { inherit tauridium; };
  modules = [ ./configuration.nix ./tauridium-system.nix ];
};
```

`tauridium-system.nix`:

```nix
{ pkgs, tauridium, ... }:
{
  environment.systemPackages = [
    tauridium.packages.${pkgs.stdenv.hostPlatform.system}.default
  ];
}
```

### Standalone Home Manager: `extraSpecialArgs`

Use the Home Manager branch matching your configuration's nixpkgs channel. For
an unstable configuration, these inputs can accompany the Tauridium input:

```nix
inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
inputs.home-manager = {
  url = "github:nix-community/home-manager";
  inputs.nixpkgs.follows = "nixpkgs";
};
```

Bind `home-manager` as well as `nixpkgs` and `tauridium` in `outputs`. Then:

```nix
homeConfigurations.demo = home-manager.lib.homeManagerConfiguration {
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  extraSpecialArgs = { inherit tauridium; };
  modules = [ ./home.nix ./tauridium-home.nix ];
};
```

`tauridium-home.nix`:

```nix
{ pkgs, tauridium, ... }:
{
  home.packages = [
    tauridium.packages.${pkgs.stdenv.hostPlatform.system}.default
  ];
}
```

Keep your real username, home directory and existing `home.stateVersion` in
`home.nix`. **Do not bump stateVersion merely to install or update Tauridium.**
An input declared in a flake is not automatically a Home Manager module argument;
forward it explicitly as above. See the
[Home Manager standalone manual](https://home-manager.dev/manual/unstable/nix-flakes/standalone.html).

### Home Manager as a NixOS module: a separate argument boundary

Inside your flake's `outputs`, using the same `tauridium-home.nix`:

```nix
nixosConfigurations.desktop = nixpkgs.lib.nixosSystem {
  system = "x86_64-linux";
  modules = [
    ./configuration.nix
    home-manager.nixosModules.home-manager
    {
      home-manager.useGlobalPkgs = true;
      home-manager.useUserPackages = true;
      home-manager.extraSpecialArgs = { inherit tauridium; };
      home-manager.users.demo.imports = [ ./home.nix ./tauridium-home.nix ];
    }
  ];
};
```

Replace `demo` with an existing normal NixOS user. Keep existing Home Manager
options rather than changing package/profile ownership just for Tauridium.
**NixOS `specialArgs` alone does not forward the value into Home Manager.** If
both module layers need it, set both `specialArgs` and
`home-manager.extraSpecialArgs`. See the
[Home Manager NixOS-module manual](https://home-manager.dev/manual/unstable/nix-flakes/nixos.html).

### Overlay: install through the module's `pkgs`

For NixOS, capture the overlay in `outputs` and register it once:

```nix
modules = [
  ./configuration.nix
  { nixpkgs.overlays = [ tauridium.overlays.default ]; }
  ({ pkgs, ... }: { environment.systemPackages = [ pkgs.tauridium ]; })
];
```

For standalone Home Manager, supply an overlaid package set:

```nix
homeConfigurations.demo = home-manager.lib.homeManagerConfiguration {
  pkgs = import nixpkgs {
    system = "x86_64-linux";
    overlays = [ tauridium.overlays.default ];
  };
  modules = [
    ./home.nix
    ({ pkgs, ... }: { home.packages = [ pkgs.tauridium ]; })
  ];
};
```

With `home-manager.useGlobalPkgs = true`, embedded Home Manager uses NixOS's
package set: register the overlay on **NixOS** `nixpkgs.overlays`, not a separate
Home Manager package set. If you keep `useGlobalPkgs = false`, apply the overlay
to Home Manager's own package set instead. Direct package consumption needs no
overlay. Do not install twice via both `home.packages` and
`environment.systemPackages` unless that ownership is intentional.

### Troubleshooting missing arguments

An error mentioning `attribute 'tauridium' missing`, `args.${name}` or
`config._module.args`, often inside nixpkgs/Home Manager's module evaluator,
usually means `{ tauridium, ... }:` requested an argument that was not forwarded.
This does **not** indicate that the Tauridium derivation or installer is broken.

1. Check which module system evaluates the failing file, then use the forwarding
   field in the table above. Adding NixOS `specialArgs` is not a standalone
   Home Manager fix.
2. Match argument names exactly. `extraSpecialArgs = { inherit tauridium; };`
   matches `{ tauridium, ... }:`. Alternatively,
   `extraSpecialArgs = { inherit inputs; };` matches `{ inputs, ... }:` and
   `inputs.tauridium.packages.${pkgs.stdenv.hostPlatform.system}.default`.
   These styles are not interchangeable.
3. If using lexical capture, remove `tauridium` from the inline module's arguments.
   For an overlay error mentioning `pkgs.tauridium`, check the actual package set
   used by the failing module, not merely an unrelated `import nixpkgs`.
4. Evaluate before activation, for example `nix eval --show-trace
   '.#homeConfigurations.demo.activationPackage.drvPath'`. Then use
   `home-manager build --flake .#demo` or `nixos-rebuild build --flake .#desktop`
   for your complete configuration before choosing to switch.

Merge additional arguments into your existing argument set; do not replace
other consumers' values or override reserved `lib`, `config`, `options` or `pkgs`
arguments. Prefer explicit forwarding over ad-hoc `_module.args` tricks for
values originating outside the module graph. The
[NixOS system-configuration guide](https://wiki.nixos.org/wiki/NixOS_system_configuration#Accessing_flake_inputs)
documents NixOS `specialArgs`.

### Executable examples and evaluation coverage

[Consumer examples](examples/nix/flake.nix) contain the direct, overlay and
argument-forwarding patterns in [consumer.nix](examples/nix/consumer.nix), plus
imported [NixOS](examples/nix/nixos.nix) and [Home Manager](examples/nix/home.nix)
modules. They are **evaluation examples, not a replacement host configuration**:
merge a chosen pattern into your existing files. The sample user is `demo` and
the sample Home Manager state version is for a new configuration only. After
the chosen tag is published, a copied example flake can generate its own consumer lock.

From this repository, run `just nix-integration` to evaluate the actual examples
against locked NixOS and Home Manager on both supported architecture outputs.
It also confirms three expected missing-argument failures per architecture,
including the embedded Home Manager boundary. Evidence goes to
`release/evidence/nix-integration/report.json`. This evaluates package membership,
Home Manager assertions and activation derivations; it does **not** activate a
system/user configuration, run ARM binaries on x86, or replace the VM/runtime gates.
Home Manager is locked only in the test fixture, not added to Tauridium's normal
flake inputs. The fixture requires Nix 2.35 or later for its relative flake input.

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
just nix-integration
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
