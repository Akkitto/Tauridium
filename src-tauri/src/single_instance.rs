#[cfg(any(windows, test))]
use serde::{Deserialize, Serialize};

#[cfg(any(windows, test))]
const MAX_ACTIVATION_PAYLOAD_BYTES: usize = 256 * 1024;

#[cfg(any(windows, test))]
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct InstanceActivationRequest {
    pub(crate) activation_type: String,
    pub(crate) args: Vec<String>,
    pub(crate) cwd: Option<String>,
}

#[cfg(windows)]
mod windows {
    use super::{InstanceActivationRequest, MAX_ACTIVATION_PAYLOAD_BYTES};
    use crate::reposition_active;
    use std::sync::{Arc, Mutex};
    use std::time::{Duration, Instant};
    use tauri::{AppHandle, Emitter, Manager};
    use windows_sys::Win32::{
        Foundation::{
            CloseHandle, GetLastError, SetLastError, ERROR_ALREADY_EXISTS, ERROR_PIPE_CONNECTED,
            GENERIC_READ, GENERIC_WRITE, HANDLE, INVALID_HANDLE_VALUE, WAIT_ABANDONED, WAIT_FAILED,
            WAIT_OBJECT_0, WAIT_TIMEOUT,
        },
        Storage::FileSystem::{
            CreateFileW, FlushFileBuffers, ReadFile, WriteFile, OPEN_EXISTING, PIPE_ACCESS_DUPLEX,
        },
        System::{
            Pipes::{
                ConnectNamedPipe, CreateNamedPipeW, DisconnectNamedPipe,
                GetNamedPipeServerProcessId, PeekNamedPipe, WaitNamedPipeW, PIPE_READMODE_BYTE,
                PIPE_REJECT_REMOTE_CLIENTS, PIPE_TYPE_BYTE, PIPE_UNLIMITED_INSTANCES, PIPE_WAIT,
            },
            RemoteDesktop::ProcessIdToSessionId,
            Threading::{CreateMutexW, GetCurrentProcessId, ReleaseMutex, WaitForSingleObject},
        },
        UI::WindowsAndMessaging::{AllowSetForegroundWindow, SetForegroundWindow},
    };

    const APP_IDENTIFIER: &str = if cfg!(debug_assertions) {
        "dev.brani.tauridium.dev"
    } else {
        "dev.brani.tauridium"
    };
    const ACTIVATION_RETRY_WINDOW: Duration = Duration::from_secs(5);
    const ACTIVATION_RETRY_SLICE_MS: u32 = 50;
    const PIPE_BUFFER_BYTES: u32 = 64 * 1024;
    const ACTIVATION_ACK: u8 = 1;

    #[derive(Default)]
    struct ActivationTargetState {
        app: Option<AppHandle>,
        pending: Vec<InstanceActivationRequest>,
    }

    #[derive(Default)]
    pub(crate) struct WindowsActivationTarget {
        state: Mutex<ActivationTargetState>,
    }

    impl WindowsActivationTarget {
        fn accept(&self, request: InstanceActivationRequest) -> Result<(), String> {
            let app = {
                let mut state = self
                    .state
                    .lock()
                    .map_err(|_| "Tauridium activation queue is unavailable".to_string())?;
                let Some(app) = state.app.clone() else {
                    state.pending.push(request);
                    return Ok(());
                };
                app
            };
            schedule_activation(app, request)
        }

        pub(crate) fn bind(&self, app: AppHandle) {
            let pending = match self.state.lock() {
                Ok(mut state) => {
                    state.app = Some(app.clone());
                    std::mem::take(&mut state.pending)
                }
                Err(_) => {
                    eprintln!("Unable to bind Tauridium's Windows activation queue");
                    return;
                }
            };
            for request in pending {
                if let Err(error) = schedule_activation(app.clone(), request) {
                    eprintln!("Unable to process queued Tauridium activation: {error}");
                }
            }
        }
    }

