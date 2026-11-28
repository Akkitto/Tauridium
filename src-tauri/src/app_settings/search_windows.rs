//! Let the local app shell handle its Settings search shortcut.
use crate::startup_diagnostics;
use tauri::Webview;
use webview2_com::{
    AcceleratorKeyPressedEventHandler,
    Microsoft::Web::WebView2::Win32::ICoreWebView2AcceleratorKeyPressedEventArgs2,
};
use windows::core::Interface;
use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
    GetKeyState, VK_CONTROL, VK_F, VK_MENU, VK_SHIFT,
};

pub(crate) fn reserve_settings_search(webview: &Webview) -> tauri::Result<()> {
    webview.with_webview(|platform| {
        let handler = AcceleratorKeyPressedEventHandler::create(Box::new(|_, args| {
            let Some(args) = args else {
                return Ok(());
            };
            let mut key = 0;
            // SAFETY: WebView2 invokes this callback on the owning UI thread
            // with live event arguments and keyboard state for this input.
            unsafe {
                args.VirtualKey(&mut key)?;
                if key == u32::from(VK_F)
                    && GetKeyState(i32::from(VK_CONTROL)) < 0
                    && GetKeyState(i32::from(VK_MENU)) >= 0
                    && GetKeyState(i32::from(VK_SHIFT)) >= 0
                {
                    if let Ok(args) = args.cast::<ICoreWebView2AcceleratorKeyPressedEventArgs2>() {
                        // Skip native Find and still deliver the key to the DOM.
                        args.SetIsBrowserAcceleratorKeyEnabled(false)?;
                    }
                }
            }
            Ok(())
        }));
        let mut token = 0;
        // SAFETY: the platform controller is live on its UI thread. The
        // controller owns the callback and releases it when the shell closes.
        if let Err(error) = unsafe {
            platform
                .controller()
                .add_AcceleratorKeyPressed(&handler, &mut token)
        } {
            startup_diagnostics::log(
                "primary",
                "settings_search.install_error",
                &error.to_string(),
            );
        }
    })
}
