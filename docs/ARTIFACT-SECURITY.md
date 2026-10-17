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
historical blobs and recognized containers inside those blobs. Nesting context and
global expansion budgets continue through Git/archive boundaries. Local hooks,
credentials, aliases, remotes, reflogs, unrelated
refs and unreachable producer objects never belong in a public source ZIP.
Approved objects are repacked from scratch with fixed compression/delta settings
and a single packing thread before their hashes enter the source manifest. This
removes transport-pack scheduling and producer compression as ZIP inputs; no
producer configuration is copied or normalized into public Git metadata.

Package recognition is signature-based at every boundary, not a top-level filename
shortcut: renamed/nested DEB, RPM, compound/MSI and AppImage payloads are decoded.
MSI databases identified inside compound containers also receive auxiliary table
and stream inspection; a missing reader fails closed rather than dropping coverage.
ZIP recognition also checks the bounded end structure, so a renamed or historical
ZIP with prepended bytes cannot fall back to raw compressed-byte inspection.
Public ZIPs deliberately reject preambles, concatenated archives, unindexed local
records, overlaps and trailing container data. Normal ZIPs, comments, ZIP64 and
streaming data descriptors remain supported; CRC/member safety checks still apply.

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
Content deduplication is separate from OCR and scoped vector transformations. An
image seen first outside evidence still requires OCR at its evidence occurrence;
an OCR-completed set avoids duplicate work without dropping that obligation.
Container traversal is cached by content and inherited evidence context, not content
alone or arbitrary path aliases. A later evidence alias replays descendant obligations,
including through Git object identities and renamed PNGs recognized by signature.
At most two inherited contexts exist per container; all traversals retain depth and
aggregate budgets. Scoped public-vector substitution changes scan views only, never
the original container bytes consumed by archive parsers.

The only private-key-shaped exclusions are exact normalized, publicly documented
GnuTLS known-answer self-test constants, restricted to decoded libgnutls payloads
or their upstream self-test source. `data/public-crypto-selftests.json` records
immutable upstream source URLs/hashes and the exact vector hashes. No arbitrary
private key or whole detector rule is ignored. Public test vectors must never be
used as application authentication keys.

Synthetic regression controls cover plaintext, UTF-16, base64, nested archives,
deleted compressed approved Git-history secrets, inline-ignore bypass attempts, NSIS budgets,
Git-hook rejection, creation of auxiliary files and MSI fallback constraints.
Set `TAURIDIUM_ARTIFACT_SECURITY_TOOLS` to the checksum-verified tool directory when
running these integration controls. CI must run them, not accept environment skips.
Controls include a real nested/renamed MSI property, direct/nested/deleted-history
DEB secrets and actual OCR/Gitleaks rejection in both duplicate orders and across
artifacts, including nested-container aliases and deleted historical PNGs. Prefixed
and unindexed compressed ZIP controls fail closed at direct/nested/history boundaries.
Security CI installs msitools/wixl, Tesseract, ImageMagick and DejaVu Mono
for those controls; portable unit runs without those tools explicitly report skips.

Untrusted parser/OS/process exception strings never belong in public diagnostics:
they can contain private member names, paths or argv. The public scanner boundary
emits stable error categories; only explicitly reviewed static rejections and
rule/payload-hash findings use the detailed public channel. A valid outer archive
with a corrupt nested archive is regression-tested through the actual CLI to
ensure its sensitive synthetic member name is not printed before rejection.
