# Quickstart: Validating ad and tracker blocking

## Prerequisites

- Linux with WebKitGTK 2.40+ (installed 2.54.2), `just`, Python 3, Node, pinned Rust 1.97.1.
- Windows 11 host for the Windows gate (not available on the development machine).

## Linux

1. `python3 tools/adblock_smoke.py` serves a fixture page that requests a listed ad host, an exception-listed host and a clean host; expect blocked, loaded, loaded (SC-001).
2. Toggle global, per-service and allowlist settings through the probe; expect the blocked request to reappear without restart and the `Saved` confirmation each time (FR-002, FR-003, FR-010).
3. Disable the network and restart; expect blocking from cache and startup within 5% of baseline (SC-003).
4. Serve a corrupt list; expect the previous list to stay active and exactly one error (SC-006).

## Windows 11 (release gate)

1. Run the benchmark harness with real EasyList and EasyPrivacy; record p50/p99 per request (S2).
2. Repeat steps 1 and 2 above through the real app; record results in `research.md`.

## Unit and regression

`just test`, plus `just rust-supply-chain` and `python3 tools/audit_dependencies.py`. Compare backup digests of a pre-feature backup before and after (SC-005).
