# Compatibility

## Temporary Proton web-client workaround

Tauridium 0.7.6 broadens the temporary Proton compatibility workaround introduced in 0.7.5.

Proton's shared web-client configuration can select platform-specific native client identities when
it believes a page is running inside a native desktop shell. Tauri exposes the generic
`window.isTauri === true` marker before hosted application scripts run, so a normal Proton web
client inside Tauridium can otherwise be misclassified as Proton's own native desktop client.

Tauridium therefore hides only the generic `window.isTauri` marker in service WebViews whose
initial service host currently corresponds to a Proton web client with platform-specific native
client identities:

- `account.proton.me` (the host also used by Account Lite authentication flows)
- `mail.proton.me`
- `calendar.proton.me`
- `pass.proton.me`
- `authenticator.proton.me`
- `meet.proton.me`

This list is intentionally evidence-based rather than a blanket `*.proton.me` rule. Proton web
clients that currently have no platform-specific native client identity, such as Drive, Wallet,
Docs/Sheets, Lumo, and Contacts, remain untouched.

The workaround does **not** rewrite Proton requests, cookies, selectors, client IDs, Tauri IPC,
ACLs, commands, or plugins.

### Temporary dependency patch

Tauri 2.11.3 normally defines `window.isTauri` as a non-configurable property before application
initialization scripts. Tauridium temporarily vendors that exact Tauri crate and changes only the
property descriptor so the marker is configurable. Its value remains `true` everywhere by
default. The Proton-specific initialization script can then delete the marker in the selected
Proton service WebViews before hosted page JavaScript executes.

The local Tauri dependency is intentionally pinned to exactly 2.11.3 so a dependency update
cannot silently bypass the compatibility patch.

Upstream references:

- Tauri WebView initialization and `window.isTauri` marker:
  <https://github.com/tauri-apps/tauri/blob/dev/crates/tauri/src/manager/webview.rs>
- Proton shared application/client-ID configuration:
  <https://github.com/ProtonMail/WebClients/blob/main/packages/shared/lib/constants.ts>

### Removal

This workaround is expected to be temporary. Once Proton no longer treats the generic Tauri
runtime marker as sufficient proof that a hosted webpage is running inside Proton's own native
desktop client:

1. remove `src-tauri/src/proton_compat.rs`;
2. remove its conditional injection from `src-tauri/src/main.rs`;
3. remove `vendor/tauri` and the local `tauri` entry from `[patch.crates-io]`;
4. restore the normal Tauri dependency and regenerate `Cargo.lock`;
5. remove the corresponding compatibility regression invariants.

Keep this host list aligned only with Proton web clients that expose platform-specific native client
identities. Remove entries when upstream no longer relies on the generic Tauri marker for that
classification.
