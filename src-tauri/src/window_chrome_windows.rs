//! Stable Win32/DWM frame integration. Windows owns all three caption buttons.
use super::{Snapshot, HEIGHT};
use std::{
    cell::Cell,
    mem::size_of,
    ptr::{self, NonNull},
};
use tauri::{AppHandle, Emitter, EventTarget, Manager};
use windows_sys::Win32::{
    Foundation::{HWND, LPARAM, LRESULT, POINT, RECT, WPARAM},
    Graphics::{Dwm::*, Gdi::*},
    UI::{
        Accessibility::{HCF_HIGHCONTRASTON, HIGHCONTRASTW},
        Controls::{
            BeginBufferedPaint, BufferedPaintInit, BufferedPaintSetAlpha, BufferedPaintUnInit,
            EndBufferedPaint, BPBF_TOPDOWNDIB, MARGINS,
        },
        HiDpi::{GetDpiForWindow, GetSystemMetricsForDpi},
        Shell::{DefSubclassProc, GetWindowSubclass, RemoveWindowSubclass, SetWindowSubclass},
        WindowsAndMessaging::*,
    },
};

const SUBCLASS: usize = 0x54415552;
struct PaintState;
impl PaintState {
    fn new() -> Result<Self, String> {
        // SAFETY: frame lifetime and all painting stay on this window's UI thread.
        let result = unsafe { BufferedPaintInit() };
        if result < 0 {
            return Err(format!(
                "Unable to initialize opaque frame painting ({result:#x})"
            ));
        }
        Ok(Self)
    }
}
impl Drop for PaintState {
    fn drop(&mut self) {
        // SAFETY: exactly balances the successful init on the same UI thread.
        unsafe {
            BufferedPaintUnInit();
        }
    }
}
struct Frame {
    _painting: PaintState,
    paint_error_reported: Cell<bool>,
    app: Option<AppHandle>,
    height: Cell<i32>,
    background: Cell<u32>,
    previous_caption: Option<u32>,
    previous_text: Option<u32>,
    previous_dark: Option<u32>,
}

pub(super) struct Geometry {
    pub left: u32,
    pub width: u32,
    pub height: u32,
    pub border: u32,
}

fn failure(operation: &str) -> String {
    format!("{operation}: {}", std::io::Error::last_os_error())
}

unsafe fn attribute(hwnd: HWND, name: u32) -> Option<u32> {
    let mut value = 0;
    // SAFETY: the HWND is live on its owning thread and the buffer has the documented size.
    (unsafe {
        DwmGetWindowAttribute(
            hwnd,
            name,
            (&mut value as *mut u32).cast(),
            size_of::<u32>() as u32,
        )
    } >= 0)
        .then_some(value)
}

unsafe fn frame(hwnd: HWND) -> Option<NonNull<Frame>> {
    let mut data = 0;
    // SAFETY: this subclass exclusively owns its boxed Frame until removal/WM_NCDESTROY.
    if unsafe { GetWindowSubclass(hwnd, Some(procedure), SUBCLASS, &mut data) } == 0 || data == 0 {
        return None;
    }
    NonNull::new(data as *mut Frame)
}

unsafe fn extend(hwnd: HWND, height: i32) -> Result<(), String> {
    let margins = MARGINS {
        cxLeftWidth: 0,
        cxRightWidth: 0,
        cyTopHeight: height,
        cyBottomHeight: 0,
    };
    // SAFETY: a live HWND and initialized, fixed-size MARGINS structure.
    let result = unsafe { DwmExtendFrameIntoClientArea(hwnd, &margins) };
    if result < 0 {
        Err(format!("DWM frame extension failed ({result:#x})"))
    } else {
        Ok(())
    }
}

