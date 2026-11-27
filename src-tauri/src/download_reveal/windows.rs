//! Open Explorer and confirm selection against the actual folder view.
use super::{Failure, Outcome};
use std::{
    os::windows::ffi::OsStrExt,
    path::Path,
    ptr,
    time::{Duration, Instant},
};
use windows::{
    core::{Interface, PCWSTR},
    Win32::{
        Foundation::{HWND, RPC_E_CHANGED_MODE},
        System::{
            Com::{
                CoCreateInstance, CoInitializeEx, CoTaskMemFree, CoUninitialize,
                CLSCTX_INPROC_SERVER, CLSCTX_LOCAL_SERVER, COINIT_APARTMENTTHREADED,
                COINIT_DISABLE_OLE1DDE,
            },
            Variant::VARIANT,
        },
        UI::{
            Shell::{
                Common::ITEMIDLIST, IFolderView2, ILClone, ILFindLastID, ILIsEqual, ILRemoveLastID,
                IPersistFolder2, IShellBrowser, IShellView, IShellWindows, IUnknown_QueryService,
                SHOpenFolderAndSelectItems, SHParseDisplayName, SID_STopLevelBrowser, ShellWindows,
                SVSI_DESELECTOTHERS, SVSI_ENSUREVISIBLE, SVSI_FOCUSED, SVSI_SELECT,
            },
            WindowsAndMessaging::{GetAncestor, GetForegroundWindow, GA_ROOT},
        },
    },
};

struct Apartment(bool);
impl Apartment {
    fn new() -> Result<Self, Failure> {
        // SAFETY: This worker's COM initialization is balanced by Drop.
        let result =
            unsafe { CoInitializeEx(None, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE) };
        if result.is_err() && result != RPC_E_CHANGED_MODE {
            return Err(Failure::Unavailable);
        }
        // A pre-existing apartment remains owned by its original initializer.
        Ok(Self(result.is_ok()))
    }
}
impl Drop for Apartment {
    fn drop(&mut self) {
        if self.0 {
            // SAFETY: Balances this worker's successful initialization.
            unsafe { CoUninitialize() };
        }
    }
}

struct Item(*mut ITEMIDLIST);
impl Item {
    fn parse(path: &Path) -> Result<Self, Failure> {
        let mut wide: Vec<u16> = path.as_os_str().encode_wide().collect();
        if wide.contains(&0) {
            return Err(Failure::Unavailable);
        }
        wide.push(0);
        let mut item = Self(ptr::null_mut());
        // SAFETY: NUL-terminated path and writable out-parameter owned by Item.
        unsafe { SHParseDisplayName(PCWSTR(wide.as_ptr()), None, &mut item.0, 0, None) }
            .map_err(|_| Failure::Unavailable)?;
        if item.0.is_null() {
            return Err(Failure::Unavailable);
        }
        Ok(item)
    }

    fn parent(&self) -> Result<Self, Failure> {
        // SAFETY: Clone the live Shell PIDL and remove its final child in place.
        // Deriving both from one parse preserves the Shell's namespace identity.
        unsafe {
            let parent = Self(ILClone(self.0));
            if parent.0.is_null() || !ILRemoveLastID(Some(parent.0)).as_bool() {
                return Err(Failure::Unavailable);
            }
            Ok(parent)
        }
    }

    fn relative_child(&self) -> *const ITEMIDLIST {
        // SAFETY: self owns the live absolute item list; this borrows its last ID.
        unsafe { ILFindLastID(self.0).cast_const() }
    }
}
impl Drop for Item {
    fn drop(&mut self) {
        // SAFETY: The Shell allocated the PIDL with the COM allocator.
        unsafe { CoTaskMemFree(Some(self.0.cast())) };
    }
}

struct FolderView {
    shell: IShellView,
    folder: IFolderView2,
    window: HWND,
}
impl FolderView {
    fn from_registered_window(
        windows: &IShellWindows,
        index: i32,
        expected: &Item,
    ) -> windows::core::Result<Option<Self>> {
        // SAFETY: COM is initialized. Retain only live interfaces and an owned
        // folder PIDL; never read titles, contents or selections of other folders.
        unsafe {
            let dispatch = windows.Item(&VARIANT::from(index))?;
            let browser: IShellBrowser = IUnknown_QueryService(&dispatch, &SID_STopLevelBrowser)?;
            let shell = browser.QueryActiveShellView()?;
            let folder: IFolderView2 = shell.cast()?;
            let location: IPersistFolder2 = folder.GetFolder()?;
            let location = Item(location.GetCurFolder()?);
            if location.0.is_null() || !ILIsEqual(location.0, expected.0).as_bool() {
                return Ok(None);
            }
            let window = GetAncestor(shell.GetWindow()?, GA_ROOT);
            Ok(Some(Self {
                shell,
                folder,
                window,
            }))
        }
    }

