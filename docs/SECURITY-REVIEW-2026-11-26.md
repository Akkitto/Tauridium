# Dependency and privilege review: Show in folder

The application adds a direct Linux dependency edge to **libc 0.2.191**, already
present in the exact lock. No package record, existing dependency edge, version,
source or checksum changes. The Windows implementation adds a root edge to the existing locked windows
0.62.2 bindings and uses typed Shell and COM interfaces. No dependency package is
added. Explorer view identity is compared using native folder IDs. The app reads
selection state only for the requested item in its matching folder, and never
reads other folders' item names or selections. Linux reuses existing GTK/GIO; no new D-Bus runtime is shipped.
The development-only zbus service fixture remains test-only.

Linux portals receive an O_PATH | O_NOFOLLOW descriptor: it cannot read contents,
block on a FIFO or follow a replaced final symlink. Native platforms reject missing,
nonregular and final-symlink targets. The overlay-only command accepts a current
completion ID, never a renderer path or URI. Paths remain in the bounded native
queue and are removed on dismissal/clear/summary; errors are typed and path-free.
No file execution, generic shell/open API, service permission or Flatpak sandbox
permission is introduced. Native selection necessarily tells the trusted desktop
file manager the location requested by the user.

Application lock SHA-256: `73118ddeeadf3dcd28d63da064c22752f0f14a17ce8342764d58b717b0fa22ca`.
Builder lock is unchanged. Existing exact-package/version/kind assessments and their deadlines, including
the 30 November 2026 reviews, remain unchanged. The policy binding reflects only the
reviewed libc and Windows binding edges; unknown findings and unsoundness continue to fail closed.

The online whole-lock gate for the initial libc edge passed at `2026-11-26T10:30:04.564025+00:00` against
official RustSec database `c9f6c91a44dbad9d71742329e9df061279f9c4be`. Both full locks
were scanned without target/severity filters or advisory ignores. No new finding
or assessment was introduced. Existing application maintenance assessments and
the explicitly bounded, key-free SDK RSA assessment remain visible and enforced.
The live npm backport checks also passed.

The application lock with the Windows binding edge also passed a current online
audit at `2026-11-27T22:29:40.276316+00:00` against RustSec database
`c5279d0b0c9e8b70df666eb6d1edbabcfd1176bd`. No new advisory assessment was needed.
