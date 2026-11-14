//! Safe wrapper over WebKitGTK's `WebKitUserContentFilterStore` and the
//! `UserContentManager` filter calls.
//!
//! The safe `webkit2gtk` crate does not expose these APIs, so this module calls
//! the raw `webkit2gtk-sys` bindings. It is the only place in the ad blocking
//! feature that contains `unsafe`. All calls must run on the GTK main thread;
//! completion callbacks are delivered on the thread-default main context.

use std::ffi::{CStr, CString};
use std::path::Path;

use gtk::gio;
use gtk::glib::{self, translate::ToGlibPtr};
use webkit2gtk::UserContentManager;
use webkit2gtk_sys as ffi;

/// A compiled WebKit content filter. Owns one reference.
pub(crate) struct Filter(*mut ffi::WebKitUserContentFilter);

impl Filter {
    /// Takes ownership of one reference. `ptr` must be a valid, non-null filter.
    fn from_owned(ptr: *mut ffi::WebKitUserContentFilter) -> Self {
        Self(ptr)
    }

    /// The identifier the filter was saved under.
    pub(crate) fn identifier(&self) -> String {
        // SAFETY: `self.0` is a valid filter for the lifetime of `self`; the
        // returned string is owned by the filter and copied before we return.
        unsafe {
            let id = ffi::webkit_user_content_filter_get_identifier(self.0);
            if id.is_null() {
                String::new()
            } else {
                CStr::from_ptr(id).to_string_lossy().into_owned()
            }
        }
    }

    /// Attaches the filter to a content manager (and so to its web views).
    pub(crate) fn add_to(&self, manager: &UserContentManager) {
        // SAFETY: both pointers are valid; WebKit takes its own reference.
        unsafe { ffi::webkit_user_content_manager_add_filter(manager.to_glib_none().0, self.0) }
    }
}

impl Clone for Filter {
    fn clone(&self) -> Self {
        // SAFETY: `self.0` is valid; ref returns the same pointer with +1.
        Self(unsafe { ffi::webkit_user_content_filter_ref(self.0) })
    }
}

impl Drop for Filter {
    fn drop(&mut self) {
        // SAFETY: we own exactly one reference.
        unsafe { ffi::webkit_user_content_filter_unref(self.0) }
    }
}

type FilterCallback = Box<dyn FnOnce(Result<Filter, String>)>;
type DoneCallback = Box<dyn FnOnce(Result<(), String>)>;

/// Removes every filter with this identifier from a content manager.
pub(crate) fn remove_by_id(manager: &UserContentManager, identifier: &str) -> Result<(), String> {
    let id = CString::new(identifier).map_err(|_| "Filter identifier contains NUL".to_string())?;
    // SAFETY: manager and id are valid for the duration of the call.
    unsafe {
        ffi::webkit_user_content_manager_remove_filter_by_id(manager.to_glib_none().0, id.as_ptr())
    };
    Ok(())
}

/// Handle to an on-disk store of compiled filters.
pub(crate) struct FilterStore(*mut ffi::WebKitUserContentFilterStore);

impl FilterStore {
    /// Opens (creating on demand) the store rooted at `path`.
    pub(crate) fn new(path: &Path) -> Result<Self, String> {
        let text = path
            .to_str()
            .ok_or_else(|| "Filter store path is not valid UTF-8".to_string())?;
        let c_path =
            CString::new(text).map_err(|_| "Filter store path contains NUL".to_string())?;
        // SAFETY: c_path is valid for the call; WebKit copies it.
        let ptr = unsafe { ffi::webkit_user_content_filter_store_new(c_path.as_ptr()) };
        if ptr.is_null() {
            return Err("WebKit could not create the content filter store".into());
        }
        Ok(Self(ptr))
    }

    /// Compiles `json` (WebKit content blocking rules) and saves it under
    /// `identifier`. `done` runs on the main context with the compiled filter.
    pub(crate) fn save(
        &self,
        identifier: &str,
        json: &[u8],
        done: impl FnOnce(Result<Filter, String>) + 'static,
    ) {
        let Ok(id) = CString::new(identifier) else {
            done(Err("Filter identifier contains NUL".into()));
            return;
        };
        let bytes = glib::Bytes::from(json);
        let callback: Box<FilterCallback> = Box::new(Box::new(done));
        // SAFETY: store and id are valid; GBytes is ref'd by WebKit; user_data is
        // a leaked box reclaimed exactly once in `on_save_done`.
        unsafe {
            ffi::webkit_user_content_filter_store_save(
                self.0,
                id.as_ptr(),
                bytes.to_glib_none().0,
                std::ptr::null_mut(),
                Some(on_save_done),
                Box::into_raw(callback).cast(),
            );
        }
    }

