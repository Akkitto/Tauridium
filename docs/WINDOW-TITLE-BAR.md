# Windows unified title bar

Starting with 1.0.7, Windows uses one title-bar row for Tauridium's application
menus and window title. Windows continues to draw and handle the native
minimize, maximize/restore and close buttons. The service area starts below this
row; hosted websites cannot cover it.

To restore the layout used before 1.0.7, open **Settings → Advanced → Window
title bar**, turn **Unified title bar** off, then **quit and reopen Tauridium**.
Closing to the system tray does not restart the application. The saved preference
is included in normal settings backups. Older settings default to enabled; an
explicit disabled preference is preserved. Linux and macOS keep their existing
native title/menu-bar layouts.

The title-bar menus open Tauridium's existing native menus, including the current
Services menu and keyboard shortcuts. F10 or Alt enters the menu bar; arrow keys,
Home and End move between its entries, Down opens a menu, and Escape or Tab
returns to the content. A narrow title-bar surface shows a single **Menu** entry
that exposes the complete native menu tree. No commands disappear into an
inaccessible clipped row.

Drag an empty title-bar area to move the window; double-click it to maximize or
restore. Native non-client regions also retain Windows' system menu. The native
caption buttons keep Windows' maximize-hover hit target for Snap Layouts. Which
flyout Windows displays still depends on the OS version and Snap settings.

When DWM supplies only a generic client/title hit after maximization, Tauridium
uses Windows' own per-button screen rectangles and availability states as the
hit-test fallback. Disabled, invisible and off-screen controls are excluded;
Windows still handles the actual native controls and system commands.

The startup frame uses documented Win32/DWM APIs rather than experimental
WebView2 window-controls overlays or synthetic Windows-key shortcuts. It reads
native caption-button bounds and reserves a conservative system-scaled clearance
while those bounds are unavailable. Window resize, maximize/restore, DPI changes
and full-screen layout use physical bounds; the classic frame is restored if
initialization fails or the title-bar renderer never becomes ready.

The title-bar renderer loads only Tauridium's local document, rejects external
navigation and new windows, and has a dedicated command allowlist. It can read its
presentation, open existing native application menus and return keyboard focus.
It receives no filesystem, account, backup or settings-write authority. Mouse
dragging also has Tauri's supported fallback; modern WebView2 non-client regions
handle touch/pen, system-menu and double-click behavior.

## Validation

Normal `just ci` and `just release` remain the build gates. Native Windows CI also
runs `tools/test_windows_titlebar.ps1` against the production executable on fresh
GitHub-hosted x64 and Windows 11 ARM64 users. This test deliberately refuses an
existing Tauridium data directory and uses only a new, account-free local session.
It checks native caption rectangles/hit tests, WebView clearance, popup menus,
Advanced switch geometry, persistence and both restart-applied modes, then
maximize/minimize/restore and keyboard access. It is not a command to run against
an existing personal profile.

Manual platform checks should include multiple monitor scales, high contrast,
light/dark/OLED themes, touch/pen dragging, Snap settings, full screen, tray
restoration and changing the preference in both directions. Automated hit tests
do not establish every combination of display driver, accessibility tool and
future WebView2 runtime behavior.

## Design references

- [Microsoft title-bar design](https://learn.microsoft.com/en-us/windows/apps/design/basics/titlebar-design)
- [Microsoft title-bar customization](https://learn.microsoft.com/en-us/windows/apps/develop/title-bar)
- [Custom Window Frame Using DWM](https://learn.microsoft.com/en-us/windows/win32/dwm/customframe)
- [Support Snap Layouts](https://learn.microsoft.com/en-us/windows/apps/desktop/modernize/ui/apply-snap-layout-menu)
- [Native caption-button bounds](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute)
- [Tauri window customization](https://v2.tauri.app/learn/window-customization/)

- [Extended native title-bar information](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-titlebarinfoex)
- [DWM hit-test fallback](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/nf-dwmapi-dwmdefwindowproc)
