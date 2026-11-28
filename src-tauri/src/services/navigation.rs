//! Recipe configuration and service URL resolution.
use crate::local_profile::validate_recipe_id;

use crate::{
    http_security, ipc_security, recipe_cache_directory, recipe_source, recipes, write_atomic,
    API_UA, HTTP,
};
use serde_json::Value;
use std::path::Path;
use tauri::{AppHandle, Url};

pub(crate) async fn recipe_config(
    app: &AppHandle,
    app_data: &Path,
    recipe_id: &str,
) -> Result<Value, String> {
    validate_recipe_id(recipe_id)?;
    if let Some(local) = recipes::local_recipe_config(app, recipe_id)? {
        return Ok(local);
    }

    let dir = recipe_cache_directory(app)?;
    let _ = std::fs::create_dir_all(&dir);
    let cache = dir.join(format!("{recipe_id}.json"));

    if let Some(text) = recipe_source::read_cache_with_legacy(
        &cache,
        &recipe_source::legacy_cache_directory(app_data).join(format!("{recipe_id}.json")),
        http_security::MAX_RECIPE_BYTES,
    ) {
        if let Ok(v) = serde_json::from_str::<Value>(&text) {
            return Ok(v);
        }
    }

    let url = recipe_source::asset_url(recipe_id, "package.json");
    let res = HTTP
        .clone()
        .get(&url)
        .header(reqwest::header::USER_AGENT, API_UA)
        .send()
        .await
        .map_err(|e| format!("Recipe {recipe_id} download failed: {e}"))?;
    if !res.status().is_success() {
        return Err(format!(
            "Recipe {recipe_id} not found (HTTP {})",
            res.status()
        ));
    }
    let text = http_security::text(res, http_security::MAX_RECIPE_BYTES)
        .await
        .map_err(|e| format!("Unable to parse recipe {recipe_id}: {e}"))?;
    let _ = write_atomic(&cache, &text);
    serde_json::from_str(&text).map_err(|e| format!("Invalid package.json for {recipe_id}: {e}"))
}

pub(super) fn ensure_scheme(u: &str) -> String {
    if u.starts_with("http://") || u.starts_with("https://") {
        u.to_string()
    } else {
        format!("https://{u}")
    }
}

#[derive(Clone, Debug, Default)]
pub(crate) struct CustomUrlTemplateValues {
    enabled: bool,
    custom_id_1: String,
    custom_id_2: String,
}

pub(crate) fn service_custom_url_template_values(
    settings: &Value,
    service_id: &str,
) -> CustomUrlTemplateValues {
    let global = settings
        .get("customUrlTemplatesEnabled")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let entry = settings
        .get("serviceCustomUrlTemplates")
        .and_then(Value::as_object)
        .and_then(|entries| entries.get(service_id))
        .and_then(Value::as_object);
    CustomUrlTemplateValues {
        enabled: global
            || entry
                .and_then(|value| value.get("enabled"))
                .and_then(Value::as_bool)
                .unwrap_or(false),
        custom_id_1: entry
            .and_then(|value| value.get("customId1"))
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        custom_id_2: entry
            .and_then(|value| value.get("customId2"))
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
    }
}

fn apply_custom_url_templates(
    url: &str,
    values: &CustomUrlTemplateValues,
) -> Result<String, String> {
    if !values.enabled {
        return Ok(url.to_string());
    }
    let mut resolved = url.to_string();
    for (placeholder, value, label) in [
        ("{{custom_id_1}}", values.custom_id_1.trim(), "custom ID 1"),
        ("{{custom_id_2}}", values.custom_id_2.trim(), "custom ID 2"),
    ] {
        if resolved.contains(placeholder) {
            if value.is_empty() {
                return Err(format!(
                    "Custom URL uses {placeholder} but {label} is empty"
                ));
            }
            resolved = resolved.replace(placeholder, value);
        }
    }
    if resolved.contains("{{custom_id_") {
        return Err("Custom URL contains an unsupported custom ID placeholder".into());
    }
    Ok(resolved)
}

pub(crate) fn resolve_url(
    cfg: &Value,
    custom_url: Option<&str>,
    team: Option<&str>,
    templates: &CustomUrlTemplateValues,
) -> Result<String, String> {
    let config = cfg.get("config").ok_or("Recipe has no config block")?;
    let service_url = config
        .get("serviceURL")
        .and_then(Value::as_str)
        .unwrap_or("");
    let has_team = config
        .get("hasTeamId")
        .and_then(Value::as_bool)
        .unwrap_or(false);

    // An explicit instance setting wins over the recipe's default, even
    // when the recipe does not advertise support for custom deployments.
    if let Some(value) = custom_url.map(str::trim).filter(|value| !value.is_empty()) {
        let has_explicit_scheme = value
            .split_once("://")
            .is_some_and(|(scheme, _)| !scheme.contains(['/', '?', '#']));
        let mut resolved = if has_explicit_scheme {
            value.to_owned()
        } else {
            ensure_scheme(value)
        };
        if has_team {
            if let Some(team) = team.map(str::trim).filter(|team| !team.is_empty()) {
                resolved = resolved.replace("{teamId}", team);
            }
        }
        let resolved = apply_custom_url_templates(&resolved, templates)?;
        let url = Url::parse(&resolved).map_err(|error| format!("Invalid custom URL: {error}"))?;
        if !matches!(url.scheme(), "http" | "https")
            || !ipc_security::service_navigation_allowed(&url)
        {
            return Err(
                "Custom URLs must use HTTP or HTTPS outside Tauridium's internal origins".into(),
            );
        }
        return Ok(resolved);
    }
    if has_team {
        if let Some(t) = team.map(str::trim).filter(|t| !t.is_empty()) {
            let team_url = config
                .get("teamURL")
                .and_then(Value::as_str)
                .filter(|value| !value.is_empty())
                .unwrap_or(service_url);
            return Ok(team_url.replace("{teamId}", t));
        }
    }
    if service_url.is_empty() {
        return Err("Recipe has no serviceURL".into());
    }
    Ok(service_url.to_string())
}

/// Fixed-origin recipes may contain redirects or DOM logic for their own site.
/// A cross-origin override still opens as a normal service webview. Preserve
/// recipe support for explicitly advertised custom deployments.
pub(super) fn recipe_runtime_allowed(cfg: &Value, team: Option<&str>, destination: &Url) -> bool {
    if cfg.pointer("/config/hasCustomUrl").and_then(Value::as_bool) == Some(true) {
        return true;
    }
    resolve_url(cfg, None, team, &CustomUrlTemplateValues::default())
        .ok()
        .and_then(|default| Url::parse(&default).ok())
        .is_some_and(|default| default.origin() == destination.origin())
}

#[cfg(test)]
mod tests;