    fn schedule_activation(
        app: AppHandle,
        request: InstanceActivationRequest,
    ) -> Result<(), String> {
        let main_thread_app = app.clone();
        app.run_on_main_thread(move || {
            if let Some(window) = main_thread_app.get_webview_window("main") {
                let _ = window.show();
                if window.is_minimized().unwrap_or(false) {
                    let _ = window.unminimize();
                }
                // Do not use Tauri/tao set_focus here. tao's Windows implementation
                // falls back to synthesizing an Alt keypress when SetForegroundWindow
                // is denied. The user-launched secondary already grants this primary
                // foreground rights through AllowSetForegroundWindow, so make the
                // documented Win32 request directly and respect a denied activation.
                if let Ok(hwnd) = window.hwnd() {
                    unsafe {
                        let _ = SetForegroundWindow(hwnd.0);
                    }
                }
            }
            reposition_active(&main_thread_app);
            let _ = main_thread_app.emit("single-instance-activation", request);
        })
        .map_err(|error| format!("Unable to schedule Tauridium activation: {error}"))
    }

    fn current_activation_request() -> InstanceActivationRequest {
        InstanceActivationRequest {
            activation_type: "launch".into(),
            args: std::env::args_os()
                .skip(1)
                .map(|arg| arg.to_string_lossy().into_owned())
                .collect(),
            cwd: std::env::current_dir()
                .ok()
                .map(|path| path.to_string_lossy().into_owned()),
        }
    }

    fn current_windows_session_id() -> Result<u32, String> {
        let mut session_id = 0_u32;
        unsafe {
            if ProcessIdToSessionId(GetCurrentProcessId(), &mut session_id) == 0 {
                return Err(format!(
                    "Unable to resolve the Windows session for Tauridium instance coordination: {}",
                    std::io::Error::last_os_error()
                ));
            }
        }
        Ok(session_id)
    }

    fn wide(value: &str) -> Vec<u16> {
        value.encode_utf16().chain(std::iter::once(0)).collect()
    }

    fn mutex_name() -> Vec<u16> {
        wide(&format!("Local\\{APP_IDENTIFIER}.instance"))
    }

    fn pipe_name() -> Result<Vec<u16>, String> {
        Ok(wide(&format!(
            r"\\.\pipe\{APP_IDENTIFIER}.session-{}.activation",
            current_windows_session_id()?
        )))
    }

    pub(crate) struct WindowsInstanceCoordinator {
        mutex: HANDLE,
        pipe_name: Vec<u16>,
        activation_target: Arc<WindowsActivationTarget>,
    }

    // The coordinator owns the named mutex for the lifetime of the primary process.
    // Windows automatically abandons the mutex if the process crashes, so no stale
    // marker file or PID cleanup is required.
    impl Drop for WindowsInstanceCoordinator {
        fn drop(&mut self) {
            unsafe {
                let _ = ReleaseMutex(self.mutex);
                let _ = CloseHandle(self.mutex);
            }
        }
    }

    impl WindowsInstanceCoordinator {
        pub(crate) fn activation_target(&self) -> Arc<WindowsActivationTarget> {
            self.activation_target.clone()
        }

        pub(crate) fn start_activation_listener(&self) {
            let pipe_name = self.pipe_name.clone();
            let target = self.activation_target.clone();
            std::thread::spawn(move || activation_server_loop(pipe_name, target));
        }
    }

    pub(crate) enum WindowsInstancePreflight {
        Primary(WindowsInstanceCoordinator),
        ActivatedExisting,
    }

    pub(crate) fn windows_instance_preflight() -> Result<WindowsInstancePreflight, String> {
        let pipe_name = pipe_name()?;
        let mutex_name = mutex_name();
        unsafe {
            // Initial ownership is essential: the mutex is the atomic durable-primary
            // lease, not merely a process-presence marker.
            SetLastError(0);
            let mutex = CreateMutexW(std::ptr::null(), 1, mutex_name.as_ptr());
            if mutex.is_null() {
                return Err(format!(
                    "Unable to initialize Tauridium instance coordination mutex: {}",
                    std::io::Error::last_os_error()
                ));
            }
            if GetLastError() != ERROR_ALREADY_EXISTS {
                return Ok(WindowsInstancePreflight::Primary(
                    WindowsInstanceCoordinator {
                        mutex,
                        pipe_name,
                        activation_target: Arc::new(WindowsActivationTarget::default()),
                    },
                ));
            }

            redirect_to_primary_or_take_over(mutex, pipe_name)
        }
    }

