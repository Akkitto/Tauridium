# Tauridium GTK child-view layout patch

Tauri 2.11.3 builds both its main document and additional Linux webviews in the
window's default `GtkBox`. Wry 0.55.1 vertically packs those views, ignoring child
positions and sizes. This prevents service views and download notifications from
occupying their intended rectangles.

The narrowly scoped `webkitgtk/mod.rs` patch keeps the first content view as the
normal expanding child, then wraps it in `GtkOverlay` when another webview is
created. Each additional view has its own fill-aligned `GtkFixed` overlay layer,
so GTK can order overlapping WebKit surfaces reliably. Their bounds
update both the fixed-container position and the child size request. Overlay
children do not increase the window's minimum size. Reparenting uses that same
layering and does not show hidden service views or take focus. Destroying a view
also removes its empty GTK layer. Tauridium places the toast itself in a bounded
GTK overlay rather than a fill container. Its native bin is raised after GTK
completes allocations, including late sibling mapping, without taking focus.
An explicit child-position handler preserves the measured card bounds instead
of WebKit's old preferred viewport size; overlay allocation is invalidated when
that measurement changes. The GTK signal trampoline follows gtk-rs's owned weak
closure convention, and both handlers disconnect when the renderer is destroyed.
The main content allocation schedules bounds updates off the GTK callback,
since the native window resize event precedes that layout. The local document is
reloaded once after moving to its final GTK parent so WebKit paints that surface.
The empty part of each fill container passes pointer input through, while its
WebKit child retains native input; notifications must not block the sidebar or
downloads in the service behind them.

The native production download smoke exercises actual downloads, notification
visibility, creation of another service, queued dismissals and window resizing.
Preserve the existing IPC, Proton and Windows patches when upgrading Wry; recheck
this layout patch against upstream and remove it once equivalent GTK child-view
behavior is available.

The adjacent `web_context.rs` patch keeps failure state per download rather than
per browser context, and decodes WebKit file URIs into native paths with GLib.
This prevents a failed transfer from suppressing later successes and displays
the actual local destination rather than a percent-encoded URI.
