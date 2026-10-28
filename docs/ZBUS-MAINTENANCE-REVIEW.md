# D-Bus standalone-crate maintenance review

Re-reviewed 27 October 2026; reassessment due **15 November 2026**. This is an
explicit temporary maintenance assessment, not a vulnerability fix or a claim
that the standalone crate has become maintained again.

## Upstream evidence

[RUSTSEC-2026-0371](https://github.com/RustSec/advisory-db/blob/3279c99911354c400e1d41e47c7d60e39258b147/crates/zbus_names/RUSTSEC-2026-0371.md)
is dated 16 October 2026 and classified `informational = "unmaintained"`.
The advisory describes the standalone crate being merged into zbus 6's `names`
module. It identifies no exploitable vulnerability or patched standalone release.
The related official notices
[RUSTSEC-2026-0370](https://github.com/RustSec/advisory-db/blob/3279c99911354c400e1d41e47c7d60e39258b147/crates/zvariant/RUSTSEC-2026-0370.md)
and
[RUSTSEC-2026-0372](https://github.com/RustSec/advisory-db/blob/3279c99911354c400e1d41e47c7d60e39258b147/crates/zvariant_derive/RUSTSEC-2026-0372.md)
cover standalone `zvariant` and `zvariant_derive` moving into zbus 6's wire
module/derive support. Both are also maintenance notices, with no vulnerability
or patched standalone version asserted. Both actual locks were inspected in full,
not merely until the gate's first unassessed finding.
The official database file and the actual locked reverse dependency tree were
inspected; this decision is not based on a scanner severity filter.

## Exact current scope

The application lock has SHA-256
`ebaed9290a2e514727e2bf09a24d8dd1e87ead651e2abac2671faf3600eda854`.
Re-reviewed on 27 October against official RustSec database commit
`3279c99911354c400e1d41e47c7d60e39258b147` after the compatible native dependency
refresh. Fresh whole-lock scanning reports zero known application vulnerabilities
and the same four explicitly assessed maintenance notices (including the separate
GTK tooling notice). The assessment expiry remains 15 November.
It contains `zbus_names 4.3.5`, `zvariant 5.15.1`, `zvariant_derive 5.15.1`,
`zbus 5.19.0` and `zbus_macros 5.19.0`.
An actual Linux all-feature reverse dependency inspection shows:

| Parent | Application integration |
| --- | --- |
| `notify-rust 4.18.2` | `tauri-plugin-notification 2.7.0` |
| `secret-service 5.2.0` | `zbus-secret-service-keyring-store 1.0.1` |
| `zbus-secret-service-keyring-store 1.0.1` | Native OS-vault storage |
| `ashpd 0.11.1` | `rfd 0.16.1` and `tauri-plugin-dialog 2.8.3` portal dialogs |
| Tauridium's optional direct zbus dependency | Flatpak portal integration |

Changing only Tauridium's direct dependency to zbus 6 would not remove the
independently constrained transitive zbus 5 consumers. A complete migration must
coordinate these APIs and validate portal dialogs, notifications, vault access,
migration/removal and all distribution feature combinations. Do not force a
major-version crate replacement under existing dependants or silently replace
the vault with plaintext storage.

## Enforced interim controls

Only the three exact application-lock maintenance findings above are recorded
as `reviewed-maintenance-warning`, expiring on
15 November 2026. Fresh whole-lock scanning still prints the finding, reason and
expiry. The full application lock is now SHA-256-bound, as the builder lock already
was; a changed lock requires review before its assessment remains valid. Both
locks have explicit LF Git attributes so Windows conversion cannot change the
reviewed bytes. No audit-time byte normalization is used.

Tests require different versions, lock scopes, vulnerability/unsound warning kinds,
changed or missing lock hashes and expiry to fail closed. Existing ignore/severity/
target-filter prohibitions remain in force. No `cargo audit --ignore`, broad
informational-warning exemption, reduced coverage or automatic expiry extension
was introduced. Other existing advisory assessments remain separately visible.

## Required follow-up

Track the coordinated zbus 6 migration for all three crates through the notification, portal and vault
parents. Prepare it in an isolated checkout, inspect dependency/source changes,
refresh the locked Flatpak/Nix inputs and run real feature matrices, Nix package/
installation checks, Flatpak build/runtime checks and native vault/notification/
dialog acceptance. Reassess before 15 November; do not merely move the date.
The interim policy does not waive hosted Windows CI, manual GUI checks, release
environment protections, signature verification or any other publication gate.
