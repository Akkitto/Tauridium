use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager};

const AUDIT_DIR: &str = "audit";
const AUDIT_FILE: &str = "tauridium-audit.jsonl";
const MAX_AUDIT_FILE_BYTES: u64 = 5 * 1024 * 1024;
const AUDIT_ROTATIONS: usize = 4;
const MAX_READ_ENTRIES: usize = 10_000;
static AUDIT_LOCK: Mutex<()> = Mutex::new(());

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct AuditEntry {
    pub timestamp_unix_ms: u64,
    pub level: String,
    pub category: String,
    pub action: String,
    pub outcome: String,
    pub message: String,
    pub details: Value,
}

fn now_ms() -> u64 {
    u64::try_from(
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis(),
    )
    .unwrap_or(u64::MAX)
}

fn audit_root(app: &AppHandle) -> Result<PathBuf, String> {
    app.path()
        .app_config_dir()
        .map(|root| root.join(AUDIT_DIR))
        .map_err(|error| format!("Tauridium configuration directory unavailable: {error}"))
}

fn audit_path(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(audit_root(app)?.join(AUDIT_FILE))
}

fn rotated_path(path: &Path, generation: usize) -> PathBuf {
    path.with_file_name(format!("{AUDIT_FILE}.{generation}"))
}

fn rotate_if_needed(path: &Path) -> Result<(), String> {
    let oversized = fs::metadata(path)
        .map(|metadata| metadata.len() >= MAX_AUDIT_FILE_BYTES)
        .unwrap_or(false);
    if !oversized {
        return Ok(());
    }
    for generation in (1..=AUDIT_ROTATIONS).rev() {
        let destination = rotated_path(path, generation);
        if generation == AUDIT_ROTATIONS && destination.exists() {
            fs::remove_file(&destination)
                .map_err(|error| format!("Unable to expire old audit log: {error}"))?;
        }
        let source = if generation == 1 {
            path.to_path_buf()
        } else {
            rotated_path(path, generation - 1)
        };
        if source.exists() {
            fs::rename(&source, &destination)
                .map_err(|error| format!("Unable to rotate audit log: {error}"))?;
        }
    }
    Ok(())
}

fn sensitive_key(key: &str) -> bool {
    let normalized = key.to_ascii_lowercase();
    [
        "password",
        "token",
        "secret",
        "credential",
        "authorization",
        "cookie",
    ]
    .iter()
    .any(|needle| normalized.contains(needle))
}

pub(crate) fn redact(value: &Value) -> Value {
    match value {
        Value::Object(object) => Value::Object(
            object
                .iter()
                .map(|(key, value)| {
                    (
                        key.clone(),
                        if sensitive_key(key) {
                            Value::String("[redacted]".into())
                        } else {
                            redact(value)
                        },
                    )
                })
                .collect(),
        ),
        Value::Array(values) => Value::Array(values.iter().map(redact).collect()),
        _ => value.clone(),
    }
}

fn audit_guard() -> Result<std::sync::MutexGuard<'static, ()>, String> {
    AUDIT_LOCK
        .lock()
        .map_err(|_| "Tauridium audit log lock is poisoned".to_string())
}

pub(crate) fn record(
    app: &AppHandle,
    level: &str,
    category: &str,
    action: &str,
    outcome: &str,
    message: impl Into<String>,
    details: Value,
) -> Result<(), String> {
    let _guard = audit_guard()?;
    let path = audit_path(app)?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("Unable to create audit log directory: {error}"))?;
    }
    rotate_if_needed(&path)?;
    let entry = AuditEntry {
        timestamp_unix_ms: now_ms(),
        level: level.to_string(),
        category: category.to_string(),
        action: action.to_string(),
        outcome: outcome.to_string(),
        message: message.into(),
        details: redact(&details),
    };
    let mut file = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|error| format!("Unable to open audit log: {error}"))?;
    serde_json::to_writer(&mut file, &entry)
        .map_err(|error| format!("Unable to serialize audit event: {error}"))?;
    file.write_all(b"\n")
        .map_err(|error| format!("Unable to write audit log: {error}"))?;
    file.sync_data()
        .map_err(|error| format!("Unable to flush audit log: {error}"))
}

pub(crate) fn best_effort(
    app: &AppHandle,
    level: &str,
    category: &str,
    action: &str,
    outcome: &str,
    message: impl Into<String>,
    details: Value,
) {
    if let Err(error) = record(app, level, category, action, outcome, message, details) {
        eprintln!("Unable to record Tauridium audit event: {error}");
    }
}

