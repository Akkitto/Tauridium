use base64::Engine;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use tauri::{AppHandle, Manager};

use crate::local_profile::validate_recipe_id;
use crate::write_atomic;

const CUSTOM_RECIPE_DIR: &str = "recipes";
const PACKAGE_FILE: &str = "package.json";
const WEBVIEW_FILE: &str = "webview.js";
const ICON_FILE: &str = "icon.svg";

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct RecipeDraft {
    pub id: String,
    pub name: String,
    pub service_url: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub has_custom_url: bool,
    #[serde(default)]
    pub has_team_id: bool,
    #[serde(default)]
    pub icon_svg: String,
    #[serde(default)]
    pub webview_js: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct RecipeStorageInfo {
    pub config_dir: String,
    pub recipes_dir: String,
}

fn generic_icon(label: &str) -> String {
    let text = label.chars().next().unwrap_or('T');
    format!(
        r##"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#252936"/><text x="32" y="41" text-anchor="middle" font-family="system-ui,sans-serif" font-size="31" font-weight="700" fill="#fff">{text}</text></svg>"##
    )
}

fn bundled_recipes() -> Vec<(&'static str, &'static str, &'static str, bool, &'static str)> {
    vec![
        (
            "custom-website",
            "Custom Website",
            "https://example.com",
            true,
            "Open any HTTP(S) website with a per-service URL.",
        ),
        (
            "nanogpt",
            "NanoGPT",
            "https://nano-gpt.com/chat",
            false,
            "NanoGPT browser chat.",
        ),
        (
            "chutes",
            "Chutes",
            "https://chutes.ai/chat",
            false,
            "Chutes browser chat.",
        ),
        (
            "opencode",
            "OpenCode Web",
            "http://127.0.0.1:4096",
            true,
            "OpenCode local web UI. Start OpenCode with a stable port or override this URL per service.",
        ),
    ]
}

pub(crate) fn is_bundled_recipe(recipe_id: &str) -> bool {
    bundled_recipes().iter().any(|recipe| recipe.0 == recipe_id)
}

fn bundled_recipe(recipe_id: &str) -> Option<Value> {
    bundled_recipes()
        .into_iter()
        .find(|recipe| recipe.0 == recipe_id)
        .map(|(id, name, service_url, has_custom_url, description)| {
            json!({
                "id": id,
                "name": name,
                "description": description,
                "version": "1.0.0",
                "config": {
                    "serviceURL": service_url,
                    "hasCustomUrl": has_custom_url,
                    "hasTeamId": false
                }
            })
        })
}

fn svg_data_uri(svg: &str) -> String {
    format!(
        "data:image/svg+xml;base64,{}",
        base64::engine::general_purpose::STANDARD.encode(svg.as_bytes())
    )
}

fn preview_from_package(id: &str, package: &Value, source: &str, icon: Option<String>) -> Value {
    let name = package
        .get("name")
        .and_then(Value::as_str)
        .filter(|name| !name.trim().is_empty())
        .unwrap_or(id);
    let description = package
        .get("description")
        .and_then(Value::as_str)
        .unwrap_or("");
    let mut preview = json!({
        "id": id,
        "name": name,
        "description": description,
        "source": source
    });
    if let Some(icon) = icon {
        preview["icons"] = json!({ "svg": icon });
    }
    preview
}

fn bundled_previews() -> Vec<Value> {
    bundled_recipes()
        .into_iter()
        .filter_map(|(id, name, _url, _custom, _description)| {
            let package = bundled_recipe(id)?;
            Some(preview_from_package(
                id,
                &package,
                "bundled",
                Some(svg_data_uri(&generic_icon(name))),
            ))
        })
        .collect()
}

pub(crate) fn custom_recipes_dir(app: &AppHandle) -> Result<PathBuf, String> {
    app.path()
        .app_config_dir()
        .map(|dir| dir.join(CUSTOM_RECIPE_DIR))
        .map_err(|error| format!("Custom recipe configuration directory unavailable: {error}"))
}

pub(crate) fn storage_info(app: &AppHandle) -> Result<RecipeStorageInfo, String> {
    let recipes_dir = custom_recipes_dir(app)?;
    let config_dir = recipes_dir
        .parent()
        .ok_or_else(|| "Custom recipe configuration directory has no parent".to_string())?;
    Ok(RecipeStorageInfo {
        config_dir: config_dir.to_string_lossy().into_owned(),
        recipes_dir: recipes_dir.to_string_lossy().into_owned(),
    })
}

fn validate_service_url(service_url: &str) -> Result<(), String> {
    let service_url = service_url.trim();
    if service_url.is_empty() {
        return Err("Recipe service URL is required".into());
    }
    let parsed = tauri::Url::parse(service_url)
        .map_err(|error| format!("Recipe service URL is invalid: {error}"))?;
    if parsed.scheme() != "http" && parsed.scheme() != "https" {
        return Err("Recipe service URL must use http:// or https://".into());
    }
    if parsed.host_str().is_none() {
        return Err("Recipe service URL must contain a host".into());
    }
    Ok(())
}

fn validate_package(package: &Value) -> Result<(), String> {
    let config = package
        .get("config")
        .and_then(Value::as_object)
        .ok_or_else(|| "Recipe requires an object config block".to_string())?;
    let service_url = config
        .get("serviceURL")
        .and_then(Value::as_str)
        .ok_or_else(|| "Recipe config.serviceURL is required".to_string())?;
    validate_service_url(service_url)?;
    for key in ["hasCustomUrl", "hasTeamId"] {
        if let Some(value) = config.get(key) {
            if !value.is_boolean() {
                return Err(format!("Recipe config.{key} must be boolean"));
            }
        }
    }
    Ok(())
}

fn read_package(path: &Path) -> Result<Value, String> {
    let text = fs::read_to_string(path)
        .map_err(|error| format!("Unable to read recipe {}: {error}", path.display()))?;
    let package: Value = serde_json::from_str(&text)
        .map_err(|error| format!("Invalid recipe JSON {}: {error}", path.display()))?;
    validate_package(&package)?;
    Ok(package)
}

fn custom_recipe_package(app: &AppHandle, recipe_id: &str) -> Result<Option<Value>, String> {
    validate_recipe_id(recipe_id)?;
    let path = custom_recipes_dir(app)?.join(recipe_id).join(PACKAGE_FILE);
    if !path.is_file() {
        return Ok(None);
    }
    read_package(&path).map(Some)
}

pub(crate) fn local_recipe_config(app: &AppHandle, recipe_id: &str) -> Result<Option<Value>, String> {
    if let Some(bundled) = bundled_recipe(recipe_id) {
        return Ok(Some(bundled));
    }
    custom_recipe_package(app, recipe_id)
}

pub(crate) fn local_webview_js(app: &AppHandle, recipe_id: &str) -> Option<String> {
    validate_recipe_id(recipe_id).ok()?;
    if is_bundled_recipe(recipe_id) {
        return None;
    }
    let path = custom_recipes_dir(app).ok()?.join(recipe_id).join(WEBVIEW_FILE);
    fs::read_to_string(path).ok()
}

pub(crate) fn local_icon_url(app: &AppHandle, recipe_id: &str) -> Option<String> {
    if validate_recipe_id(recipe_id).is_err() {
        return None;
    }
    if let Some(recipe) = bundled_recipes()
        .into_iter()
        .find(|recipe| recipe.0 == recipe_id)
    {
        return Some(svg_data_uri(&generic_icon(recipe.1)));
    }
    let path = custom_recipes_dir(app).ok()?.join(recipe_id).join(ICON_FILE);
    if let Ok(svg) = fs::read_to_string(path) {
        return Some(svg_data_uri(&svg));
    }
    if let Ok(Some(package)) = custom_recipe_package(app, recipe_id) {
        let name = package
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or(recipe_id);
        return Some(svg_data_uri(&generic_icon(name)));
    }
    None
}

fn custom_previews(app: &AppHandle) -> Result<Vec<Value>, String> {
    let root = custom_recipes_dir(app)?;
    if !root.exists() {
        return Ok(Vec::new());
    }
    let entries = fs::read_dir(&root)
        .map_err(|error| format!("Unable to list custom recipes {}: {error}", root.display()))?;
    let mut previews = Vec::new();
    for entry in entries.flatten() {
        let Ok(file_type) = entry.file_type() else {
            continue;
        };
        if !file_type.is_dir() {
            continue;
        }
        let id = entry.file_name().to_string_lossy().into_owned();
        if validate_recipe_id(&id).is_err() || is_bundled_recipe(&id) {
            continue;
        }
        let package_path = entry.path().join(PACKAGE_FILE);
        let Ok(package) = read_package(&package_path) else {
            continue;
        };
        let icon_path = entry.path().join(ICON_FILE);
        let icon = fs::read_to_string(icon_path).ok().map(|svg| svg_data_uri(&svg));
        previews.push(preview_from_package(&id, &package, "custom", icon));
    }
    previews.sort_by(|left, right| {
        left.get("name")
            .and_then(Value::as_str)
            .cmp(&right.get("name").and_then(Value::as_str))
    });
    Ok(previews)
}

pub(crate) fn merge_catalog(app: &AppHandle, remote: Option<Value>) -> Result<Value, String> {
    let mut merged = BTreeMap::<String, Value>::new();
    if let Some(Value::Array(recipes)) = remote {
        for recipe in recipes {
            if let Some(id) = recipe.get("id").and_then(Value::as_str) {
                if validate_recipe_id(id).is_ok() {
                    let mut recipe = recipe;
                    recipe["source"] = Value::String("remote".into());
                    merged.insert(id.to_string(), recipe);
                }
            }
        }
    }
    for recipe in bundled_previews() {
        if let Some(id) = recipe.get("id").and_then(Value::as_str) {
            merged.insert(id.to_string(), recipe.clone());
        }
    }
    for recipe in custom_previews(app)? {
        if let Some(id) = recipe.get("id").and_then(Value::as_str) {
            merged.insert(id.to_string(), recipe.clone());
        }
    }
    let mut recipes = merged.into_values().collect::<Vec<_>>();
    recipes.sort_by(|left, right| {
        left.get("name")
            .and_then(Value::as_str)
            .cmp(&right.get("name").and_then(Value::as_str))
    });
    Ok(Value::Array(recipes))
}

fn write_optional_file(path: &Path, contents: &str) -> Result<(), String> {
    if contents.trim().is_empty() {
        if path.exists() {
            fs::remove_file(path)
                .map_err(|error| format!("Unable to remove {}: {error}", path.display()))?;
        }
        return Ok(());
    }
    write_atomic(path, contents)
        .map_err(|error| format!("Unable to write {}: {error}", path.display()))
}

fn save_recipe_files(
    root: &Path,
    recipe_id: &str,
    package: &Value,
    icon_svg: &str,
    webview_js: &str,
) -> Result<Value, String> {
    validate_recipe_id(recipe_id)?;
    if is_bundled_recipe(recipe_id) {
        return Err(format!("Recipe id is reserved by Tauridium: {recipe_id}"));
    }
    validate_package(package)?;
    let dir = root.join(recipe_id);
    fs::create_dir_all(&dir)
        .map_err(|error| format!("Unable to create recipe directory {}: {error}", dir.display()))?;

    // Companion files are committed first; package.json is the discovery marker and is
    // written last so a partially written new recipe is never listed as valid.
    write_optional_file(&dir.join(ICON_FILE), icon_svg)?;
    write_optional_file(&dir.join(WEBVIEW_FILE), webview_js)?;
    let text = serde_json::to_string_pretty(package)
        .map_err(|error| format!("Unable to serialize recipe: {error}"))?;
    write_atomic(&dir.join(PACKAGE_FILE), &format!("{text}\n"))
        .map_err(|error| format!("Unable to write recipe package: {error}"))?;
    Ok(package.clone())
}

pub(crate) fn save_custom_recipe(app: &AppHandle, draft: RecipeDraft) -> Result<Value, String> {
    let id = draft.id.trim().to_ascii_lowercase();
    validate_recipe_id(&id)?;
    if draft.name.trim().is_empty() {
        return Err("Recipe name is required".into());
    }
    validate_service_url(draft.service_url.trim())?;
    let package = json!({
        "id": id,
        "name": draft.name.trim(),
        "description": draft.description.trim(),
        "version": "1.0.0",
        "config": {
            "serviceURL": draft.service_url.trim(),
            "hasCustomUrl": draft.has_custom_url,
            "hasTeamId": draft.has_team_id
        },
        "tauridium": {
            "schemaVersion": 1,
            "local": true
        }
    });
    let root = custom_recipes_dir(app)?;
    save_recipe_files(&root, &id, &package, &draft.icon_svg, &draft.webview_js)
}

fn recipe_id_from_import(package: &Value, source_dir: &Path) -> Result<String, String> {
    if let Some(id) = package.get("id").and_then(Value::as_str) {
        validate_recipe_id(id)?;
        return Ok(id.to_ascii_lowercase());
    }
    let id = source_dir
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| "Imported recipe needs an id field or a valid parent folder name".to_string())?
        .to_ascii_lowercase();
    validate_recipe_id(&id)?;
    Ok(id)
}

