# D-Bus standalone-crate maintenance review

Re-reviewed 16 November 2026; reassessment due **30 November 2026**. This is an
explicit temporary maintenance assessment, not a vulnerability fix or a claim
that the standalone crate has become maintained again.

## Upstream evidence

[RUSTSEC-2026-0371](https://github.com/RustSec/advisory-db/blob/263a4d951a0867d4bddc29dddd6d59427c78f9a7/crates/zbus_names/RUSTSEC-2026-0371.md)
is dated 16 October 2026 and classified `informational = "unmaintained"`.
The advisory describes the standalone crate being merged into zbus 6's `names`
module. It identifies no exploitable vulnerability or patched standalone release.
The related official notices
[RUSTSEC-2026-0370](https://github.com/RustSec/advisory-db/blob/263a4d951a0867d4bddc29dddd6d59427c78f9a7/crates/zvariant/RUSTSEC-2026-0370.md)
and
[RUSTSEC-2026-0372](https://github.com/RustSec/advisory-db/blob/263a4d951a0867d4bddc29dddd6d59427c78f9a7/crates/zvariant_derive/RUSTSEC-2026-0372.md)
cover standalone `zvariant` and `zvariant_derive` moving into zbus 6's wire
module/derive support. Both are also maintenance notices, with no vulnerability
or patched standalone version asserted. Both actual locks were inspected in full,
not merely until the gate's first unassessed finding.
The official database file and the actual locked reverse dependency tree were
inspected; this decision is not based on a scanner severity filter.

## Exact current scope

The application lock has SHA-256
`9f0893c09b238be6abb4a6ef6fa0bc4440f21ae09d4e62fbdfca5175266e56ad`.
Re-reviewed on 16 November against current official RustSec database commit
`02e2517f457a359fc6d3440ea4560c8ea188fee8` after the portal migration. The 1.0.9 portal migration adds the separately reviewed zbus 6.2.1 runtime; the required zbus 5 wire/name consumers remain as listed below. Fresh whole-lock scanning reports zero known application vulnerabilities
and the same four explicitly assessed maintenance notices (including the separate
GTK tooling notice). The yanked `async-executor 1.14.0` discovered during
reassessment was replaced by non-yanked `1.14.1`; the final scan has no yanked
findings. The assessment expiry is 30 November following the fresh source and upstream review.
It contains `zbus_names 4.3.5`, `zvariant 5.15.1`, `zvariant_derive 5.15.1`,
`zbus 5.19.0` and `zbus_macros 5.19.0`.
An actual Linux all-feature reverse dependency inspection shows:

| Parent | Application integration |
| --- | --- |
| `notify-rust 4.18.2` | `tauri-plugin-notification 2.8.1` |
| `secret-service 5.2.0` | `zbus-secret-service-keyring-store 1.0.1` |
| `zbus-secret-service-keyring-store 1.0.1` | Native OS-vault storage |
| `tauri-plugin-notification 2.8.1` direct zbus dependency | Native notification integration |
| Tauridium's optional direct `zbus 6.2.1` dependency | Flatpak portal integration |

The compatible `rfd 0.17.2` / dialog `2.8.4` update removes the prior ashpd
parent. Current published notification and vault parents still require zbus 5.
Version 1.0.9 migrates the direct portal dependency to zbus 6.2.1. Its async
operations use the independent default runtime and new root wire types. All
response subscriptions precede requests. Real private-bus tests cover immediate
responses, cancellation, denial, unknown codes, incorrect handles and malformed
payloads, including calls from inside a Tokio runtime.

The current vault/notification parents retain their supported zbus 5 APIs. Those
versions coexist explicitly; upgrading the portal alone does not retire the
standalone maintenance findings or justify replacing credential storage.

Changing Tauridium's direct dependency to zbus 6 does not remove the
independently constrained transitive zbus 5 consumers. A complete migration must
coordinate these APIs and validate portal dialogs, notifications, vault access,
migration/removal and all distribution feature combinations. Do not force a
major-version crate replacement under existing dependants or silently replace
the vault with plaintext storage.

## Enforced interim controls

Only the three exact application-lock maintenance findings above are recorded
as `reviewed-maintenance-warning`, expiring on
30 November 2026. Fresh whole-lock scanning still prints the finding, reason and
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
dialog acceptance. Reassess before 30 November; do not merely move the date.
The interim policy does not waive hosted Windows CI, manual GUI checks, release
environment protections, signature verification or any other publication gate.

The current update and exact upstream/source evidence are recorded in
[the 16 November reassessment](SECURITY-REVIEW-2026-11-16.md). Stable vault
parents still lack a released zbus-6 migration; a prerelease replacement is not
a safe substitute for validating credential storage and its upgrade behavior.