    fn select(&self, item: &Item) -> windows::core::Result<bool> {
        let child = item.relative_child();
        let selected = SVSI_SELECT.0 as u32;
        // SAFETY: This view was matched to the actual parent and the relative ID
        // borrows from item for both calls. These flags only change selection.
        unsafe {
            if self.folder.GetSelectionState(child).unwrap_or(0) & selected == 0 {
                let flags =
                    SVSI_SELECT.0 | SVSI_DESELECTOTHERS.0 | SVSI_ENSUREVISIBLE.0 | SVSI_FOCUSED.0;
                self.shell.SelectItem(child, flags as u32)?;
            }
            Ok(self.folder.GetSelectionState(child)? & selected != 0)
        }
    }
}

fn select_when_ready(folder: &Item, file: &Item) -> bool {
    // SAFETY: COM is initialized on this worker. Use the system Shell windows service.
    let Ok(windows): windows::core::Result<IShellWindows> = (unsafe {
        CoCreateInstance(
            &ShellWindows,
            None,
            CLSCTX_INPROC_SERVER | CLSCTX_LOCAL_SERVER,
        )
    }) else {
        return false;
    };
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        // SAFETY: Read-only queries on this worker's Shell proxy and current desktop.
        let count = unsafe { windows.Count() }.unwrap_or(0);
        let foreground = unsafe { GetForegroundWindow() };
        let mut matches = (0..count).filter_map(|index| {
            FolderView::from_registered_window(&windows, index, folder)
                .ok()
                .flatten()
        });
        if let Some(first) = matches.next() {
            // Prefer the active Explorer when several views show this directory.
            // An unambiguous sole match is also usable if Windows denies foreground.
            let view = if first.window == foreground {
                Some(first)
            } else if let Some(second) = matches.next() {
                std::iter::once(second)
                    .chain(matches)
                    .find(|view| view.window == foreground)
            } else {
                Some(first)
            };
            if view.is_some_and(|view| view.select(file).unwrap_or(false)) {
                return true;
            }
        }
        if Instant::now() >= deadline {
            return false;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
}

pub(super) fn show(path: &Path) -> Result<Outcome, Failure> {
    let _apartment = Apartment::new()?;
    let file = Item::parse(path)?;
    let folder = file.parent()?;
    let child = file.relative_child();
    if child.is_null() {
        return Err(Failure::Unavailable);
    }
    // SAFETY: Live absolute parent PIDL and one relative child borrowed from file.
    // Zero flags ask Explorer to select the file without editing or opening it.
    unsafe { SHOpenFolderAndSelectItems(folder.0, Some(&[child]), 0) }
        .map_err(|_| Failure::Unavailable)?;

    // On a cold Windows Server Explorer view the initial request can return
    // success before the view is ready and the selection is lost. Confirm or
    // repair selection in the matching ready view without opening a second window.
    Ok(if select_when_ready(&folder, &file) {
        Outcome::Shown
    } else {
        Outcome::FolderOpened
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use windows::Win32::UI::Shell::{ILGetSize, ILIsParent};

    #[test]
    fn selection_uses_the_actual_parent_and_a_relative_child_id() {
        let _apartment = Apartment::new().unwrap();
        let directory = tempfile::tempdir().unwrap();
        for name in [
            "file with spaces, % #.txt",
            "-literal;[name].txt",
            "Gr\u{fc}\u{df}e.txt",
        ] {
            let path = directory.path().join(name);
            std::fs::write(&path, "synthetic metadata fixture").unwrap();
            let item = Item::parse(&path).unwrap();
            // SAFETY: All arguments are live Shell-allocated PIDLs; queries only.
            unsafe {
                let derived = item.parent().unwrap();
                assert!(ILIsParent(derived.0, item.0, true).as_bool());
                let child = item.relative_child();
                assert!(!child.is_null());
                assert!(ILGetSize(Some(child)) > 2);
                assert!(ILGetSize(Some(child)) < ILGetSize(Some(item.0)));
            }
        }
    }
}