unsafe fn install_frame(hwnd: HWND, app: Option<AppHandle>) -> Result<(), String> {
    let mut composition = 0;
    // SAFETY: all operations run on this HWND's owning thread before it is revealed.
    if unsafe { DwmIsCompositionEnabled(&mut composition) } < 0 || composition == 0 {
        return Err("Windows desktop composition is unavailable".into());
    }
    if unsafe { frame(hwnd) }.is_some() {
        return Err("Window frame is already installed".into());
    }
    let dpi = unsafe { GetDpiForWindow(hwnd) }.max(96);
    let data = Box::new(Frame {
        _painting: PaintState::new()?,
        paint_error_reported: Cell::new(false),
        app,
        height: Cell::new((HEIGHT * f64::from(dpi) / 96.0).ceil() as i32),
        background: Cell::new(unsafe { GetSysColor(COLOR_WINDOW) }),
        previous_caption: unsafe { attribute(hwnd, DWMWA_CAPTION_COLOR as u32) },
        previous_text: unsafe { attribute(hwnd, DWMWA_TEXT_COLOR as u32) },
        previous_dark: unsafe { attribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE as u32) },
    });
    let height = data.height.get();
    let raw = Box::into_raw(data);
    if unsafe { SetWindowSubclass(hwnd, Some(procedure), SUBCLASS, raw as usize) } == 0 {
        // SAFETY: registration failed, so Windows never took ownership.
        drop(unsafe { Box::from_raw(raw) });
        return Err(failure("Unable to install native title-bar frame"));
    }
    if let Err(error) = unsafe { extend(hwnd, height) } {
        unsafe { remove_frame(hwnd) }?;
        return Err(error);
    }
    if unsafe {
        SetWindowPos(
            hwnd,
            ptr::null_mut(),
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )
    } == 0
    {
        let error = failure("Unable to recalculate the native frame");
        unsafe { remove_frame(hwnd) }?;
        return Err(error);
    }
    Ok(())
}

unsafe fn remove_frame(hwnd: HWND) -> Result<(), String> {
    let Some(data) = (unsafe { frame(hwnd) }) else {
        return Ok(());
    };
    let raw = data.as_ptr();
    let caption = unsafe { data.as_ref() }
        .previous_caption
        .unwrap_or(DWMWA_COLOR_DEFAULT);
    let text = unsafe { data.as_ref() }
        .previous_text
        .unwrap_or(DWMWA_COLOR_DEFAULT);
    let dark = unsafe { data.as_ref() }.previous_dark.unwrap_or(0);
    if unsafe { RemoveWindowSubclass(hwnd, Some(procedure), SUBCLASS) } == 0 {
        return Err(failure("Unable to restore the native frame"));
    }
    // SAFETY: callback removed; no future callback can borrow this unique box.
    drop(unsafe { Box::from_raw(raw) });
    unsafe {
        DwmSetWindowAttribute(
            hwnd,
            DWMWA_CAPTION_COLOR as u32,
            (&caption as *const u32).cast(),
            4,
        );
    }
    unsafe {
        DwmSetWindowAttribute(
            hwnd,
            DWMWA_TEXT_COLOR as u32,
            (&text as *const u32).cast(),
            4,
        );
    }
    unsafe {
        DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE as u32,
            (&dark as *const u32).cast(),
            4,
        );
    }
    unsafe { extend(hwnd, 0) }?;
    if unsafe {
        SetWindowPos(
            hwnd,
            ptr::null_mut(),
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )
    } == 0
    {
        return Err(failure("Unable to restore native window geometry"));
    }
    Ok(())
}

pub(super) fn install(app: &AppHandle) -> Result<(), String> {
    let window = app.get_window("main").ok_or("Main window is unavailable")?;
    let hwnd = window.hwnd().map_err(|e| e.to_string())?.0 as HWND;
    // SAFETY: setup runs on the UI thread; the HWND belongs to this main window.
    unsafe { install_frame(hwnd, Some(app.clone())) }
}

pub(super) fn remove(app: &AppHandle) -> Result<(), String> {
    let window = app.get_window("main").ok_or("Main window is unavailable")?;
    let hwnd = window.hwnd().map_err(|e| e.to_string())?.0 as HWND;
    // SAFETY: startup rollback runs on the same owning UI thread.
    unsafe { remove_frame(hwnd) }
}

