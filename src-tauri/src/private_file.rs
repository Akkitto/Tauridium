//! Private from creation, exclusive staging and atomic same-directory replacement.
use std::fs::{self, File};
use std::io::{self, Write};
use std::path::{Path, PathBuf};

struct Staging(PathBuf);

impl Drop for Staging {
    fn drop(&mut self) {
        // Only our random, exclusively created staging file. Never a caller's destination.
        let _ = fs::remove_file(&self.0);
    }
}

pub(crate) fn write(path: &Path, contents: &[u8]) -> io::Result<()> {
    write_verified(path, contents, |_| Ok(()))
}

pub(crate) fn append(path: &Path) -> io::Result<File> {
    let metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return create(path),
        Err(error) => return Err(error),
    };
    if !metadata.is_file() || metadata.file_type().is_symlink() {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "Private append requires a regular file",
        ));
    }
    let mut options = fs::OpenOptions::new();
    options.append(true);
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        options.custom_flags(windows_sys::Win32::Storage::FileSystem::FILE_FLAG_OPEN_REPARSE_POINT);
    }
    let file = options.open(path)?;
    let opened = file.metadata()?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::{MetadataExt, PermissionsExt};
        if opened.dev() != metadata.dev() || opened.ino() != metadata.ino() {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "Private append file changed during opening",
            ));
        }
        file.set_permissions(fs::Permissions::from_mode(0o600))?;
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        if opened.file_attributes() & 0x400 != 0 {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "Private append rejects reparse points",
            ));
        }
    }
    Ok(file)
}

pub(crate) fn write_verified(
    path: &Path,
    contents: &[u8],
    verify: impl FnOnce(&Path) -> io::Result<()>,
) -> io::Result<()> {
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    if path.file_name().is_none() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "Destination has no filename",
        ));
    }
    let mut random = [0_u8; 24];
    getrandom::fill(&mut random).map_err(io::Error::other)?;
    let suffix = random
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<String>();
    let temporary = parent.join(format!(".tauridium-{suffix}.tmp"));
    let mut file = create(&temporary)?;
    let staging = Staging(temporary);
    file.write_all(contents)?;
    file.sync_all()?;
    drop(file); // Windows replacement and independent verification need a closed handle.
    verify(&staging.0)?;
    replace(&staging.0, path)?;
    #[cfg(unix)]
    File::open(parent)?.sync_all()?;
    Ok(())
}

#[cfg(unix)]
pub(crate) fn create(path: &Path) -> io::Result<File> {
    use std::os::unix::fs::OpenOptionsExt;
    fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .mode(0o600)
        .open(path)
}

#[cfg(not(windows))]
pub(crate) fn replace(source: &Path, destination: &Path) -> io::Result<()> {
    fs::rename(source, destination)
}

#[cfg(windows)]
mod windows {
    use super::*;
    use std::os::windows::ffi::OsStrExt;
    use std::os::windows::io::{AsRawHandle, FromRawHandle};
    use std::ptr::null_mut;
    use windows_sys::Win32::Foundation::{
        CloseHandle, LocalFree, GENERIC_READ, GENERIC_WRITE, HANDLE, INVALID_HANDLE_VALUE,
    };
    use windows_sys::Win32::Security::Authorization::{
        ConvertSidToStringSidW, ConvertStringSecurityDescriptorToSecurityDescriptorW,
    };
    use windows_sys::Win32::Security::{
        GetTokenInformation, TokenUser, SECURITY_ATTRIBUTES, TOKEN_QUERY, TOKEN_USER,
    };
    use windows_sys::Win32::Storage::FileSystem::{
        CreateFileW, GetVolumeInformationByHandleW, MoveFileExW, CREATE_NEW, FILE_ATTRIBUTE_NORMAL,
        FILE_FLAG_OPEN_REPARSE_POINT, MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH,
    };
    use windows_sys::Win32::System::Threading::{GetCurrentProcess, OpenProcessToken};

    struct Token(HANDLE);
    impl Drop for Token {
        fn drop(&mut self) {
            unsafe {
                CloseHandle(self.0);
            }
        }
    }
    struct Local(*mut core::ffi::c_void);
    impl Drop for Local {
        fn drop(&mut self) {
            unsafe {
                LocalFree(self.0);
            }
        }
    }

