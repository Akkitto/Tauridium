//! Creation-time, non-inheriting DACLs for the actual process user and SYSTEM.
use std::io;
use std::mem::size_of;
use std::ptr::null_mut;
use windows_sys::Win32::Foundation::{CloseHandle, LocalFree, HANDLE};
use windows_sys::Win32::Security::Authorization::{
    ConvertSidToStringSidW, ConvertStringSecurityDescriptorToSecurityDescriptorW, GetSecurityInfo,
    SE_KERNEL_OBJECT,
};
use windows_sys::Win32::Security::{
    EqualSid, GetTokenInformation, TokenUser, OWNER_SECURITY_INFORMATION, PSID,
    SECURITY_ATTRIBUTES, TOKEN_QUERY, TOKEN_USER,
};
use windows_sys::Win32::System::Threading::{
    GetCurrentProcess, OpenProcess, OpenProcessToken, PROCESS_QUERY_LIMITED_INFORMATION,
};

struct Token(HANDLE);
impl Drop for Token {
    fn drop(&mut self) {
        unsafe {
            CloseHandle(self.0);
        }
    }
}

struct Allocation(*mut core::ffi::c_void);
impl Drop for Allocation {
    fn drop(&mut self) {
        unsafe {
            LocalFree(self.0);
        }
    }
}

struct UserSid(Vec<usize>);

impl UserSid {
    fn process(process: HANDLE) -> io::Result<Self> {
        let mut token = null_mut();
        if unsafe { OpenProcessToken(process, TOKEN_QUERY, &mut token) } == 0 {
            return Err(io::Error::last_os_error());
        }
        let token = Token(token);
        let mut needed = 0;
        unsafe { GetTokenInformation(token.0, TokenUser, null_mut(), 0, &mut needed) };
        if needed < size_of::<TOKEN_USER>() as u32 {
            return Err(io::Error::last_os_error());
        }
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
        Ok(Self(storage))
    }

    fn get(&self) -> PSID {
        // TOKEN_USER and its referenced SID live in this aligned allocation.
        unsafe { (*self.0.as_ptr().cast::<TOKEN_USER>()).User.Sid }
    }
}

fn require_owner(handle: HANDLE, expected: PSID) -> io::Result<()> {
    let mut owner = null_mut();
    let mut descriptor = null_mut();
    let result = unsafe {
        GetSecurityInfo(
            handle,
            SE_KERNEL_OBJECT,
            OWNER_SECURITY_INFORMATION,
            &mut owner,
            null_mut(),
            null_mut(),
            null_mut(),
            &mut descriptor,
        )
    };
    if result != 0 {
        return Err(io::Error::from_raw_os_error(result as i32));
    }
    let _descriptor = Allocation(descriptor);
    if owner.is_null() || unsafe { EqualSid(owner, expected) } == 0 {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "Instance endpoint has an unexpected owner",
        ));
    }
    Ok(())
}

pub(crate) fn require_current_user_owner(handle: HANDLE) -> io::Result<()> {
    require_owner(
        handle,
        UserSid::process(unsafe { GetCurrentProcess() })?.get(),
    )
}

pub(crate) fn require_current_user_process(pid: u32) -> io::Result<()> {
    let handle = unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid) };
    if handle.is_null() {
        return Err(io::Error::last_os_error());
    }
    let handle = Token(handle);
    let peer = UserSid::process(handle.0)?;
    let current = UserSid::process(unsafe { GetCurrentProcess() })?;
    if unsafe { EqualSid(peer.get(), current.get()) } == 0 {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "Instance peer has an unexpected user",
        ));
    }
    Ok(())
}

pub(crate) struct PrivateAttributes {
    attributes: SECURITY_ATTRIBUTES,
    _descriptor: Allocation,
}

impl PrivateAttributes {
    pub(crate) fn file() -> io::Result<Self> {
        Self::new("FA")
    }

    pub(crate) fn kernel_object() -> io::Result<Self> {
        Self::new("GA")
    }

    pub(crate) fn get(&self) -> &SECURITY_ATTRIBUTES {
        &self.attributes
    }

