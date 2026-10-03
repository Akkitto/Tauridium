{
  lib,
  stdenv,
  rustPlatform,
  cargo-tauri,
  fetchNpmDeps,
  npmHooks,
  nodejs_24,
  pkg-config,
  wrapGAppsHook3,
  gtk3,
  webkitgtk_4_1,
  openssl,
  glib-networking,
  libayatana-appindicator,
  xdotool,
  xdg-utils,
  glib,
  gst_all_1,
  appstream,
  desktop-file-utils,
  python3,
}:

rustPlatform.buildRustPackage (finalAttrs: {
  pname = "tauridium";
  version = (lib.importJSON ../../package.json).version;

  # Explicit inclusion excludes worktree output, credentials, .git and caches.
  src = lib.fileset.toSource {
    root = ../..;
    fileset = lib.fileset.unions [
      ../../package.json
      ../../package-lock.json
      ../../index.html
      ../../vite.config.ts
      ../../svelte.config.js
      ../../tsconfig.json
      ../../src
      ../../vendor
      ../../data
      ../../LICENSE
      ../../src-tauri/Cargo.toml
      ../../src-tauri/Cargo.lock
      ../../src-tauri/build.rs
      ../../src-tauri/tauri.conf.json
      ../../src-tauri/src
      ../../src-tauri/assets
      ../../src-tauri/icons
      ../../src-tauri/capabilities
      ../../src-tauri/bundled-recipes
    ];
  };

  cargoRoot = "src-tauri";
  buildAndTestSubdir = finalAttrs.cargoRoot;
  cargoDepsName = finalAttrs.pname;
  cargoHash = "sha256-v3sJDnliP4NibBBPvo1eaYK9d7K8pEaMe3StJalVqa4=";
  npmDeps = fetchNpmDeps {
    inherit (finalAttrs) src;
    hash = "sha256-gxkKMT1PrUlXpw121H8YbFiDn9EQpkf2Ku/J4lpittA=";
  };
  npmRoot = ".";
  nativeBuildInputs = [
    cargo-tauri.hook
    nodejs_24
    npmHooks.npmConfigHook
    pkg-config
    wrapGAppsHook3
  ];
  buildInputs = [
    gtk3
    webkitgtk_4_1
    openssl
    glib-networking
    libayatana-appindicator
    xdotool
    gst_all_1.gst-plugins-base
    gst_all_1.gst-plugins-good
    gst_all_1.gst-plugins-bad
    gst_all_1.gst-libav
  ];
  buildNoDefaultFeatures = true;
  buildFeatures = [ "nix" ];
  checkFeatures = [
    "nix"
    "tauri/custom-protocol"
  ];
  tauriBuildFlags = [
    "--no-bundle"
    "--ci"
  ];
  dontTauriInstall = true;
  installPhase = ''
    runHook preInstall
    install -Dm755 target/${stdenv.hostPlatform.rust.cargoShortTarget}/release/tauridium "$out/bin/tauridium"
    install -Dm644 data/dev.brani.tauridium.desktop "$out/share/applications/dev.brani.tauridium.desktop"
    install -Dm644 data/dev.brani.tauridium.metainfo.xml "$out/share/metainfo/dev.brani.tauridium.metainfo.xml"
    install -Dm644 src-tauri/icons/icon.png "$out/share/icons/hicolor/512x512/apps/dev.brani.tauridium.png"
    install -Dm644 data/dev.brani.tauridium.svg "$out/share/icons/hicolor/scalable/apps/dev.brani.tauridium.svg"
    install -Dm644 LICENSE "$out/share/licenses/tauridium/LICENSE"
    runHook postInstall
  '';
  preFixup = ''
    gappsWrapperArgs+=(
      --prefix LD_LIBRARY_PATH : "${lib.makeLibraryPath [ libayatana-appindicator ]}"
      --prefix PATH : "${
        lib.makeBinPath [
          xdg-utils
          glib
        ]
      }"
    )
  '';
  doInstallCheck = true;
  nativeInstallCheckInputs = [
    appstream
    desktop-file-utils
    python3
  ];
  installCheckPhase = ''
    runHook preInstallCheck
    desktop-file-validate "$out/share/applications/dev.brani.tauridium.desktop"
    appstreamcli validate --no-net "$out/share/metainfo/dev.brani.tauridium.metainfo.xml"
    test -x "$out/bin/tauridium"
    test -s "$out/share/icons/hicolor/512x512/apps/dev.brani.tauridium.png"
    "$out/bin/tauridium" --build-info-file "$TMPDIR/tauridium-build-info.json"
    python3 - "$TMPDIR/tauridium-build-info.json" <<'PY'
    import json, sys
    with open(sys.argv[1], encoding="utf-8") as handle:
        info = json.load(handle)
    assert info["buildMode"] == "production", info
    policy = info["distribution"]
    assert policy["mode"] == "nix" and policy["updaterManagedExternally"] is True, info
    for flag in ("portalFileAccess", "portalNotifications", "portalAutostart", "downloadsRequireDestination", "automaticBackupsUsePrivateStorage"):
        assert policy[flag] is False, (flag, info)
    PY
    runHook postInstallCheck
  '';
  meta = {
    description = "Native WebView desktop hub for web services and workspaces";
    homepage = "https://github.com/Akkitto/Tauridium";
    license = lib.licenses.mit;
    mainProgram = "tauridium";
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
    ];
  };
})
