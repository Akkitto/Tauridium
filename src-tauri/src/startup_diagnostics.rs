use std::ffi::OsStr;
use std::fs::{File, OpenOptions};
#[cfg(windows)]
use std::io::Read;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};
use std::time::{SystemTime, UNIX_EPOCH};

pub(crate) const STARTUP_DIAGNOSTICS_FLAG: &str = "--startup-diagnostics";
const MAX_DIAGNOSTIC_MESSAGE_CHARS: usize = 4096;

struct StartupDiagnostics {
    path: PathBuf,
    console: Mutex<Option<File>>,
}

static DIAGNOSTICS: OnceLock<StartupDiagnostics> = OnceLock::new();

fn diagnostics_requested() -> bool {
    std::env::args_os()
        .skip(1)
        .any(|arg| arg.as_os_str() == OsStr::new(STARTUP_DIAGNOSTICS_FLAG))
}

fn diagnostics_root() -> PathBuf {
    dirs::data_local_dir()
        .unwrap_or_else(std::env::temp_dir)
        .join("Tauridium")
        .join("diagnostics")
}

fn unix_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

#[cfg(windows)]
fn attach_parent_console() -> Option<File> {
    use windows_sys::Win32::System::Console::{AttachConsole, ATTACH_PARENT_PROCESS};

    // A release Tauridium executable uses the Windows GUI subsystem, so it does not
    // automatically inherit the terminal's console. Attach only in explicit diagnostics
    // mode. If a console is already attached, opening CONOUT$ below still succeeds.
    unsafe {
        let _ = AttachConsole(ATTACH_PARENT_PROCESS);
    }
    OpenOptions::new().write(true).open("CONOUT$").ok()
}

#[cfg(not(windows))]
fn attach_parent_console() -> Option<File> {
    None
}

fn write_console_file(console: &Mutex<Option<File>>, text: &str) {
    if let Ok(mut guard) = console.lock() {
        if let Some(handle) = guard.as_mut() {
            let _ = handle.write_all(text.as_bytes());
            let _ = handle.flush();
        } else {
            eprint!("{text}");
        }
    }
}

fn sanitize_message(message: &str) -> String {
    let mut sanitized = String::with_capacity(message.len().min(MAX_DIAGNOSTIC_MESSAGE_CHARS));
    for character in message.chars().take(MAX_DIAGNOSTIC_MESSAGE_CHARS) {
        match character {
            '\r' => sanitized.push_str("\\r"),
            '\n' => sanitized.push_str("\\n"),
            '\t' => sanitized.push_str("\\t"),
            character if character.is_control() => sanitized.push('?'),
            character => sanitized.push(character),
        }
    }
    if message.chars().count() > MAX_DIAGNOSTIC_MESSAGE_CHARS {
        sanitized.push_str("…[truncated]");
    }
    sanitized
}

fn format_line(role: &str, event: &str, message: &str) -> String {
    format!(
        "t={} pid={} role={} event={} message={}\n",
        unix_millis(),
        std::process::id(),
        sanitize_message(role),
        sanitize_message(event),
        sanitize_message(message)
    )
}

fn append_line(path: &Path, line: &str) -> std::io::Result<()> {
    let mut file = OpenOptions::new().create(true).append(true).open(path)?;
    file.write_all(line.as_bytes())?;
    file.flush()
}

#[cfg(any(windows, test))]
fn forwarded_path_is_safe(path: &Path) -> bool {
    let Some(file_name) = path.file_name().and_then(|value| value.to_str()) else {
        return false;
    };
    if !file_name.starts_with("startup-") || !file_name.ends_with(".log") {
        return false;
    }
    path.parent()
        .is_some_and(|parent| parent == diagnostics_root())
}

