//! Native stacking support for GTK-managed overlay children.

use gtk::prelude::*;

pub(crate) fn prepare_parent_for_stacking(window: &gtk::gdk::Window) {
    // X11 needs a native child for sibling stacking. On Wayland, promoting
    // GtkOverlay's ordinary child window can create an unintended xdg_toplevel
    // and stall the frame clock shared with the application window. Let GTK
    // manage that child's native role on every other backend.
    if window.display().type_().name() == "GdkX11Display" {
        window.ensure_native();
    }
}
