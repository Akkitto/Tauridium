//! Service preference, CRUD and cache-management commands.

use super::navigation::ensure_scheme;
use super::storage::{purge_service_storage, sandbox_for_service};
use crate::{
    audit, current, http_security, icons, is_local_mode, recipes, require_known_service,
    save_local_profile, storage_security, AppState, ServiceFlags, API_UA, HTTP,
};
use serde_json::Value;
use tauri::{AppHandle, Manager, State, Url};

use super::lifecycle::close_service_ids;

#[tauri::command]
pub(crate) fn set_service_flags(
    state: State<'_, AppState>,
    service_id: String,
    notif: bool,
    muted: bool,
    badge: bool,
    indirect_badge: Option<bool>,
) {
    state.flags.lock().unwrap().insert(
        service_id,
        ServiceFlags {
            notif,
            muted,
            badge,
            indirect_badge: indirect_badge.unwrap_or(false),
        },
    );
}

fn finish_service_update(
    app: &AppHandle,
    service_id: &str,
    patch: &Value,
    result: Result<Value, String>,
) -> Result<Value, String> {
    match result {
        Ok(updated) => {
            audit::best_effort(
                app,
                "info",
                "settings",
                "service-change",
                "success",
                "Service settings changed",
                serde_json::json!({ "serviceId": service_id, "changes": patch }),
            );
            Ok(updated)
        }
        Err(error) => {
            audit::best_effort(
                app,
                "error",
                "settings",
                "service-change",
                "failure",
                "Service settings change failed",
                serde_json::json!({
                    "serviceId": service_id,
                    "changes": patch,
                    "error": &error
                }),
            );
            Err(error)
        }
    }
}

#[tauri::command]
pub(crate) async fn update_service(
    app: AppHandle,
    state: State<'_, AppState>,
    service_id: String,
    patch: Value,
) -> Result<Value, String> {
    let local_service = state
        .local_profile
        .lock()
        .unwrap()
        .has_local_recipe_service(&service_id);
    if is_local_mode(&state) || local_service {
        let operation = (|| -> Result<Value, String> {
            let mut profile = state.local_profile.lock().unwrap();
            let mut next = profile.clone();
            let updated = next.update_service(&service_id, &patch)?;
            save_local_profile(&app, &next)?;
            *profile = next;
            Ok(updated)
        })();
        return finish_service_update(&app, &service_id, &patch, operation);
    }

    let operation = async {
        let (base, token) = current(&state)?;
        let res = HTTP
            .clone()
            .put(format!("{base}/v1/service/{service_id}"))
            .bearer_auth(&token)
            .header(reqwest::header::USER_AGENT, API_UA)
            .json(&patch)
            .send()
            .await
            .map_err(|error| error.to_string())?;
        if !res.status().is_success() {
            return Err(format!("Service update failed: HTTP {}", res.status()));
        }
        http_security::json(res).await
    }
    .await;
    finish_service_update(&app, &service_id, &patch, operation)
}

#[tauri::command]
pub(crate) async fn create_service(
    app: AppHandle,
    state: State<'_, AppState>,
    name: String,
    recipe_id: String,
) -> Result<Value, String> {
    let local_recipe = recipes::local_recipe_config(&app, &recipe_id)?.is_some();
    if is_local_mode(&state) || local_recipe {
        let icon_url = if local_recipe {
            recipes::local_icon_url(&app, &recipe_id)
        } else {
            None
        };
        let prefer_website_icon = local_recipe && !recipes::is_bundled_recipe(&recipe_id);
        let mut profile = state.local_profile.lock().unwrap();
        let mut next = profile.clone();
        let mut service = next.create_service(name, recipe_id, icon_url, local_recipe)?;
        if prefer_website_icon {
            let service_id = service
                .get("id")
                .and_then(Value::as_str)
                .ok_or_else(|| "Created custom-recipe service has no id".to_string())?
                .to_string();
            service =
                next.update_service(&service_id, &serde_json::json!({ "useFavicon": true }))?;
        }
        save_local_profile(&app, &next)?;
        *profile = next;
        if let Some(id) = service.get("id").and_then(Value::as_str) {
            storage_security::validate_service_id(id)?;
            state.known_services.lock().unwrap().insert(id.to_string());
        }
        return Ok(service);
    }
    let (base, token) = current(&state)?;
    let res = HTTP
        .clone()
        .post(format!("{base}/v1/service"))
        .bearer_auth(&token)
        .header(reqwest::header::USER_AGENT, API_UA)
        .json(&serde_json::json!({ "name": name, "recipeId": recipe_id }))
        .send()
        .await
        .map_err(|e| e.to_string())?;
    if !res.status().is_success() {
        return Err(format!("Service creation failed: HTTP {}", res.status()));
    }
    let service: Value = http_security::json(res).await?;
    let id = service
        .get("id")
        .and_then(Value::as_str)
        .ok_or("Created service has no string id")?;
    storage_security::validate_service_id(id)?;
    if state
        .known_services
        .lock()
        .unwrap()
        .iter()
        .any(|known| known != id && known.eq_ignore_ascii_case(id))
    {
        return Err("Created service id aliases an existing session directory".into());
    }
    state.known_services.lock().unwrap().insert(id.to_string());
    Ok(service)
}

