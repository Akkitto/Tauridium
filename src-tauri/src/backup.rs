use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::fs;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use crate::recipes::CustomRecipeBackup;
use crate::write_atomic;

const BACKUP_FORMAT: &str = "tauridium-backup";
const BACKUP_SCHEMA: u32 = 1;
const MAX_BACKUP_BYTES: u64 = 64 * 1024 * 1024;

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
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct BackupSummary {
    pub path: String,
    pub custom_recipe_count: usize,
    pub service_count: usize,
    pub workspace_count: usize,
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
        Self {
            format: BACKUP_FORMAT.to_string(),
            schema: BACKUP_SCHEMA,
            app_version: app_version.to_string(),
            exported_at_unix,
            contains_sensitive_data: true,
            excluded: vec![
                "ferdiumSessionCredentials".into(),
                "websiteCookiesAndStorage".into(),
                "remoteRecipeCache".into(),
            ],
            app_settings,
            local_profile,
            custom_recipes,
        }
    }

    pub(crate) fn validate(&self) -> Result<(), String> {
        if self.format != BACKUP_FORMAT {
            return Err("Selected file is not a Tauridium backup".into());
        }
        if self.schema != BACKUP_SCHEMA {
            return Err(format!(
                "Unsupported Tauridium backup schema {} (expected {BACKUP_SCHEMA})",
                self.schema
            ));
        }
        if !self.app_settings.is_object() {
            return Err("Backup appSettings must be a JSON object".into());
        }
        if !self.local_profile.is_object() {
            return Err("Backup localProfile must be a JSON object".into());
        }
        Ok(())
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
        }
    }
}

pub(crate) fn save(path: &Path, document: &BackupDocument) -> Result<BackupSummary, String> {
    if path.as_os_str().is_empty() {
        return Err("Backup destination path is empty".into());
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("Unable to create backup directory: {error}"))?;
    }
    let text = serde_json::to_string_pretty(document)
        .map_err(|error| format!("Unable to serialize Tauridium backup: {error}"))?;
    write_atomic(path, &format!("{text}\n"))
        .map_err(|error| format!("Unable to write Tauridium backup: {error}"))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o600))
            .map_err(|error| format!("Unable to protect Tauridium backup: {error}"))?;
    }
    Ok(document.summary(path))
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
    let text = fs::read_to_string(path).map_err(|error| format!("Unable to read backup: {error}"))?;
    let document: BackupDocument = serde_json::from_str(&text)
        .map_err(|error| format!("Unable to parse Tauridium backup: {error}"))?;
    document.validate()?;
    Ok(document)
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
        let root = std::env::temp_dir().join(format!(
            "tauridium-backup-test-{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        let path = root.join("backup.json");
        let summary = save(&path, &sample()).unwrap();
        assert_eq!(summary.custom_recipe_count, 1);
        assert_eq!(summary.service_count, 1);
        assert_eq!(summary.workspace_count, 0);
        let loaded = load(&path).unwrap();
        assert_eq!(loaded.custom_recipes().len(), 1);
        assert_eq!(loaded.app_settings()["theme"], "dark");
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn backup_rejects_wrong_format_and_schema() {
        let mut wrong_format = sample();
        wrong_format.format = "other".into();
        assert!(wrong_format.validate().is_err());

        let mut wrong_schema = sample();
        wrong_schema.schema = BACKUP_SCHEMA + 1;
        assert!(wrong_schema.validate().is_err());
    }
}
