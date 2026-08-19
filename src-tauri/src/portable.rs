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

const PORTABLE_FORMAT: &str = "tauridium-portable-collection";
const PORTABLE_SCHEMA: u32 = 1;
const MAX_PORTABLE_BYTES: u64 = 64 * 1024 * 1024;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct PortableIntegrity {
    algorithm: String,
    payload_sha256: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct PortablePayload {
    pub services: Vec<Value>,
    pub workspaces: Vec<Value>,
    pub sandboxes: Vec<Value>,
    pub service_sandboxes: Value,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct PortableDocument {
    format: String,
    schema: u32,
    app_version: String,
    exported_at_unix: u64,
    kind: String,
    payload: PortablePayload,
    custom_recipes: Vec<CustomRecipeBackup>,
    integrity: PortableIntegrity,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct PortableSummary {
    pub path: String,
    pub kind: String,
    pub service_count: usize,
    pub workspace_count: usize,
    pub sandbox_count: usize,
    pub custom_recipe_count: usize,
    pub integrity_verified: bool,
}

impl PortableDocument {
    fn new(
        app_version: &str,
        kind: &str,
        payload: PortablePayload,
        custom_recipes: Vec<CustomRecipeBackup>,
    ) -> Result<Self, String> {
        validate_kind(kind)?;
        validate_payload(&payload)?;
        let mut document = Self {
            format: PORTABLE_FORMAT.into(),
            schema: PORTABLE_SCHEMA,
            app_version: app_version.into(),
            exported_at_unix: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs(),
            kind: kind.into(),
            payload,
            custom_recipes,
            integrity: PortableIntegrity {
                algorithm: "sha256".into(),
                payload_sha256: String::new(),
            },
        };
        document.integrity.payload_sha256 = document.digest();
        document.validate()?;
        Ok(document)
    }

    fn digest(&self) -> String {
        let material = serde_json::json!({
            "format": &self.format,
            "schema": self.schema,
            "appVersion": &self.app_version,
            "exportedAtUnix": self.exported_at_unix,
            "kind": &self.kind,
            "payload": &self.payload,
            "customRecipes": &self.custom_recipes,
        });
        Sha256::digest(serde_json::to_vec(&material).unwrap_or_default())
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect()
    }

    fn validate(&self) -> Result<(), String> {
        if self.format != PORTABLE_FORMAT || self.schema != PORTABLE_SCHEMA {
            return Err("Portable Tauridium export format is invalid".into());
        }
        validate_kind(&self.kind)?;
        validate_payload(&self.payload)?;
        if self.integrity.algorithm != "sha256" || self.integrity.payload_sha256 != self.digest() {
            return Err("Portable Tauridium export integrity verification failed".into());
        }
        Ok(())
    }

    fn summary(&self, path: &Path) -> PortableSummary {
        PortableSummary {
            path: path.to_string_lossy().into_owned(),
            kind: self.kind.clone(),
            service_count: self.payload.services.len(),
            workspace_count: self.payload.workspaces.len(),
            sandbox_count: self.payload.sandboxes.len(),
            custom_recipe_count: self.custom_recipes.len(),
            integrity_verified: true,
        }
    }
}

fn validate_kind(kind: &str) -> Result<(), String> {
    if matches!(kind, "sandbox" | "sandboxes" | "workspace" | "workspaces") {
        Ok(())
    } else {
        Err("Portable export kind is invalid".into())
    }
}

fn validate_payload(payload: &PortablePayload) -> Result<(), String> {
    if payload.services.len() > 10_000
        || payload.workspaces.len() > 10_000
        || payload.sandboxes.len() > 256
    {
        return Err("Portable export contains too many objects".into());
    }
    let mut service_ids = HashSet::new();
    let mut workspace_ids = HashSet::new();
    let mut sandbox_ids = HashSet::new();
    for (label, values, ids) in [
        ("service", &payload.services, &mut service_ids),
        ("workspace", &payload.workspaces, &mut workspace_ids),
        ("sandbox", &payload.sandboxes, &mut sandbox_ids),
    ] {
        for value in values {
            let id = value
                .get("id")
                .and_then(Value::as_str)
                .map(str::trim)
                .filter(|id| !id.is_empty())
                .ok_or_else(|| format!("Portable {label} is missing an id"))?;
            if !ids.insert(id.to_string()) {
                return Err(format!(
                    "Portable export contains duplicate {label} id: {id}"
                ));
            }
        }
    }

    for workspace in &payload.workspaces {
        let workspace_id = workspace
            .get("id")
            .and_then(Value::as_str)
            .unwrap_or("<unknown>");
        let members = workspace
            .get("services")
            .and_then(Value::as_array)
            .ok_or_else(|| {
                format!("Portable workspace {workspace_id} services must be an array")
            })?;
        for service_id in members {
            let service_id = service_id.as_str().ok_or_else(|| {
                format!("Portable workspace {workspace_id} contains a non-string service id")
            })?;
            if !service_ids.contains(service_id) {
                return Err(format!(
                    "Portable workspace {workspace_id} references missing service id: {service_id}"
                ));
            }
        }
    }

    let assignments = payload
        .service_sandboxes
        .as_object()
        .ok_or_else(|| "Portable serviceSandboxes must be an object".to_string())?;
    for (service_id, sandbox_id) in assignments {
        let sandbox_id = sandbox_id.as_str().ok_or_else(|| {
            format!("Portable sandbox assignment for {service_id} must be a string")
        })?;
        if !service_ids.contains(service_id) {
            return Err(format!(
                "Portable sandbox assignment references missing service id: {service_id}"
            ));
        }
        if !sandbox_ids.contains(sandbox_id) {
            return Err(format!(
                "Portable sandbox assignment references missing sandbox id: {sandbox_id}"
            ));
        }
    }
    Ok(())
}

fn staging_path(path: &Path) -> Result<PathBuf, String> {
    let name = path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| "Portable export filename is invalid".to_string())?;
    Ok(path.with_file_name(format!(".{name}.tauridium-tmp-{}", std::process::id())))
}

pub(crate) fn select_custom_recipes(
    payload: &PortablePayload,
    all_recipes: &[CustomRecipeBackup],
) -> Vec<CustomRecipeBackup> {
    let recipe_ids = payload
        .services
        .iter()
        .filter_map(|service| service.get("recipeId").and_then(Value::as_str))
        .collect::<HashSet<_>>();
    all_recipes
        .iter()
        .filter(|recipe| recipe_ids.contains(recipe.id.as_str()))
        .cloned()
        .collect()
}

pub(crate) fn save(
    path: &Path,
    app_version: &str,
    kind: &str,
    payload: PortablePayload,
    all_recipes: &[CustomRecipeBackup],
) -> Result<PortableSummary, String> {
    if path.as_os_str().is_empty() {
        return Err("Portable export destination path is empty".into());
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("Unable to create portable export directory: {error}"))?;
    }
    let recipes = select_custom_recipes(&payload, all_recipes);
    let document = PortableDocument::new(app_version, kind, payload, recipes)?;
    let text = serde_json::to_string_pretty(&document)
        .map_err(|error| format!("Unable to serialize portable Tauridium export: {error}"))?;
    if text.len() as u64 > MAX_PORTABLE_BYTES {
        return Err("Portable Tauridium export is too large".into());
    }
    let staging = staging_path(path)?;
    if staging.exists() {
        fs::remove_file(&staging).map_err(|error| {
            format!("Unable to clear stale portable export staging file: {error}")
        })?;
    }
    let staged = (|| -> Result<(), String> {
        let mut file = fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&staging)
            .map_err(|error| format!("Unable to create portable export staging file: {error}"))?;
        file.write_all(format!("{text}\n").as_bytes())
            .map_err(|error| format!("Unable to write portable export staging file: {error}"))?;
        file.sync_all()
            .map_err(|error| format!("Unable to flush portable export staging file: {error}"))?;
        let reread = fs::read_to_string(&staging)
            .map_err(|error| format!("Unable to reread portable export: {error}"))?;
        let verified: PortableDocument = serde_json::from_str(&reread)
            .map_err(|error| format!("Unable to parse staged portable export: {error}"))?;
        verified.validate()?;
        if verified.integrity.payload_sha256 != document.integrity.payload_sha256 {
            return Err("Portable export verification produced different content".into());
        }
        Ok(())
    })();
    if let Err(error) = staged {
        let _ = fs::remove_file(&staging);
        return Err(error);
    }
    replace_file(&staging, path)
        .map_err(|error| format!("Unable to finalize portable Tauridium export: {error}"))?;
    Ok(document.summary(path))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn payload() -> PortablePayload {
        PortablePayload {
            services: vec![json!({ "id": "svc", "recipeId": "custom-mail" })],
            workspaces: vec![json!({ "id": "work", "services": ["svc"] })],
            sandboxes: vec![json!({ "id": "shared", "name": "Shared" })],
            service_sandboxes: json!({ "svc": "shared" }),
        }
    }

    fn recipes() -> Vec<CustomRecipeBackup> {
        vec![
            CustomRecipeBackup {
                id: "custom-mail".into(),
                package: json!({ "id": "custom-mail" }),
                icon_svg: "<svg/>".into(),
                webview_js: String::new(),
            },
            CustomRecipeBackup {
                id: "unused".into(),
                package: json!({ "id": "unused" }),
                icon_svg: "<svg/>".into(),
                webview_js: String::new(),
            },
        ]
    }

    #[test]
    fn portable_export_selects_only_referenced_custom_recipes() {
        let selected = select_custom_recipes(&payload(), &recipes());
        assert_eq!(selected.len(), 1);
        assert_eq!(selected[0].id, "custom-mail");
    }

    #[test]
    fn portable_export_rejects_duplicate_ids() {
        let mut duplicate = payload();
        duplicate.services.push(duplicate.services[0].clone());
        assert!(validate_payload(&duplicate)
            .unwrap_err()
            .contains("duplicate service"));
    }

    #[test]
    fn portable_export_round_trips_with_integrity() {
        let root = std::env::temp_dir().join(format!("tauridium-portable-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        let path = root.join("sandbox.json");
        let summary = save(&path, "9.9.9", "sandbox", payload(), &recipes()).unwrap();
        assert!(summary.integrity_verified);
        assert_eq!(summary.custom_recipe_count, 1);
        let value: PortableDocument =
            serde_json::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
        value.validate().unwrap();
        let _ = fs::remove_dir_all(root);
    }
    #[test]
    fn portable_export_detects_payload_tampering() {
        let mut document = PortableDocument::new("9.9.9", "sandbox", payload(), recipes()).unwrap();
        document.payload.services[0]["name"] = Value::String("Changed".into());
        assert!(document
            .validate()
            .unwrap_err()
            .contains("integrity verification failed"));
    }

    #[test]
    fn portable_export_rejects_invalid_kind_and_payload_shapes() {
        assert!(PortableDocument::new("9.9.9", "recipe", payload(), recipes()).is_err());
        let mut bad_assignments = payload();
        bad_assignments.service_sandboxes = Value::Array(Vec::new());
        assert!(validate_payload(&bad_assignments)
            .unwrap_err()
            .contains("serviceSandboxes"));
        let mut duplicate_workspace = payload();
        duplicate_workspace
            .workspaces
            .push(duplicate_workspace.workspaces[0].clone());
        assert!(validate_payload(&duplicate_workspace)
            .unwrap_err()
            .contains("duplicate workspace"));
    }

    #[test]
    fn portable_export_without_referenced_custom_recipe_includes_none() {
        let mut value = payload();
        value.services[0]["recipeId"] = Value::String("built-in".into());
        assert!(select_custom_recipes(&value, &recipes()).is_empty());
    }

    #[test]
    fn portable_export_rejects_dangling_workspace_service_references() {
        let mut value = payload();
        value.workspaces[0]["services"] = json!(["svc", "missing"]);
        assert!(validate_payload(&value)
            .unwrap_err()
            .contains("references missing service id"));
    }

    #[test]
    fn portable_export_rejects_dangling_sandbox_assignments() {
        let mut missing_service = payload();
        missing_service.service_sandboxes = json!({ "missing": "shared" });
        assert!(validate_payload(&missing_service)
            .unwrap_err()
            .contains("missing service id"));

        let mut missing_sandbox = payload();
        missing_sandbox.service_sandboxes = json!({ "svc": "missing" });
        assert!(validate_payload(&missing_sandbox)
            .unwrap_err()
            .contains("missing sandbox id"));
    }

    #[test]
    fn portable_export_clears_stale_staging_and_replaces_existing_file() {
        let root = std::env::temp_dir().join(format!(
            "tauridium-portable-replace-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos()
        ));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("workspace.json");
        fs::write(&path, "old").unwrap();
        let staging = staging_path(&path).unwrap();
        fs::write(&staging, "stale").unwrap();
        let summary = save(&path, "9.9.9", "workspace", payload(), &recipes()).unwrap();
        assert!(summary.integrity_verified);
        assert!(!staging.exists());
        let document: PortableDocument =
            serde_json::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
        document.validate().unwrap();
        let _ = fs::remove_dir_all(root);
    }
}
