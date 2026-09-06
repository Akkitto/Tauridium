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
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(crate) diagnostics_log: Option<String>,
}

#[cfg(windows)]
mod windows {
    use super::{InstanceActivationRequest, MAX_ACTIVATION_PAYLOAD_BYTES};
    use crate::{reposition_active, startup_diagnostics};
    use std::sync::{mpsc, Arc, Mutex};
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
        UI::WindowsAndMessaging::{
            AllowSetForegroundWindow, IsIconic, IsWindowVisible, SetForegroundWindow, ShowWindow,
            SW_RESTORE, SW_SHOW,
        },
    };

    const APP_IDENTIFIER: &str = if cfg!(debug_assertions) {
        "dev.brani.tauridium.dev"
    } else {
        "dev.brani.tauridium"
    };
    const ACTIVATION_RETRY_WINDOW: Duration = Duration::from_secs(5);
    const ACTIVATION_UI_TIMEOUT: Duration = Duration::from_secs(4);
    const ACTIVATION_RETRY_SLICE_MS: u32 = 50;
    const PIPE_BUFFER_BYTES: u32 = 64 * 1024;
    const ACTIVATION_NACK: u8 = 0;
    const ACTIVATION_ACK: u8 = 1;

    struct PendingActivation {
        request: InstanceActivationRequest,
        completion: mpsc::SyncSender<Result<(), String>>,
    }

    #[derive(Default)]
    struct ActivationTargetState {
        app: Option<AppHandle>,
        pending: Vec<PendingActivation>,
    }

    #[derive(Default)]
    pub(crate) struct WindowsActivationTarget {
        state: Mutex<ActivationTargetState>,
    }

    impl WindowsActivationTarget {
        fn accept(&self, request: InstanceActivationRequest) -> Result<(), String> {
            let diagnostics_log = request.diagnostics_log.clone();
            startup_diagnostics::log_for_path(
                diagnostics_log.as_deref(),
                "primary",
                "activation.accept",
                &format!(
                    "activation_type={} args_count={} cwd={}",
                    request.activation_type,
                    request.args.len(),
                    request.cwd.as_deref().unwrap_or("<unavailable>")
                ),
            );

            let (completion_tx, completion_rx) = mpsc::sync_channel(1);
            let app = {
                let mut state = self
                    .state
                    .lock()
                    .map_err(|_| "Tauridium activation queue is unavailable".to_string())?;
                if let Some(app) = state.app.clone() {
                    Some(app)
                } else {
                    startup_diagnostics::log_for_path(
                        diagnostics_log.as_deref(),
                        "primary",
                        "activation.queued",
                        "primary UI is still starting; request queued until startup visibility restoration completes",
                    );
                    state.pending.push(PendingActivation {
                        request: request.clone(),
                        completion: completion_tx.clone(),
                    });
                    None
                }
            };

            if let Some(app) = app {
                schedule_activation(app, request, completion_tx)?;
            }

            match completion_rx.recv_timeout(ACTIVATION_UI_TIMEOUT) {
                Ok(result) => result,
                Err(mpsc::RecvTimeoutError::Timeout) => Err(
                    "Timed out waiting for the Tauridium UI thread to complete activation".into(),
                ),
                Err(mpsc::RecvTimeoutError::Disconnected) => {
                    Err("Tauridium activation completion channel closed unexpectedly".into())
                }
            }
        }

        pub(crate) fn bind(&self, app: AppHandle) -> Result<(), String> {
            let pending = {
                let mut state = self.state.lock().map_err(|_| {
                    "Unable to bind Tauridium's Windows activation queue".to_string()
                })?;
                state.app = Some(app.clone());
                std::mem::take(&mut state.pending)
            };

            startup_diagnostics::log(
                "primary",
                "activation.bind",
                &format!(
                    "UI activation target bound; pending_requests={}",
                    pending.len()
                ),
            );
            for pending_activation in pending {
                let result = activate_existing_window(&app, pending_activation.request);
                let _ = pending_activation.completion.send(result);
            }
            Ok(())
        }
    }

    fn schedule_activation(
        app: AppHandle,
        request: InstanceActivationRequest,
        completion: mpsc::SyncSender<Result<(), String>>,
    ) -> Result<(), String> {
        let main_thread_app = app.clone();
        app.run_on_main_thread(move || {
            let result = activate_existing_window(&main_thread_app, request);
            let _ = completion.send(result);
        })
        .map_err(|error| format!("Unable to schedule Tauridium activation: {error}"))
    }

    fn restore_main_window(
        app: &AppHandle,
        diagnostics_log: Option<&str>,
        source: &str,
    ) -> Result<(), String> {
        let window = app
            .get_window("main")
            .ok_or_else(|| "Main Tauridium window is unavailable during activation".to_string())?;
        let was_visible = window
            .is_visible()
            .map_err(|error| format!("Unable to inspect Tauridium window visibility: {error}"))?;
        let was_minimized = window
            .is_minimized()
            .map_err(|error| format!("Unable to inspect Tauridium minimized state: {error}"))?;
        let hwnd = window
            .hwnd()
            .map_err(|error| format!("Unable to access Tauridium native window handle: {error}"))?;

        startup_diagnostics::log_for_path(
            diagnostics_log,
            "primary",
            "window.activation.begin",
            &format!(
                "source={source} visible={was_visible} minimized={was_minimized} hwnd={:?}",
                hwnd.0
            ),
        );

        if was_minimized {
            if let Err(error) = window.unminimize() {
                startup_diagnostics::log_for_path(
                    diagnostics_log,
                    "primary",
                    "window.unminimize.tauri_error",
                    &error.to_string(),
                );
            }
            unsafe {
                let _ = ShowWindow(hwnd.0, SW_RESTORE);
            }
            startup_diagnostics::log_for_path(
                diagnostics_log,
                "primary",
                "window.unminimize",
                "requested Tauri unminimize plus Win32 SW_RESTORE fallback",
            );
        }

        if !was_visible {
            if let Err(error) = window.show() {
                startup_diagnostics::log_for_path(
                    diagnostics_log,
                    "primary",
                    "window.show.tauri_error",
                    &error.to_string(),
                );
            }
            unsafe {
                let _ = ShowWindow(hwnd.0, SW_SHOW);
            }
            startup_diagnostics::log_for_path(
                diagnostics_log,
                "primary",
                "window.show",
                "requested Tauri show plus Win32 SW_SHOW fallback",
            );
        }

        let tauri_visible = window.is_visible().unwrap_or(false);
        let tauri_minimized = window.is_minimized().unwrap_or(true);
        let (native_visible, native_minimized) =
            unsafe { (IsWindowVisible(hwnd.0) != 0, IsIconic(hwnd.0) != 0) };
        startup_diagnostics::log_for_path(
            diagnostics_log,
            "primary",
            "window.activation.state",
            &format!(
                "tauri_visible={tauri_visible} tauri_minimized={tauri_minimized} native_visible={native_visible} native_minimized={native_minimized}"
            ),
        );
        if !native_visible || native_minimized {
            return Err(format!(
                "Tauridium main window did not become restorable/visible (tauri_visible={tauri_visible}, tauri_minimized={tauri_minimized}, native_visible={native_visible}, native_minimized={native_minimized})"
            ));
        }

        let foreground_accepted = unsafe { SetForegroundWindow(hwnd.0) != 0 };
        startup_diagnostics::log_for_path(
            diagnostics_log,
            "primary",
            "window.foreground",
            if foreground_accepted {
                "Windows accepted SetForegroundWindow"
            } else {
                "Windows declined SetForegroundWindow; window remains visible and focus policy is respected"
            },
        );
        reposition_active(app);
        Ok(())
    }

    fn activate_existing_window(
        app: &AppHandle,
        request: InstanceActivationRequest,
    ) -> Result<(), String> {
        let diagnostics_log = request.diagnostics_log.clone();
        restore_main_window(app, diagnostics_log.as_deref(), "secondary-launch")?;

        let event_request = InstanceActivationRequest {
            diagnostics_log: None,
            ..request
        };
        app.emit("single-instance-activation", event_request)
            .map_err(|error| format!("Unable to emit Tauridium activation context: {error}"))?;
        startup_diagnostics::log_for_path(
            diagnostics_log.as_deref(),
            "primary",
            "activation.completed",
            "window restoration completed and launch context was delivered",
        );
        Ok(())
    }

    pub(crate) fn show_existing_main_window(app: &AppHandle) -> Result<(), String> {
        restore_main_window(app, None, "tray-or-menu")
    }

    fn current_activation_request() -> InstanceActivationRequest {
        InstanceActivationRequest {
            activation_type: "launch".into(),
            args: std::env::args_os()
                .skip(1)
                .filter(|arg| {
                    arg.as_os_str()
                        != std::ffi::OsStr::new(startup_diagnostics::STARTUP_DIAGNOSTICS_FLAG)
                })
                .map(|arg| arg.to_string_lossy().into_owned())
                .collect(),
            cwd: std::env::current_dir()
                .ok()
                .map(|path| path.to_string_lossy().into_owned()),
            diagnostics_log: startup_diagnostics::current_log_path_string(),
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
            startup_diagnostics::log(
                "primary",
                "activation.listener.start",
                "starting Windows named-pipe activation listener",
            );
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
        let session_id = current_windows_session_id()?;
        startup_diagnostics::log(
            "launch",
            "instance.preflight",
            &format!("starting Windows single-instance preflight session_id={session_id}"),
        );
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
                startup_diagnostics::log(
                    "primary",
                    "instance.primary",
                    "acquired the session mutex as the durable primary instance",
                );
                return Ok(WindowsInstancePreflight::Primary(
                    WindowsInstanceCoordinator {
                        mutex,
                        pipe_name,
                        activation_target: Arc::new(WindowsActivationTarget::default()),
                    },
                ));
            }

            startup_diagnostics::log(
                "secondary",
                "instance.secondary",
                "session mutex already exists; redirecting activation to the primary instance",
            );
            redirect_to_primary_or_take_over(mutex, pipe_name)
        }
    }

    unsafe fn redirect_to_primary_or_take_over(
        mutex: HANDLE,
        pipe_name: Vec<u16>,
    ) -> Result<WindowsInstancePreflight, String> {
        let deadline = Instant::now() + ACTIVATION_RETRY_WINDOW;
        let request = current_activation_request();
        startup_diagnostics::log(
            "secondary",
            "activation.redirect.begin",
            &format!(
                "args_count={} cwd={} retry_window_ms={}",
                request.args.len(),
                request.cwd.as_deref().unwrap_or("<unavailable>"),
                ACTIVATION_RETRY_WINDOW.as_millis()
            ),
        );
        let payload = serde_json::to_vec(&request)
            .map_err(|error| format!("Unable to serialize Tauridium activation: {error}"))?;
        if payload.len() > MAX_ACTIVATION_PAYLOAD_BYTES {
            let _ = CloseHandle(mutex);
            return Err("Tauridium activation payload is too large".into());
        }

        let mut connection_attempt = 0_u32;
        loop {
            connection_attempt = connection_attempt.saturating_add(1);
            match WaitForSingleObject(mutex, 0) {
                WAIT_OBJECT_0 | WAIT_ABANDONED => {
                    startup_diagnostics::log(
                        "primary",
                        "instance.takeover",
                        "previous primary released or abandoned the mutex; this launch is taking over cleanly",
                    );
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
                startup_diagnostics::log(
                    "secondary",
                    "activation.pipe.connected",
                    &format!("connected to the existing primary activation pipe attempt={connection_attempt}"),
                );
                let result = send_activation_request(pipe, &payload, deadline);
                let _ = CloseHandle(pipe);
                if result.is_ok() {
                    startup_diagnostics::log(
                        "secondary",
                        "activation.redirect.completed",
                        "primary acknowledged completed UI activation; secondary will exit",
                    );
                    startup_diagnostics::replay_forwarded_primary_lines_to_console();
                    let _ = CloseHandle(mutex);
                    return Ok(WindowsInstancePreflight::ActivatedExisting);
                }
                if let Err(error) = result {
                    if error == "The existing Tauridium instance rejected activation" {
                        startup_diagnostics::log(
                            "secondary",
                            "activation.redirect.rejected",
                            &format!(
                                "attempt={connection_attempt} primary explicitly rejected activation"
                            ),
                        );
                        startup_diagnostics::replay_forwarded_primary_lines_to_console();
                        let _ = CloseHandle(mutex);
                        return Err(error);
                    }
                    startup_diagnostics::log(
                        "secondary",
                        "activation.redirect.retry",
                        &format!(
                            "attempt={connection_attempt} activation did not complete: {error}"
                        ),
                    );
                }
            } else {
                startup_diagnostics::log(
                    "secondary",
                    "activation.pipe.connect_retry",
                    &format!(
                        "attempt={connection_attempt} unable to open primary pipe: {}",
                        std::io::Error::last_os_error()
                    ),
                );
            }

            if Instant::now() >= deadline {
                startup_diagnostics::replay_forwarded_primary_lines_to_console();
                let _ = CloseHandle(mutex);
                return Err(
                    "Another Tauridium instance owns the session but did not acknowledge activation within 5 seconds; refusing to start a parallel application session"
                        .into(),
                );
            }

            // WaitNamedPipeW efficiently handles a busy endpoint; startup can also
            // report file-not-found before the primary listener thread has bound it.
            if WaitNamedPipeW(pipe_name.as_ptr(), ACTIVATION_RETRY_SLICE_MS) == 0 {
                startup_diagnostics::log(
                    "secondary",
                    "activation.pipe.wait_retry",
                    &format!(
                        "attempt={connection_attempt} primary pipe not ready: {}",
                        std::io::Error::last_os_error()
                    ),
                );
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
            let foreground_granted = AllowSetForegroundWindow(primary_pid) != 0;
            startup_diagnostics::log(
                "secondary",
                "activation.foreground_permission",
                &format!("primary_pid={primary_pid} granted={foreground_granted}"),
            );
        } else {
            startup_diagnostics::log(
                "secondary",
                "activation.primary_pid_unavailable",
                "named pipe connected but the primary PID could not be queried",
            );
        }

        startup_diagnostics::log(
            "secondary",
            "activation.request.send",
            &format!("payload_bytes={}", payload.len()),
        );
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
        startup_diagnostics::log(
            "secondary",
            "activation.ack",
            "received acknowledgement after the primary completed UI activation",
        );
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
                    let error = format!(
                        "Unable to create Tauridium activation pipe: {}",
                        std::io::Error::last_os_error()
                    );
                    startup_diagnostics::log("primary", "activation.pipe.create_error", &error);
                    eprintln!("{error}");
                    std::thread::sleep(Duration::from_millis(250));
                    continue;
                }

                let connected = ConnectNamedPipe(pipe, std::ptr::null_mut()) != 0
                    || GetLastError() == ERROR_PIPE_CONNECTED;
                if connected {
                    if let Err(error) = handle_activation_client(pipe, &target) {
                        startup_diagnostics::log("primary", "activation.request.error", &error);
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
        let diagnostics_log = request.diagnostics_log.clone();
        startup_diagnostics::log_for_path(
            diagnostics_log.as_deref(),
            "primary",
            "activation.request.received",
            &format!("payload_bytes={length}"),
        );
        // ACK only after accept() returns successfully. Failed activation is explicitly
        // rejected so the secondary can distinguish a primary-side UI failure from a
        // transport failure; the exact reason is also written to the forwarded log.
        if let Err(error) = target.accept(request) {
            startup_diagnostics::log_for_path(
                diagnostics_log.as_deref(),
                "primary",
                "activation.rejected",
                &error,
            );
            write_all(pipe, &[ACTIVATION_NACK])?;
            let _ = FlushFileBuffers(pipe);
            return Err(error);
        }
        write_all(pipe, &[ACTIVATION_ACK])?;
        startup_diagnostics::log_for_path(
            diagnostics_log.as_deref(),
            "primary",
            "activation.ack.sent",
            "acknowledgement sent after completed and verified UI activation",
        );
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
pub(crate) use windows::{
    show_existing_main_window, windows_instance_preflight, WindowsInstancePreflight,
};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn activation_request_round_trips_command_line_context() {
        let request = InstanceActivationRequest {
            activation_type: "launch".into(),
            args: vec!["tauridium://settings/about".into(), "notes.txt".into()],
            cwd: Some(r"C:\Users\Akito".into()),
            diagnostics_log: Some(
                r"C:\Users\Akito\AppData\Local\Tauridium\diagnostics\startup-1-2.log".into(),
            ),
        };
        let encoded = serde_json::to_vec(&request).unwrap();
        assert!(encoded.len() < MAX_ACTIVATION_PAYLOAD_BYTES);
        let decoded: InstanceActivationRequest = serde_json::from_slice(&encoded).unwrap();
        assert_eq!(decoded, request);
    }
}
