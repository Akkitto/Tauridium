use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::{read_persistent, replace_file};

const PROFILE_VERSION: u32 = 1;
static ID_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub(crate) struct LocalProfile {
    version: u32,
    services: Vec<Value>,
    workspaces: Vec<Value>,
}

impl Default for LocalProfile {
    fn default() -> Self {
        Self {
            version: PROFILE_VERSION,
            services: Vec::new(),
            workspaces: Vec::new(),
        }
    }
}

impl LocalProfile {
    pub(crate) fn load(path: &Path) -> Result<Self, String> {
        let text = match read_persistent(path) {
            Ok(text) => text,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                return Ok(Self::default())
            }
            Err(error) => return Err(format!("Lecture du profil local impossible : {error}")),
        };
        let mut profile: Self = serde_json::from_str(&text)
            .map_err(|error| format!("Profil local illisible : {error}"))?;
        if profile.version == 0 {
            profile.version = PROFILE_VERSION;
        }
        if profile.version > PROFILE_VERSION {
            return Err(format!(
                "Profil local version {} non pris en charge (maximum {PROFILE_VERSION})",
                profile.version
            ));
        }
        Ok(profile)
    }

    pub(crate) fn save(&self, path: &Path) -> Result<(), String> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)
                .map_err(|error| format!("Création du dossier local impossible : {error}"))?;
        }
        let text = serde_json::to_string_pretty(self)
            .map_err(|error| format!("Sérialisation du profil local impossible : {error}"))?;
        let tmp = path.with_extension("tmp");
        fs::write(&tmp, format!("{text}\n"))
            .map_err(|error| format!("Écriture du profil local impossible : {error}"))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&tmp, fs::Permissions::from_mode(0o600))
                .map_err(|error| format!("Permissions du profil local impossibles : {error}"))?;
        }
        replace_file(&tmp, path)
            .map_err(|error| format!("Finalisation du profil local impossible : {error}"))?;
        Ok(())
    }

    pub(crate) fn services_value(&self) -> Value {
        Value::Array(self.services.clone())
    }

    pub(crate) fn workspaces_value(&self) -> Value {
        Value::Array(self.workspaces.clone())
    }

    pub(crate) fn create_service(
        &mut self,
        name: String,
        recipe_id: String,
    ) -> Result<Value, String> {
        validate_recipe_id(&recipe_id)?;
        let order = self
            .services
            .iter()
            .filter_map(|service| service.get("order").and_then(Value::as_i64))
            .max()
            .unwrap_or(-1)
            + 1;
        let id = new_id();
        let icon_url = format!(
            "https://raw.githubusercontent.com/ferdium/ferdium-recipes/main/recipes/{recipe_id}/icon.svg"
        );
        let service = json!({
            "id": id,
            "name": name,
            "recipeId": recipe_id,
            "iconUrl": icon_url,
            "isEnabled": true,
            "isMuted": false,
            "isNotificationEnabled": true,
            "isBadgeEnabled": true,
            "isMediaBadgeEnabled": false,
            "isIndirectMessageBadgeEnabled": false,
            "isHibernationEnabled": false,
            "isWakeUpEnabled": false,
            "trapLinkClicks": false,
            "useFavicon": false,
            "isDarkModeEnabled": false,
            "isProgressbarEnabled": true,
            "onlyShowFavoritesInUnreadCount": false,
            "darkReaderBrightness": 100,
            "darkReaderContrast": 90,
            "darkReaderSepia": 10,
            "isProxyFeatureEnabled": false,
            "proxyHost": "",
            "proxyPort": "",
            "proxyUser": "",
            "proxyPassword": "",
            "customUrl": "",
            "team": "",
            "userAgentPref": "",
            "order": order,
            "workspaces": []
        });
        self.services.push(service.clone());
        Ok(service)
    }

    pub(crate) fn update_service(
        &mut self,
        service_id: &str,
        patch: &Value,
    ) -> Result<Value, String> {
        let patch = patch
            .as_object()
            .ok_or_else(|| "Réglages de service locaux invalides".to_string())?;
        let service = self
            .services
            .iter_mut()
            .find(|service| service.get("id").and_then(Value::as_str) == Some(service_id))
            .ok_or_else(|| format!("Service local introuvable : {service_id}"))?;
        let object = service
            .as_object_mut()
            .ok_or_else(|| format!("Service local invalide : {service_id}"))?;
        merge_service_patch(object, patch);
        Ok(service.clone())
    }

    pub(crate) fn delete_service(&mut self, service_id: &str) -> Result<(), String> {
        let before = self.services.len();
        self.services
            .retain(|service| service.get("id").and_then(Value::as_str) != Some(service_id));
        if self.services.len() == before {
            return Err(format!("Service local introuvable : {service_id}"));
        }
        for workspace in &mut self.workspaces {
            if let Some(services) = workspace.get_mut("services").and_then(Value::as_array_mut) {
                services.retain(|id| id.as_str() != Some(service_id));
            }
        }
        Ok(())
    }

    pub(crate) fn create_workspace(&mut self, name: String) -> Value {
        let order = self
            .workspaces
            .iter()
            .filter_map(|workspace| workspace.get("order").and_then(Value::as_i64))
            .max()
            .unwrap_or(-1)
            + 1;
        let workspace = json!({
            "id": new_id(),
            "name": name,
            "order": order,
            "services": [],
            "userId": "local"
        });
        self.workspaces.push(workspace.clone());
        workspace
    }

    pub(crate) fn update_workspace(
        &mut self,
        workspace_id: &str,
        name: String,
        services: Vec<String>,
    ) -> Result<Value, String> {
        let known_services = self
            .services
            .iter()
            .filter_map(|service| service.get("id").and_then(Value::as_str))
            .collect::<std::collections::HashSet<_>>();
        let services = services
            .into_iter()
            .filter(|id| known_services.contains(id.as_str()))
            .map(Value::String)
            .collect::<Vec<_>>();
        let workspace = self
            .workspaces
            .iter_mut()
            .find(|workspace| workspace.get("id").and_then(Value::as_str) == Some(workspace_id))
            .ok_or_else(|| format!("Workspace local introuvable : {workspace_id}"))?;
        let object = workspace
            .as_object_mut()
            .ok_or_else(|| format!("Workspace local invalide : {workspace_id}"))?;
        object.insert("name".into(), Value::String(name));
        object.insert("services".into(), Value::Array(services));
        Ok(workspace.clone())
    }

    pub(crate) fn delete_workspace(&mut self, workspace_id: &str) -> Result<(), String> {
        let before = self.workspaces.len();
        self.workspaces
            .retain(|workspace| workspace.get("id").and_then(Value::as_str) != Some(workspace_id));
        if self.workspaces.len() == before {
            return Err(format!("Workspace local introuvable : {workspace_id}"));
        }
        Ok(())
    }
}

