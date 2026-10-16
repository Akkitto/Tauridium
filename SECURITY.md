# Security policy

## Reporting

Do not post credentials, tokens, private profiles/backups, raw diagnostic logs,
full-Git recovery archives, or working exploit details in public issues or PRs.
If GitHub offers **Report a vulnerability** on the repository's
[Security page](https://github.com/Akkitto/Tauridium/security), use that private
advisory channel and verify it is private before attaching sensitive material.
This file does not claim private reporting is enabled: the owner must activate
and verify it as part of secure release setup.

If the private reporting entry is unavailable, do not publish the report or attach
sensitive material. This repository may have public issues/discussions disabled;
they are not a promised fallback contact route. Use an already verified private
maintainer contact if you have one, otherwise wait for the owner to enable private
reporting. Do not invent an email address. Never use an application/service account
password as a test credential. The owner must verify a working private reporting
route before the next security-reviewed publication.

A useful private report identifies the version/platform, expected boundary,
minimal synthetic reproduction, impact and proposed mitigation. Prefer generated
never-issued credentials and isolated temporary profiles. Coordinate disclosure
and patched-release testing with the maintainer; no response deadline is promised.

## Support and verification

The latest published release is the primary maintenance target; historical
versions have no blanket backport guarantee. Unreleased security fixes in `master`
are not automatically available to installed applications. Follow actual release
notes rather than assuming a local commit has been published.

Windows is the primary native platform, Linux is supported, and macOS is
best-effort. Cross-compilation is not native Windows/macOS runtime validation.
See [secure releases](docs/SECURE-RELEASES.md), [build controls](docs/BUILD-SECURITY.md)
and [static artifact inspection](docs/ARTIFACT-SECURITY.md). OS vaults, webview
isolation, signatures and secret scanners each address different threats; none is
a guarantee of zero vulnerabilities, zero sensitive content, or encryption of
user-selected profile backups. Keep backups/exports private and review before sharing.