    fn wide(path: &Path) -> io::Result<Vec<u16>> {
        let mut value: Vec<_> = path.as_os_str().encode_wide().collect();
        if value.contains(&0) {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "NUL in file path",
            ));
        }
        value.push(0);
        Ok(value)
    }

    pub(crate) fn create(path: &Path) -> io::Result<File> {
        // Build the protected DACL with the actual process-user SID, not the possibly
        // administrative default owner. All allocations/handles remain live through CreateFileW.
        let mut token = null_mut();
        if unsafe { OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut token) } == 0 {
            return Err(io::Error::last_os_error());
        }
        let token = Token(token);
        let mut needed = 0;
        unsafe {
            GetTokenInformation(token.0, TokenUser, null_mut(), 0, &mut needed);
        }
        if needed == 0 {
            return Err(io::Error::last_os_error());
        }
        // usize storage gives TOKEN_USER its required pointer alignment.
        let mut storage = vec![0_usize; (needed as usize).div_ceil(size_of::<usize>())];
        if unsafe {
            GetTokenInformation(
                token.0,
                TokenUser,
                storage.as_mut_ptr().cast(),
                needed,
                &mut needed,
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        let user = unsafe { &*storage.as_ptr().cast::<TOKEN_USER>() };
        let mut sid_text = null_mut();
        if unsafe { ConvertSidToStringSidW(user.User.Sid, &mut sid_text) } == 0 {
            return Err(io::Error::last_os_error());
        }
        let sid_allocation = Local(sid_text.cast());
        let mut length = 0;
        while unsafe { *sid_text.add(length) } != 0 {
            length += 1;
        }
        let sid = String::from_utf16(unsafe { std::slice::from_raw_parts(sid_text, length) })
            .map_err(io::Error::other)?;
        let descriptor_text: Vec<u16> = format!("D:P(A;;FA;;;SY)(A;;FA;;;{sid})\0")
            .encode_utf16()
            .collect();
        let mut descriptor = null_mut();
        if unsafe {
            ConvertStringSecurityDescriptorToSecurityDescriptorW(
                descriptor_text.as_ptr(),
                1,
                &mut descriptor,
                null_mut(),
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        let descriptor_allocation = Local(descriptor);
        let attributes = SECURITY_ATTRIBUTES {
            nLength: size_of::<SECURITY_ATTRIBUTES>() as u32,
            lpSecurityDescriptor: descriptor,
            bInheritHandle: 0,
        };
        let path_wide = wide(path)?;
        let handle = unsafe {
            CreateFileW(
                path_wide.as_ptr(),
                GENERIC_READ | GENERIC_WRITE,
                0,
                &attributes,
                CREATE_NEW,
                FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT,
                null_mut(),
            )
        };
        if handle == INVALID_HANDLE_VALUE {
            return Err(io::Error::last_os_error());
        }
        let file = unsafe { File::from_raw_handle(handle) };
        drop(descriptor_allocation);
        drop(sid_allocation);
        let mut flags = 0;
        let result = unsafe {
            GetVolumeInformationByHandleW(
                file.as_raw_handle(),
                null_mut(),
                0,
                null_mut(),
                null_mut(),
                &mut flags,
                null_mut(),
                0,
            )
        };
        const FILE_PERSISTENT_ACLS: u32 = 0x0000_0008;
        if result == 0 || flags & FILE_PERSISTENT_ACLS == 0 {
            let error = if result == 0 {
                io::Error::last_os_error()
            } else {
                io::Error::new(io::ErrorKind::PermissionDenied, "Private Tauridium files require a filesystem with persistent ACLs (for example NTFS)")
            };
            drop(file);
            fs::remove_file(path)?;
            return Err(error);
        }
        Ok(file)
    }

    pub(crate) fn replace(source: &Path, destination: &Path) -> io::Result<()> {
        // Same-directory move: retains the new file's private DACL. No copy fallback,
        // public .bak, or interval in which the previous destination disappears.
        let source = wide(source)?;
        let destination = wide(destination)?;
        if unsafe {
            MoveFileExW(
                source.as_ptr(),
                destination.as_ptr(),
                MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        Ok(())
    }
}

#[cfg(windows)]
pub(crate) use windows::{create, replace};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn private_staging_is_exclusive_and_verified_before_atomic_replacement() {
        let root = std::env::temp_dir().join(format!(
            "tauridium-private-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir(&root).unwrap();
        let destination = root.join("secret.json");
        fs::write(&destination, b"old").unwrap();
        let legacy_temporary = destination.with_extension("tmp");
        fs::write(&legacy_temporary, b"do not touch").unwrap();
        let error = write_verified(&destination, b"new", |staged| {
            assert_eq!(fs::read(&destination).unwrap(), b"old");
            assert_eq!(fs::read(staged).unwrap(), b"new");
            assert!(create(staged).is_err());
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                assert_eq!(
                    fs::metadata(staged).unwrap().permissions().mode() & 0o777,
                    0o600
                );
            }
            Err(io::Error::other("synthetic verification failure"))
        })
        .unwrap_err();
        assert!(error.to_string().contains("verification failure"));
        assert_eq!(fs::read(&destination).unwrap(), b"old");
        assert_eq!(fs::read_dir(&root).unwrap().count(), 2);
        write(&destination, b"valid").unwrap();
        assert_eq!(fs::read(&destination).unwrap(), b"valid");
        assert_eq!(fs::read(&legacy_temporary).unwrap(), b"do not touch");
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn replacing_a_link_does_not_modify_its_target() {
        let root =
            std::env::temp_dir().join(format!("tauridium-private-link-{}", std::process::id()));
        fs::create_dir(&root).unwrap();
        let canary = root.join("canary");
        fs::write(&canary, b"safe").unwrap();
        let destination = root.join("destination");
        std::os::unix::fs::symlink(&canary, &destination).unwrap();
        write(&destination, b"new").unwrap();
        assert_eq!(fs::read(canary).unwrap(), b"safe");
        assert!(!fs::symlink_metadata(destination)
            .unwrap()
            .file_type()
            .is_symlink());
        fs::remove_dir_all(root).unwrap();
    }
}
