use base64::Engine;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::fs;
use std::io::{Cursor, Read, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Url};
use zip::write::SimpleFileOptions;
use zip::{CompressionMethod, DateTime, ZipArchive, ZipWriter};

use crate::icons;
use crate::recipes::CustomRecipeBackup;
use crate::replace_file;

const EXPORT_FORMAT: &str = "tauridium-service-export";
const EXPORT_SCHEMA: u32 = 2;
const MAX_SERVICES: usize = 10_000;
const MAX_RECIPES: usize = 10_000;
const MAX_ICON_BYTES: usize = 512 * 1024;
const MAX_UNCOMPRESSED_BYTES: usize = 256 * 1024 * 1024;
const README_PATH: &str = "README.md";
const MANIFEST_PATH: &str = "manifest.json";

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ServiceExportRequest {
    pub services: Vec<Value>,
    #[serde(default)]
    pub include_all_personal_recipes: bool,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ServiceExportSummary {
    pub path: String,
    pub service_count: usize,
    pub portable_recipe_count: usize,
    pub service_icon_count: usize,
    pub include_all_personal_recipes: bool,
    pub archive_sha256: String,
    pub integrity_verified: bool,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ExportedAsset {
    path: String,
    media_type: String,
    bytes: usize,
    sha256: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ExportedService {
    service: Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    icon: Option<ExportedAsset>,
    #[serde(skip_serializing_if = "Option::is_none")]
    portable_recipe_path: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ExportedRecipe {
    id: String,
    path: String,
    files: Vec<ExportedAsset>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ServiceExportManifest {
    format: String,
    schema: u32,
    app_version: String,
    exported_at_unix: u64,
    include_all_personal_recipes: bool,
    services: Vec<ExportedService>,
    portable_recipes: Vec<ExportedRecipe>,
    security: Value,
}

#[derive(Clone, Debug)]
struct ZipEntry {
    path: String,
    bytes: Vec<u8>,
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn validate_entries(entries: &[ZipEntry]) -> Result<usize, String> {
    if entries.len() > u16::MAX as usize {
        return Err("Service export contains too many ZIP entries".into());
    }
    let mut seen = HashSet::new();
    let total = entries.iter().try_fold(0usize, |sum, entry| {
        validate_archive_path(&entry.path)?;
        if !seen.insert(entry.path.as_str()) {
            return Err(format!("Duplicate service export path: {}", entry.path));
        }
        sum.checked_add(entry.bytes.len())
            .ok_or_else(|| "Service export size overflow".to_string())
    })?;
    if total > MAX_UNCOMPRESSED_BYTES {
        return Err("Service export exceeds the 256 MiB uncompressed safety limit".into());
    }
    Ok(total)
}

fn validate_archive_path(path: &str) -> Result<(), String> {
    if path.is_empty()
        || path.starts_with('/')
        || path.starts_with('\\')
        || path.contains("\\")
        || path
            .split('/')
            .any(|part| part.is_empty() || part == "." || part == "..")
    {
        return Err(format!("Unsafe service export path: {path}"));
    }
    Ok(())
}

fn build_zip(entries: &[ZipEntry]) -> Result<Vec<u8>, String> {
    let total = validate_entries(entries)?;
    let cursor = Cursor::new(Vec::with_capacity(total.min(16 * 1024 * 1024)));
    let mut archive = ZipWriter::new(cursor);
    let options = SimpleFileOptions::default()
        .compression_method(CompressionMethod::Deflated)
        .last_modified_time(DateTime::default())
        .unix_permissions(0o644);

    for entry in entries {
        archive
            .start_file(&entry.path, options)
            .map_err(|error| format!("Unable to add {} to service export: {error}", entry.path))?;
        archive.write_all(&entry.bytes).map_err(|error| {
            format!("Unable to write {} to service export: {error}", entry.path)
        })?;
    }

    archive
        .finish()
        .map(Cursor::into_inner)
        .map_err(|error| format!("Unable to finalize service export ZIP: {error}"))
}

fn verify_zip(bytes: &[u8], expected: &[ZipEntry]) -> Result<(), String> {
    validate_entries(expected)?;
    let reader = Cursor::new(bytes);
    let mut archive = ZipArchive::new(reader)
        .map_err(|error| format!("Unable to reopen service export ZIP: {error}"))?;
    if archive.len() != expected.len() {
        return Err(format!(
            "Service export ZIP contains {} entries; expected {}",
            archive.len(),
            expected.len()
        ));
    }

    let expected_by_path = expected
        .iter()
        .map(|entry| (entry.path.as_str(), entry))
        .collect::<HashMap<_, _>>();
    let mut seen = HashSet::new();
    for index in 0..archive.len() {
        let mut file = archive
            .by_index(index)
            .map_err(|error| format!("Unable to read service export ZIP entry {index}: {error}"))?;
        if file.enclosed_name().is_none() {
            return Err(format!(
                "Unsafe path in service export ZIP: {}",
                file.name()
            ));
        }
        let Some(expected_entry) = expected_by_path.get(file.name()) else {
            return Err(format!(
                "Unexpected service export ZIP entry: {}",
                file.name()
            ));
        };
        if !seen.insert(file.name().to_string()) {
            return Err(format!(
                "Duplicate service export ZIP entry: {}",
                file.name()
            ));
        }
        if file.size() != expected_entry.bytes.len() as u64 {
            return Err(format!(
                "Service export ZIP size verification failed for {}",
                file.name()
            ));
        }
        let mut data = Vec::with_capacity(expected_entry.bytes.len());
        file.read_to_end(&mut data)
            .map_err(|error| format!("Unable to verify {}: {error}", file.name()))?;
        if data != expected_entry.bytes {
            return Err(format!(
                "Service export ZIP content verification failed for {}",
                file.name()
            ));
        }
    }
    if seen.len() != expected.len() {
        return Err("Service export ZIP verification did not observe every expected entry".into());
    }
    Ok(())
}

fn staging_path(path: &Path) -> Result<PathBuf, String> {
    let name = path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| "Service export filename is invalid".to_string())?;
    Ok(path.with_file_name(format!(".{name}.tauridium-tmp-{}", std::process::id())))
}

fn sanitize_service(value: &Value) -> Value {
    fn sanitize(value: &Value) -> Value {
        match value {
            Value::Object(map) => Value::Object(
                map.iter()
                    .map(|(key, value)| {
                        let normalized = key.to_ascii_lowercase();
                        let sensitive = [
                            "password",
                            "passwd",
                            "token",
                            "secret",
                            "cookie",
                            "authorization",
                        ]
                        .iter()
                        .any(|needle| normalized.contains(needle));
                        (
                            key.clone(),
                            if sensitive {
                                Value::String("[redacted]".into())
                            } else {
                                sanitize(value)
                            },
                        )
                    })
                    .collect(),
            ),
            Value::Array(values) => Value::Array(values.iter().map(sanitize).collect()),
            _ => value.clone(),
        }
    }
    sanitize(value)
}

fn service_for_manifest(service: &Value, icon_embedded_as_asset: bool) -> Value {
    let mut sanitized = sanitize_service(service);
    if icon_embedded_as_asset
        && service
            .get("iconUrl")
            .and_then(Value::as_str)
            .is_some_and(|value| value.starts_with("data:"))
    {
        if let Some(object) = sanitized.as_object_mut() {
            object.insert("iconUrl".into(), Value::Null);
        }
    }
    sanitized
}

fn service_id(service: &Value) -> Result<&str, String> {
    service
        .get("id")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|id| !id.is_empty())
        .ok_or_else(|| "Selected service is missing an id".to_string())
}

fn recipe_id(service: &Value) -> Option<&str> {
    service
        .get("recipeId")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|id| !id.is_empty())
}

fn decode_data_uri(value: &str) -> Result<Option<(String, Vec<u8>)>, String> {
    let Some(rest) = value.strip_prefix("data:") else {
        return Ok(None);
    };
    let Some((metadata, encoded)) = rest.split_once(',') else {
        return Err("Service icon data URI is malformed".into());
    };
    let mut parts = metadata.split(';');
    let media_type = parts.next().unwrap_or_default().trim().to_ascii_lowercase();
    if !media_type.starts_with("image/") || !parts.any(|part| part.eq_ignore_ascii_case("base64")) {
        return Err("Service icon data URI must be a base64 image".into());
    }
    let bytes = base64::engine::general_purpose::STANDARD
        .decode(encoded.trim())
        .map_err(|_| "Service icon base64 data is invalid".to_string())?;
    if bytes.is_empty() || bytes.len() > MAX_ICON_BYTES {
        return Err("Service icon has an invalid size".into());
    }
    Ok(Some((media_type, bytes)))
}

fn icon_extension(media_type: &str) -> &'static str {
    match media_type {
        "image/svg+xml" => "svg",
        "image/png" => "png",
        "image/jpeg" => "jpg",
        "image/gif" => "gif",
        "image/webp" => "webp",
        "image/x-icon" | "image/vnd.microsoft.icon" => "ico",
        "image/avif" => "avif",
        "image/bmp" => "bmp",
        _ => "img",
    }
}

fn generic_recipe_icon(label: &str) -> String {
    let text = label
        .chars()
        .next()
        .filter(|character| character.is_ascii_alphanumeric())
        .unwrap_or('T');
    format!(
        r##"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024"><rect width="1024" height="1024" rx="224" fill="#252936"/><text x="512" y="660" text-anchor="middle" font-family="sans-serif" font-size="500" font-weight="700" fill="#fff">{text}</text></svg>"##
    )
}

fn select_recipes(
    services: &[Value],
    all_recipes: &[CustomRecipeBackup],
    include_all: bool,
) -> Result<Vec<CustomRecipeBackup>, String> {
    if all_recipes.len() > MAX_RECIPES {
        return Err("Too many personal recipes to export".into());
    }
    if include_all {
        return Ok(all_recipes.to_vec());
    }
    let ids = services
        .iter()
        .filter_map(recipe_id)
        .collect::<HashSet<_>>();
    Ok(all_recipes
        .iter()
        .filter(|recipe| ids.contains(recipe.id.as_str()))
        .cloned()
        .collect())
}

fn recipe_package(recipe: &CustomRecipeBackup) -> Result<Vec<u8>, String> {
    let mut package = sanitize_service(&recipe.package);
    let object = package
        .as_object_mut()
        .ok_or_else(|| format!("Personal recipe {} package must be an object", recipe.id))?;
    object.remove("tauridium");
    if !object.contains_key("license") {
        object.insert("license".into(), Value::String("MIT".into()));
    }
    serde_json::to_vec_pretty(&package)
        .map(|mut bytes| {
            bytes.push(b'\n');
            bytes
        })
        .map_err(|error| format!("Unable to serialize personal recipe {}: {error}", recipe.id))
}

fn is_custom_website_service(service: &Value) -> bool {
    service
        .get("isLocalRecipe")
        .and_then(Value::as_bool)
        .unwrap_or(false)
        && recipe_id(service) == Some("custom-website")
}

fn custom_website_recipe_id(service: &Value) -> Result<String, String> {
    let id = service_id(service)?;
    let digest = sha256_hex(id.as_bytes());
    Ok(format!("tauridium-website-{}", &digest[..16]))
}

fn custom_website_recipe_package(service: &Value, id: &str) -> Result<Vec<u8>, String> {
    let name = service
        .get("name")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or("Custom Website");
    let url = service
        .get("customUrl")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("Custom website {name} is missing a valid HTTP(S) URL"))?;
    let parsed = Url::parse(url)
        .map_err(|error| format!("Custom website {name} has an invalid URL: {error}"))?;
    if !matches!(parsed.scheme(), "http" | "https") {
        return Err(format!("Custom website {name} must use HTTP or HTTPS"));
    }
    let package = json!({
        "id": id,
        "name": name,
        "version": "1.0.0",
        "description": "Standalone recipe exported from a Tauridium custom website service.",
        "license": "MIT",
        "config": {
            "serviceURL": url,
            "hasCustomUrl": false,
            "hasTeamId": false
        }
    });
    serde_json::to_vec_pretty(&package)
        .map(|mut bytes| {
            bytes.push(b'\n');
            bytes
        })
        .map_err(|error| format!("Unable to serialize custom website recipe {id}: {error}"))
}

fn svg_icon_from_image(media_type: &str, bytes: &[u8], label: &str) -> String {
    if bytes.is_empty() {
        return generic_recipe_icon(label);
    }
    let encoded = base64::engine::general_purpose::STANDARD.encode(bytes);
    format!(
        r##"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024"><image width="1024" height="1024" preserveAspectRatio="xMidYMid meet" href="data:{media_type};base64,{encoded}"/></svg>"##
    )
}

fn custom_website_services<'a>(
    selected: &'a [Value],
    all_local_services: &'a [Value],
    include_all: bool,
) -> Result<Vec<&'a Value>, String> {
    let mut by_id = HashMap::<String, &Value>::new();
    for service in selected
        .iter()
        .chain(
            include_all
                .then_some(all_local_services)
                .into_iter()
                .flatten(),
        )
        .filter(|service| is_custom_website_service(service))
    {
        by_id.insert(service_id(service)?.to_string(), service);
    }
    let mut values = by_id.into_values().collect::<Vec<_>>();
    values.sort_by_key(|service| service_id(service).unwrap_or_default().to_string());
    Ok(values)
}

