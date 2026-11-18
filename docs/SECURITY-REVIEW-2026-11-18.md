# Dependency security review — 18 November 2026

This is a fresh assessment of the newly issued Chrono maintenance advisory in
both exact dependency locks. Reassessment is due **30 November 2026**. It does
not extend the existing zbus or builder RSA assessments, alter their conclusions,
or exempt a Chrono vulnerability. No advisory ignore, severity filter or target
filter is added.

## Official advisory and exact scope

[RUSTSEC-2026-0543](https://rustsec.org/advisories/RUSTSEC-2026-0543.html)
was issued on 17 November 2026. Its official record classifies it as
`informational = "unmaintained"`, applies to every Chrono version, and lists
`patched = []`. It asserts maintenance status rather than a vulnerability.
The maintainer confirmed the intention to move users to alternatives in the
[upstream discussion](https://github.com/chronotope/chrono/issues/1768).
Replacing Chrono with jiff or time requires its parents to migrate their APIs;
neither crate is a compatible dependency substitution.

The current official RustSec database inspected was
`233155b4025b854c68a4b199c0e32d7fd53291a2`. The
[immutable advisory source](https://github.com/RustSec/advisory-db/blob/233155b4025b854c68a4b199c0e32d7fd53291a2/crates/chrono/RUSTSEC-2026-0543.md)
has SHA-256
`18424c6a155f754151a55ce9fb73376bf66f3709d81750d921f5293da91ccc59`.

The assessment covers only Chrono **0.4.45**, advisory
**RUSTSEC-2026-0543**, and kind **unmaintained**, separately for:

* Application lock `src-tauri/Cargo.lock`, SHA-256
  `bf0a32d493f3e84e898b6b1596753aced5bfadbd0ebb3332f82ecd23e34a8eeb`.
* Builder lock `flatpak/tauri-cli.Cargo.lock`, SHA-256
  `6019075d357d3ff887c4fb0f59584c2720971749d95789dd60cee5f42550a202`.

The application lock differs from the prior release only in the local Tauridium
root version, now 1.0.12. No dependency version, source or checksum is changed by
this review. The builder lock is unchanged. Both retain the Chrono crate checksum
`1aa79e62e7697b8e29b513a68abacf485adcd1fe8284a4316c5ae868e6633327`.

## Current supported releases and parent constraints

Live official crates.io metadata was checked on 18 November, and each archive
below was downloaded from static.crates.io and matched against the registry's
SHA-256. Chrono **0.4.45** remains the latest stable release; there is no newer
maintained 0.4 release that removes this advisory.

| Crate | Latest stable checked | Archive SHA-256 |
| --- | --- | --- |
| [chrono](https://crates.io/crates/chrono/0.4.45) | 0.4.45 | `1aa79e62e7697b8e29b513a68abacf485adcd1fe8284a4316c5ae868e6633327` |
| [serde_with](https://crates.io/crates/serde_with/3.24.0) | 3.24.0 | `df9adc193c780ef8f159aee8b61e2d5801aaa555e6eb0947fe45530ec506296f` |
| [tauri-utils](https://crates.io/crates/tauri-utils/2.10.3) | 2.10.3 | `d6bf649f12d6fb11e1867214973cd37d89786ae2c0904f79b787b1db4fdcd14c` |
| [tauri-macos-sign](https://crates.io/crates/tauri-macos-sign/2.4.3) | 2.4.3 | `4478507a7aeee53b73ac780f4f645a584ae07eab599a3d171f8afb258fb02026` |
| [x509-certificate](https://crates.io/crates/x509-certificate/0.25.0) | 0.25.0 | `ca9eb9a0c822c67129d5b8fcc2806c6bc4f50496b420825069a440669bcfbf7f` |
| [tauri-cli](https://crates.io/crates/tauri-cli/2.12.5) | 2.12.5 | `a600195403c00148babdfa8d52846355efe377241a439b85dd83d1636ee97c55` |
| [tauri-bundler](https://crates.io/crates/tauri-bundler/2.10.5) | 2.10.5 | `9b52892733fcde76307489a6a3625e8815dd49916e47640d0f64434b8e21fca4` |

The application lock has one immediate Chrono parent, serde_with 3.24.0, through
tauri-utils 2.10.2. The latest serde_with still provides its Chrono 0.4 adapters,
and latest tauri-utils 2.10.3 still depends on serde_with 3. An inverse Cargo
graph for the locked Linux application, including normal, build and development
edges, printed no active Chrono dependency. That observation is limited to the
checked Linux graph; it does not remove Chrono from the whole-lock audit or
establish that other targets or feature sets exclude it.

The builder lock has three immediate Chrono parents: serde_with 3.24.0,
tauri-macos-sign 2.4.3 and x509-certificate 0.24.0. The latest stable CLI 2.12.5
and bundler 2.10.5 still pin tauri-macos-sign to `=2.4.3` under macOS. That
signing helper requires `chrono = "0.4"` and `x509-certificate = "0.24"`;
its certificate-generation interfaces use `chrono::Duration`. Even the newer
x509-certificate 0.25.0 still requires Chrono 0.4.38 and exposes Chrono date/time
types. A supported parent bump therefore does not resolve this finding.

Keep the existing reviewed builder security backports and credential-parent
graph. This review does not force incompatible Chrono, x509, vault or signing
API replacements, and does not change the separate RSA assessment from
[16 November](SECURITY-REVIEW-2026-11-16.md).

## Enforcement and required follow-up

Fresh unfiltered whole-lock scans against the database above reported zero
known application vulnerabilities and five application maintenance notices.
The builder reported its existing RSA vulnerability and four maintenance
notices. Chrono is the only newly assessed finding in either lock. These
results do not assert the absence of undiscovered vulnerabilities.

The policy records two exact maintenance assessments reviewed on 18 November
and expiring on 30 November. Its existing whole-lock SHA-256 bindings remain
enforced. A different advisory, version, finding kind, unknown vulnerability,
unsoundness, changed lock or expired review still fails the gate. Existing
assessment dates and deadlines remain unchanged.

Before 30 November, check the current official advisory and supported parent
releases again. Replace the maintenance assessment with a supported migration
when available. Run the required current online gate, the Rust supply-chain
guard and the native/distribution validation matrix before release. An offline
snapshot diagnostic is not a substitute for the current online gate. Raw
scanner reports and source-review working material remain private.

## Picomatch ReDoS backport

The live npm scan now reports [GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf)
against picomatch 4.0.7, propagated to seven build-tool dependency entries.
The registry still has no patched release. Keep the tested Vite/Vitest versions;
`npm audit fix --force` proposes a major downgrade, not a supported security fix.
Picomatch runs in the Node build/test tools; it is not an application runtime
service or a native command available to hosted websites.

The in-tree 4.0.7+tauridium.1 backport preserves the upstream MIT license and
records the original npm tarball SHA-512 plus every installed file SHA-256.
It adapts the narrow equivalence rewrite proposed at upstream commit
[`f03bec2c02e46f063fbfdc161aae1d0f854b2565`](https://github.com/micromatch/picomatch/commit/f03bec2c02e46f063fbfdc161aae1d0f854b2565),
which is an unmerged proposal, not a published upstream fix. A simple branch
containing literals and ordinary stars absorbs its own repetitions. Removing
that redundant outer repetition avoids the nested unbounded quantifiers while
preserving ordinary matching. Capture mode uses the existing conservative
literal safeguard, since repeated captures cannot be preserved by collapsing.

Additional local hardening applies that existing literal safeguard to complex
single-branch wildcard-star forms that cannot safely use the equivalence
rewrite, including globstars, paths and character classes. Those risky forms
are deliberately treated as literal text, consistent with upstream's existing
handling of other unsafe repeated extglobs. Quoted/escaped stars remain distinct
from wildcard stars. This is a bounded security backport, not a claim that
arbitrary user-provided regular expressions or explicit safeguard opt-outs are
safe. Current Tauridium build-tool callers do not request that opt-out.

Controls require the exact parser hash, a complete integrity manifest, the
explicit root override and actual resolution by Vite, Vitest, tinyglobby and
fdir. Nested unpatched copies are rejected. Every production frontend build
executes compatibility and exploit cases in child processes with deadlines.
An independent comparison against the checksum-verified upstream package
matched **843,480** short-input results across normal, dot, Windows, Bash,
substring and case-insensitive options. Long failing inputs and complex
wildcard-star variants are tested under deadlines; frontend tests and complete
production builds remain required.

The canonical audit still executes the complete, all-severity `npm audit` graph
against the official registry, explicitly including development, optional and
peer dependencies. A separate current npm bulk query for
the original 4.0.7 version keeps the advisory visible even though npm does not
report local package links. Only the exact known advisory metadata and exact
verified backport are assessed; new or changed advisories, source drift,
bypassed resolution and an expired review fail closed. The new assessment is
reviewed on **18 November** and expires **30 November 2026**. It does not extend
the earlier deepmerge, zbus or builder RSA deadlines. Replace the backport with
a supported upstream release after compatibility review when one is available.

### Consistent reporting across supported npm versions

npm10 can report a patched local link and its dependent packages against the
original version, while npm11 can omit local links from its audit report.
Canonical initialization, routine audits and CI therefore use
`tools/audit_npm.py`. It executes both exact backport controls and current
upstream queries, then scans the complete graph without severity or dependency
omission. Direct findings are accepted only when their full advisory metadata
and installed paths exactly match an executed, verified backport assessment.
A transitive report is assessed only when every dependency path ends at one
of those verified facts. Unknown direct advisories, mixed findings, unpatched
copies, cycles, missing counts, malformed output and scanner failures close
the gate. The report preserves npm's raw exit code and every assessed graph
entry; it does not relabel npm's raw finding count as zero.

The same actual source was checked with checksum-verified npm10.9.4 and the
pinned npm11 environment. npm10 returned its seven known propagated findings;
the full gate passed only after exact patch/exploit/live-advisory controls.
npm11 returned no raw findings and passed the same controls. Raw `npm audit`
on an older npm may continue to describe the modified local source as the
upstream release; the canonical report explains that distinction explicitly.
