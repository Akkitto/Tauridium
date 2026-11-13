# Phase 0 Research: Ad and Tracker Blocking

Findings come from reading this repo, the vendored crates and the locally cached `adblock` 0.13.5 and `webkit2gtk(-sys)` 2.0.2 sources. Nothing here was run in a live WebView yet; items needing that are **spikes** that MUST be resolved before dependent tasks start.

## Findings about the current code and crates

- Service webviews are built in `src-tauri/src/main.rs` (~line 2224); spelling applies per-webview via `with_webview` (`spelling.rs`, `apply_to_webview`) and live via `apply_spelling_settings` (~4574). Reuse both patterns.
- `adblock` 0.13.5 is MPL-2.0, edition 2024, not in `Cargo.lock`. It has a `content-blocking` feature (module `content_blocking`: `CbRule`, `CbAction`, `CbTrigger`, conversion with a `CbRuleCreationFailure` for unsupported filters). Default features: `embedded-domain-resolver`, `full-regex-handling`, `single-thread`. Transitive crates include flatbuffers, selectors, cssparser, idna, addr, rustc-hash, seahash, memchr, thiserror 1.x.
- `webkit2gtk` 2.0.2 safe crate: `UserContentFilterStore` and `UserContentManager::add_filter`/`remove_filter` are commented out ("Ignored"). `webkit2gtk-sys` 2.0.2 does expose `webkit_user_content_filter_store_{new,save,load,remove,fetch_identifiers}` and `webkit_user_content_manager_{add,remove}_filter(_by_id)`. The installed WebKitGTK is 2.54.2, so the API exists at runtime.
- `vendor/wry/src/webview2/mod.rs` (~1018-1060) registers `WebResourceRequested` filters and the handler only for custom protocols. Ordinary traffic needs a separate filter (`*`) and handler.
- `webview2-com` and `windows` are not direct dependencies of `src-tauri` (only `windows-sys`); they are present transitively through wry.

## Decisions

### D1. One rule engine, native enforcement per platform
- **Decision**: Parse lists once with `adblock`; enforce natively where possible (Linux/macOS content rule lists) and via the in-process `Engine` on Windows.
- **Rationale**: Native enforcement keeps matching off our threads and out of the UI hot path; Windows has no native rule-list API.
- **Alternatives**: JS-injected blocking (cannot block network); local filtering proxy (breaks isolation and TLS, heavy); Engine matching on every platform via a request hook (no such hook exists on WebKitGTK sandboxed WebProcess without an extension).

### D2. Linux through `webkit2gtk-sys` FFI
- **Decision**: Add a direct dependency on `webkit2gtk-sys` (same locked version/features) and wrap the store/manager calls in one small unsafe module; compile rules to JSON via `content-blocking`, `store_save` once per list-set hash, `store_load` and `add_filter` per webview.
- **Rationale**: Only route to native filters without a new native crate. Direct dependency on an already locked crate is the constitution's preferred form.
- **Alternatives**: New safe wrapper crate (new supply chain); patching `webkit2gtk` (vendoring burden).

### D3. Windows through a `*` request handler in `with_webview`
- **Decision**: Prefer a `with_webview` hook over patching vendored wry; match with a shared `Engine` snapshot held behind an atomic swap; never read disk or network in the handler.
- **Rationale**: Keeps `vendor/wry` untouched (constitution II). Requires direct `webview2-com` and `windows` at locked versions.
- **Alternatives**: Patch wry (documented patch, harder upgrades). Decide after S2 if `with_webview` timing is wrong.

### D4. Settings and state shape
- **Decision**: `adblockEnabled`, `adblockLists` (ids), `adblockCustomLists` (URLs), `adblockAllowlist` (hosts) globally; `serviceAdblock = { <serviceId>: { enabled?, allowlist? } }` per service; absent means inherit. Counters are session-only memory.
- **Rationale**: Mirrors `serviceSpellcheck`; additive and optional so absent differs from empty.

### D5. List management
- **Decision**: Rust downloads over HTTPS only with size and time limits, validates by parsing (non-empty, rule count threshold, no parse-fatal), writes atomically, keeps the last good copy, and records `lastError` once per failure episode. Compile/convert runs on a worker thread; startup uses cache only and schedules a background refresh.
- **Alternatives**: Bundling lists in the binary (stale, licence/size); refreshing on the UI thread (violates FR-007/FR-009).

