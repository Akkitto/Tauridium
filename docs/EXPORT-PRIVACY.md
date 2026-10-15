# Export privacy and executable recipes

Service-export ZIPs are sharing aids, not a promise that arbitrary private content
can be identified automatically. Known credential fields and sensitive URL values
are filtered. Website session storage and cookies are excluded. Review the complete
ZIP, including icons, names, URLs and free-form configuration before publishing it.

Personal webview.js scripts are excluded by default. An explicit export option and
confirmation allow their inclusion, unchanged. Code can contain private literals;
automatic text replacement would both miss secrets and damage legitimate recipes.
Generated index.js stubs contain no personal script. Exported package metadata
excludes package lifecycle hooks and unrelated package fields. The manifest records
the script opt-in, actual script inclusion and requirement for privacy review.

Personal recipe imports require an explicit trust confirmation. Review the source
and author first: scripts execute inside their configured website and can read or
change signed-in service content. They are not sandboxed away from that website's
data. Service renderers are separately denied Tauridium's privileged native commands.

Full recovery backups and portable workspace/sandbox exports intentionally preserve
private service configuration and personal scripts, including legitimate proxy
credentials. They are labeled sensitive and the manual export/restore UI warns
about privacy and executable content. Keep automatic backups private as well.
File permissions are restrictive from creation, but backups are not encrypted
archives and are not intended for public release. Never upload them as build evidence.

Private full-Git development checkpoints are also not public source releases.
Public source ZIPs contain only the approved release tree and sanitized Git ancestry;
public documentation evidence is separately allowlisted and reviewed.

Remote Ferdium recipe metadata, executable scripts and default recipe icons use
the full immutable commit in data/recipe-source.json, shared by Rust and the UI.
Upstream updates require an explicit source change and review of the upstream
diff; they are not automatically accepted from a mutable branch. This is a
provenance pin, not a claim that every upstream recipe has been independently
audited. Downloads remain on demand. Their bounded caches are separated by the
revision; old unversioned caches are not executed. Existing personal recipes,
built-in recipes and user-selected service icons remain independent.