unsafe fn geometry_for(hwnd: HWND, scale: f64) -> Result<Geometry, String> {
    let mut client: RECT = unsafe { std::mem::zeroed() };
    let mut outer: RECT = unsafe { std::mem::zeroed() };
    let mut origin = POINT { x: 0, y: 0 };
    if unsafe { GetClientRect(hwnd, &mut client) } == 0
        || unsafe { GetWindowRect(hwnd, &mut outer) } == 0
        || unsafe { ClientToScreen(hwnd, &mut origin) } == 0
    {
        return Err(failure("Unable to read native frame geometry"));
    }
    let dpi = unsafe { GetDpiForWindow(hwnd) }.max(96);
    let height = (HEIGHT * scale).ceil().max(f64::from(unsafe {
        GetSystemMetricsForDpi(SM_CYCAPTION, dpi)
    })) as u32;
    let width = client.right.max(1);
    // DWM may not have valid button bounds while hidden/minimized. Reserve a
    // conservative system-scaled clearance until real bounds become available.
    let reserve = (3 * unsafe { GetSystemMetricsForDpi(SM_CXSIZE, dpi) }
        .max((46.0 * scale).ceil() as i32))
    .min(width);
    let rtl = unsafe { GetWindowLongPtrW(hwnd, GWL_EXSTYLE) } as u32 & WS_EX_LAYOUTRTL != 0;
    let (mut left, mut right) = if rtl {
        (reserve, width)
    } else {
        (0, width - reserve)
    };
    let mut buttons: RECT = unsafe { std::mem::zeroed() };
    let result = unsafe {
        DwmGetWindowAttribute(
            hwnd,
            DWMWA_CAPTION_BUTTON_BOUNDS as u32,
            (&mut buttons as *mut RECT).cast(),
            size_of::<RECT>() as u32,
        )
    };
    let x = origin.x - outer.left;
    let button_left = buttons.left - x;
    let button_right = buttons.right - x;
    if result >= 0
        && buttons.bottom > buttons.top
        && button_right > button_left
        && button_right > 0
        && button_left < width
        && buttons.right <= outer.right - outer.left
    {
        if button_left > width / 2 {
            right = button_left.clamp(0, width);
        } else if button_right < width / 2 {
            left = button_right.clamp(0, width);
        }
    }
    let border = if unsafe { IsZoomed(hwnd) } != 0 {
        0
    } else {
        // Visible border, not the wider native resize hit area. A standard
        // 32px title row must align menus with the OS caption glyphs.
        unsafe { attribute(hwnd, DWMWA_VISIBLE_FRAME_BORDER_THICKNESS as u32) }
            .unwrap_or_else(|| scale.ceil().max(1.0) as u32)
    };
    Ok(Geometry {
        left: left.max(0) as u32,
        width: (right - left).max(1) as u32,
        height,
        border: border.min(height.saturating_sub(1)),
    })
}

pub(super) fn geometry(window: &tauri::Window) -> Result<Geometry, String> {
    let hwnd = window.hwnd().map_err(|e| e.to_string())?.0 as HWND;
    let scale = window.scale_factor().map_err(|e| e.to_string())?;
    // SAFETY: only native geometry is queried; handles belong to this window.
    let geometry = unsafe { geometry_for(hwnd, scale) }?;
    // Frame access/changes are UI-thread-only, just like the parent resize hook.
    if let Some(data) = unsafe { frame(hwnd) } {
        if unsafe { data.as_ref() }.height.get() != geometry.height as i32 {
            unsafe { data.as_ref() }.height.set(geometry.height as i32);
            unsafe { extend(hwnd, geometry.height as i32) }?;
        }
    }
    Ok(geometry)
}