### D6. Allowlist and per-service disable in native rules
- **Decision**: Per-service disable = do not attach the filter. Site allowlist on Linux/macOS = `ignore-previous-rules` with `if-top-url`/`if-domain` appended after the list rules (conversion helper `ignore_previous_fp_documents` exists). On Windows the handler checks the top-level site first.
- **Open**: confirm `if-top-url` semantics on WebKitGTK in S1.

### D7. Live toggle on Linux
- **Decision**: Toggling removes or re-adds the filter on the live `UserContentManager` and then reloads is NOT forced; the change applies to subsequent requests. S1 verifies that remove/add on a live view takes effect without reload.

## Spikes (must pass before dependent tasks)

- **S1 Linux**: Convert real EasyList and EasyPrivacy with `content-blocking`; record rule count, skipped-rule count, compile time, store size, memory, first-load time; confirm a local fixture ad request is blocked, an exception rule is honoured, `if-top-url` allowlist works, and live remove/add takes effect. Also record WebKit's rule-count limit (Safari-family limits can be 150k; confirm on WebKitGTK) and the splitting strategy if exceeded. Pass: blocked, no load regression above SC-002/SC-003.
- **S2 Windows**: On real Windows 11, add a `*` filter and handler via `with_webview`; match with `Engine`; measure per-request latency p50/p99 and page-load impact with a real list, with and without request-source-kinds; confirm blocking returns a 4xx/empty response without hanging subresources and that service workers and iframes are covered. Pass: p99 within the plan target; otherwise reduce list size or restrict the handler to resource contexts that matter. Cannot be run on this Linux host.
- **S3 License and supply chain**: Review MPL-2.0 against `LICENSE`/distribution policy; run `tools/check_rust_supply_chain.py` and `tools/audit_dependencies.py` with `adblock` added; regenerate Flatpak/Nix sources; confirm the new tree adds no blocked crates. Edition 2024 compatibility with the pinned toolchain is already satisfied (Rust 1.97.1).
- **S4 macOS**: Confirm `WKContentRuleListStore` access through `objc2-web-kit` and its lock footprint. Not buildable here; ship labelled untested or defer the platform if S3 shows excess cost.
- **S5 Counters**: Determine whether blocked counts can be observed on WebKitGTK (content filters do not report blocked loads); if not, show counts on Windows only or omit the counter on Linux (do not offer a control the platform cannot honour, principle VII).

## Spike results (Linux, measured 2026-11-14)

Host: Fedora, WebKitGTK 2.54.2, Wayland session, Rust 1.97.1. Lists: EasyList (version 202611131942) and EasyPrivacy fetched the same day. The conversion and probe programs lived in the scratchpad (not in the repository); the FFI wrapper they exercise is `src-tauri/src/adblock/linux_filter.rs`.

### S3 License and supply chain: PASS
- Adding `adblock` 0.13.5 (features `content-blocking`, `embedded-domain-resolver`, `full-regex-handling`, `single-thread`) adds exactly 9 packages: `adblock`, `addr`, `arrayvec`, `either`, `flatbuffers`, `itertools`, `psl`, `psl-types`, `seahash`. No existing package changed version or was removed. A few existing dependency edges were re-pointed by the resolver (for example `cssparser-macros` now uses the already locked `syn` 3.0.9).
- Adding `webkit2gtk-sys` 2.0.2 as a direct Linux dependency changed no package.
- `tools/check_rust_supply_chain.py` passes. `cargo audit` against RustSec (commit 4ef2df8e, 2026-11-13) reports no vulnerabilities for the new lock; the only warnings are four pre-existing unmaintained notices (`proc-macro-error`, `zbus_names`, `zvariant`, `zvariant_derive`) unrelated to this change. `tools/audit_dependencies.py` passes online after re-binding `applicationLockSha256`.
- License: `adblock` is MPL-2.0 (file-level copyleft; used unmodified as a dependency). The tree already contains MPL-2.0 crates (`cssparser`, `selectors`), so no new license class is introduced. The project is MIT.
- Still to do: Flatpak and Nix source regeneration (T047).

### S1a Conversion: PASS
- EasyList + EasyPrivacy: 134,360 non-comment lines, of which about 24,800 are cosmetic or scriptlet rules (ignored, network-only parse) and about 109,600 are network rules.
- Converted: 106,288 filters into 106,430 content-blocking rules (about 11.1 MB JSON) in about 116 ms. About 3,300 network rules (roughly 3%) have no content-blocking equivalent and are skipped. The skipped count is estimated from line classification, since the crate does not report it directly; T018 must report an exact figure.

