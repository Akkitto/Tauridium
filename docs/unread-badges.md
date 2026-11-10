# Service unread badges

Sidebar badges represent the unread state reported by a service. They are separate
from Windows notification popups and are never cleared just by selecting a service.
An open chat can still contain unread messages; other chats can still be unread.

## Signals and settings

- The standard browser `navigator.setAppBadge(count)` and `clearAppBadge()` APIs
  update Tauridium's per-service badge. Zero explicitly clears it. A call without
  a count shows an activity indicator (represented as 1). Once a page uses this
  explicit API, that signal takes precedence over recipe DOM estimates until the
  next page navigation. Sites must keep their reported state current.
- Otherwise the immutable service recipe supplies direct and indirect counts.
  Recipe initialization waits for the document to be parsed, then checks continue
  periodically. The native poller samples the latest state every two seconds.
- **Unread badge** controls whether the service appears in the sidebar/dock count.
  **Indirect message badge** additionally includes group/channel activity when the
  service reports it separately; off by default. Standard browser APIs provide a
  single total, so Tauridium cannot split that total into message categories.
- Muted badges keep the existing global **Unread badges for muted services**
  preference. Notification popup settings remain independent of badge counts.

## Telegram and Discord

Hosted Telegram Web A now runs its browser badge path. It previously detected the
embedding Tauri marker and sent counts to Telegram's unrelated desktop commands.
Only `web.telegram.org` gets this compatibility correction; remote native-command
permissions remain closed. Web K keeps its pinned recipe and can read its version
metadata after document parsing. No account data or cache migration is needed.

Discord distinguishes direct mentions from an unread-channel activity indicator.
Reading mentions clears the badge with indirect activity disabled, even if another
channel is still unread. With indirect activity enabled, its indicator remains
until Discord reports that activity read. GitHub continues using its pinned recipe,
with a small reviewed adapter for its header indicator: use it as a direct unread
fallback when no numeric notification count is available, without double-counting
it alongside a numeric count. This preserves the default GitHub badge on other
pages even when indirect/group badges are off. Raw pinned cache files and personal
GitHub recipes are not rewritten.

## Verification and limits

`just test` executes the production injected scripts with unmodified public
GitHub/Discord/Telegram recipes and synthetic unread/read transitions, plus native
count parsing, explicit-zero and settings-boundary regressions. Tests use no real
accounts or messages. Browser API support is generic and needs no recipe for sites
that use it; arbitrary sites still need a maintained recipe or explicit badge API.

Website DOM/API changes, disconnected clients and hibernated services cannot be
made universally reliable by a desktop wrapper. If a badge disagrees with the
service, first check other unread chats/channels and the indirect preference, then
reload that service. Report the service, Web A/K where relevant, Tauridium version,
platform and whether all chats were marked read. Do not include private messages,
sessions, credentials or a personal profile export.
