# Tauridium updater signing key setup

Updated 25 October 2026. Generate the key yourself on a trusted machine. Only the
public key belongs in Tauridium's repository; private values stay under your control.

## 1. Generate one password-protected key

In an interactive WSL Bash terminal with Tauridium's installed Tauri CLI:

```bash
umask 077
mkdir -p "$HOME/.tauri"
chmod 700 "$HOME/.tauri"
cargo tauri signer generate -w "$HOME/.tauri/tauridium-updater.key"
```

Enter a strong, unique password at the prompt. Do not use `--ci`, `--force`, or a
password command-line argument. Use a single-line password of at most 1022 UTF-8
bytes. If the file already exists, stop and use the
existing owner-controlled key rather than overwriting it. This creates:

- `tauridium-updater.key`: encrypted private key; keep secret.
- `tauridium-updater.key.pub`: public key; safe to commit and share.

Back up the private key and password in a password manager and an encrypted
offline backup. Test that you can recover both. GitHub must not be the only copy.
Keep private values out of Git, chat, Terraform, logs, source archives and build
environments. Do not regenerate this key for every release.

## 2. Commit the public key

Copy the complete contents of the `.pub` file into `plugins.updater.pubkey` in
`src-tauri/tauri.conf.json`. Use the encoded value, not the filename or decoded
Minisign text. Keep `requireSignedVersion` enabled.

The owner's October 2026 setup deliberately replaces the previously configured
identity with an owner-generated key. The public key alone does not prove
possession of its private counterpart.

**Migration:** installations containing the previous public key cannot accept
updates signed by the new key. Without the previous private key, users must
manually install the first release containing the new public key. Keep existing
release tags immutable and state this requirement in the next release notes.

## 3. Store the secrets in the protected GitHub environment

Open [Tauridium's environments](https://github.com/Akkitto/Tauridium/settings/environments),
select `release-signing`, then add these environment secrets privately:

| Name | Value |
| --- | --- |
| `TAURI_SIGNING_PRIVATE_KEY` | Complete encoded contents of the private `.key` file |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | The key's password |

Tauridium's isolated signer requires the key contents, not a local file path.
Keep both secrets exclusively in `release-signing`, with no repository,
organization or other environment copies. Keep the owner reviewer, `v*` tag-only
deployment policies and disabled administrator bypass on both release environments.
Normal builds remain key-free; signing happens in a separate protected job.

If both private key and password were accidentally entered as ordinary GitHub
configuration variables, replace the pair and password before first use. Moving
the same values into secrets does not establish that no earlier copy exists.
Generate the replacement under a new filename; do not overwrite the old files.

## 4. Review and activate custody confirmation

After the public-key PR passes checks and merges, use the existing infrastructure
repository in WSL:

```bash
cd /home/akito/src/codex/tauridium-github-opentofu
python3 scripts/manage.py plan --review-updater-key-scope
```

Review the private saved plan. For initial activation, expect only
`RELEASE_KEY_SCOPE_CONFIRMED` to change from `false` to `true`, with no unrelated
changes or supplemental actions. Apply the exact hash printed by that plan:

```bash
python3 scripts/manage.py apply --plan-sha256 PLAN_SHA256
```

Replace `PLAN_SHA256` with that exact hash. The helper rechecks live scopes and
protections and requires zero drift after applying. It reads secret names and
scopes, never their values. After activation, retain the explicit review flag for
plans that should keep signing enabled; omitting it proposes disabling confirmation.

## 5. Verify the next signed release

Prepare a new version/tag from the fixed, clean default branch. Leave existing
tags unchanged. Review the exact source and successful gates before approving
`release-signing`. Its output must pass independent verification against the
committed public key before you approve `release-publishing`.

Secret names alone cannot prove the password or private key is correct. If the
protected signer fails or the signature does not verify, keep publication blocked
and correct the environment privately. Never bypass signature verification.

Updater signing authenticates updates; Windows Authenticode is a separate setup.

References: [official Tauri updater guide](https://v2.tauri.app/plugin/updater/)
and [Tauridium secure releases](https://github.com/Akkitto/Tauridium/blob/master/docs/SECURE-RELEASES.md).