fn asset(path: String, media_type: &str, bytes: &[u8]) -> ExportedAsset {
    ExportedAsset {
        path,
        media_type: media_type.into(),
        bytes: bytes.len(),
        sha256: sha256_hex(bytes),
    }
}

fn readme() -> Vec<u8> {
    b"# Tauridium service export\n\nThis ZIP is a portable, reviewable export of selected Tauridium services. `manifest.json` contains service settings and SHA-256 metadata for included assets. Secret-like fields (passwords, tokens, cookies, authorization values, and secrets) are deliberately redacted. Website session storage, cookies, authentication state, and other browser profile data are never exported.\n\nRecipe terminology:\n- **Ferdium recipes** come from the upstream Ferdium catalog. They are referenced by recipe id and are not copied into the ZIP.\n- **Tauridium built-in recipes** ship with Tauridium. They are also referenced by recipe id and are not bulk-exported as personal recipes.\n- **Personal recipes** are recipes the user created or imported on this device. Referenced personal recipes are included automatically, and the export option can include all of them.\n- **Custom websites** are one-off services created with Tauridium's built-in Custom Website template. When exported, Tauridium generates a standalone Ferdium-compatible recipe for each included custom website.\n\n`icons/services/` contains locally available service icons. `recipes/<id>/` contains exported personal recipes and generated Custom Website recipes in the upstream Ferdium recipe layout: `package.json`, `index.js`, `icon.svg`, and optional `webview.js`. Recipe folders can be reviewed before copying into the `recipes/` directory of the Ferdium recipes repository.\n\nTauridium does not fetch remote icon URLs during export; the bundle only captures icon bytes already present locally.\n".to_vec()
}