pub(super) fn colors(app: &AppHandle) -> Result<(), String> {
    let window = app.get_window("main").ok_or("Main window is unavailable")?;
    let hwnd = window.hwnd().map_err(|e| e.to_string())?.0 as HWND;
    let Snapshot { theme, .. } = super::snapshot(app);
    let mut dark = u32::from(theme != "light");
    let (mut background, mut foreground) = match theme.as_str() {
        "light" => (0x00f8f4f3u32, 0x0030201cu32),
        "oled" => (0u32, 0x00f5f5f5u32),
        _ => (0x0030221fu32, 0x00efe8e8u32),
    };
    // Windows high-contrast colors take precedence over every app theme.
    let mut contrast: HIGHCONTRASTW = unsafe { std::mem::zeroed() };
    contrast.cbSize = size_of::<HIGHCONTRASTW>() as u32;
    if unsafe {
        SystemParametersInfoW(
            SPI_GETHIGHCONTRAST,
            contrast.cbSize,
            (&mut contrast as *mut HIGHCONTRASTW).cast(),
            0,
        )
    } != 0
        && contrast.dwFlags & HCF_HIGHCONTRASTON != 0
    {
        dark = 0;
        background = unsafe { GetSysColor(COLOR_WINDOW) };
        foreground = unsafe { GetSysColor(COLOR_WINDOWTEXT) };
    }
    // SAFETY: owned HWND; only documented color attributes and a GDI repaint.
    unsafe {
        if let Some(data) = frame(hwnd) {
            data.as_ref().background.set(background);
        }
        for (name, color) in [
            (DWMWA_CAPTION_COLOR, background),
            (DWMWA_TEXT_COLOR, foreground),
            (DWMWA_USE_IMMERSIVE_DARK_MODE, dark),
        ] {
            let result = DwmSetWindowAttribute(hwnd, name as u32, (&color as *const u32).cast(), 4);
            // These color attributes require Windows 11. Earlier Windows keeps
            // its system caption colors; no experimental WebView API is needed.
            if result < 0 && result as u32 != 0x80070057 {
                return Err(format!("Unable to apply title-bar colors ({result:#x})"));
            }
        }
        InvalidateRect(hwnd, ptr::null(), 0);
    }
    Ok(())
}

// DWM does not supply every hit after maximization with an extended client
// frame. Use the OS-owned caption rectangles/states for that documented fallback;
// never invent button geometry, controls, or a synthetic Snap keyboard shortcut.
fn caption_target(info: &TITLEBARINFOEX, point: POINT, style: u32) -> Option<LRESULT> {
    if style & WS_CAPTION != WS_CAPTION || style & WS_SYSMENU == 0 || style & WS_DISABLED != 0 {
        return None;
    }
    for (index, hit, required) in [
        (2, HTMINBUTTON, WS_MINIMIZEBOX),
        (3, HTMAXBUTTON, WS_MAXIMIZEBOX),
        (5, HTCLOSE, WS_SYSMENU),
    ] {
        let rect = info.rgrect[index];
        // Documented STATE_SYSTEM_UNAVAILABLE, INVISIBLE and OFFSCREEN flags.
        if style & required != 0
            && info.rgstate[index] & 0x0001_8001 == 0
            && rect.right > rect.left
            && rect.bottom > rect.top
            && point.x >= rect.left
            && point.x < rect.right
            && point.y >= rect.top
            && point.y < rect.bottom
        {
            return Some(hit as LRESULT);
        }
    }
    None
}

unsafe fn caption_info(hwnd: HWND) -> TITLEBARINFOEX {
    let mut info = TITLEBARINFOEX {
        cbSize: size_of::<TITLEBARINFOEX>() as u32,
        ..Default::default()
    };
    // SAFETY: synchronous same-window query on its owning UI thread; Windows
    // initializes the fixed-size structure and returns physical screen bounds.
    unsafe {
        SendMessageW(
            hwnd,
            WM_GETTITLEBARINFOEX,
            0,
            (&mut info as *mut TITLEBARINFOEX) as LPARAM,
        )
    };
    info
}