#[tauri::command]
pub(crate) fn create_custom_website_service(
    app: AppHandle,
    state: State<'_, AppState>,
    name: String,
    url: String,
) -> Result<Value, String> {
    let url = ensure_scheme(url.trim());
    let parsed = Url::parse(&url).map_err(|error| format!("Invalid website URL: {error}"))?;
    if parsed.scheme() != "http" && parsed.scheme() != "https" {
        return Err("Custom websites must use http:// or https://".into());
    }
    let display_name = if name.trim().is_empty() {
        parsed.host_str().unwrap_or("Custom Website").to_string()
    } else {
        name.trim().to_string()
    };
    let mut profile = state.local_profile.lock().unwrap();
    let mut next = profile.clone();
    let mut service = next.create_service(
        display_name,
        "custom-website".into(),
        recipes::local_icon_url(&app, "custom-website"),
        true,
    )?;
    let service_id = service
        .get("id")
        .and_then(Value::as_str)
        .ok_or_else(|| "Created custom website service has no id".to_string())?
        .to_string();
    service = next.update_service(
        &service_id,
        &serde_json::json!({ "customUrl": url, "useFavicon": true }),
    )?;
    save_local_profile(&app, &next)?;
    *profile = next;
    Ok(service)
}

#[tauri::command]
pub(crate) async fn delete_service(
    app: AppHandle,
    state: State<'_, AppState>,
    service_id: String,
) -> Result<(), String> {
    require_known_service(&state, &service_id)?;
    let sandbox_id = sandbox_for_service(&state.settings.lock().unwrap(), &service_id);
    let local_service = state
        .local_profile
        .lock()
        .unwrap()
        .has_local_recipe_service(&service_id);
    if is_local_mode(&state) || local_service {
        let mut profile = state.local_profile.lock().unwrap();
        let mut next = profile.clone();
        next.delete_service(&service_id)?;
        save_local_profile(&app, &next)?;
        *profile = next;
    } else {
        let (base, token) = current(&state)?;
        let res = HTTP
            .clone()
            .delete(format!("{base}/v1/service/{service_id}"))
            .bearer_auth(&token)
            .header(reqwest::header::USER_AGENT, API_UA)
            .send()
            .await
            .map_err(|e| e.to_string())?;
        if !res.status().is_success() {
            return Err(format!("Service deletion failed: HTTP {}", res.status()));
        }
    }
    if let Some(wv) = app.get_webview(&format!("svc-{service_id}")) {
        let _ = wv.close();
    }
    state.created.lock().unwrap().remove(&service_id);
    state.unread.lock().unwrap().remove(&service_id);
    state.flags.lock().unwrap().remove(&service_id);
    icons::remove_cached(&app, &service_id);
    // Isolated services own their storage and can be purged safely. Shared sandbox data
    // belongs to the sandbox, so deleting one member must not sign out the remaining members.
    if sandbox_id.is_none() {
        purge_service_storage(&app, &service_id, None)?;
    }
    state.known_services.lock().unwrap().remove(&service_id);
    Ok(())
}

#[tauri::command]
pub(crate) fn clear_service_cache(
    app: AppHandle,
    state: State<'_, AppState>,
    service_id: String,
) -> Result<(), String> {
    require_known_service(&state, &service_id)?;
    let sandbox_id = sandbox_for_service(&state.settings.lock().unwrap(), &service_id);
    let service_ids = if let Some(ref sandbox_id) = sandbox_id {
        services_in_sandbox(&state.settings.lock().unwrap(), sandbox_id)
    } else {
        vec![service_id.clone()]
    };
    close_service_ids(&app, &state, &service_ids);
    purge_service_storage(&app, &service_id, sandbox_id.as_deref())
}

fn services_in_sandbox(settings: &Value, sandbox_id: &str) -> Vec<String> {
    settings
        .get("serviceSandboxes")
        .and_then(Value::as_object)
        .map(|assignments| {
            assignments
                .iter()
                .filter(|(_, value)| value.as_str() == Some(sandbox_id))
                .map(|(service_id, _)| service_id.clone())
                .collect()
        })
        .unwrap_or_default()
}

#[tauri::command]
pub(crate) fn clear_sandbox(
    app: AppHandle,
    state: State<'_, AppState>,
    sandbox_id: String,
) -> Result<(), String> {
    let sandbox_id = sandbox_id.trim();
    if sandbox_id.is_empty() {
        return Err("Sandbox id is empty".into());
    }
    let settings = state.settings.lock().unwrap().clone();
    let known = settings
        .get("sandboxes")
        .and_then(Value::as_array)
        .is_some_and(|sandboxes| {
            sandboxes
                .iter()
                .any(|sandbox| sandbox.get("id").and_then(Value::as_str) == Some(sandbox_id))
        });
    if !known {
        return Err(format!("Unknown sandbox: {sandbox_id}"));
    }
    let service_ids = services_in_sandbox(&settings, sandbox_id);
    close_service_ids(&app, &state, &service_ids);
    purge_service_storage(&app, "sandbox", Some(sandbox_id))?;
    Ok(())
}