pub(crate) fn initialize_from_args() -> Result<bool, String> {
    if !diagnostics_requested() {
        return Ok(false);
    }
    if DIAGNOSTICS.get().is_some() {
        return Ok(true);
    }

    let console = attach_parent_console();
    let root = diagnostics_root();
    std::fs::create_dir_all(&root).map_err(|error| {
        let message = format!("Unable to create Tauridium diagnostics directory: {error}");
        if let Some(handle) = console.as_ref() {
            if let Ok(mut duplicate) = handle.try_clone() {
                let _ = writeln!(duplicate, "{message}");
            }
        }
        message
    })?;
    let path = root.join(format!(
        "startup-{}-{}.log",
        unix_millis(),
        std::process::id()
    ));
    File::create(&path)
        .map_err(|error| format!("Unable to create Tauridium startup diagnostics log: {error}"))?;

    let diagnostics = StartupDiagnostics {
        path,
        console: Mutex::new(console),
    };
    DIAGNOSTICS
        .set(diagnostics)
        .map_err(|_| "Tauridium startup diagnostics were initialized more than once".to_string())?;

    let default_panic_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |panic_info| {
        log("process", "panic", &panic_info.to_string());
        default_panic_hook(panic_info);
    }));

    log(
        "launch",
        "diagnostics.enabled",
        &format!(
            "version={} build_mode={} target={} log={}",
            env!("CARGO_PKG_VERSION"),
            crate::TAURIDIUM_BUILD_MODE,
            crate::TAURIDIUM_TARGET,
            current_log_path_string().unwrap_or_else(|| "unavailable".into())
        ),
    );
    log(
        "launch",
        "process.context",
        &format!(
            "cwd={} args_count={} (argument values are intentionally not logged)",
            std::env::current_dir()
                .map(|path| path.to_string_lossy().into_owned())
                .unwrap_or_else(|_| "<unavailable>".into()),
            std::env::args_os().skip(1).count()
        ),
    );
    Ok(true)
}

pub(crate) fn current_log_path_string() -> Option<String> {
    DIAGNOSTICS
        .get()
        .map(|diagnostics| diagnostics.path.to_string_lossy().into_owned())
}

pub(crate) fn log(role: &str, event: &str, message: &str) {
    let Some(diagnostics) = DIAGNOSTICS.get() else {
        return;
    };
    let line = format_line(role, event, message);
    if let Err(error) = append_line(&diagnostics.path, &line) {
        write_console_file(
            &diagnostics.console,
            &format!("Tauridium diagnostics file write failed: {error}\n"),
        );
    }
    write_console_file(&diagnostics.console, &line);
}

#[cfg(windows)]
pub(crate) fn log_for_path(path: Option<&str>, role: &str, event: &str, message: &str) {
    let current = current_log_path_string();
    if path.is_none() || path == current.as_deref() {
        log(role, event, message);
        return;
    }

    let Some(path) = path.map(PathBuf::from) else {
        return;
    };
    if !forwarded_path_is_safe(&path) {
        log(
            role,
            "diagnostics.forwarded_path_rejected",
            "activation supplied a diagnostics path outside Tauridium's diagnostics directory",
        );
        return;
    }
    let _ = append_line(&path, &format_line(role, event, message));
}

#[cfg(windows)]
pub(crate) fn replay_forwarded_primary_lines_to_console() {
    let Some(diagnostics) = DIAGNOSTICS.get() else {
        return;
    };
    let mut contents = String::new();
    if File::open(&diagnostics.path)
        .and_then(|mut file| file.read_to_string(&mut contents))
        .is_err()
    {
        return;
    }
    for line in contents
        .lines()
        .filter(|line| line.contains(" role=primary "))
    {
        write_console_file(&diagnostics.console, &format!("{line}\n"));
    }
}

pub(crate) fn report_fatal(role: &str, event: &str, message: &str) {
    if DIAGNOSTICS.get().is_some() {
        log(role, event, message);
    } else {
        eprintln!("{message}");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn forwarded_diagnostics_paths_are_confined_to_the_diagnostics_root() {
        let safe = diagnostics_root().join("startup-123-456.log");
        assert!(forwarded_path_is_safe(&safe));
        assert!(!forwarded_path_is_safe(
            &diagnostics_root().join("other.log")
        ));
        assert!(!forwarded_path_is_safe(
            &std::env::temp_dir().join("startup-123-456.log")
        ));
    }

    #[test]
    fn diagnostic_messages_are_single_line_and_bounded() {
        let sanitized = sanitize_message("hello\nworld\t!");
        assert_eq!(sanitized, "hello\\nworld\\t!");
        assert!(
            sanitize_message(&"x".repeat(MAX_DIAGNOSTIC_MESSAGE_CHARS + 20))
                .ends_with("…[truncated]")
        );
    }
}