    fn new(rights: &str) -> io::Result<Self> {
        let user = UserSid::process(unsafe { GetCurrentProcess() })?;
        let mut sid_text = null_mut();
        if unsafe { ConvertSidToStringSidW(user.get(), &mut sid_text) } == 0 {
            return Err(io::Error::last_os_error());
        }
        let _sid_allocation = Allocation(sid_text.cast());
        let mut length = 0;
        while unsafe { *sid_text.add(length) } != 0 {
            length += 1;
        }
        let sid = String::from_utf16(unsafe { std::slice::from_raw_parts(sid_text, length) })
            .map_err(io::Error::other)?;
        let sddl: Vec<u16> = format!("O:{sid}D:P(A;;{rights};;;SY)(A;;{rights};;;{sid})\0")
            .encode_utf16()
            .collect();
        let mut descriptor = null_mut();
        if unsafe {
            ConvertStringSecurityDescriptorToSecurityDescriptorW(
                sddl.as_ptr(),
                1,
                &mut descriptor,
                null_mut(),
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        Ok(Self {
            attributes: SECURITY_ATTRIBUTES {
                nLength: size_of::<SECURITY_ATTRIBUTES>() as u32,
                lpSecurityDescriptor: descriptor,
                bInheritHandle: 0,
            },
            _descriptor: Allocation(descriptor),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use windows_sys::Win32::Security::{
        AclSizeInformation, GetAclInformation, GetSecurityDescriptorControl,
        GetSecurityDescriptorDacl, ACL_SIZE_INFORMATION, SE_DACL_PROTECTED,
    };

    #[test]
    fn actual_kernel_object_owner_and_process_user_are_verified() {
        use windows_sys::Win32::Security::Authorization::ConvertStringSidToSidW;
        use windows_sys::Win32::System::Threading::{CreateEventW, GetCurrentProcessId};
        let attributes = PrivateAttributes::kernel_object().unwrap();
        let event = unsafe { CreateEventW(attributes.get(), 1, 0, std::ptr::null()) };
        assert!(!event.is_null());
        let event = Token(event);
        require_current_user_owner(event.0).unwrap();
        require_current_user_process(unsafe { GetCurrentProcessId() }).unwrap();
        let text: Vec<u16> = "S-1-1-0\0".encode_utf16().collect();
        let mut other = null_mut();
        assert_ne!(
            unsafe { ConvertStringSidToSidW(text.as_ptr(), &mut other) },
            0
        );
        let _other = Allocation(other);
        assert_eq!(
            require_owner(event.0, other).unwrap_err().kind(),
            io::ErrorKind::PermissionDenied
        );
    }

    #[test]
    fn native_private_descriptors_are_protected_and_have_exactly_two_noninherited_grants() {
        for attributes in [
            PrivateAttributes::file().unwrap(),
            PrivateAttributes::kernel_object().unwrap(),
        ] {
            assert_eq!(attributes.get().bInheritHandle, 0);
            let mut present = 0;
            let mut defaulted = 0;
            let mut acl = null_mut();
            let mut control = 0;
            let mut revision = 0;
            unsafe {
                assert_ne!(
                    GetSecurityDescriptorDacl(
                        attributes.get().lpSecurityDescriptor,
                        &mut present,
                        &mut acl,
                        &mut defaulted
                    ),
                    0
                );
                assert_ne!(present, 0);
                assert!(!acl.is_null());
                let mut info = ACL_SIZE_INFORMATION {
                    AceCount: 0,
                    AclBytesInUse: 0,
                    AclBytesFree: 0,
                };
                assert_ne!(
                    GetAclInformation(
                        acl,
                        (&mut info as *mut ACL_SIZE_INFORMATION).cast(),
                        size_of::<ACL_SIZE_INFORMATION>() as u32,
                        AclSizeInformation
                    ),
                    0
                );
                assert_eq!(info.AceCount, 2);
                assert_ne!(
                    GetSecurityDescriptorControl(
                        attributes.get().lpSecurityDescriptor,
                        &mut control,
                        &mut revision
                    ),
                    0
                );
                assert_ne!(control & SE_DACL_PROTECTED, 0);
            }
        }
    }
}