pub(crate) fn import_custom_recipe(app: &AppHandle, selected: &Path) -> Result<Value, String> {
    let package_path = if selected.is_dir() {
        selected.join(PACKAGE_FILE)
    } else {
        selected.to_path_buf()
    };
    if package_path.file_name().and_then(|name| name.to_str()) != Some(PACKAGE_FILE) {
        return Err("Select a recipe folder or its package.json".into());
    }
    let source_dir = package_path
        .parent()
        .ok_or_else(|| "Imported package.json has no parent directory".to_string())?;
    let mut package = read_package(&package_path)?;
    let id = recipe_id_from_import(&package, source_dir)?;
    if is_bundled_recipe(&id) {
        return Err(format!("Recipe id is reserved by Tauridium: {id}"));
    }
    package["id"] = Value::String(id.clone());
    let icon_svg = fs::read_to_string(source_dir.join(ICON_FILE)).unwrap_or_default();
    let webview_js = fs::read_to_string(source_dir.join(WEBVIEW_FILE)).unwrap_or_default();
    let root = custom_recipes_dir(app)?;
    save_recipe_files(&root, &id, &package, &icon_svg, &webview_js)?;
    Ok(preview_from_package(
        &id,
        &package,
        "custom",
        (!icon_svg.is_empty()).then(|| svg_data_uri(&icon_svg)),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bundled_recipe_urls_are_valid() {
        for (id, _name, url, _custom, _description) in bundled_recipes() {
            validate_recipe_id(id).unwrap();
            validate_service_url(url).unwrap();
        }
    }

    #[test]
    fn custom_website_and_opencode_allow_url_override() {
        for id in ["custom-website", "opencode"] {
            let recipe = bundled_recipe(id).unwrap();
            assert_eq!(
                recipe.pointer("/config/hasCustomUrl").and_then(Value::as_bool),
                Some(true)
            );
        }
    }

    #[test]
    fn provider_recipes_use_expected_endpoints() {
        assert_eq!(
            bundled_recipe("nanogpt")
                .unwrap()
                .pointer("/config/serviceURL")
                .and_then(Value::as_str),
            Some("https://nano-gpt.com/chat")
        );
        assert_eq!(
            bundled_recipe("chutes")
                .unwrap()
                .pointer("/config/serviceURL")
                .and_then(Value::as_str),
            Some("https://chutes.ai/chat")
        );
        assert_eq!(
            bundled_recipe("opencode")
                .unwrap()
                .pointer("/config/serviceURL")
                .and_then(Value::as_str),
            Some("http://127.0.0.1:4096")
        );
    }

    #[test]
    fn service_url_rejects_non_http_schemes() {
        assert!(validate_service_url("file:///tmp/test").is_err());
        assert!(validate_service_url("javascript:alert(1)").is_err());
        assert!(validate_service_url("https://example.com").is_ok());
    }

    #[test]
    fn save_recipe_files_round_trips_companion_files() {
        let root = std::env::temp_dir().join(format!(
            "tauridium-recipe-test-{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&root);
        let package = json!({
            "id": "test-local",
            "name": "Test Local",
            "config": { "serviceURL": "https://example.com", "hasCustomUrl": true }
        });
        save_recipe_files(&root, "test-local", &package, "<svg></svg>", "console.log('ok');")
            .unwrap();
        assert_eq!(read_package(&root.join("test-local/package.json")).unwrap()["name"], "Test Local");
        assert_eq!(fs::read_to_string(root.join("test-local/icon.svg")).unwrap(), "<svg></svg>");
        assert_eq!(fs::read_to_string(root.join("test-local/webview.js")).unwrap(), "console.log('ok');");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn reserved_bundled_ids_cannot_be_saved_as_custom() {
        let root = std::env::temp_dir().join("tauridium-reserved-recipe-test");
        let package = bundled_recipe("nanogpt").unwrap();
        assert!(save_recipe_files(&root, "nanogpt", &package, "", "").is_err());
    }
}
