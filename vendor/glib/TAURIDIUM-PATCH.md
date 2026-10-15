# GLib 0.18.5 security backport

Published crate SHA-256:
`233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5`.
Original MIT license and upstream source are preserved. Compiler-suggested
explicit elided lifetimes and redundant type-parenthesis removal keep the
old ABI family warning-free on Rust 1.97.1 without lint suppressions. Unicode
test fixtures use equivalent Rust escapes to pass the project's prose gate.

The only functional change is the upstream two-line fix for
[RUSTSEC-2024-0429](https://rustsec.org/advisories/RUSTSEC-2024-0429.html):
`VariantStrIter::impl_get` supplies a mutable pointer out-argument to
`g_variant_get_child`. Passing an immutable reference permitted optimization
to discard the C write and dereference null. See
[gtk-rs-core PR 1343](https://github.com/gtk-rs/gtk-rs-core/pull/1343).

GTK3/WebKitGTK requires the 0.18 ABI family; replacing it with GLib 0.20 alone
is not compatible. This path patch repairs the affected implementation without
pretending that an unpatched registry release is fixed. Optimized Tauridium
tests exercise next/nth/last/next_back/nth_back. Retire this patch when the
complete native GTK/WebKit dependency family can be upgraded together.
