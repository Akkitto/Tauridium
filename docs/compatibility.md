# Compatibility

## Temporary Proton Mail and Calendar workaround

Tauridium 0.7.5 contains a narrowly scoped compatibility workaround for hosted Proton Mail and
Proton Calendar.

Proton's shared web client currently distinguishes ordinary web clients such as `web-mail` and
`web-calendar` from native desktop identities such as `windows-mail`. Tauri exposes the generic
`window.isTauri === true` runtime marker to pages before their own scripts run. When a normal
Proton Mail or Calendar website is hosted inside Tauridium, that generic marker can make Proton
treat the page as a Proton native desktop client instead of as the ordinary website.

Tauridium therefore hides only the generic `window.isTauri` marker in service WebViews whose
initial service host is exactly:

- `mail.proton.me`
- `calendar.proton.me`

The workaround remains attached to those WebViews across their authentication navigation to
`account.proton.me`.

It deliberately does **not** apply to Proton Pass (`pass.proton.me`), a standalone
`account.proton.me` service, other Proton products, or unrelated websites. It does not rewrite
Proton requests, cookies, selectors, client IDs, Tauri IPC, ACLs, commands, or plugins.

### Temporary dependency patch

Tauri 2.11.3 normally defines `window.isTauri` as a non-configurable property before application
initialization scripts. Tauridium temporarily vendors that exact Tauri crate and changes only the
property descriptor so the marker is configurable. Its value remains `true` everywhere by
default. The Proton-specific initialization script can then delete the marker in the two selected
service WebViews before hosted page JavaScript executes.

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

Do not broaden this workaround to additional services without evidence that the same upstream
misclassification affects them.