pub(crate) fn save(
    app: &AppHandle,
    path: &Path,
    app_version: &str,
    request: ServiceExportRequest,
    all_recipes: &[CustomRecipeBackup],
    all_local_services: &[Value],
) -> Result<ServiceExportSummary, String> {
    if path.as_os_str().is_empty() {
        return Err("Service export destination path is empty".into());
    }
    if request.services.len() > MAX_SERVICES {
        return Err("Too many services selected for export".into());
    }
    let mut seen_services = HashSet::new();
    for service in &request.services {
        let id = service_id(service)?;
        if !seen_services.insert(id.to_string()) {
            return Err(format!("Duplicate selected service id: {id}"));
        }
    }
    let recipes = select_recipes(
        &request.services,
        all_recipes,
        request.include_all_personal_recipes,
    )?;
    let recipe_ids = recipes
        .iter()
        .map(|recipe| recipe.id.as_str())
        .collect::<HashSet<_>>();
    let custom_websites = custom_website_services(
        &request.services,
        all_local_services,
        request.include_all_personal_recipes,
    )?;
    let custom_website_recipe_ids = custom_websites
        .iter()
        .map(|service| {
            Ok((
                service_id(service)?.to_string(),
                custom_website_recipe_id(service)?,
            ))
        })
        .collect::<Result<HashMap<_, _>, String>>()?;

    let mut entries = Vec::<ZipEntry>::new();
    entries.push(ZipEntry {
        path: README_PATH.into(),
        bytes: readme(),
    });

    let mut exported_services = Vec::with_capacity(request.services.len());
    let mut icon_count = 0usize;
    for service in &request.services {
        let id = service_id(service)?;
        let cached = icons::cached_data_uri(app, id);
        let embedded = service.get("iconUrl").and_then(Value::as_str);
        let icon_source = cached.as_deref().or(embedded);
        let icon = if let Some(icon_source) = icon_source {
            if let Some((media_type, bytes)) = decode_data_uri(icon_source)? {
                let path = format!("icons/services/{id}.{}", icon_extension(&media_type));
                let metadata = asset(path.clone(), &media_type, &bytes);
                entries.push(ZipEntry { path, bytes });
                icon_count += 1;
                Some(metadata)
            } else {
                None
            }
        } else {
            None
        };
        let portable_recipe_path = if let Some(recipe_id) = custom_website_recipe_ids.get(id) {
            Some(format!("recipes/{recipe_id}/"))
        } else {
            recipe_id(service)
                .filter(|recipe_id| recipe_ids.contains(*recipe_id))
                .map(|recipe_id| format!("recipes/{recipe_id}/"))
        };
        let icon_embedded_as_asset = icon.is_some();
        exported_services.push(ExportedService {
            service: service_for_manifest(service, icon_embedded_as_asset),
            icon,
            portable_recipe_path,
        });
    }

    let mut exported_recipes = Vec::with_capacity(recipes.len());
    for recipe in &recipes {
        let base = format!("recipes/{}/", recipe.id);
        let package = recipe_package(recipe)?;
        let index = b"module.exports = Ferdium => Ferdium;\n".to_vec();
        let name = recipe
            .package
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or(&recipe.id);
        let icon = if recipe.icon_svg.trim().is_empty() {
            generic_recipe_icon(name)
        } else {
            recipe.icon_svg.clone()
        }
        .into_bytes();
        let mut files = Vec::new();
        for (filename, media_type, bytes) in [
            ("package.json", "application/json", package),
            ("index.js", "text/javascript", index),
            ("icon.svg", "image/svg+xml", icon),
        ] {
            let path = format!("{base}{filename}");
            files.push(asset(path.clone(), media_type, &bytes));
            entries.push(ZipEntry { path, bytes });
        }
        if !recipe.webview_js.trim().is_empty() {
            let bytes = recipe.webview_js.as_bytes().to_vec();
            let path = format!("{base}webview.js");
            files.push(asset(path.clone(), "text/javascript", &bytes));
            entries.push(ZipEntry { path, bytes });
        }
        exported_recipes.push(ExportedRecipe {
            id: recipe.id.clone(),
            path: base,
            files,
        });
    }

    for service in custom_websites {
        let service_id = service_id(service)?;
        let recipe_id = custom_website_recipe_ids
            .get(service_id)
            .ok_or_else(|| "Custom website recipe mapping is incomplete".to_string())?;
        let base = format!("recipes/{recipe_id}/");
        let package = custom_website_recipe_package(service, recipe_id)?;
        let index = b"module.exports = Ferdium => Ferdium;
"
        .to_vec();
        let name = service
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or("Custom Website");
        let cached = icons::cached_data_uri(app, service_id);
        let embedded = service.get("iconUrl").and_then(Value::as_str);
        let recipe_icon = match cached.as_deref().or(embedded) {
            Some(source) => match decode_data_uri(source)? {
                Some((media_type, bytes)) => svg_icon_from_image(&media_type, &bytes, name),
                None => generic_recipe_icon(name),
            },
            None => generic_recipe_icon(name),
        }
        .into_bytes();
        let mut files = Vec::new();
        for (filename, media_type, bytes) in [
            ("package.json", "application/json", package),
            ("index.js", "text/javascript", index),
            ("icon.svg", "image/svg+xml", recipe_icon),
        ] {
            let path = format!("{base}{filename}");
            files.push(asset(path.clone(), media_type, &bytes));
            entries.push(ZipEntry { path, bytes });
        }
        exported_recipes.push(ExportedRecipe {
            id: recipe_id.clone(),
            path: base,
            files,
        });
    }

    let exported_recipe_count = exported_recipes.len();
    let manifest = ServiceExportManifest {
        format: EXPORT_FORMAT.into(),
        schema: EXPORT_SCHEMA,
        app_version: app_version.into(),
        exported_at_unix: SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs(),
        include_all_personal_recipes: request.include_all_personal_recipes,
        services: exported_services,
        portable_recipes: exported_recipes,
        security: json!({
            "secretsRedacted": true,
            "browserSessionDataIncluded": false,
            "remoteIconsFetchedDuringExport": false
        }),
    };
    let mut manifest_bytes = serde_json::to_vec_pretty(&manifest)
        .map_err(|error| format!("Unable to serialize service export manifest: {error}"))?;
    manifest_bytes.push(b'\n');
    entries.push(ZipEntry {
        path: MANIFEST_PATH.into(),
        bytes: manifest_bytes,
    });
    entries.sort_by(|left, right| left.path.cmp(&right.path));

    let archive = build_zip(&entries)?;
    verify_zip(&archive, &entries)?;
    let archive_sha256 = sha256_hex(&archive);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("Unable to create service export directory: {error}"))?;
    }
    let staging = staging_path(path)?;
    if staging.exists() {
        fs::remove_file(&staging).map_err(|error| {
            format!("Unable to clear stale service export staging file: {error}")
        })?;
    }
    let staged = (|| -> Result<(), String> {
        let mut file = fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&staging)
            .map_err(|error| format!("Unable to create service export staging file: {error}"))?;
        file.write_all(&archive)
            .map_err(|error| format!("Unable to write service export: {error}"))?;
        file.sync_all()
            .map_err(|error| format!("Unable to flush service export: {error}"))?;
        let reread = fs::read(&staging)
            .map_err(|error| format!("Unable to reread staged service export: {error}"))?;
        if sha256_hex(&reread) != archive_sha256 {
            return Err("Service export verification produced different archive bytes".into());
        }
        verify_zip(&reread, &entries)
    })();
    if let Err(error) = staged {
        let _ = fs::remove_file(&staging);
        return Err(error);
    }
    replace_file(&staging, path)
        .map_err(|error| format!("Unable to finalize Tauridium service export: {error}"))?;

    Ok(ServiceExportSummary {
        path: path.to_string_lossy().into_owned(),
        service_count: request.services.len(),
        portable_recipe_count: exported_recipe_count,
        service_icon_count: icon_count,
        include_all_personal_recipes: request.include_all_personal_recipes,
        archive_sha256,
        integrity_verified: true,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn service(id: &str, recipe_id: &str) -> Value {
        json!({
            "id": id,
            "name": "Example",
            "recipeId": recipe_id,
            "proxyPassword": "private",
            "iconUrl": "data:image/png;base64,iVBORw0KGgo="
        })
    }

    fn custom_website(id: &str, url: &str) -> Value {
        json!({
            "id": id,
            "name": "Private Dashboard",
            "recipeId": "custom-website",
            "customUrl": url,
            "iconUrl": "data:image/png;base64,AQID",
            "isEnabled": true,
            "isLocalRecipe": true
        })
    }

    fn recipes() -> Vec<CustomRecipeBackup> {
        vec![
            CustomRecipeBackup {
                id: "local-one".into(),
                package: json!({
                    "id": "local-one",
                    "name": "Local One",
                    "version": "1.0.0",
                    "config": { "serviceURL": "https://example.com", "hasCustomUrl": true },
                    "tauridium": { "local": true }
                }),
                icon_svg: "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 1 1\"></svg>"
                    .into(),
                webview_js: "console.log('test');".into(),
            },
            CustomRecipeBackup {
                id: "local-unused".into(),
                package: json!({
                    "id": "local-unused",
                    "name": "Unused",
                    "version": "1.0.0",
                    "config": { "serviceURL": "https://unused.example" }
                }),
                icon_svg: String::new(),
                webview_js: String::new(),
            },
        ]
    }

    #[test]
    fn zip_writer_round_trips_entries_and_crc() {
        let entries = vec![
            ZipEntry {
                path: "manifest.json".into(),
                bytes: b"{}\n".to_vec(),
            },
            ZipEntry {
                path: "icons/services/a.png".into(),
                bytes: vec![1, 2, 3, 4],
            },
        ];
        let bytes = build_zip(&entries).unwrap();
        verify_zip(&bytes, &entries).unwrap();
        assert!(bytes.starts_with(&0x0403_4b50u32.to_le_bytes()));
        assert_eq!(
            &bytes[bytes.len() - 22..bytes.len() - 18],
            &0x0605_4b50u32.to_le_bytes()
        );
    }

    #[test]
    fn zip_writer_rejects_unsafe_and_duplicate_paths() {
        assert!(build_zip(&[ZipEntry {
            path: "../bad".into(),
            bytes: vec![]
        }])
        .is_err());
        assert!(build_zip(&[
            ZipEntry {
                path: "a".into(),
                bytes: vec![]
            },
            ZipEntry {
                path: "a".into(),
                bytes: vec![]
            },
        ])
        .is_err());
    }

    #[test]
    fn recipe_selection_defaults_to_referenced_and_can_include_all() {
        let services = vec![service("svc", "local-one")];
        assert_eq!(
            select_recipes(&services, &recipes(), false).unwrap().len(),
            1
        );
        assert_eq!(
            select_recipes(&services, &recipes(), true).unwrap().len(),
            2
        );
    }

    #[test]
    fn service_sanitization_redacts_secret_like_fields() {
        let sanitized = sanitize_service(&json!({
            "id": "svc",
            "password": "one",
            "nested": { "apiToken": "two", "safe": "yes" }
        }));
        assert_eq!(sanitized["password"], "[redacted]");
        assert_eq!(sanitized["nested"]["apiToken"], "[redacted]");
        assert_eq!(sanitized["nested"]["safe"], "yes");
    }

    #[test]
    fn manifest_service_references_embedded_icon_asset_without_duplicate_base64() {
        let service = service("svc", "local-one");
        let manifest_service = service_for_manifest(&service, true);
        assert_eq!(manifest_service["iconUrl"], Value::Null);
        let unchanged = service_for_manifest(&service, false);
        assert!(unchanged["iconUrl"]
            .as_str()
            .is_some_and(|value| value.starts_with("data:image/png;base64,")));
    }

    #[test]
    fn ferdium_recipe_package_drops_tauridium_metadata_and_adds_license() {
        let recipe = recipes().remove(0);
        let bytes = recipe_package(&recipe).unwrap();
        let package: Value = serde_json::from_slice(&bytes).unwrap();
        assert!(package.get("tauridium").is_none());
        assert_eq!(package["license"], "MIT");
        assert_eq!(package["config"]["serviceURL"], "https://example.com");
    }

    #[test]
    fn custom_website_becomes_standalone_ferdium_recipe() {
        let service = custom_website("website-1", "https://dashboard.example.test/path");
        let id = custom_website_recipe_id(&service).unwrap();
        assert!(id.starts_with("tauridium-website-"));
        let package: Value =
            serde_json::from_slice(&custom_website_recipe_package(&service, &id).unwrap()).unwrap();
        assert_eq!(package["id"], id);
        assert_eq!(package["name"], "Private Dashboard");
        assert_eq!(
            package["config"]["serviceURL"],
            "https://dashboard.example.test/path"
        );
        assert_eq!(package["config"]["hasCustomUrl"], false);
        assert_eq!(package["version"], "1.0.0");
    }

    #[test]
    fn custom_website_selection_always_keeps_selected_and_optionally_adds_all_local() {
        let selected = vec![custom_website("selected", "https://selected.example.test")];
        let all_local = vec![
            custom_website("selected", "https://selected.example.test"),
            custom_website("other", "https://other.example.test"),
        ];
        let referenced = custom_website_services(&selected, &all_local, false).unwrap();
        assert_eq!(referenced.len(), 1);
        assert_eq!(service_id(referenced[0]).unwrap(), "selected");

        let all = custom_website_services(&selected, &all_local, true).unwrap();
        assert_eq!(all.len(), 2);
        assert_eq!(service_id(all[0]).unwrap(), "other");
        assert_eq!(service_id(all[1]).unwrap(), "selected");
    }

    #[test]
    fn custom_website_recipe_rejects_non_http_urls() {
        let service = custom_website("website-1", "file:///tmp/private.html");
        assert!(custom_website_recipe_package(&service, "tauridium-website-test").is_err());
    }

    #[test]
    fn data_uri_icons_are_bounded_and_decoded() {
        let (media_type, bytes) = decode_data_uri("data:image/png;base64,AQID")
            .unwrap()
            .unwrap();
        assert_eq!(media_type, "image/png");
        assert_eq!(bytes, vec![1, 2, 3]);
        assert!(decode_data_uri("https://example.com/icon.png")
            .unwrap()
            .is_none());
        assert!(decode_data_uri("data:text/plain;base64,AQID").is_err());
    }
}
