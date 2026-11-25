# Frontend architecture

Tauridium uses Svelte 5 runes and typed TypeScript boundaries. The shell and service
webviews have different lifecycles: rendering a settings panel must never recreate a
service session or change its native bounds unexpectedly.

## Ownership

| Owner | Responsibility |
| --- | --- |
| `src/App.svelte` | Application composition, service lifecycle coordination, native bounds and menus, global shortcuts, shared persisted state, settings navigation/search and lifecycle cleanup |
| `src/components/Settings*.svelte` | One settings tab per component; shared accessible switch markup in `SettingsToggle` |
| `ServiceSettingsPanel`, `ServiceToggle` | Selected-service controls and accessible boolean settings |
| `ServicePicker`, `ServiceSidebar`, `ServiceRow`, `QuickSwitcher`, `SessionScreen` | Service creation, sidebar rendering, quick navigation and authentication views |
| `src/lib/controllers/*.svelte.ts` | Per-owner state and actions for appearance, authentication, backups, audit history, updates, service editing, workspace editing and support information |
| `src/lib/appSettingsDefaults.ts` | A fresh settings object, including independent nested records, for each application instance |
| `src/lib/api.ts` | Typed native command boundary; privileged work remains in Rust |

Application-scoped controllers are factories instantiated once in the root component.
The support-information controller is owned by its mounted panel because its preview,
request and feedback state are temporary. Factories do not export mutable singleton state. Their typed host objects use getters and setters to read the
latest shared state, including arrays and preferences replaced after persistence.
Passing a snapshot into a controller would break that contract.

Use `$derived` for calculations. Do not mirror parent state into local state with an
effect. Keep editable drafts separate from acknowledged persisted data; retain drafts
and report errors when a save fails. Authentication retry credentials remain private
to the authentication controller.

## Components and interaction

Use typed `$props` and callbacks for actions. `$bindable` is reserved for existing
editable values that intentionally share ownership with the application or feature
controller. Select values and input previews retain their previous event ordering.
Pass the selected non-null service separately to its settings panel so callback IDs
remain safe without assertions.

The root owns global listeners, native integration and recurring backup scheduling.
The authentication controller owns its retry interval; root destruction cancels it.
Audit pagination exposes a cleanup-aware observer action in its panel. Mounting,
switching or destroying a panel must preserve those boundaries.

## Support information

The reusable `SupportInformation` panel appears in About and before authentication.
It sends no renderer text to the native clipboard command. Rust builds an explicit
allowlist of report fields; neither command reads clipboard contents, accounts,
service identities, URLs, paths or logs. Copying returns the exact report written by
the native side. The panel announces success only after acknowledgement and keeps
its read-only selectable preview when copying fails. Preview/refresh does not write
the clipboard or preferences.

## Styles

Keep scoped selectors beside the elements they style. Shared switch geometry belongs
to the switch component, not a parent stylesheet. Global theme tokens and document
defaults stay in the root. An ancestor outside a component may be targeted with a
narrow `:global(...)` selector when it is a real layout context; do not globalize whole
control stylesheets to make extraction compile.

## Regression coverage

- Vitest exercises controller isolation, reactive derivation, save acknowledgement,
  failure rollback and retry cleanup, plus existing search, layout and UI contracts.
- `frontendTestSources.ts` follows actual component imports and records node/style
  ownership, so layout assertions check the component that renders the control.
- `tools/frontend_source.py` lets historical source contracts follow reachable feature
  owners. Owner-specific assertions select the real file rather than slicing a tab
  out of the root component.
- The Vitest-only browser resolution condition enables Svelte rune reactivity in
  Node tests; it does not change production dependency resolution.
- Native production smoke tests and Windows CI validate real webview boundaries,
  menus, settings search, themes and keyboard interactions.

Follow the official Svelte guidance on [component props](https://svelte.dev/docs/svelte/$props),
[reactive modules](https://svelte.dev/docs/svelte/svelte-js-files),
[scoped styles](https://svelte.dev/docs/svelte/scoped-styles),
[lifecycle cleanup](https://svelte.dev/docs/svelte/lifecycle-hooks) and
[testing](https://svelte.dev/docs/svelte/testing).
