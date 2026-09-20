use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::fs::{self, File};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager};

const AUDIT_DIR: &str = "audit";
const AUDIT_FILE: &str = "tauridium-audit.jsonl";
const MAX_AUDIT_FILE_BYTES: u64 = 5 * 1024 * 1024;
const AUDIT_ROTATIONS: usize = 4;
const MAX_READ_ENTRIES: usize = 10_000;
const AUDIT_REVERSE_CHUNK_BYTES: usize = 64 * 1024;
const AUDIT_CURSOR_VERSION: u8 = 1;
const AUDIT_CURSOR_FINGERPRINT_BYTES: u64 = 4 * 1024;
pub(crate) const AUDIT_PAGE_DEFAULT: usize = 100;
pub(crate) const AUDIT_PAGE_MAX: usize = 500;

// Keep audit retention/read limits large enough for useful diagnostics. These are
// compile-time invariants so Clippy does not have to lint constant runtime tests.
const _: () = {
    assert!(MAX_READ_ENTRIES >= 5_000);
    assert!(AUDIT_PAGE_DEFAULT <= AUDIT_PAGE_MAX);
    assert!(AUDIT_PAGE_MAX <= MAX_READ_ENTRIES);
    assert!(MAX_AUDIT_FILE_BYTES >= 1024 * 1024);
    assert!(AUDIT_ROTATIONS == 4);
};

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

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct AuditLogPage {
    pub entries: Vec<AuditEntry>,
    pub next_cursor: Option<String>,
    pub has_more: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct AuditCursor {
    version: u8,
    generation: usize,
    offset: u64,
    snapshot_len: u64,
    fingerprint: String,
}

#[derive(Debug)]
struct ReverseReadResult {
    entries: Vec<AuditEntry>,
    next_offset: u64,
    bytes_read: u64,
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

fn generation_path(path: &Path, generation: usize) -> PathBuf {
    if generation == 0 {
        path.to_path_buf()
    } else {
        rotated_path(path, generation)
    }
}

fn malformed_entry(error: impl ToString) -> AuditEntry {
    AuditEntry {
        timestamp_unix_ms: now_ms(),
        level: "warning".into(),
        category: "audit".into(),
        action: "parse".into(),
        outcome: "warning".into(),
        message: "A malformed audit-log record was skipped".into(),
        details: json!({ "error": error.to_string() }),
    }
}

fn parse_audit_line(line: &[u8]) -> Option<AuditEntry> {
    if line.iter().all(|byte| byte.is_ascii_whitespace()) {
        return None;
    }
    Some(match serde_json::from_slice::<AuditEntry>(line) {
        Ok(entry) => entry,
        Err(error) => malformed_entry(error),
    })
}

fn assemble_reverse_line(prefix: &[u8], fragments: &[Vec<u8>]) -> Vec<u8> {
    let capacity = prefix.len() + fragments.iter().map(Vec::len).sum::<usize>();
    let mut line = Vec::with_capacity(capacity);
    line.extend_from_slice(prefix);
    for fragment in fragments.iter().rev() {
        line.extend_from_slice(fragment);
    }
    line
}

fn read_reverse_entries(
    path: &Path,
    end_offset: u64,
    limit: usize,
) -> Result<ReverseReadResult, String> {
    if limit == 0 {
        return Ok(ReverseReadResult {
            entries: Vec::new(),
            next_offset: end_offset,
            bytes_read: 0,
        });
    }

    let mut file = File::open(path)
        .map_err(|error| format!("Unable to open audit log for reading: {error}"))?;
    let file_len = file
        .metadata()
        .map_err(|error| format!("Unable to inspect audit log: {error}"))?
        .len();
    let mut position = end_offset.min(file_len);
    let mut fragments: Vec<Vec<u8>> = Vec::new();
    let mut entries = Vec::with_capacity(limit);
    let mut bytes_read = 0_u64;

    while position > 0 {
        let start = position.saturating_sub(AUDIT_REVERSE_CHUNK_BYTES as u64);
        let read_len = usize::try_from(position - start)
            .map_err(|_| "Audit-log reverse read chunk is too large".to_string())?;
        let mut buffer = vec![0_u8; read_len];
        file.seek(SeekFrom::Start(start))
            .map_err(|error| format!("Unable to seek audit log: {error}"))?;
        file.read_exact(&mut buffer)
            .map_err(|error| format!("Unable to read audit log: {error}"))?;
        bytes_read += read_len as u64;

        let mut segment_end = buffer.len();
        for newline_index in (0..buffer.len())
            .rev()
            .filter(|index| buffer[*index] == b'\n')
        {
            let line = assemble_reverse_line(&buffer[newline_index + 1..segment_end], &fragments);
            fragments.clear();
            segment_end = newline_index;
            if let Some(entry) = parse_audit_line(&line) {
                entries.push(entry);
                if entries.len() == limit {
                    return Ok(ReverseReadResult {
                        entries,
                        next_offset: start + newline_index as u64,
                        bytes_read,
                    });
                }
            }
        }

        if segment_end > 0 {
            fragments.push(buffer[..segment_end].to_vec());
        }
        position = start;
    }

    if !fragments.is_empty() {
        let line = assemble_reverse_line(&[], &fragments);
        if let Some(entry) = parse_audit_line(&line) {
            entries.push(entry);
        }
    }

    Ok(ReverseReadResult {
        entries,
        next_offset: 0,
        bytes_read,
    })
}

fn audit_file_fingerprint(path: &Path, snapshot_len: u64) -> Result<String, String> {
    let mut file = File::open(path)
        .map_err(|error| format!("Unable to open audit log for cursor validation: {error}"))?;
    let mut hasher = Sha256::new();
    hasher.update(snapshot_len.to_le_bytes());

    let head_len = snapshot_len.min(AUDIT_CURSOR_FINGERPRINT_BYTES);
    if head_len > 0 {
        let mut head = vec![
            0_u8;
            usize::try_from(head_len).map_err(|_| {
                "Audit-log fingerprint chunk is too large".to_string()
            })?
        ];
        file.read_exact(&mut head)
            .map_err(|error| format!("Unable to read audit-log cursor fingerprint: {error}"))?;
        hasher.update(&head);
    }

    if snapshot_len > AUDIT_CURSOR_FINGERPRINT_BYTES {
        let tail_start = snapshot_len.saturating_sub(AUDIT_CURSOR_FINGERPRINT_BYTES);
        file.seek(SeekFrom::Start(tail_start))
            .map_err(|error| format!("Unable to seek audit-log cursor fingerprint: {error}"))?;
        let mut tail = vec![
            0_u8;
            usize::try_from(snapshot_len - tail_start).map_err(|_| {
                "Audit-log fingerprint chunk is too large".to_string()
            })?
        ];
        file.read_exact(&mut tail)
            .map_err(|error| format!("Unable to read audit-log cursor fingerprint: {error}"))?;
        hasher.update(&tail);
    }

    Ok(format!("{:x}", hasher.finalize()))
}

fn encode_cursor(cursor: &AuditCursor) -> Result<String, String> {
    let payload = serde_json::to_vec(cursor)
        .map_err(|error| format!("Unable to serialize audit-log cursor: {error}"))?;
    Ok(URL_SAFE_NO_PAD.encode(payload))
}

fn decode_cursor(encoded: &str) -> Result<AuditCursor, String> {
    let payload = URL_SAFE_NO_PAD
        .decode(encoded)
        .map_err(|_| "Audit log cursor is invalid; refresh the audit log.".to_string())?;
    let cursor = serde_json::from_slice::<AuditCursor>(&payload)
        .map_err(|_| "Audit log cursor is invalid; refresh the audit log.".to_string())?;
    if cursor.version != AUDIT_CURSOR_VERSION
        || cursor.generation > AUDIT_ROTATIONS
        || cursor.offset > cursor.snapshot_len
    {
        return Err("Audit log cursor is invalid; refresh the audit log.".into());
    }
    Ok(cursor)
}

fn validate_cursor(path: &Path, cursor: &AuditCursor) -> Result<(), String> {
    let candidate = generation_path(path, cursor.generation);
    let metadata = fs::metadata(&candidate)
        .map_err(|_| "Audit log cursor is stale; refresh the audit log.".to_string())?;
    let len_matches = if cursor.generation == 0 {
        metadata.len() >= cursor.snapshot_len
    } else {
        metadata.len() == cursor.snapshot_len
    };
    if !len_matches {
        return Err("Audit log cursor is stale; refresh the audit log.".into());
    }
    let fingerprint = audit_file_fingerprint(&candidate, cursor.snapshot_len)?;
    if fingerprint != cursor.fingerprint {
        return Err("Audit log cursor is stale; refresh the audit log.".into());
    }
    Ok(())
}

fn older_entries_exist(path: &Path, generation: usize, offset: u64) -> Result<bool, String> {
    let current = generation_path(path, generation);
    if current.exists() && offset > 0 {
        let read = read_reverse_entries(&current, offset, 1)?;
        debug_assert!(read.bytes_read <= offset);
        if !read.entries.is_empty() {
            return Ok(true);
        }
    }

    for older_generation in generation + 1..=AUDIT_ROTATIONS {
        let older = generation_path(path, older_generation);
        let Ok(metadata) = fs::metadata(&older) else {
            continue;
        };
        if metadata.len() == 0 {
            continue;
        }
        let read = read_reverse_entries(&older, metadata.len(), 1)?;
        debug_assert!(read.bytes_read <= metadata.len());
        if !read.entries.is_empty() {
            return Ok(true);
        }
    }
    Ok(false)
}

fn read_page_from_path(
    path: &Path,
    cursor: Option<&str>,
    limit: usize,
) -> Result<AuditLogPage, String> {
    let limit = limit.clamp(1, AUDIT_PAGE_MAX);
    let mut cursor_state = cursor.map(decode_cursor).transpose()?;
    if let Some(state) = &cursor_state {
        validate_cursor(path, state)?;
    }

    let mut generation = cursor_state.as_ref().map_or(0, |state| state.generation);
    let mut entries = Vec::with_capacity(limit);

    while generation <= AUDIT_ROTATIONS {
        let candidate = generation_path(path, generation);
        let state_for_generation = cursor_state
            .as_ref()
            .filter(|state| state.generation == generation)
            .cloned();

        let (snapshot_len, fingerprint, end_offset) = if let Some(state) = state_for_generation {
            (state.snapshot_len, state.fingerprint, state.offset)
        } else {
            let Ok(metadata) = fs::metadata(&candidate) else {
                generation += 1;
                continue;
            };
            let snapshot_len = metadata.len();
            let fingerprint = audit_file_fingerprint(&candidate, snapshot_len)?;
            (snapshot_len, fingerprint, snapshot_len)
        };

        cursor_state = None;
        if end_offset > 0 && entries.len() < limit {
            let read = read_reverse_entries(&candidate, end_offset, limit - entries.len())?;
            debug_assert!(read.bytes_read <= end_offset);
            entries.extend(read.entries);

            if entries.len() == limit {
                let has_more = older_entries_exist(path, generation, read.next_offset)?;
                let next_cursor = if has_more {
                    Some(encode_cursor(&AuditCursor {
                        version: AUDIT_CURSOR_VERSION,
                        generation,
                        offset: read.next_offset,
                        snapshot_len,
                        fingerprint,
                    })?)
                } else {
                    None
                };
                return Ok(AuditLogPage {
                    entries,
                    next_cursor,
                    has_more,
                });
            }
        }

        generation += 1;
    }

    Ok(AuditLogPage {
        entries,
        next_cursor: None,
        has_more: false,
    })
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
                Err(error) => entries.push(malformed_entry(error)),
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

pub(crate) fn read_page(
    app: &AppHandle,
    cursor: Option<&str>,
    limit: usize,
) -> Result<AuditLogPage, String> {
    let _guard = audit_guard()?;
    let path = audit_path(app)?;
    read_page_from_path(&path, cursor, limit)
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
    use std::sync::atomic::{AtomicU64, Ordering};

    static TEST_DIR_COUNTER: AtomicU64 = AtomicU64::new(0);

    struct TestAuditDir {
        root: PathBuf,
    }

    impl TestAuditDir {
        fn new() -> Self {
            let counter = TEST_DIR_COUNTER.fetch_add(1, Ordering::Relaxed);
            let root = std::env::temp_dir().join(format!(
                "tauridium-audit-{}-{}-{counter}",
                std::process::id(),
                now_ms()
            ));
            fs::create_dir_all(&root).expect("create audit test directory");
            Self { root }
        }

        fn path(&self) -> PathBuf {
            self.root.join(AUDIT_FILE)
        }
    }

    impl Drop for TestAuditDir {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.root);
        }
    }

    fn test_entry(index: usize) -> AuditEntry {
        AuditEntry {
            timestamp_unix_ms: index as u64,
            level: "info".into(),
            category: "test".into(),
            action: "page".into(),
            outcome: "success".into(),
            message: format!("event-{index}"),
            details: json!({ "index": index }),
        }
    }

    fn write_entries(path: &Path, entries: &[AuditEntry], trailing_newline: bool) {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).expect("create audit parent");
        }
        let mut text = entries
            .iter()
            .map(|entry| serde_json::to_string(entry).expect("serialize audit entry"))
            .collect::<Vec<_>>()
            .join("\n");
        if trailing_newline && !text.is_empty() {
            text.push('\n');
        }
        fs::write(path, text).expect("write audit fixture");
    }

    fn append_entries(path: &Path, entries: &[AuditEntry]) {
        let mut file = fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)
            .expect("open audit fixture for append");
        for entry in entries {
            serde_json::to_writer(&mut file, entry).expect("serialize appended audit entry");
            file.write_all(b"\n").expect("append audit newline");
        }
    }

    fn messages(entries: &[AuditEntry]) -> Vec<&str> {
        entries.iter().map(|entry| entry.message.as_str()).collect()
    }

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
        assert_eq!(
            rotated_path(path, AUDIT_ROTATIONS),
            Path::new("audit/tauridium-audit.jsonl.4")
        );
    }

    #[test]
    fn reverse_reader_returns_newest_page_without_consuming_full_history() {
        let dir = TestAuditDir::new();
        let path = dir.path();
        let entries = (0..10_000).map(test_entry).collect::<Vec<_>>();
        write_entries(&path, &entries, true);

        let file_len = fs::metadata(&path).expect("audit fixture metadata").len();
        let page = read_reverse_entries(&path, file_len, 100).expect("read newest page");

        assert_eq!(page.entries.len(), 100);
        assert_eq!(page.entries[0].message, "event-9999");
        assert_eq!(page.entries[99].message, "event-9900");
        assert!(page.next_offset > 0);
        assert!(
            page.bytes_read < file_len / 4,
            "tail page should not read the complete audit file"
        );
    }

    #[test]
    fn pagination_walks_one_file_without_duplicates_or_omissions() {
        let dir = TestAuditDir::new();
        let path = dir.path();
        let entries = (1..=11).map(test_entry).collect::<Vec<_>>();
        write_entries(&path, &entries, true);

        let mut cursor = None;
        let mut seen = Vec::new();
        loop {
            let page = read_page_from_path(&path, cursor.as_deref(), 3).expect("read audit page");
            seen.extend(page.entries.iter().map(|entry| entry.message.clone()));
            if !page.has_more {
                assert!(page.next_cursor.is_none());
                break;
            }
            cursor = page.next_cursor;
        }

        let expected = (1..=11)
            .rev()
            .map(|index| format!("event-{index}"))
            .collect::<Vec<_>>();
        assert_eq!(seen, expected);
    }

    #[test]
    fn pagination_crosses_rotated_files_newest_first() {
        let dir = TestAuditDir::new();
        let path = dir.path();
        write_entries(
            &rotated_path(&path, 1),
            &(1..=5).map(test_entry).collect::<Vec<_>>(),
            true,
        );
        write_entries(&path, &(6..=10).map(test_entry).collect::<Vec<_>>(), true);

        let first = read_page_from_path(&path, None, 7).expect("first rotated page");
        assert_eq!(
            messages(&first.entries),
            vec!["event-10", "event-9", "event-8", "event-7", "event-6", "event-5", "event-4"]
        );
        assert!(first.has_more);

        let second = read_page_from_path(&path, first.next_cursor.as_deref(), 7)
            .expect("second rotated page");
        assert_eq!(
            messages(&second.entries),
            vec!["event-3", "event-2", "event-1"]
        );
        assert!(!second.has_more);
    }

    #[test]
    fn reverse_reader_handles_record_larger_than_read_chunk() {
        let dir = TestAuditDir::new();
        let path = dir.path();
        let mut large = test_entry(2);
        large.details = json!({ "payload": "x".repeat(AUDIT_REVERSE_CHUNK_BYTES * 2 + 17) });
        write_entries(&path, &[test_entry(1), large], true);

        let page = read_page_from_path(&path, None, 2).expect("read long audit record");

        assert_eq!(messages(&page.entries), vec!["event-2", "event-1"]);
        assert!(!page.has_more);
    }

    #[test]
    fn reverse_reader_handles_file_without_final_newline() {
        let dir = TestAuditDir::new();
        let path = dir.path();
        write_entries(&path, &[test_entry(1), test_entry(2)], false);

        let page = read_page_from_path(&path, None, 10).expect("read audit without final newline");

        assert_eq!(messages(&page.entries), vec!["event-2", "event-1"]);
        assert!(!page.has_more);
    }

    #[test]
    fn paging_skips_empty_current_and_rotated_files() {
        let dir = TestAuditDir::new();
        let path = dir.path();
        fs::write(&path, "").expect("write empty current audit");
        fs::write(rotated_path(&path, 1), "").expect("write empty rotation");
        write_entries(&rotated_path(&path, 2), &[test_entry(1)], true);

        let page = read_page_from_path(&path, None, 10).expect("read through empty audit files");

        assert_eq!(messages(&page.entries), vec!["event-1"]);
        assert!(!page.has_more);
    }

    #[test]
    fn all_empty_audit_files_return_empty_page() {
        let dir = TestAuditDir::new();
        let path = dir.path();
        fs::write(&path, "").expect("write empty current audit");
        fs::write(rotated_path(&path, 1), "").expect("write empty rotation");

        let page = read_page_from_path(&path, None, 10).expect("read empty audit history");

        assert!(page.entries.is_empty());
        assert!(!page.has_more);
        assert!(page.next_cursor.is_none());
    }

    #[test]
    fn malformed_or_out_of_range_cursor_fails_safely() {
        let dir = TestAuditDir::new();
        let path = dir.path();
        write_entries(&path, &[test_entry(1)], true);

        let malformed = read_page_from_path(&path, Some("not-a-cursor"), 10)
            .expect_err("malformed cursor must fail");
        assert!(malformed.contains("cursor is invalid"));

        let invalid = AuditCursor {
            version: AUDIT_CURSOR_VERSION,
            generation: AUDIT_ROTATIONS + 1,
            offset: 0,
            snapshot_len: 0,
            fingerprint: String::new(),
        };
        let encoded = encode_cursor(&invalid).expect("encode invalid cursor fixture");
        let out_of_range = read_page_from_path(&path, Some(&encoded), 10)
            .expect_err("out-of-range cursor must fail");
        assert!(out_of_range.contains("cursor is invalid"));
    }

    #[test]
    fn cursor_remains_stable_when_current_log_is_appended() {
        let dir = TestAuditDir::new();
        let path = dir.path();
        write_entries(&path, &(1..=6).map(test_entry).collect::<Vec<_>>(), true);

        let first = read_page_from_path(&path, None, 2).expect("first page");
        assert_eq!(messages(&first.entries), vec!["event-6", "event-5"]);
        append_entries(&path, &[test_entry(7), test_entry(8)]);

        let second = read_page_from_path(&path, first.next_cursor.as_deref(), 2)
            .expect("older page after append");
        assert_eq!(messages(&second.entries), vec!["event-4", "event-3"]);
    }

    #[test]
    fn rotation_between_pages_marks_cursor_stale_instead_of_misreading() {
        let dir = TestAuditDir::new();
        let path = dir.path();
        write_entries(&path, &(1..=6).map(test_entry).collect::<Vec<_>>(), true);
        let first = read_page_from_path(&path, None, 2).expect("first page");
        let cursor = first.next_cursor.expect("first page cursor");

        fs::rename(&path, rotated_path(&path, 1)).expect("rotate current fixture");
        write_entries(&path, &[test_entry(7)], true);

        let error = read_page_from_path(&path, Some(&cursor), 2)
            .expect_err("rotation should invalidate current-file cursor");
        assert!(error.contains("cursor is stale"));
    }

    #[test]
    fn malformed_historical_record_is_tolerated_as_warning_entry() {
        let dir = TestAuditDir::new();
        let path = dir.path();
        fs::write(
            &path,
            format!(
                "{}\n{{not-json}}\n",
                serde_json::to_string(&test_entry(1)).expect("serialize fixture")
            ),
        )
        .expect("write malformed audit fixture");

        let page = read_page_from_path(&path, None, 10).expect("read malformed history");

        assert_eq!(page.entries.len(), 2);
        assert_eq!(page.entries[0].level, "warning");
        assert_eq!(page.entries[0].action, "parse");
        assert_eq!(page.entries[1].message, "event-1");
    }
}