    /// Loads a previously saved filter.
    pub(crate) fn load(
        &self,
        identifier: &str,
        done: impl FnOnce(Result<Filter, String>) + 'static,
    ) {
        let Ok(id) = CString::new(identifier) else {
            done(Err("Filter identifier contains NUL".into()));
            return;
        };
        let callback: Box<FilterCallback> = Box::new(Box::new(done));
        // SAFETY: as in `save`; reclaimed once in `on_load_done`.
        unsafe {
            ffi::webkit_user_content_filter_store_load(
                self.0,
                id.as_ptr(),
                std::ptr::null_mut(),
                Some(on_load_done),
                Box::into_raw(callback).cast(),
            );
        }
    }

    /// Deletes a saved filter from disk.
    pub(crate) fn remove(&self, identifier: &str, done: impl FnOnce(Result<(), String>) + 'static) {
        let Ok(id) = CString::new(identifier) else {
            done(Err("Filter identifier contains NUL".into()));
            return;
        };
        let callback: Box<DoneCallback> = Box::new(Box::new(done));
        // SAFETY: as in `save`; reclaimed once in `on_remove_done`.
        unsafe {
            ffi::webkit_user_content_filter_store_remove(
                self.0,
                id.as_ptr(),
                std::ptr::null_mut(),
                Some(on_remove_done),
                Box::into_raw(callback).cast(),
            );
        }
    }
}

impl Drop for FilterStore {
    fn drop(&mut self) {
        // SAFETY: we own one reference to the GObject.
        unsafe { glib::gobject_ffi::g_object_unref(self.0.cast()) }
    }
}

/// Converts and frees a `GError`, returning its message.
///
/// # Safety
/// `error` must be null or a valid `GError` that the caller owns.
unsafe fn take_error(error: *mut glib::ffi::GError, fallback: &str) -> String {
    if error.is_null() {
        return fallback.to_string();
    }
    // SAFETY: guaranteed by the caller.
    unsafe {
        let text = (*error).message;
        let message = if text.is_null() {
            fallback.to_string()
        } else {
            CStr::from_ptr(text).to_string_lossy().into_owned()
        };
        glib::ffi::g_error_free(error);
        message
    }
}

unsafe extern "C" fn on_save_done(
    source: *mut glib::gobject_ffi::GObject,
    result: *mut gio::ffi::GAsyncResult,
    user_data: glib::ffi::gpointer,
) {
    // SAFETY: user_data is the box leaked in `save`, reclaimed once here.
    let callback: Box<FilterCallback> = unsafe { Box::from_raw(user_data.cast()) };
    let mut error = std::ptr::null_mut();
    // SAFETY: source is the store that started the operation.
    let filter = unsafe {
        ffi::webkit_user_content_filter_store_save_finish(source.cast(), result, &mut error)
    };
    if filter.is_null() {
        // SAFETY: error was set by the failing call.
        callback(Err(unsafe {
            take_error(error, "WebKit rejected the filter rules")
        }));
    } else {
        callback(Ok(Filter::from_owned(filter)));
    }
}

unsafe extern "C" fn on_load_done(
    source: *mut glib::gobject_ffi::GObject,
    result: *mut gio::ffi::GAsyncResult,
    user_data: glib::ffi::gpointer,
) {
    // SAFETY: as in `on_save_done`.
    let callback: Box<FilterCallback> = unsafe { Box::from_raw(user_data.cast()) };
    let mut error = std::ptr::null_mut();
    // SAFETY: source is the store that started the operation.
    let filter = unsafe {
        ffi::webkit_user_content_filter_store_load_finish(source.cast(), result, &mut error)
    };
    if filter.is_null() {
        // SAFETY: error was set by the failing call.
        callback(Err(unsafe {
            take_error(error, "WebKit could not load the filter")
        }));
    } else {
        callback(Ok(Filter::from_owned(filter)));
    }
}

unsafe extern "C" fn on_remove_done(
    source: *mut glib::gobject_ffi::GObject,
    result: *mut gio::ffi::GAsyncResult,
    user_data: glib::ffi::gpointer,
) {
    // SAFETY: as in `on_save_done`.
    let callback: Box<DoneCallback> = unsafe { Box::from_raw(user_data.cast()) };
    let mut error = std::ptr::null_mut();
    // SAFETY: source is the store that started the operation.
    let ok = unsafe {
        ffi::webkit_user_content_filter_store_remove_finish(source.cast(), result, &mut error)
    };
    if ok == glib::ffi::GFALSE {
        // SAFETY: error was set by the failing call.
        callback(Err(unsafe {
            take_error(error, "WebKit could not remove the filter")
        }));
    } else {
        callback(Ok(()));
    }
}
