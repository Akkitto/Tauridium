# Updater ZIP parser compatibility patch

Base: official published `tauri-plugin-updater` **2.14.0** crate, SHA-256
`7259989d4fe11b2bf51f7d671642249b1837c4ae2da1430dc713ae38f98ceeec`.
Original licenses and upstream sources are retained. The sole patch is the
optional Windows ZIP dependency requirement in `Cargo.toml`/`Cargo.toml.orig`:
`4` → exact `9.0.4`. All old ZIP crate versions are withdrawn from crates.io.
The maintained parser includes extraction and actual-byte bounds corrections.
No updater signature, signed-version, installation or platform logic is changed.
Windows builds must compile the ZIP extraction feature against this patch.
Remove this path override when a reviewed upstream release selects a maintained
ZIP parser. The upstream crate's own lockfile is provenance, not the app lock.

Sources: https://static.crates.io/crates/tauri-plugin-updater/tauri-plugin-updater-2.14.0.crate
and https://github.com/zip-rs/zip2/releases/tag/v9.0.4 .
