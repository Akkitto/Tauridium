# Tauridium patch to Tauri 2.11.3

This directory is the upstream `tauri` crate version 2.11.3 with one intentionally
small temporary patch for Tauridium.

## Temporary patch

Tauri's document-start runtime marker is normally defined as a non-configurable
`window.isTauri === true` property. Tauridium changes only the property's
`configurable` descriptor to `true`; its value remains `true` everywhere by default.

Tauridium's own Proton Mail/Calendar compatibility module can therefore delete the
marker in those two hosted-service webviews before page JavaScript runs. No Tauri IPC
capability, ACL, command, plugin, or `__TAURI_INTERNALS__` behavior is changed.

This exists solely to work around the upstream Proton web-client environment-detection
regression that treats any page exposing the generic Tauri marker as a Proton native
desktop application.

## Removal

When Proton no longer classifies ordinary hosted Mail/Calendar pages from the generic
Tauri marker alone:

1. remove `src-tauri/src/proton_compat.rs`;
2. remove its conditional initialization-script injection from `src-tauri/src/main.rs`;
3. remove this `vendor/tauri` directory and the `tauri` entry from `[patch.crates-io]`;
4. restore the ordinary crates.io Tauri dependency and regenerate `Cargo.lock`;
5. remove the corresponding 0.7.5 regression invariants.

Do not expand this patch into a general hosted-site compatibility layer.