    unsafe fn redirect_to_primary_or_take_over(
        mutex: HANDLE,
        pipe_name: Vec<u16>,
    ) -> Result<WindowsInstancePreflight, String> {
        let deadline = Instant::now() + ACTIVATION_RETRY_WINDOW;
        let request = current_activation_request();
        let payload = serde_json::to_vec(&request)
            .map_err(|error| format!("Unable to serialize Tauridium activation: {error}"))?;
        if payload.len() > MAX_ACTIVATION_PAYLOAD_BYTES {
            let _ = CloseHandle(mutex);
            return Err("Tauridium activation payload is too large".into());
        }

        loop {
            match WaitForSingleObject(mutex, 0) {
                WAIT_OBJECT_0 | WAIT_ABANDONED => {
                    return Ok(WindowsInstancePreflight::Primary(
                        WindowsInstanceCoordinator {
                            mutex,
                            pipe_name,
                            activation_target: Arc::new(WindowsActivationTarget::default()),
                        },
                    ));
                }
                WAIT_TIMEOUT => {}
                WAIT_FAILED => {
                    let error = std::io::Error::last_os_error();
                    let _ = CloseHandle(mutex);
                    return Err(format!(
                        "Unable to inspect the existing Tauridium instance: {error}"
                    ));
                }
                other => {
                    let _ = CloseHandle(mutex);
                    return Err(format!(
                        "Unexpected Windows mutex wait result while coordinating Tauridium: {other}"
                    ));
                }
            }

            let pipe = CreateFileW(
                pipe_name.as_ptr(),
                GENERIC_READ | GENERIC_WRITE,
                0,
                std::ptr::null(),
                OPEN_EXISTING,
                0,
                std::ptr::null_mut(),
            );
            if pipe != INVALID_HANDLE_VALUE {
                let result = send_activation_request(pipe, &payload, deadline);
                let _ = CloseHandle(pipe);
                if result.is_ok() {
                    let _ = CloseHandle(mutex);
                    return Ok(WindowsInstancePreflight::ActivatedExisting);
                }
            }

            if Instant::now() >= deadline {
                let _ = CloseHandle(mutex);
                return Err(
                    "Another Tauridium instance owns the session but did not acknowledge activation within 5 seconds; refusing to start a parallel application session"
                        .into(),
                );
            }

            // WaitNamedPipeW efficiently handles a busy endpoint; startup can also
            // report file-not-found before the primary listener thread has bound it.
            if WaitNamedPipeW(pipe_name.as_ptr(), ACTIVATION_RETRY_SLICE_MS) == 0 {
                std::thread::sleep(Duration::from_millis(ACTIVATION_RETRY_SLICE_MS as u64));
            }
        }
    }