### S1b/S1c Engine and behaviour on real WebKitGTK: PASS
Local fixture server, one page with a listed script, an exception-listed script, a clean script, a listed image and a cross-host iframe containing a listed script. Ground truth is the server's request log.
- Listed requests are blocked, including inside the cross-host iframe; exception rules are honoured; clean requests load.
- Live toggle: `remove_from` then `add_to` on a running view takes effect for the next navigation without recreating the view or its context (reload of the page is needed for the current page).
- Allowlist: an appended `ignore-previous-rules` rule with `if-top-url` working as a per-site allowlist (page on the allowed top URL loads the ad script; the same page on another host stays blocked).
- U1 first-navigation race: with the filter loaded asynchronously and `load_uri` issued before it attached, the first navigation was still blocked in 3 of 3 runs. This is not a documented guarantee, so T022 still attaches before the first navigation, which is deterministic and cheap.
- Rule limit: one filter accepts 150,000 rules; 200,000 fails with "Too many rules in JSON array." The default lists (about 106k) fit. If more lists are added, rules must be split across several filters, and an exception rule must live in the same filter as the rules it negates because `ignore-previous-rules` does not cross filters. The compiler should report the rule count and refuse over-limit sets with a clear message.
- Compile cost: `store.save` for the full set took about 3.5 s (4 s at 150k rules) and ran without blocking the main loop; compiled filters are cached on disk and `store.load` took 4 ms.
- Memory: compile happens in the application process: total resident memory rose by roughly 330-430 MB transiently and was still about 90 MB above baseline four seconds later (the probe also held the JSON and parsed lists). Once compiled, attaching the cached filter costs almost nothing per view: three isolated web contexts each used about 166 MB (network plus web process) with or without the full filter, with unchanged load time (about 120-137 ms). Decision for T018: compile only when the list set changes, off the interaction path, and measure whether a short-lived helper process is needed to keep the transient out of the main process; record the result.
- Page timing on the local fixture was unchanged by the filter (about 120 ms either way). Real-page timing is tracked under T059.

### S5 Blocked counter on Linux: NOT AVAILABLE
Connecting to `resource-load-started`, `failed` and `finished` shows no event at all for requests blocked by a content filter. WebKitGTK cannot report blocked loads, so the per-service blocked counter is not offered on Linux (T045 returns null and the UI explains why).

### Decisions from the spikes (T011)
- Curated default lists: EasyList and EasyPrivacy (`https://easylist.to/easylist/easylist.txt`, `https://easylist.to/easylist/easyprivacy.txt`), downloaded at runtime only, never bundled.
- Default global state: off for upgraded profiles and for new profiles. Blocking can break chat and workspace services, so it is an explicit opt-in, shown prominently and one step to enable.
- Update interval: use each list's `Expires` header when present (EasyList publishes 4 days), otherwise 4 days, with a floor of 1 day.

### G1 Reference set (T059)
- Fixture page: the local fixture above (deterministic; used for pass/fail of blocking behaviour and SC-001 on known requests).
- Real pages (informational, because content changes): choose at least three ad-heavy public pages at test time and record their URLs and dates with the results.
- Method for SC-002: median of five cold loads (fresh web context each time), blocking on versus off, measured from navigation start to the load-finished signal.
- SC-007 chat/workspace services: to be named by the maintainer from the services available (candidates in this app include the chat and workspace recipes the maintainer actually uses); at least three must be exercised in T060.

## Post-implementation notes (2026-11-14)

- Maintainer verification in the running app: ad slots on dailymail.co.uk and forbes.com were blocked with default lists. This is qualitative evidence for SC-001 on real pages; the numeric SC-001/SC-002/SC-003 measurements with the T059 method were not taken.
- Instagram feed ads were not blocked, as expected: they are served first-party in the feed data. A search of EasyList, EasyPrivacy, uBlock Origin's filter lists and AdGuard's Base, Social and Annoyances lists found no active rule that hides sponsored feed posts (uBlock's `unbreak` list only carries an exception that neutralises an old AdGuard rule). Hiding them needs cosmetic filtering with our own maintained rule.
- Compiled filter size on disk: about 37 MB for EasyList plus EasyPrivacy.
- A simulated non-Linux build of the module (Linux `cfg` gates flipped) found and fixed dead-code failures that would have broken `clippy -D warnings` on Windows and macOS.