unsafe fn paint_background(dc: HDC, rect: &RECT, color: u32) -> Result<(), String> {
    if rect.right <= rect.left || rect.bottom <= rect.top {
        return Ok(());
    }
    let brush = unsafe { CreateSolidBrush(color) };
    if brush.is_null() {
        return Err(failure("Unable to create title-bar brush"));
    }
    let mut memory = ptr::null_mut();
    // GDI FillRect alone clears alpha on extended DWM glass, tinting the
    // exposed caption area. Paint an explicitly opaque buffer instead.
    let buffer = unsafe { BeginBufferedPaint(dc, rect, BPBF_TOPDOWNDIB, ptr::null(), &mut memory) };
    if buffer == 0 {
        unsafe {
            DeleteObject(brush);
        }
        return Err(failure("Unable to buffer title-bar background"));
    }
    let filled = unsafe { FillRect(memory, rect, brush) };
    unsafe {
        DeleteObject(brush);
    }
    let alpha = unsafe { BufferedPaintSetAlpha(buffer, ptr::null(), 255) };
    let result = unsafe { EndBufferedPaint(buffer, i32::from(filled != 0 && alpha >= 0)) };
    if filled == 0 || alpha < 0 || result < 0 {
        return Err(format!("Unable to paint opaque title bar (fill={filled}, alpha={alpha:#x}, commit={result:#x})"));
    }
    Ok(())
}

unsafe extern "system" fn procedure(
    hwnd: HWND,
    message: u32,
    wp: WPARAM,
    lp: LPARAM,
    _: usize,
    reference: usize,
) -> LRESULT {
    // SAFETY: the owned box is installed on this HWND, accessed only on its UI
    // thread, and removed/freed exactly once on rollback or WM_NCDESTROY.
    if message == WM_NCDESTROY {
        unsafe {
            RemoveWindowSubclass(hwnd, Some(procedure), SUBCLASS);
        }
        let result = unsafe { DefSubclassProc(hwnd, message, wp, lp) };
        if reference != 0 {
            drop(unsafe { Box::from_raw(reference as *mut Frame) });
        }
        return result;
    }
    if message == WM_NCCALCSIZE
        && lp != 0
        && unsafe { GetWindowLongPtrW(hwnd, GWL_STYLE) } as u32 & WS_CAPTION != 0
    {
        let rect = if wp == 0 {
            lp as *mut RECT
        } else {
            unsafe { &raw mut (*(lp as *mut NCCALCSIZE_PARAMS)).rgrc[0] }
        };
        let top = unsafe { (*rect).top };
        unsafe {
            DefSubclassProc(hwnd, message, wp, lp);
        }
        let dpi = unsafe { GetDpiForWindow(hwnd) }.max(96);
        let maximized_inset = if unsafe { IsZoomed(hwnd) } != 0 {
            unsafe {
                GetSystemMetricsForDpi(SM_CYFRAME, dpi)
                    + GetSystemMetricsForDpi(SM_CXPADDEDBORDER, dpi)
            }
        } else {
            0
        };
        unsafe {
            (*rect).top = top + maximized_inset;
        }
        return 0;
    }
    if message == WM_SYSCOMMAND && wp & 0xfff0 == SC_KEYMENU as usize && lp != 32 && reference != 0
    {
        let data = unsafe { &*(reference as *const Frame) };
        if let Some(app) = data.app.as_ref() {
            let app = app.clone();
            let index = match char::from_u32(lp as u32).map(|c| c.to_ascii_lowercase()) {
                Some('e') => 1,
                Some('v') => 2,
                Some('n') => 3,
                Some('s') => 4,
                Some('a') => 5,
                _ => 0,
            };
            tauri::async_runtime::spawn_blocking(move || {
                if let Some(view) = app.get_webview(super::LABEL) {
                    if let Err(error) = view.set_focus().and_then(|_| {
                        app.emit_to(
                            EventTarget::webview(super::LABEL),
                            "window-chrome-focus-menu",
                            index,
                        )
                    }) {
                        crate::startup_diagnostics::log(
                            "primary",
                            "titlebar.keyboard.error",
                            &error.to_string(),
                        );
                    }
                }
            });
            return 0;
        }
    }
    let mut result = 0;
    // Native caption hit testing/hover/press goes to DWM first. In particular,
    // HTMAXBUTTON remains a real native hit, so Windows owns Snap Layouts.
    let dwm_handled = unsafe { DwmDefWindowProc(hwnd, message, wp, lp, &mut result) } != 0;
    if message == WM_NCHITTEST
        && unsafe { GetWindowLongPtrW(hwnd, GWL_STYLE) } as u32 & WS_CAPTION != 0
    {
        let mut point = POINT {
            x: lp as i16 as i32,
            y: (lp >> 16) as i16 as i32,
        };
        if (!dwm_handled || result == HTCLIENT as LRESULT || result == HTCAPTION as LRESULT)
            && unsafe { IsIconic(hwnd) } == 0
        {
            let info = unsafe { caption_info(hwnd) };
            let style = unsafe { GetWindowLongPtrW(hwnd, GWL_STYLE) } as u32;
            if let Some(hit) = caption_target(&info, point, style) {
                return hit;
            }
        }
        if dwm_handled {
            return result;
        }
        if unsafe { ScreenToClient(hwnd, &mut point) } != 0 && unsafe { IsZoomed(hwnd) } == 0 {
            let dpi = unsafe { GetDpiForWindow(hwnd) }.max(96);
            let border = unsafe {
                GetSystemMetricsForDpi(SM_CYFRAME, dpi)
                    + GetSystemMetricsForDpi(SM_CXPADDEDBORDER, dpi)
            };
            let mut client: RECT = unsafe { std::mem::zeroed() };
            let border_x = unsafe {
                GetSystemMetricsForDpi(SM_CXFRAME, dpi)
                    + GetSystemMetricsForDpi(SM_CXPADDEDBORDER, dpi)
            };
            if unsafe { GetClientRect(hwnd, &mut client) } != 0
                && point.y >= 0
                && point.y < border
                && point.x >= -border_x
                && point.x < client.right + border_x
            {
                return if point.x < border_x {
                    HTTOPLEFT
                } else if point.x >= client.right - border_x {
                    HTTOPRIGHT
                } else {
                    HTTOP
                } as LRESULT;
            }
        }
    }
    if dwm_handled {
        return result;
    }
    if message == WM_PAINT && reference != 0 {
        let mut paint: PAINTSTRUCT = unsafe { std::mem::zeroed() };
        let dc = unsafe { BeginPaint(hwnd, &mut paint) };
        if !dc.is_null() {
            let data = unsafe { &*(reference as *const Frame) };
            let color = data.background.get();
            if let Err(error) = unsafe { paint_background(dc, &paint.rcPaint, color) } {
                if !data.paint_error_reported.replace(true) {
                    crate::startup_diagnostics::log("primary", "titlebar.paint.error", &error);
                }
                // Keep the window painted even under resource exhaustion.
                let brush = unsafe { CreateSolidBrush(color) };
                if !brush.is_null() {
                    unsafe {
                        FillRect(dc, &paint.rcPaint, brush);
                        DeleteObject(brush);
                    }
                }
            }
            unsafe {
                EndPaint(hwnd, &paint);
            }
        }
        return 0;
    }
    unsafe { DefSubclassProc(hwnd, message, wp, lp) }
}

