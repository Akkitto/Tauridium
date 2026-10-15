//! Creation-time, non-inheriting DACLs for the actual process user and SYSTEM.
use std::io;
use std::mem::size_of;
use std::ptr::null_mut;
use windows_sys::Win32::Foundation::{CloseHandle, LocalFree, HANDLE};
use windows_sys::Win32::Security::Authorization::{
    ConvertSidToStringSidW, ConvertStringSecurityDescriptorToSecurityDescriptorW,
};
use windows_sys::Win32::Security::{
    GetTokenInformation, TokenUser, SECURITY_ATTRIBUTES, TOKEN_QUERY, TOKEN_USER,
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

struct Allocation(*mut core::ffi::c_void);
impl Drop for Allocation {
    fn drop(&mut self) {
        unsafe {
            LocalFree(self.0);
        }
    }
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
        let _sid_allocation = Allocation(sid_text.cast());
        let mut length = 0;
        while unsafe { *sid_text.add(length) } != 0 {
            length += 1;
        }
        let sid = String::from_utf16(unsafe { std::slice::from_raw_parts(sid_text, length) })
            .map_err(io::Error::other)?;
        let sddl: Vec<u16> = format!("D:P(A;;{rights};;;SY)(A;;{rights};;;{sid})\0")
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
