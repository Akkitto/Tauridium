# Public artifact security gate

Public source, runtime, documentation, installers, updater signatures and metadata
must pass `tools/artifact_security.py` on an isolated Linux x64 runner before
signing, after signing/final metadata generation, and before publication. Install
the official checksum-pinned readers with `tools/security_tools.py FRESH_DIRECTORY`.
The runner additionally needs Git, msitools (`msiinfo`), and Tesseract when reviewed
public screenshot evidence is requested. Scanner versions/hashes live in
`data/security-tools.json`; do not substitute unmaintained p7zip.

The gate statically decodes ZIP, nested compressed/tar/cpio/CAB streams, MSI,
NSIS, AppImage/SquashFS, DEB and RPM payloads. It scans raw bytes, contiguous ASCII
and both UTF-16 byte orders, and base64/other encoded secrets using Gitleaks.
Source Git configuration/ref/file inventories are checked before Git is invoked;
all approved reachable Git objects are decoded and scanned, including deleted
historical blobs. Local hooks, credentials, aliases, remotes, reflogs, unrelated
refs and unreachable producer objects never belong in a public source ZIP.

No application, installer, DLL, archive script, extracted hook, maintainer script,
or reconstructed uninstaller is executed. Decoders use disposable working
directories with time, actual-byte, nesting and aggregate expansion limits;
unexpected auxiliary writes fail the gate. MSI SQL metadata export avoids the
IDT export operation that writes Binary/Icon files. The documented msitools
empty-table SQL-export failure is independently checked through a non-object
schema before a read-only IDT fallback; arbitrary decoder failures are not ignored.

NSIS solid LZMA is also independently decompressed in full with CRC and byte-budget
validation. Each file record is compared to the static decoder output. The
uninstaller is reconstructed as data using bounded stub patches and its following
record. This resolves the misleading StartMenu.dll listing size without dropping
bytes or asserting a truncated result is complete.

Private scanner payloads, raw findings and process diagnostics live in a private
temporary directory and are removed on completion/failure. Only counts and
rule/payload-hash metadata may reach CI logs; never upload raw scanner findings,
raw ignored `release/evidence`, local recovery checkpoints or unreviewed logs.
Reviewed public PNG evidence is OCR-scanned too; human privacy review and its
version-specific hash allowlist remain required. Automated scanners cannot prove
that every possible secret format, image, personal datum or novel encoding is safe.

The only private-key-shaped exclusions are exact normalized, publicly documented
GnuTLS known-answer self-test constants, restricted to decoded libgnutls payloads
or their upstream self-test source. `data/public-crypto-selftests.json` records
immutable upstream source URLs/hashes and the exact vector hashes. No arbitrary
private key or whole detector rule is ignored. Public test vectors must never be
used as application authentication keys.

Synthetic regression controls cover plaintext, UTF-16, base64, nested archives,
deleted approved Git-history secrets, inline-ignore bypass attempts, NSIS budgets,
Git-hook rejection, creation of auxiliary files and MSI fallback constraints.
Set `TAURIDIUM_ARTIFACT_SECURITY_TOOLS` to the checksum-verified tool directory when
running these integration controls. CI must run them, not accept environment skips.