#[cfg(test)]
mod tests {
    use super::*;

    // windows-sys has no UTF-16 literal macro; construct stable terminated arrays.
    const CLASS: [u16; 7] = [83, 84, 65, 84, 73, 67, 0];
    const TITLE: [u16; 5] = [84, 101, 115, 116, 0];

    #[test]
    fn caption_fallback_respects_native_bounds_states_and_styles() {
        let mut info = TITLEBARINFOEX::default();
        info.rgrect[2] = RECT {
            left: -140,
            top: 0,
            right: -94,
            bottom: 32,
        };
        info.rgrect[3] = RECT {
            left: -94,
            top: 0,
            right: -48,
            bottom: 32,
        };
        info.rgrect[5] = RECT {
            left: -48,
            top: 0,
            right: 0,
            bottom: 32,
        };
        for (x, expected) in [(-120, HTMINBUTTON), (-80, HTMAXBUTTON), (-20, HTCLOSE)] {
            assert_eq!(
                caption_target(&info, POINT { x, y: 16 }, WS_OVERLAPPEDWINDOW),
                Some(expected as LRESULT)
            );
        }
        for point in [
            POINT { x: -141, y: 16 },
            POINT { x: 0, y: 16 },
            POINT { x: -80, y: 32 },
        ] {
            assert_eq!(caption_target(&info, point, WS_OVERLAPPEDWINDOW), None);
        }
        for state in [1, 0x8000, 0x10000] {
            info.rgstate[3] = state;
            assert_eq!(
                caption_target(&info, POINT { x: -80, y: 16 }, WS_OVERLAPPEDWINDOW),
                None
            );
        }
        info.rgstate[3] = 0;
        assert_eq!(
            caption_target(
                &info,
                POINT { x: -80, y: 16 },
                WS_OVERLAPPEDWINDOW | WS_DISABLED
            ),
            None
        );
        assert_eq!(
            caption_target(
                &info,
                POINT { x: -80, y: 16 },
                WS_OVERLAPPEDWINDOW & !WS_MAXIMIZEBOX
            ),
            None
        );
        assert_eq!(
            caption_target(
                &info,
                POINT { x: -120, y: 16 },
                WS_OVERLAPPEDWINDOW & !WS_MINIMIZEBOX
            ),
            None
        );
        assert_eq!(
            caption_target(
                &info,
                POINT { x: -20, y: 16 },
                WS_OVERLAPPEDWINDOW & !WS_SYSMENU
            ),
            None
        );
        assert_eq!(
            caption_target(
                &info,
                POINT { x: -80, y: 16 },
                WS_OVERLAPPEDWINDOW & !WS_CAPTION
            ),
            None
        );
    }

