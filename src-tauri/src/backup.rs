use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::recipes::CustomRecipeBackup;
use crate::replace_file;

const BACKUP_FORMAT: &str = "tauridium-backup";
const BACKUP_SCHEMA_CURRENT: u32 = 2;
const BACKUP_SCHEMA_MIN: u32 = 1;
const INTEGRITY_ALGORITHM: &str = "sha256";
const MAX_BACKUP_BYTES: u64 = 64 * 1024 * 1024;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum RetentionMode {
    Count,
    Age,
    CountAndAge,
    Tiered,
}

impl RetentionMode {
    pub(crate) fn parse(value: &str) -> Result<Self, String> {
        match value {
            "count" => Ok(Self::Count),
            "age" => Ok(Self::Age),
            "countAndAge" => Ok(Self::CountAndAge),
            "tiered" => Ok(Self::Tiered),
            _ => Err(format!(
                "Unsupported automatic backup retention mode: {value}"
            )),
        }
    }
}

#[derive(Clone, Debug)]
pub(crate) struct RetentionCandidate {
    pub path: PathBuf,
    pub modified: SystemTime,
}

const DAY_SECS: u64 = 24 * 60 * 60;

fn filename_calendar_key(path: &Path, bytes: usize) -> Option<String> {
    let name = path.file_name()?.to_str()?;
    let stamp = name.strip_prefix("tauridium-auto-backup-")?;
    if stamp.len() < bytes {
        return None;
    }
    let key = &stamp[..bytes];
    if key
        .bytes()
        .all(|byte| byte.is_ascii_digit() || byte == b'-')
    {
        Some(key.to_string())
    } else {
        None
    }
}

fn age_days(now: SystemTime, modified: SystemTime) -> u64 {
    now.duration_since(modified).unwrap_or_default().as_secs() / DAY_SECS
}

