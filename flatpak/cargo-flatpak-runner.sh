#!/bin/sh
set -eu

# Tauri invokes the configured runner as if it were Cargo. Force the Flatpak
# feature set and disable Tauridium's native-distribution default features so
# updater/autostart/native notification backends are not compiled into the
# sandboxed build.
exec cargo "$@" --no-default-features --features flatpak