pub(crate) fn validate_recipe_id(recipe_id: &str) -> Result<(), String> {
    if recipe_id.is_empty()
        || !recipe_id.chars().all(|character| {
            character.is_ascii_alphanumeric() || character == '-' || character == '_'
        })
    {
        return Err(format!("Identifiant de recipe invalide : {recipe_id}"));
    }
    Ok(())
}

fn merge_service_patch(service: &mut Map<String, Value>, patch: &Map<String, Value>) {
    for (key, value) in patch {
        if key != "id" && key != "recipeId" {
            service.insert(key.clone(), value.clone());
        }
    }
}

fn new_id() -> String {
    let sequence = ID_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or_default();
    let mut hasher = Sha256::new();
    hasher.update(nanos.to_le_bytes());
    hasher.update(std::process::id().to_le_bytes());
    hasher.update(sequence.to_le_bytes());
    let digest = hasher.finalize();
    let mut bytes = [0u8; 16];
    bytes.copy_from_slice(&digest[..16]);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    format!(
        "{:02x}{:02x}{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}",
        bytes[0],
        bytes[1],
        bytes[2],
        bytes[3],
        bytes[4],
        bytes[5],
        bytes[6],
        bytes[7],
        bytes[8],
        bytes[9],
        bytes[10],
        bytes[11],
        bytes[12],
        bytes[13],
        bytes[14],
        bytes[15]
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashSet;

    #[test]
    fn profile_round_trips_without_losing_data() {
        let root = std::env::temp_dir().join(format!("tauridium-local-profile-{}", new_id()));
        let path = root.join("profile.json");
        let mut profile = LocalProfile::default();
        let service = profile
            .create_service("Example".into(), "franz-custom-website".into())
            .unwrap();
        let service_id = service["id"].as_str().unwrap().to_string();
        let workspace = profile.create_workspace("Work".into());
        profile
            .update_workspace(
                workspace["id"].as_str().unwrap(),
                "Work".into(),
                vec![service_id],
            )
            .unwrap();
        profile.save(&path).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(
                fs::metadata(&path).unwrap().permissions().mode() & 0o777,
                0o600
            );
        }

        let loaded = LocalProfile::load(&path).unwrap();
        assert_eq!(loaded.services_value(), profile.services_value());
        assert_eq!(loaded.workspaces_value(), profile.workspaces_value());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn load_recovers_an_interrupted_windows_backup() {
        let root =
            std::env::temp_dir().join(format!("tauridium-local-profile-backup-{}", new_id()));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("profile.json");
        let backup = path.with_extension("bak");
        let mut profile = LocalProfile::default();
        profile
            .create_service("Recovered".into(), "gmail".into())
            .unwrap();
        fs::write(&backup, serde_json::to_string(&profile).unwrap()).unwrap();

        let loaded = LocalProfile::load(&path).unwrap();

        assert_eq!(loaded.services_value()[0]["name"], "Recovered");
        assert!(path.exists());
        assert!(!backup.exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn repeated_saves_replace_the_existing_profile() {
        let root =
            std::env::temp_dir().join(format!("tauridium-local-profile-replace-{}", new_id()));
        let path = root.join("profile.json");
        let mut profile = LocalProfile::default();
        profile
            .create_service("First".into(), "gmail".into())
            .unwrap();
        profile.save(&path).unwrap();

        profile
            .create_service("Second".into(), "discord".into())
            .unwrap();
        profile.save(&path).unwrap();

        let loaded = LocalProfile::load(&path).unwrap();
        assert_eq!(loaded.services_value().as_array().unwrap().len(), 2);
        assert_eq!(loaded.services_value()[1]["name"], "Second");
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn service_crud_preserves_identity_and_removes_workspace_membership() {
        let mut profile = LocalProfile::default();
        let service = profile
            .create_service("Old".into(), "gmail".into())
            .unwrap();
        let id = service["id"].as_str().unwrap().to_string();
        let workspace = profile.create_workspace("Inbox".into());
        let workspace_id = workspace["id"].as_str().unwrap().to_string();
        profile
            .update_workspace(&workspace_id, "Inbox".into(), vec![id.clone()])
            .unwrap();

        let updated = profile
            .update_service(
                &id,
                &json!({ "id": "evil", "recipeId": "evil", "name": "New", "order": 7 }),
            )
            .unwrap();
        assert_eq!(updated["id"], id);
        assert_eq!(updated["recipeId"], "gmail");
        assert_eq!(updated["name"], "New");
        assert_eq!(updated["order"], 7);

        profile.delete_service(&id).unwrap();
        assert!(profile.services_value().as_array().unwrap().is_empty());
        assert!(profile.workspaces_value()[0]["services"]
            .as_array()
            .unwrap()
            .is_empty());
    }

    #[test]
    fn workspace_rejects_unknown_service_ids() {
        let mut profile = LocalProfile::default();
        let service = profile
            .create_service("Mail".into(), "gmail".into())
            .unwrap();
        let known = service["id"].as_str().unwrap().to_string();
        let workspace = profile.create_workspace("Work".into());
        let updated = profile
            .update_workspace(
                workspace["id"].as_str().unwrap(),
                "Work".into(),
                vec![known.clone(), "missing".into()],
            )
            .unwrap();
        assert_eq!(updated["services"], json!([known]));
    }

    #[test]
    fn generated_ids_are_unique_uuid_shaped_values() {
        let ids = (0..128).map(|_| new_id()).collect::<HashSet<_>>();
        assert_eq!(ids.len(), 128);
        for id in ids {
            assert_eq!(id.len(), 36);
            assert_eq!(&id[14..15], "4");
            assert!(matches!(&id[19..20], "8" | "9" | "a" | "b"));
        }
    }

    #[test]
    fn invalid_recipe_ids_are_rejected() {
        assert!(validate_recipe_id("gmail").is_ok());
        assert!(validate_recipe_id("office365-owa").is_ok());
        assert!(validate_recipe_id("").is_err());
        assert!(validate_recipe_id("../gmail").is_err());
        assert!(validate_recipe_id("gmail/test").is_err());
    }
}