/// Returns the automatic-backup paths that may be deleted after a newly created backup
/// has already passed integrity verification. The newest backup is always retained.
pub(crate) fn retention_paths_to_delete(
    mut candidates: Vec<RetentionCandidate>,
    mode: RetentionMode,
    count: usize,
    max_age_days: u64,
    now: SystemTime,
) -> Vec<PathBuf> {
    candidates.sort_by(|left, right| {
        right
            .modified
            .cmp(&left.modified)
            .then_with(|| left.path.cmp(&right.path))
    });
    if candidates.len() <= 1 {
        return Vec::new();
    }

    let mut keep = HashSet::<PathBuf>::new();
    if let Some(newest) = candidates.first() {
        keep.insert(newest.path.clone());
    }

    match mode {
        RetentionMode::Count => {
            for candidate in candidates.iter().take(count.max(1)) {
                keep.insert(candidate.path.clone());
            }
        }
        RetentionMode::Age => {
            for candidate in &candidates {
                if age_days(now, candidate.modified) <= max_age_days {
                    keep.insert(candidate.path.clone());
                }
            }
        }
        RetentionMode::CountAndAge => {
            for candidate in candidates.iter().take(count.max(1)) {
                if age_days(now, candidate.modified) <= max_age_days {
                    keep.insert(candidate.path.clone());
                }
            }
        }
        RetentionMode::Tiered => {
            // GFS-style history: one representative per recent day, then per week-age bucket,
            // calendar month, and calendar year. This preserves long-range recovery points while
            // bounding growth without pretending a single directory satisfies 3-2-1 storage.
            let mut buckets = HashSet::<String>::new();
            for candidate in &candidates {
                let days = age_days(now, candidate.modified);
                let bucket = if days <= 7 {
                    filename_calendar_key(&candidate.path, 10)
                        .map(|key| format!("day:{key}"))
                        .unwrap_or_else(|| format!("day-age:{days}"))
                } else if days <= 35 {
                    format!("week-age:{}", days / 7)
                } else if days <= 400 {
                    filename_calendar_key(&candidate.path, 7)
                        .map(|key| format!("month:{key}"))
                        .unwrap_or_else(|| format!("month-age:{}", days / 30))
                } else if days <= 5 * 366 {
                    filename_calendar_key(&candidate.path, 4)
                        .map(|key| format!("year:{key}"))
                        .unwrap_or_else(|| format!("year-age:{}", days / 365))
                } else {
                    continue;
                };
                if buckets.insert(bucket) {
                    keep.insert(candidate.path.clone());
                }
            }
        }
    }

    candidates
        .into_iter()
        .filter(|candidate| !keep.contains(&candidate.path))
        .map(|candidate| candidate.path)
        .collect()
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct BackupIntegrity {
    algorithm: String,
    payload_sha256: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct IntegrityMaterial<'a> {
    format: &'a str,
    schema: u32,
    app_version: &'a str,
    exported_at_unix: u64,
    contains_sensitive_data: bool,
    excluded: &'a [String],
    app_settings: &'a Value,
    local_profile: &'a Value,
    custom_recipes: &'a [CustomRecipeBackup],
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct BackupDocument {
    format: String,
    schema: u32,
    app_version: String,
    exported_at_unix: u64,
    contains_sensitive_data: bool,
    excluded: Vec<String>,
    app_settings: Value,
    local_profile: Value,
    custom_recipes: Vec<CustomRecipeBackup>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    integrity: Option<BackupIntegrity>,
    #[serde(skip)]
    source_schema: u32,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct BackupSummary {
    pub path: String,
    pub schema: u32,
    pub source_schema: u32,
    pub integrity_verified: bool,
    pub custom_recipe_count: usize,
    pub service_count: usize,
    pub workspace_count: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub recovery_backup_path: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub warnings: Vec<String>,
}

impl BackupDocument {
    pub(crate) fn new(
        app_version: &str,
        app_settings: Value,
        local_profile: Value,
        custom_recipes: Vec<CustomRecipeBackup>,
    ) -> Self {
        let exported_at_unix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        let mut document = Self {
            format: BACKUP_FORMAT.to_string(),
            schema: BACKUP_SCHEMA_CURRENT,
            app_version: app_version.to_string(),
            exported_at_unix,
            contains_sensitive_data: true,
            excluded: vec![
                "ferdiumSessionCredentials".into(),
                "websiteCookiesAndStorage".into(),
                "remoteRecipeCache".into(),
                "windowMonitorGeometry".into(),
            ],
            app_settings,
            local_profile,
            custom_recipes,
            integrity: None,
            source_schema: BACKUP_SCHEMA_CURRENT,
        };
        document.refresh_integrity();
        document
    }

    fn from_value(value: Value) -> Result<Self, String> {
        let format = value
            .get("format")
            .and_then(Value::as_str)
            .ok_or_else(|| "Selected file is not a Tauridium backup".to_string())?;
        if format != BACKUP_FORMAT {
            return Err("Selected file is not a Tauridium backup".into());
        }
        let source_schema = value
            .get("schema")
            .and_then(Value::as_u64)
            .and_then(|schema| u32::try_from(schema).ok())
            .ok_or_else(|| "Tauridium backup schema is missing or invalid".to_string())?;
        if !(BACKUP_SCHEMA_MIN..=BACKUP_SCHEMA_CURRENT).contains(&source_schema) {
            return Err(format!(
                "Unsupported Tauridium backup schema {source_schema} (supported {BACKUP_SCHEMA_MIN}..={BACKUP_SCHEMA_CURRENT})"
            ));
        }

        let mut document: Self = serde_json::from_value(value)
            .map_err(|error| format!("Unable to parse Tauridium backup: {error}"))?;
        document.source_schema = source_schema;
        if source_schema == 1 {
            document.schema = BACKUP_SCHEMA_CURRENT;
            document.integrity = None;
        }
        document.validate()?;
        Ok(document)
    }

    fn integrity_material(&self) -> IntegrityMaterial<'_> {
        IntegrityMaterial {
            format: &self.format,
            schema: BACKUP_SCHEMA_CURRENT,
            app_version: &self.app_version,
            exported_at_unix: self.exported_at_unix,
            contains_sensitive_data: self.contains_sensitive_data,
            excluded: &self.excluded,
            app_settings: &self.app_settings,
            local_profile: &self.local_profile,
            custom_recipes: &self.custom_recipes,
        }
    }

    fn payload_digest(&self) -> String {
        let payload = serde_json::to_vec(&self.integrity_material()).unwrap_or_default();
        let digest = Sha256::digest(payload);
        digest
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<Vec<_>>()
            .join("")
    }

    fn refresh_integrity(&mut self) {
        self.integrity = Some(BackupIntegrity {
            algorithm: INTEGRITY_ALGORITHM.into(),
            payload_sha256: self.payload_digest(),
        });
    }

    fn validate_integrity(&self) -> Result<(), String> {
        if self.source_schema < 2 {
            return Ok(());
        }
        let integrity = self
            .integrity
            .as_ref()
            .ok_or_else(|| "Backup integrity metadata is missing".to_string())?;
        if integrity.algorithm != INTEGRITY_ALGORITHM {
            return Err(format!(
                "Unsupported backup integrity algorithm: {}",
                integrity.algorithm
            ));
        }
        let expected = self.payload_digest();
        if integrity.payload_sha256 != expected {
            let message = "Backup integrity check failed; the file is corrupted or was modified";
            return Err(message.into());
        }
        Ok(())
    }

    pub(crate) fn validate(&self) -> Result<(), String> {
        if self.format != BACKUP_FORMAT {
            return Err("Selected file is not a Tauridium backup".into());
        }
        if self.schema != BACKUP_SCHEMA_CURRENT {
            return Err(format!(
                "Internal backup migration did not reach schema {BACKUP_SCHEMA_CURRENT}"
            ));
        }
        if !self.app_settings.is_object() {
            return Err("Backup appSettings must be a JSON object".into());
        }
        if !self.local_profile.is_object() {
            return Err("Backup localProfile must be a JSON object".into());
        }
        self.validate_integrity()
    }

    pub(crate) fn app_settings(&self) -> Value {
        self.app_settings.clone()
    }

    pub(crate) fn local_profile(&self) -> Value {
        self.local_profile.clone()
    }

    pub(crate) fn custom_recipes(&self) -> &[CustomRecipeBackup] {
        &self.custom_recipes
    }

    pub(crate) fn summary(&self, path: &Path) -> BackupSummary {
        BackupSummary {
            path: path.to_string_lossy().into_owned(),
            schema: BACKUP_SCHEMA_CURRENT,
            source_schema: self.source_schema,
            integrity_verified: self.source_schema >= 2,
            custom_recipe_count: self.custom_recipes.len(),
            service_count: self
                .local_profile
                .get("services")
                .and_then(Value::as_array)
                .map_or(0, Vec::len),
            workspace_count: self
                .local_profile
                .get("workspaces")
                .and_then(Value::as_array)
                .map_or(0, Vec::len),
            recovery_backup_path: None,
            warnings: Vec::new(),
        }
    }
}

impl BackupSummary {
    pub(crate) fn with_recovery_backup_path(mut self, path: &Path) -> Self {
        self.recovery_backup_path = Some(path.to_string_lossy().into_owned());
        self
    }

    pub(crate) fn with_warning(mut self, warning: impl Into<String>) -> Self {
        self.warnings.push(warning.into());
        self
    }
}

pub(crate) fn save(path: &Path, document: &BackupDocument) -> Result<BackupSummary, String> {
    if path.as_os_str().is_empty() {
        return Err("Backup destination path is empty".into());
    }
    document.validate()?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("Unable to create backup directory: {error}"))?;
    }
    let text = serde_json::to_string_pretty(document)
        .map_err(|error| format!("Unable to serialize Tauridium backup: {error}"))?;
    let staging = backup_staging_path(path)?;
    if staging.exists() {
        fs::remove_file(&staging)
            .map_err(|error| format!("Unable to clear stale backup staging file: {error}"))?;
    }

    // Never replace an existing trusted backup until the newly written bytes have been
    // flushed to disk, parsed again, and passed the same schema + SHA-256 validation used
    // during restore. A failed staging write/verification therefore leaves the old backup intact.
    let staged = (|| -> Result<(), String> {
        let mut file = fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&staging)
            .map_err(|error| format!("Unable to create backup staging file: {error}"))?;
        file.write_all(format!("{text}\n").as_bytes())
            .map_err(|error| format!("Unable to write backup staging file: {error}"))?;
        file.sync_all()
            .map_err(|error| format!("Unable to flush backup staging file: {error}"))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&staging, fs::Permissions::from_mode(0o600))
                .map_err(|error| format!("Unable to protect backup staging file: {error}"))?;
        }

        let verified =
            load(&staging).map_err(|error| format!("Backup write verification failed: {error}"))?;
        if verified.source_schema != BACKUP_SCHEMA_CURRENT
            || verified.payload_digest() != document.payload_digest()
        {
            return Err("Backup write verification produced different validated content".into());
        }
        Ok(())
    })();
    if let Err(error) = staged {
        let _ = fs::remove_file(&staging);
        return Err(error);
    }

    replace_file(&staging, path)
        .map_err(|error| format!("Unable to finalize Tauridium backup: {error}"))?;
    #[cfg(unix)]
    if let Some(parent) = path.parent() {
        if let Ok(directory) = fs::File::open(parent) {
            let _ = directory.sync_all();
        }
    }
    Ok(document.summary(path))
}

