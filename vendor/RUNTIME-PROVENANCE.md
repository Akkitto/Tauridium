# Runtime security refresh

Verified published crates, retained licenses, and three-way preservation of local
patches from Tauri 2.11.3 / Wry 0.55.1:

| Crate | Version | Published crate SHA-256 |
| --- | --- | --- |
| tauri | 2.12.4 | f316751027fc2644221d1a448564d519efb07067fda584879d9cda966391d212 |
| wry | 0.57.0 | a819957a01b3119af85e638a38d242af76dbc87d130dca67bfd0441072e21ff0 |

Tauri's upstream channel queue is now caller-WebView scoped and purges closed
views. The sole Tauridium Tauri patch remains the configurable generic marker
documented in `tauri/TAURIDIUM-PATCH.md`. Wry retains the Linux child-layer/session
patches, mutable macOS IPC bridge, and Windows compatibility policy. The missing
upstream `v2_42` feature is declared to select WebKit's matching API correctly.
Do not remove these compatibility changes when refreshing dependencies.

The updater is pinned to maintained 2.14.0 with `requireSignedVersion: true`.
Its narrowly scoped ZIP dependency patch is documented in
`tauri-plugin-updater/TAURIDIUM-PATCH.md`; the application also uses ZIP 9.0.4.
The CLI is independently pinned to 2.12.3. Old signatures lacking the signed
version are intentionally rejected by new clients. This task does not re-sign,
publish or change historical releases; the next authorized release must use the
version-bound signer and immutable artifact verification.

See `glib/TAURIDIUM-PATCH.md` for the minimal GTK3-compatible security backport.
