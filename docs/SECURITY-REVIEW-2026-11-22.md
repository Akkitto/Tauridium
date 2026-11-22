# Dependency security review — 22 November 2026

The v1.0.14 update integrates Vitest 5.1.1, Svelte 5.58.0, Tauri JavaScript API 2.12.5, tauri-build 2.7.6/tauri-utils 2.10.4, regex 1.13.2 and direct zbus 6.3.0 with compatible locked transitive updates. Runtime isolation, vendored Wry/updater/window-state patches and local npm security backports are preserved.

Fresh review identified [RUSTSEC-2026-0592](https://rustsec.org/advisories/RUSTSEC-2026-0592.html): nested blob URL origin evaluation in url <=2.5.8 can overflow the stack and abort the process. Both application and reviewed builder locks now use the supported fixed url 2.5.9 and required form_urlencoded 1.2.3. The application regression evaluates ordinary, nested and 10,000-prefix blob origins; it preserves the ordinary HTTPS tuple origin and requires opaque nested origins without recursion. A lock regression covers both producers.

The patched CLI revision is 2.12.4+tauridium.2. Upstream CLI/bundler source identities, reviewed ZIP/compression migrations, removal of RPM signing code and key-free build controls remain unchanged. The actual CLI must be rebuilt from the new reviewed lock; an older executable is rejected by the existing identity gate. Nix dependency hashes and offline Flatpak manifests are regenerated from the exact updated inputs.

Existing assessed packages and their dependency constraints remain unchanged: tauri-utils 2.10.4 retains serde_with 3.24.0/Chrono 0.4.45; notify-rust 4.18.2 and secret-service 5.2.0 retain their separately required zbus 5.19.0 family. Updating the optional direct zbus-6 portal path does not replace OS-vault or notification APIs. zbus_macros 6.5.0 is permitted by zbus 6.3.0 and fixes derived D-Bus error forwarding; private-bus feature tests remain required.

No new advisory assessment or ignore is added. Existing scope/version/kind checks, whole-lock fingerprints, signing-key refusal, unknown-finding rejection and expiry remain enforced. The 30 November 2026 reassessment deadline is not extended. Passing gates does not establish absence of undiscovered vulnerabilities.

Release validation must include fresh complete npm/RustSec audits, native and all feature regression matrices, production builds, both native Windows architectures, Nix/Flatpak/Arch distributions and decoded release scans. Actual results are recorded in the external release report rather than claimed before execution.

Exact lock bindings:

- Application: `f1ae7812e9bd775a4856d96aefe0123435d15527166f79634e5edfda93722f75`
- Patched builder: `bbc1542eebc53c9deac34dfa6d519af653e7030ad9469f49f145592238aafba6`