fn backup_staging_path(path: &Path) -> Result<PathBuf, String> {
    let name = path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| "Backup destination filename is invalid".to_string())?;
    Ok(path.with_file_name(format!(".{name}.tauridium-tmp-{}", std::process::id())))
}

pub(crate) fn load(path: &Path) -> Result<BackupDocument, String> {
    let metadata =
        fs::metadata(path).map_err(|error| format!("Unable to inspect backup: {error}"))?;
    if metadata.len() > MAX_BACKUP_BYTES {
        return Err(format!(
            "Backup is too large ({} bytes; maximum {MAX_BACKUP_BYTES})",
            metadata.len()
        ));
    }
    let text =
        fs::read_to_string(path).map_err(|error| format!("Unable to read backup: {error}"))?;
    let value: Value = serde_json::from_str(&text)
        .map_err(|error| format!("Unable to parse Tauridium backup: {error}"))?;
    BackupDocument::from_value(value)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn sample() -> BackupDocument {
        BackupDocument::new(
            "9.9.9",
            json!({"theme": "dark"}),
            json!({"version": 1, "services": [{"id": "svc"}], "workspaces": []}),
            vec![CustomRecipeBackup {
                id: "local-ai".into(),
                package: json!({
                    "id": "local-ai",
                    "name": "Local AI",
                    "config": {"serviceURL": "https://example.com"}
                }),
                icon_svg: "<svg></svg>".into(),
                webview_js: "console.log('local');".into(),
            }],
        )
    }

    #[test]
    fn backup_round_trips_and_reports_contents() {
        let root =
            std::env::temp_dir().join(format!("tauridium-backup-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        let path = root.join("backup.json");
        let staging = backup_staging_path(&path).unwrap();
        let summary = save(&path, &sample()).unwrap();
        assert!(!staging.exists());
        assert_eq!(summary.schema, BACKUP_SCHEMA_CURRENT);
        assert!(summary.integrity_verified);
        assert_eq!(summary.custom_recipe_count, 1);
        assert_eq!(summary.service_count, 1);
        assert_eq!(summary.workspace_count, 0);
        let loaded = load(&path).unwrap();
        assert_eq!(loaded.custom_recipes().len(), 1);
        assert_eq!(loaded.app_settings()["theme"], "dark");
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn backup_detects_payload_tampering() {
        let mut value = serde_json::to_value(sample()).unwrap();
        value["appSettings"]["theme"] = Value::String("light".into());
        assert!(BackupDocument::from_value(value).is_err());
    }

    #[test]
    fn legacy_schema_one_is_migrated_without_claiming_integrity() {
        let mut value = serde_json::to_value(sample()).unwrap();
        value["schema"] = Value::from(1);
        value.as_object_mut().unwrap().remove("integrity");
        let migrated = BackupDocument::from_value(value).unwrap();
        assert_eq!(migrated.schema, BACKUP_SCHEMA_CURRENT);
        assert_eq!(migrated.source_schema, 1);
        assert!(
            !migrated
                .summary(Path::new("legacy.json"))
                .integrity_verified
        );
    }

    #[test]
    fn backup_rejects_wrong_format_and_future_schema() {
        let mut wrong_format = serde_json::to_value(sample()).unwrap();
        wrong_format["format"] = Value::String("other".into());
        assert!(BackupDocument::from_value(wrong_format).is_err());

        let mut future = serde_json::to_value(sample()).unwrap();
        future["schema"] = Value::from(BACKUP_SCHEMA_CURRENT + 1);
        assert!(BackupDocument::from_value(future).is_err());
    }

    #[test]
    fn current_schema_requires_supported_integrity_metadata() {
        let mut missing = serde_json::to_value(sample()).unwrap();
        missing.as_object_mut().unwrap().remove("integrity");
        assert!(BackupDocument::from_value(missing)
            .unwrap_err()
            .contains("integrity metadata is missing"));

        let mut algorithm = serde_json::to_value(sample()).unwrap();
        algorithm["integrity"]["algorithm"] = Value::String("other".into());
        assert!(BackupDocument::from_value(algorithm)
            .unwrap_err()
            .contains("Unsupported backup integrity algorithm"));
    }

    #[test]
    fn backup_rejects_invalid_owned_payload_shapes() {
        let mut settings = serde_json::to_value(sample()).unwrap();
        settings["appSettings"] = Value::Array(Vec::new());
        // Re-sign so this test reaches structural validation rather than integrity validation.
        let mut document: BackupDocument = serde_json::from_value(settings).unwrap();
        document.source_schema = BACKUP_SCHEMA_CURRENT;
        document.refresh_integrity();
        assert!(document.validate().unwrap_err().contains("appSettings"));

        let mut profile = sample();
        profile.local_profile = Value::Array(Vec::new());
        profile.refresh_integrity();
        assert!(profile.validate().unwrap_err().contains("localProfile"));
    }

    #[test]
    fn load_rejects_oversized_backup_before_reading_payload() {
        let root =
            std::env::temp_dir().join(format!("tauridium-backup-size-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        let path = root.join("oversized.json");
        let file = fs::File::create(&path).unwrap();
        file.set_len(MAX_BACKUP_BYTES + 1).unwrap();
        drop(file);
        assert!(load(&path).unwrap_err().contains("Backup is too large"));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn restore_summary_can_report_automatic_recovery_snapshot() {
        let path = Path::new("backup.json");
        let recovery = Path::new("backups/pre-restore-123.json");
        let summary = sample().summary(path).with_recovery_backup_path(recovery);
        assert_eq!(
            summary.recovery_backup_path.as_deref(),
            Some("backups/pre-restore-123.json")
        );
    }

    fn candidate(name: &str, age_days: u64, now: SystemTime) -> RetentionCandidate {
        RetentionCandidate {
            path: PathBuf::from(name),
            modified: now - std::time::Duration::from_secs(age_days * DAY_SECS),
        }
    }

    #[test]
    fn count_retention_keeps_newest_n_and_never_deletes_only_backup() {
        let now = UNIX_EPOCH + std::time::Duration::from_secs(2_000 * DAY_SECS);
        let items = vec![
            candidate("tauridium-auto-backup-2026-08-19-120000-000.json", 0, now),
            candidate("tauridium-auto-backup-2026-08-18-120000-000.json", 1, now),
            candidate("tauridium-auto-backup-2026-08-17-120000-000.json", 2, now),
        ];
        let deleted = retention_paths_to_delete(items, RetentionMode::Count, 2, 90, now);
        assert_eq!(deleted.len(), 1);
        assert!(deleted[0].to_string_lossy().contains("2026-08-17"));
        assert!(retention_paths_to_delete(
            vec![candidate(
                "tauridium-auto-backup-2026-08-19-120000-000.json",
                0,
                now
            )],
            RetentionMode::Count,
            1,
            90,
            now
        )
        .is_empty());
    }

    #[test]
    fn age_retention_always_keeps_newest_even_when_every_backup_is_old() {
        let now = UNIX_EPOCH + std::time::Duration::from_secs(2_000 * DAY_SECS);
        let items = vec![
            candidate("tauridium-auto-backup-2026-01-01-120000-000.json", 120, now),
            candidate("tauridium-auto-backup-2025-12-01-120000-000.json", 150, now),
        ];
        let deleted = retention_paths_to_delete(items, RetentionMode::Age, 10, 30, now);
        assert_eq!(deleted.len(), 1);
        assert!(deleted[0].to_string_lossy().contains("2025-12-01"));
    }

    #[test]
    fn count_and_age_requires_both_limits_but_keeps_newest() {
        let now = UNIX_EPOCH + std::time::Duration::from_secs(2_000 * DAY_SECS);
        let items = vec![
            candidate("tauridium-auto-backup-2026-08-19-120000-000.json", 0, now),
            candidate("tauridium-auto-backup-2026-08-10-120000-000.json", 9, now),
            candidate("tauridium-auto-backup-2026-07-01-120000-000.json", 49, now),
        ];
        let deleted = retention_paths_to_delete(items, RetentionMode::CountAndAge, 2, 14, now);
        assert_eq!(deleted.len(), 1);
        assert!(deleted[0].to_string_lossy().contains("2026-07-01"));
    }

    #[test]
    fn tiered_retention_keeps_daily_weekly_monthly_and_yearly_representatives() {
        let now = UNIX_EPOCH + std::time::Duration::from_secs(2_000 * DAY_SECS);
        let items = vec![
            candidate("tauridium-auto-backup-2026-08-19-120000-000.json", 0, now),
            candidate("tauridium-auto-backup-2026-08-19-080000-000.json", 0, now),
            candidate("tauridium-auto-backup-2026-08-12-120000-000.json", 7, now),
            candidate("tauridium-auto-backup-2026-08-05-120000-000.json", 14, now),
            candidate("tauridium-auto-backup-2026-08-04-120000-000.json", 15, now),
            candidate("tauridium-auto-backup-2026-06-15-120000-000.json", 65, now),
            candidate("tauridium-auto-backup-2026-06-01-120000-000.json", 79, now),
            candidate("tauridium-auto-backup-2025-01-01-120000-000.json", 600, now),
            candidate("tauridium-auto-backup-2025-02-01-120000-000.json", 570, now),
            candidate(
                "tauridium-auto-backup-2019-01-01-120000-000.json",
                2_500,
                now,
            ),
        ];
        let deleted = retention_paths_to_delete(items, RetentionMode::Tiered, 10, 90, now);
        let names = deleted
            .iter()
            .filter_map(|path| path.file_name().and_then(|name| name.to_str()))
            .collect::<Vec<_>>();
        assert!(names.contains(&"tauridium-auto-backup-2026-08-19-080000-000.json"));
        assert!(names.contains(&"tauridium-auto-backup-2026-08-04-120000-000.json"));
        assert!(names.contains(&"tauridium-auto-backup-2026-06-01-120000-000.json"));
        assert!(
            names.contains(&"tauridium-auto-backup-2025-01-01-120000-000.json")
                || names.contains(&"tauridium-auto-backup-2025-02-01-120000-000.json")
        );
        assert!(names.contains(&"tauridium-auto-backup-2019-01-01-120000-000.json"));
    }
    #[test]
    fn retention_mode_parser_accepts_only_supported_modes() {
        assert_eq!(RetentionMode::parse("count").unwrap(), RetentionMode::Count);
        assert_eq!(RetentionMode::parse("age").unwrap(), RetentionMode::Age);
        assert_eq!(
            RetentionMode::parse("countAndAge").unwrap(),
            RetentionMode::CountAndAge
        );
        assert_eq!(
            RetentionMode::parse("tiered").unwrap(),
            RetentionMode::Tiered
        );
        assert!(RetentionMode::parse("forever").is_err());
    }

    #[test]
    fn backup_rejects_empty_destination_and_missing_source() {
        assert!(save(Path::new(""), &sample())
            .unwrap_err()
            .contains("destination path is empty"));
        let missing = std::env::temp_dir().join(format!(
            "tauridium-missing-backup-{}-{}.json",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos()
        ));
        assert!(load(&missing)
            .unwrap_err()
            .contains("Unable to inspect backup"));
    }

    #[test]
    fn backup_save_replaces_existing_valid_target_with_verified_content() {
        let root = std::env::temp_dir().join(format!(
            "tauridium-backup-replace-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos()
        ));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("backup.json");
        let first = sample();
        save(&path, &first).unwrap();
        let mut second = sample();
        second.app_settings["theme"] = Value::String("blackOled".into());
        second.refresh_integrity();
        save(&path, &second).unwrap();
        let loaded = load(&path).unwrap();
        assert_eq!(loaded.app_settings()["theme"], "blackOled");
        assert!(!backup_staging_path(&path).unwrap().exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn backup_save_clears_stale_staging_file_before_verified_write() {
        let root = std::env::temp_dir().join(format!(
            "tauridium-backup-stale-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos()
        ));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("backup.json");
        let staging = backup_staging_path(&path).unwrap();
        fs::write(&staging, "incomplete backup").unwrap();
        save(&path, &sample()).unwrap();
        assert!(!staging.exists());
        load(&path).unwrap();
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn backup_load_rejects_truncated_json_and_integrity_tampering() {
        let root = std::env::temp_dir().join(format!(
            "tauridium-backup-corrupt-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos()
        ));
        fs::create_dir_all(&root).unwrap();
        let truncated = root.join("truncated.json");
        fs::write(&truncated, "{\"format\":\"tauridium-backup\"").unwrap();
        assert!(load(&truncated).unwrap_err().contains("Unable to parse"));

        let tampered = root.join("tampered.json");
        let mut value = serde_json::to_value(sample()).unwrap();
        value["integrity"]["payloadSha256"] = Value::String("0".repeat(64));
        fs::write(&tampered, serde_json::to_vec_pretty(&value).unwrap()).unwrap();
        assert!(load(&tampered)
            .unwrap_err()
            .contains("integrity check failed"));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn backup_summary_accumulates_nonfatal_warnings() {
        let summary = sample()
            .summary(Path::new("backup.json"))
            .with_warning("first")
            .with_warning("second");
        assert_eq!(summary.warnings, vec!["first", "second"]);
    }

    #[test]
    fn count_retention_is_deterministic_when_timestamps_match() {
        let now = UNIX_EPOCH + std::time::Duration::from_secs(2_000 * DAY_SECS);
        let items = vec![
            candidate("tauridium-auto-backup-2026-08-19-120000-002.json", 0, now),
            candidate("tauridium-auto-backup-2026-08-19-120000-001.json", 0, now),
            candidate("tauridium-auto-backup-2026-08-19-120000-003.json", 0, now),
        ];
        let deleted = retention_paths_to_delete(items, RetentionMode::Count, 1, 90, now);
        let kept = [
            "tauridium-auto-backup-2026-08-19-120000-001.json",
            "tauridium-auto-backup-2026-08-19-120000-002.json",
            "tauridium-auto-backup-2026-08-19-120000-003.json",
        ]
        .into_iter()
        .filter(|name| !deleted.iter().any(|path| path.as_path() == Path::new(name)))
        .collect::<Vec<_>>();
        assert_eq!(
            kept,
            vec!["tauridium-auto-backup-2026-08-19-120000-001.json"]
        );
    }

    #[test]
    fn future_modified_time_is_treated_as_recent_not_expired() {
        let now = UNIX_EPOCH + std::time::Duration::from_secs(2_000 * DAY_SECS);
        let future = RetentionCandidate {
            path: PathBuf::from("tauridium-auto-backup-2026-08-20-120000-000.json"),
            modified: now + std::time::Duration::from_secs(DAY_SECS),
        };
        let old = candidate("tauridium-auto-backup-2026-01-01-120000-000.json", 200, now);
        let deleted = retention_paths_to_delete(vec![future, old], RetentionMode::Age, 10, 30, now);
        assert_eq!(
            deleted,
            vec![PathBuf::from(
                "tauridium-auto-backup-2026-01-01-120000-000.json"
            )]
        );
    }

    #[test]
    fn calendar_keys_require_expected_automatic_backup_prefix_and_shape() {
        assert_eq!(
            filename_calendar_key(
                Path::new("tauridium-auto-backup-2026-08-19-120000-000.json"),
                10
            )
            .as_deref(),
            Some("2026-08-19")
        );
        assert!(filename_calendar_key(Path::new("other-2026-08-19.json"), 10).is_none());
        assert!(
            filename_calendar_key(Path::new("tauridium-auto-backup-2026_AB_19.json"), 10).is_none()
        );
    }
}
