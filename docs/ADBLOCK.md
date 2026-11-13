# Ad and tracker blocking

Status: Linux only in this release. Windows and macOS show a "not available on this platform yet" notice and never download lists.

## What it does

When enabled, requests that the selected filter lists identify as advertising or tracking are blocked in service webviews. Blocking is off by default. It can be switched on globally, and each service can follow the global setting, force blocking on, or force it off. Sites can be added to an allowlist (global or per service): blocking is skipped while a page from that site or one of its subdomains is open. Changes apply the next time a page loads.

## Filter lists

- Default lists: EasyList and EasyPrivacy, downloaded at runtime (never bundled). Custom lists can be added by `https://` address.
- Lists are validated before use, cached on this device and refreshed on their own `Expires` interval (default 4 days). A failed or corrupt update keeps the previous good copy and is reported once per failure episode.
- Offline start uses the cache. Nothing is downloaded until blocking is enabled somewhere.
- List addresses that are, or resolve to, loopback, private or link-local addresses are refused, and redirects are re-checked.

## Privacy

Browsing activity, visited addresses and blocked requests never leave the device. The only network traffic this feature makes is downloading the lists you selected.

## Linux behaviour and limits

- Lists are converted to WebKitGTK content filters and compiled once per set of lists (about 4 seconds for EasyList plus EasyPrivacy, in the background). The compiled filter is stored under the app data directory (`adblock/filters`, about 37 MB for the default lists) and attached to each service webview. Unused compiled filters are removed.
- One filter holds at most 150,000 rules. The default lists use about 106,000.
- Roughly 3% of network rules have no content-filter equivalent and are skipped, so coverage differs from desktop browser extensions.
- Cosmetic filtering (hiding page elements) and scriptlets are not included; they are a later release.
- There is no blocked-request counter: WebKitGTK reports no event for requests blocked by a content filter.
- A per-service allowlist compiles a separate filter for that service.

## Verification

- `just test-adblock` runs the production app against a local fixture site (no internet needed) and checks blocking on the first load, the exception rule, the allowlist, the per-service override, persistence across a restart, and offline behaviour. It needs a production build (`just build`) and an X11 display.
- Engine behaviour and rule limits were measured on WebKitGTK 2.54.2 (see `specs/002-ad-blocking/research.md`).

## Not yet verified

- Windows and macOS are not implemented and are untested.
- Numeric page-load and memory measurements inside the running app have not been taken.
- A cold first start compiles the filter in the background, so the page that was already loading is not filtered; reload it, and later loads are blocked.