    #[test]
    fn native_frame_retains_system_controls_and_restores_classic_geometry() {
        unsafe {
            let hwnd = CreateWindowExW(
                0,
                CLASS.as_ptr(),
                TITLE.as_ptr(),
                WS_OVERLAPPEDWINDOW,
                -500,
                100,
                900,
                600,
                ptr::null_mut(),
                ptr::null_mut(),
                ptr::null_mut(),
                ptr::null(),
            );
            assert!(!hwnd.is_null());
            let mut before: RECT = std::mem::zeroed();
            GetClientRect(hwnd, &mut before);
            let style = GetWindowLongPtrW(hwnd, GWL_STYLE);
            install_frame(hwnd, None).unwrap();
            assert_eq!(GetWindowLongPtrW(hwnd, GWL_STYLE), style);
            assert!(!GetSystemMenu(hwnd, 0).is_null());
            let mut after: RECT = std::mem::zeroed();
            GetClientRect(hwnd, &mut after);
            assert!(after.bottom > before.bottom);
            let geometry = geometry_for(hwnd, f64::from(GetDpiForWindow(hwnd)) / 96.0).unwrap();
            assert!(geometry.height >= 32 && geometry.width > 0);
            assert!(geometry.left > 0 || geometry.left + geometry.width < after.right as u32);
            // Exercise the reported regression against a real maximized native
            // window, before the production mouse-click integration gate.
            ShowWindow(hwnd, SW_SHOWMAXIMIZED);
            assert_ne!(IsZoomed(hwnd), 0);
            let info = caption_info(hwnd);
            for (index, expected) in [(2, HTMINBUTTON), (3, HTMAXBUTTON), (5, HTCLOSE)] {
                let rect = info.rgrect[index];
                assert!(rect.right > rect.left && rect.bottom > rect.top);
                let x = (rect.left + rect.right) / 2;
                let y = (rect.top + rect.bottom) / 2;
                let point = (((y as u32 & 0xffff) << 16) | (x as u32 & 0xffff)) as LPARAM;
                assert_eq!(
                    SendMessageW(hwnd, WM_NCHITTEST, 0, point),
                    expected as LRESULT
                );
            }
            ShowWindow(hwnd, SW_RESTORE);
            assert_eq!(IsZoomed(hwnd), 0);
            remove_frame(hwnd).unwrap();
            let mut restored: RECT = std::mem::zeroed();
            GetClientRect(hwnd, &mut restored);
            assert_eq!(
                (restored.right, restored.bottom),
                (before.right, before.bottom)
            );
            assert!(frame(hwnd).is_none());
            assert_ne!(DestroyWindow(hwnd), 0);
        }
    }
}
