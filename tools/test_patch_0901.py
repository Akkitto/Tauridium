"""Regression contracts for opt-in, privacy-safe download completion toasts."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
NATIVE = (ROOT / "src-tauri/src/download_toast.rs").read_text(encoding="utf-8")
DOMAIN = (ROOT / "src-tauri/src/download_notifications.rs").read_text(encoding="utf-8")
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
RENDERER = (ROOT / "src/DownloadToast.svelte").read_text(encoding="utf-8")


class DownloadToastReleaseTests(unittest.TestCase):
  def test_toasts_are_disabled_by_default_and_old_settings_merge(self):
    self.assertIn('settings.insert("downloadToasts".into(), false.into())', MAIN)
    self.assertIn('downloadToasts: false', APP)
    self.assertIn('settings.insert("downloadToastLocation".into(), "none".into())', MAIN)
    self.assertIn('download_notifications::validate_settings(settings)?', MAIN)
    self.assertIn('let mut value = default_app_settings_value()', MAIN)

  def test_only_native_successful_download_completion_enqueues_a_toast(self):
    handler = MAIN.split('builder = builder.on_download', 1)[1].split('// Per-service storage isolation', 1)[0]
    requested, finished = handler.split('DownloadEvent::Finished', 1)
    self.assertNotIn('download_toast::completed', requested)
    self.assertIn('success: true', finished)
    self.assertIn('download_toast::completed(webview.app_handle(), path.as_deref(), &filename)', finished)
    self.assertNotIn('reqwest', handler)
    self.assertIn('show_system_notification', finished)

  def test_paths_stay_in_an_app_owned_renderer_and_targeted_events(self):
    self.assertIn('EventTarget::webview(LABEL)', NATIVE)
    self.assertNotIn('.emit(', NATIVE)
    self.assertIn('EventTarget::webview("main"),\n        "download-toast-geometry",\n        height,', NATIVE)
    self.assertNotIn('.eval(', NATIVE)
    self.assertNotIn('show_service_toast_overlay', NATIVE)
    self.assertIn('webview.label() == LABEL', NATIVE)
    self.assertIn('url.host_str() == main_url.host_str()', NATIVE)
    self.assertIn('url.port() == main_url.port()', NATIVE)
    self.assertIn('NewWindowResponse::Deny', NATIVE)
    self.assertNotIn('{@html', RENDERER)

  def test_global_settings_have_all_modes_and_a_private_preview(self):
    advanced = APP.split('id="settings-advanced-downloads"', 1)[1].split('id="settings-advanced-browser"', 1)[0]
    for mode in ('none', 'directory', 'full', 'partial'):
      self.assertIn(f'value="{mode}"', advanced)
    self.assertIn('min="1" max="10"', advanced)
    self.assertIn('Until dismissed', advanced)
    self.assertIn('disabled={!appSettings.downloadToasts || downloadToastSettingsBusy}', advanced)
    self.assertIn('persisted[key] !== value', APP)
    self.assertIn('Unable to save download notification settings', APP)
    self.assertIn('downloadToastExample', advanced)

  def test_overlay_lifecycle_and_focus_do_not_depend_on_service_content(self):
    self.assertIn('.focused(false)', NATIVE)
    self.assertIn('SWP_NOACTIVATE', NATIVE)
    self.assertNotIn('.set_focus(', NATIVE)
    self.assertIn('download_toast::restack(win.app_handle())', MAIN)
    self.assertIn('download_toast::restack(app)', MAIN)
    self.assertIn('download_toast::reposition(app)', MAIN)
    self.assertIn('WindowEvent::Focused(false)', MAIN)
    self.assertIn('WindowEvent::ScaleFactorChanged', MAIN)
    self.assertIn('overlay.close()', NATIVE)

  def test_notifications_are_accessible_pauseable_and_cleaned_up(self):
    for marker in ('role="status"', 'aria-live="polite"', 'Dismiss download notification', 'Escape', 'ResizeObserver', 'observer.disconnect()', 'unlisten?.()', 'countdown?.dispose()'):
      self.assertIn(marker, RENDERER)
    self.assertIn('snapshot?.active && !hovered && !focused', RENDERER)
    self.assertIn('expectedId !== id', RENDERER)
    self.assertIn('receivedEvent', RENDERER)
    self.assertIn('void tick().then', RENDERER)
    self.assertNotIn('requestAnimationFrame', RENDERER)
    self.assertIn('pixelRatio: window.devicePixelRatio', RENDERER)
    self.assertIn('(height * pixel_ratio).ceil() / scale', NATIVE)

  def test_existing_saved_feedback_does_not_overlap_download_toasts(self):
    self.assertIn('downloadToastHeight + 36', APP)
    self.assertIn('reposition_generic_toast', MAIN)
    self.assertIn('let bottom = if height > 0.0 { height + 36.0 } else { 24.0 }', MAIN)

  def test_linux_child_views_layer_without_changing_window_minimum_size(self):
    gtk = (ROOT / 'vendor/wry/src/webkitgtk/mod.rs').read_text(encoding='utf-8')
    self.assertIn('let overlay = gtk::Overlay::new()', gtk)
    self.assertIn('overlay.add_overlay(&fixed)', gtk)
    self.assertIn('fixed.move_(&self.webview, x, y)', gtk)
    self.assertIn('fixed.child_property::<i32>(&self.webview, "x")', gtk)
    self.assertIn('Never show_all here', gtk)
    self.assertIn('overlay.set_overlay_pass_through(&fixed, true)', gtk)
    self.assertIn('parent.reorder_overlay(&view, -1)', NATIVE)
    self.assertIn('parent.add_overlay(&view)', NATIVE)
    self.assertIn('view.parent_window()', NATIVE)
    self.assertIn('gtk_position_handler(&parent', NATIVE)
    self.assertIn('parent.queue_allocate()', NATIVE)
    self.assertIn('connect_size_allocate', NATIVE)
    self.assertIn('spawn_blocking(move || crate::reposition_active(&handle))', NATIVE)
    self.assertIn('parent.connect_size_allocate', NATIVE)
    self.assertIn('parent.disconnect(handler)', NATIVE)

  def test_webkit_failure_state_is_per_download_and_destinations_are_native_paths(self):
    context = (ROOT / 'vendor/wry/src/webkitgtk/web_context.rs').read_text(encoding='utf-8')
    handler = context.split('context.connect_download_started(move |_context, download| {', 1)[1]
    self.assertIn('let failed = Rc::new(RefCell::new(false))', handler)
    self.assertIn('glib::filename_from_uri(&destination)', handler)

  def test_bursts_stale_callbacks_and_reduced_path_detail_are_safe(self):
    self.assertIn('MAX_PENDING: usize = 100', DOMAIN)
    self.assertIn('summary.count += 1', DOMAIN)
    self.assertIn('summary.location = None', DOMAIN)
    self.assertIn('redact_locations', DOMAIN)
    self.assertIn('settings_changed(&app, &previous, &value)', MAIN)
    self.assertIn('stale_dismissals_do_not_skip_files', DOMAIN)


if __name__ == "__main__":
  unittest.main()
