# Dependency security reassessment — 16 November 2026

This is a fresh, bounded review of the current dependency update, not an
automatic extension of expired exceptions. Reassessment is due **30 November
2026**. The required online gate still fetches current advisory metadata and
fails on unknown findings, changed scope, unsoundness, lock drift or expiry.
No severity, platform or advisory ignore filter was added.

## Exact inputs and results

* Application Cargo.lock SHA-256:
  `9f0893c09b238be6abb4a6ef6fa0bc4440f21ae09d4e62fbdfca5175266e56ad`.
* Builder Cargo.lock SHA-256 (unchanged):
  `6019075d357d3ff887c4fb0f59584c2720971749d95789dd60cee5f42550a202`.
* Official RustSec database inspected:
  `02e2517f457a359fc6d3440ea4560c8ea188fee8`.
* Fresh whole-lock scanning found zero known application vulnerabilities and
  four maintenance notices: proc-macro-error 1.0.4, zbus_names 4.3.5,
  zvariant 5.15.1 and zvariant_derive 5.15.1. The builder still reports RSA
  below, plus the existing paste/rustybuzz/ttf-parser maintenance notices.
* The updated hook-free npm lock installs with zero registry audit findings.
  The local deepmerge backport is checked separately against live upstream
  advisory metadata; registry audit alone cannot establish its safety.

Raw scanner/source-review evidence is private workspace material. Public
documentation contains only reviewed identifiers, hashes and conclusions.
No signing-key values or personal application profiles were read.

## Application maintenance graph

The official notices [RUSTSEC-2026-0370](https://rustsec.org/advisories/RUSTSEC-2026-0370.html),
[RUSTSEC-2026-0371](https://rustsec.org/advisories/RUSTSEC-2026-0371.html) and
[RUSTSEC-2026-0372](https://rustsec.org/advisories/RUSTSEC-2026-0372.html)
describe standalone crates moving into zbus 6. They assert maintenance status,
not an exploitable vulnerability or a patched standalone release.

The notification 2.8.1 patch retains notify-rust 4.18.2 and zbus 5.19.0.
Stable zbus-secret-service-keyring-store remains 1.0.1; stable secret-service
remains 5.2.0, while its zbus-6 successor is only 6.0.0-rc.1. Direct portal
integration already uses zbus 6.2.1. Forcing a major replacement underneath
the supported notification/vault parents would risk credential compatibility.
Keep the exact three maintenance assessments visible and bounded while tracking
their coordinated migration. See [the graph review](ZBUS-MAINTENANCE-REVIEW.md).
The separate proc-macro-error assessment retains its existing January deadline.

## Builder RSA: patched upstream, constrained parent

[RUSTSEC-2023-0071](https://rustsec.org/advisories/RUSTSEC-2023-0071.html)
now identifies RSA **0.10.0** as patched. The supported tauri-macos-sign 2.4.3
parent still constrains RSA to 0.9, including in the newly published CLI
2.12.5/bundler 2.10.5. A forced unsupported major substitution is not a safe
fix. This review explicitly does not claim that RSA lacks an upstream fix.

Checksum-verified CLI and bundler manifests restrict this parent to macOS.
Actual inverse Cargo graphs for Linux and Windows contain no RSA. The exact
builder lock has one RSA parent, tauri-macos-sign. Inspection of every Rust
source file in its verified 2.4.3 crate found RSA only in fresh private-key
generation (`src/apple_codesign/certificate.rs:852`) followed by PKCS8
serialization. It exposes no network-facing RSA decryption endpoint and does
not use the owner's updater signing key. The crate archive SHA-256 is
`4478507a7aeee53b73ac780f4f645a584ae07eab599a3d171f8afb258fb02026`.

Canonical builds reject signing credentials. The unused RPM OpenPGP graph has
already been removed; updater signing uses isolated Minisign Ed25519. The
whole-lock gate still reports this exact RSA vulnerability and the bounded
`not-affected-under-enforced-controls` assessment. This is a scoped risk
assessment, not a declaration that RSA 0.9 itself is fixed.

The retained patched builder is 2.12.4+tauridium.1. Merely upgrading to
[CLI 2.12.5](https://github.com/tauri-apps/tauri/releases/tag/tauri-cli-v2.12.5)
would retain this RSA parent and its published lock includes older rustix
1.0.7. The current reviewed lock instead uses rustix 1.1.6 and the explicit
ZIP 9.1.2 backport. Do not discard those controls for an unrelated version bump.
Reassess the parent and exact macOS source before 30 November, and migrate when
the supported parent accepts patched RSA.

## Local deepmerge security backport

The current official registry still publishes deepmerge 4.3.1 with no patched
release for [GHSA-gcqx-w48m-w2h4](https://github.com/advisories/GHSA-gcqx-w48m-w2h4).
The live npm bulk response exactly matches advisory 1243505, including scope,
severity, CWE and CVSS. The local 4.3.1+tauridium.1 runtime remains SHA-256
`f52c1deed5fef6181e217aa466fb2ec6936c2b9c22060a8c0cfa9c0f015df992`.
The real check_deepmerge gate passed source provenance, Svelte resolution,
reserved-key and getter exploit controls, safe own-property construction and
configuration compatibility with the updated frontend lock.

The local policy binds the runtime, advisory details, review date and deadline;
changing only a policy date cannot extend it. Changed code/metadata, additional
advisories and expiry fail closed. A typed expiry diagnostic now tells maintainers
to re-review this backport; arbitrary scanner/parser exception details remain
private. Boundary and synthetic-private-error regression tests cover both paths.

## Required follow-up

Before 30 November, inspect fresh upstream metadata and the exact graphs and
source again; replace assessments with supported fixes when available. Re-run
the online whole-lock gate and full native/distribution matrices after any
dependency change. Refresh generated offline sources and derive Nix fixed-output
hashes from actual fetches. No approval, signing, artifact-scanning or publication
gate is waived by this review. Passing current scans does not promise absence
of undiscovered vulnerabilities.