    unsafe fn send_activation_request(
        pipe: HANDLE,
        payload: &[u8],
        deadline: Instant,
    ) -> Result<(), String> {
        let mut primary_pid = 0_u32;
        if GetNamedPipeServerProcessId(pipe, &mut primary_pid) != 0 && primary_pid != 0 {
            // A user-launched secondary process is normally eligible to transfer its
            // foreground permission. Failure is non-fatal: the activation request is
            // still delivered and Windows retains final focus policy control.
            let _ = AllowSetForegroundWindow(primary_pid);
        }

        let length = u32::try_from(payload.len())
            .map_err(|_| "Tauridium activation payload length overflow".to_string())?;
        write_all(pipe, &length.to_le_bytes())?;
        write_all(pipe, payload)?;

        let mut ack = [0_u8; 1];
        loop {
            let mut available = 0_u32;
            if PeekNamedPipe(
                pipe,
                std::ptr::null_mut(),
                0,
                std::ptr::null_mut(),
                &mut available,
                std::ptr::null_mut(),
            ) == 0
            {
                return Err(format!(
                    "Unable to await Tauridium activation acknowledgement: {}",
                    std::io::Error::last_os_error()
                ));
            }
            if available > 0 {
                read_exact(pipe, &mut ack)?;
                break;
            }
            if Instant::now() >= deadline {
                return Err("Timed out awaiting Tauridium activation acknowledgement".into());
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        if ack[0] != ACTIVATION_ACK {
            return Err("The existing Tauridium instance rejected activation".into());
        }
        Ok(())
    }

    fn activation_server_loop(pipe_name: Vec<u16>, target: Arc<WindowsActivationTarget>) {
        loop {
            unsafe {
                let pipe = CreateNamedPipeW(
                    pipe_name.as_ptr(),
                    PIPE_ACCESS_DUPLEX,
                    PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
                    PIPE_UNLIMITED_INSTANCES,
                    PIPE_BUFFER_BYTES,
                    PIPE_BUFFER_BYTES,
                    0,
                    std::ptr::null(),
                );
                if pipe == INVALID_HANDLE_VALUE {
                    eprintln!(
                        "Unable to create Tauridium activation pipe: {}",
                        std::io::Error::last_os_error()
                    );
                    std::thread::sleep(Duration::from_millis(250));
                    continue;
                }

                let connected = ConnectNamedPipe(pipe, std::ptr::null_mut()) != 0
                    || GetLastError() == ERROR_PIPE_CONNECTED;
                if connected {
                    if let Err(error) = handle_activation_client(pipe, &target) {
                        eprintln!("Unable to accept Tauridium activation request: {error}");
                    }
                }
                let _ = DisconnectNamedPipe(pipe);
                let _ = CloseHandle(pipe);
            }
        }
    }

    unsafe fn handle_activation_client(
        pipe: HANDLE,
        target: &WindowsActivationTarget,
    ) -> Result<(), String> {
        let mut length_bytes = [0_u8; 4];
        read_exact(pipe, &mut length_bytes)?;
        let length = u32::from_le_bytes(length_bytes) as usize;
        if length == 0 || length > MAX_ACTIVATION_PAYLOAD_BYTES {
            return Err("Tauridium activation request has an invalid payload length".into());
        }
        let mut payload = vec![0_u8; length];
        read_exact(pipe, &mut payload)?;
        let request: InstanceActivationRequest = serde_json::from_slice(&payload)
            .map_err(|error| format!("Invalid Tauridium activation request: {error}"))?;
        target.accept(request)?;
        write_all(pipe, &[ACTIVATION_ACK])?;
        let _ = FlushFileBuffers(pipe);
        Ok(())
    }

    unsafe fn read_exact(pipe: HANDLE, buffer: &mut [u8]) -> Result<(), String> {
        let mut offset = 0_usize;
        while offset < buffer.len() {
            let remaining = u32::try_from(buffer.len() - offset).unwrap_or(u32::MAX);
            let mut read = 0_u32;
            if ReadFile(
                pipe,
                buffer[offset..].as_mut_ptr(),
                remaining,
                &mut read,
                std::ptr::null_mut(),
            ) == 0
            {
                return Err(format!(
                    "Unable to read Tauridium activation pipe: {}",
                    std::io::Error::last_os_error()
                ));
            }
            if read == 0 {
                return Err("Tauridium activation pipe closed before the message completed".into());
            }
            offset += read as usize;
        }
        Ok(())
    }

    unsafe fn write_all(pipe: HANDLE, buffer: &[u8]) -> Result<(), String> {
        let mut offset = 0_usize;
        while offset < buffer.len() {
            let remaining = u32::try_from(buffer.len() - offset).unwrap_or(u32::MAX);
            let mut written = 0_u32;
            if WriteFile(
                pipe,
                buffer[offset..].as_ptr(),
                remaining,
                &mut written,
                std::ptr::null_mut(),
            ) == 0
            {
                return Err(format!(
                    "Unable to write Tauridium activation pipe: {}",
                    std::io::Error::last_os_error()
                ));
            }
            if written == 0 {
                return Err("Tauridium activation pipe accepted no data".into());
            }
            offset += written as usize;
        }
        Ok(())
    }
}

#[cfg(windows)]
pub(crate) use windows::{windows_instance_preflight, WindowsInstancePreflight};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn activation_request_round_trips_command_line_context() {
        let request = InstanceActivationRequest {
            activation_type: "launch".into(),
            args: vec!["tauridium://settings/about".into(), "notes.txt".into()],
            cwd: Some(r"C:\Users\Akito".into()),
        };
        let encoded = serde_json::to_vec(&request).unwrap();
        assert!(encoded.len() < MAX_ACTIVATION_PAYLOAD_BYTES);
        let decoded: InstanceActivationRequest = serde_json::from_slice(&encoded).unwrap();
        assert_eq!(decoded, request);
    }
}
