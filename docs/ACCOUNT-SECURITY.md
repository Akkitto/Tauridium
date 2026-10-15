# Account session security

Ferdium account tokens stay outside JavaScript. “Remember using OS credential
store” is enabled by default at sign-in. Tauridium stores the token in Windows
Credential Manager, macOS Keychain, or an unlocked Linux Secret Service (such as
GNOME Keyring or a compatible KWallet Secret Service). The private session.json
contains a random credential reference, not the token. Each token is bound to its
server URL. Website cookies and service sessions remain separate WebView data.

If the store is unavailable or locked, remembering fails visibly. Unlock/start
the desktop's credential service and retry. Alternatively, uncheck the option:
the account token then lives only in this application's memory until exit or
sign-out. Tauridium never silently substitutes plaintext credential storage.
Local/accountless mode does not require a credential service.

Legacy plaintext sessions are migrated before use. If migration cannot finish,
the original is protected with private file permissions, retained for recovery,
and not silently used. Unlock the store, or sign in again with remembering
unchecked to replace the legacy session. Successful migration removes obsolete
session staging files. This is not secure erasure of previously exposed bytes,
filesystem snapshots, backups or storage-device history; revoke/rotate an account
token if it may already have been disclosed.

Sign-out disables automatic account restoration even when vault cleanup fails.
Cleanup errors and retained references are reported; unlock the store and sign
out again to retry, or remove Tauridium's dev.brani.tauridium.account-session
entries using the OS credential manager. Do not publish profile data, personal
recipe scripts, service sessions, backups, or private recovery archives.

Account authentication requires HTTPS. HTTP loopback development servers remain
supported. Other HTTP servers require the explicit development-network warning
acknowledgement at sign-in; it exposes account credentials to the network and is
not suitable for production. That acknowledgement is remembered only with a
remembered account session. URLs containing userinfo, query strings or fragments
are rejected before authentication. HTTPS redirects cannot downgrade to HTTP.

Flatpak grants only the standard org.freedesktop.secrets credential-service
name, not unrestricted session-bus access. NixOS/Home Manager users need their
desktop's normal unlocked Secret Service if they choose remembered server use.