fn read_all_entries(app: &AppHandle) -> Result<Vec<AuditEntry>, String> {
    let path = audit_path(app)?;
    let mut entries = Vec::new();
    let mut paths = (1..=AUDIT_ROTATIONS)
        .rev()
        .map(|generation| rotated_path(&path, generation))
        .collect::<Vec<_>>();
    paths.push(path);
    for path in paths {
        let Ok(text) = fs::read_to_string(&path) else {
            continue;
        };
        for line in text.lines().filter(|line| !line.trim().is_empty()) {
            match serde_json::from_str::<AuditEntry>(line) {
                Ok(entry) => entries.push(entry),
                Err(error) => entries.push(AuditEntry {
                    timestamp_unix_ms: now_ms(),
                    level: "warning".into(),
                    category: "audit".into(),
                    action: "parse".into(),
                    outcome: "warning".into(),
                    message: "A malformed audit-log record was skipped".into(),
                    details: json!({ "error": error.to_string() }),
                }),
            }
        }
    }
    Ok(entries)
}

pub(crate) fn read(app: &AppHandle, limit: usize) -> Result<Vec<AuditEntry>, String> {
    let _guard = audit_guard()?;
    let mut entries = read_all_entries(app)?;
    if entries.len() > MAX_READ_ENTRIES {
        entries = entries.split_off(entries.len() - MAX_READ_ENTRIES);
    }
    entries.reverse();
    entries.truncate(limit.clamp(1, MAX_READ_ENTRIES));
    Ok(entries)
}

pub(crate) fn export(app: &AppHandle, destination: &Path) -> Result<usize, String> {
    let _guard = audit_guard()?;
    // Export every event still retained by the bounded rotation policy, not only the UI/read cap.
    let entries = read_all_entries(app)?;
    if let Some(parent) = destination.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("Unable to create audit export directory: {error}"))?;
    }
    let mut text = String::new();
    for entry in &entries {
        let line = serde_json::to_string(entry)
            .map_err(|error| format!("Unable to serialize audit export: {error}"))?;
        text.push_str(&line);
        text.push('\n');
    }
    fs::write(destination, text).map_err(|error| format!("Unable to export audit log: {error}"))?;
    Ok(entries.len())
}

pub(crate) fn clear(app: &AppHandle) -> Result<(), String> {
    let _guard = audit_guard()?;
    let path = audit_path(app)?;
    for candidate in std::iter::once(path.clone())
        .chain((1..=AUDIT_ROTATIONS).map(|generation| rotated_path(&path, generation)))
    {
        if candidate.exists() {
            fs::remove_file(&candidate)
                .map_err(|error| format!("Unable to clear audit log: {error}"))?;
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn audit_redaction_removes_nested_secret_values() {
        let value = json!({
            "password": "nope",
            "nested": { "apiToken": "nope", "safe": "yes" },
            "items": [{ "cookieValue": "nope" }]
        });
        let redacted = redact(&value);
        assert_eq!(redacted["password"], "[redacted]");
        assert_eq!(redacted["nested"]["apiToken"], "[redacted]");
        assert_eq!(redacted["nested"]["safe"], "yes");
        assert_eq!(redacted["items"][0]["cookieValue"], "[redacted]");
    }

    #[test]
    fn rotated_paths_are_predictable() {
        let path = Path::new("audit/tauridium-audit.jsonl");
        assert_eq!(
            rotated_path(path, 2),
            Path::new("audit/tauridium-audit.jsonl.2")
        );
    }
    #[test]
    fn audit_redaction_preserves_non_secret_values_and_arrays() {
        let value = json!({
            "theme": "blackOled",
            "service": { "id": "mail", "url": "https://example.test" },
            "list": [1, 2, 3]
        });
        assert_eq!(redact(&value), value);
    }

    #[test]
    fn audit_redaction_matches_secret_like_keys_case_insensitively() {
        let value = json!({
            "AuthorizationHeader": "Bearer x",
            "clientSecret": "x",
            "SESSIONCOOKIE": "x",
            "safe": "visible"
        });
        let redacted = redact(&value);
        assert_eq!(redacted["AuthorizationHeader"], "[redacted]");
        assert_eq!(redacted["clientSecret"], "[redacted]");
        assert_eq!(redacted["SESSIONCOOKIE"], "[redacted]");
        assert_eq!(redacted["safe"], "visible");
    }

    #[test]
    fn audit_rotation_generations_are_bounded() {
        let path = Path::new("audit/tauridium-audit.jsonl");
        assert_eq!(AUDIT_ROTATIONS, 4);
        assert_eq!(
            rotated_path(path, AUDIT_ROTATIONS),
            Path::new("audit/tauridium-audit.jsonl.4")
        );
        assert!(MAX_READ_ENTRIES >= 5_000);
        assert!(MAX_AUDIT_FILE_BYTES >= 1024 * 1024);
    }
}
