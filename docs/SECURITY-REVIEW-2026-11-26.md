# Dependency and privilege review: Show in folder

The application adds a direct Linux dependency edge to **libc 0.2.191**, already
present in the exact lock. No package record, existing dependency edge, version,
source or checksum changes. The Windows Shell/COM features use the already locked
windows-sys bindings. Linux reuses existing GTK/GIO; no new D-Bus runtime is shipped.
The development-only zbus service fixture remains test-only.

Linux portals receive an O_PATH | O_NOFOLLOW descriptor: it cannot read contents,
block on a FIFO or follow a replaced final symlink. Native platforms reject missing,
nonregular and final-symlink targets. The overlay-only command accepts a current
completion ID, never a renderer path or URI. Paths remain in the bounded native
queue and are removed on dismissal/clear/summary; errors are typed and path-free.
No file execution, generic shell/open API, service permission or Flatpak sandbox
permission is introduced. Native selection necessarily tells the trusted desktop
file manager the location requested by the user.

Application lock SHA-256: `05ef281aaa312d95bbff4cd453c84c8312e8056f302af12c44a0eb683669c40c`.
Builder lock is unchanged. Existing exact-package/version/kind assessments and their deadlines, including
the 30 November 2026 reviews, remain unchanged. The policy binding reflects only the
reviewed root libc edge; unknown findings and unsoundness continue to fail closed.

The current online whole-lock gate passed at `2026-11-26T10:30:04.564025+00:00` against
official RustSec database `c9f6c91a44dbad9d71742329e9df061279f9c4be`. Both full locks
were scanned without target/severity filters or advisory ignores. No new finding
or assessment was introduced. Existing application maintenance assessments and
the explicitly bounded, key-free SDK RSA assessment remain visible and enforced.
The live npm backport checks also passed.
