//! Application settings persistence and native command orchestration.
#[cfg(all(target_os = "linux", feature = "flatpak"))]
use crate::flatpak_portal;
#[cfg(all(
    target_os = "linux",
    feature = "nix",
    not(feature = "desktop-integration"),
    not(feature = "flatpak")
))]
use crate::nix_autostart;

pub(crate) mod validation;

use self::validation::{
    default_app_settings_value, effective_service_zoom_percent, merge_app_settings_value,
    valid_service_setting_id, validate_app_settings_value, validate_order_ids,
    SERVICE_ZOOM_DEFAULT_PERCENT, SERVICE_ZOOM_MAX_PERCENT, SERVICE_ZOOM_MIN_PERCENT,
};
use crate::{audit, download_toast, startup_diagnostics, window_chrome, write_atomic, AppState};
use serde_json::Value;
use std::path::PathBuf;
use tauri::{AppHandle, Manager, State};
#[cfg(all(feature = "desktop-integration", not(feature = "flatpak")))]
use tauri_plugin_autostart::ManagerExt;

fn app_settings_path(app: &AppHandle) -> Option<PathBuf> {
    app.path()
        .app_data_dir()
        .ok()
        .map(|d| d.join("app_settings.json"))
}

pub(crate) fn read_app_settings_value(app: &AppHandle) -> Value {
    let stored = app_settings_path(app)
        .and_then(|path| std::fs::read_to_string(path).ok())
        .and_then(|text| serde_json::from_str::<Value>(&text).ok());
    stored
        .as_ref()
        .and_then(|value| merge_app_settings_value(value).ok())
        .unwrap_or_else(default_app_settings_value)
}

pub(crate) fn effective_app_settings_value(app: &AppHandle) -> Value {
    let value = read_app_settings_value(app);
    #[cfg(all(feature = "desktop-integration", not(feature = "flatpak")))]
    {
        let mut value = value;
        if let Ok(enabled) = app.autolaunch().is_enabled() {
            if let Some(object) = value.as_object_mut() {
                object.insert("autostart".into(), Value::Bool(enabled));
            }
        }
        value
    }
    #[cfg(any(not(feature = "desktop-integration"), feature = "flatpak"))]
    {
        #[cfg(all(
            target_os = "linux",
            feature = "nix",
            not(feature = "desktop-integration"),
            not(feature = "flatpak")
        ))]
        let value = {
            let mut value = value;
            if let Ok(enabled) = nix_autostart::is_enabled() {
                if let Some(object) = value.as_object_mut() {
                    object.insert("autostart".into(), Value::Bool(enabled));
                }
            }
            value
        };
        value
    }
}

#[cfg(any(test, all(feature = "desktop-integration", not(feature = "flatpak"))))]
fn autostart_needs_update(current: bool, desired: bool) -> bool {
    current != desired
}

pub(crate) fn apply_autostart_setting(app: &AppHandle, settings: &Value) -> Result<bool, String> {
    // Native builds use the autostart plugin; Flatpak builds use the Background portal.
    let _ = app;
    #[cfg(any(
        all(feature = "desktop-integration", not(feature = "flatpak")),
        all(target_os = "linux", any(feature = "nix", feature = "system-package")),
        all(target_os = "linux", feature = "flatpak")
    ))]
    let enabled = settings
        .get("autostart")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    #[cfg(all(feature = "desktop-integration", not(feature = "flatpak")))]
    {
        let current = app
            .autolaunch()
            .is_enabled()
            .map_err(|error| format!("Unable to inspect autostart state: {error}"))?;
        if !autostart_needs_update(current, enabled) {
            return Ok(current);
        }
        let result = if enabled {
            app.autolaunch().enable()
        } else {
            app.autolaunch().disable()
        };
        result
            .map(|_| enabled)
            .map_err(|error| format!("Unable to update autostart: {error}"))
    }
    #[cfg(all(target_os = "linux", feature = "flatpak"))]
    {
        flatpak_portal::request_autostart(enabled)
    }
    #[cfg(all(
        target_os = "linux",
        feature = "nix",
        not(feature = "desktop-integration"),
        not(feature = "flatpak")
    ))]
    {
        nix_autostart::set_enabled(enabled)
    }
    #[cfg(all(not(target_os = "linux"), feature = "flatpak"))]
    {
        let _ = app;
        let _ = settings;
        Err("Flatpak autostart is supported only on Linux".to_string())
    }
}

pub(crate) fn persist_app_settings(
    app: &AppHandle,
    state: &AppState,
    settings: &Value,
) -> Result<(), String> {
    if let Some(path) = app_settings_path(app) {
        if let Some(dir) = path.parent() {
            std::fs::create_dir_all(dir)
                .map_err(|error| format!("Unable to create settings directory: {error}"))?;
        }
        let text = serde_json::to_string_pretty(settings)
            .map_err(|error| format!("Unable to serialize app settings: {error}"))?;
        write_atomic(&path, &format!("{text}\n"))
            .map_err(|error| format!("Unable to persist app settings: {error}"))?;
    }
    *state.settings.lock().unwrap() = settings.clone();
    Ok(())
}

#[tauri::command]
pub(crate) fn get_app_settings(app: AppHandle) -> Value {
    effective_app_settings_value(&app)
}

#[tauri::command]
pub(crate) fn set_service_zoom(
    app: AppHandle,
    state: State<'_, AppState>,
    service_id: String,
    zoom_percent: u16,
) -> Result<Value, String> {
    if !valid_service_setting_id(&service_id) {
        return Err("Service id for page zoom is invalid".into());
    }
    if !(SERVICE_ZOOM_MIN_PERCENT..=SERVICE_ZOOM_MAX_PERCENT).contains(&zoom_percent) {
        return Err(format!(
            "Service page zoom must be between {SERVICE_ZOOM_MIN_PERCENT}% and {SERVICE_ZOOM_MAX_PERCENT}%"
        ));
    }

    let _settings_write = state.settings_write.lock().unwrap();
    let previous = read_app_settings_value(&app);
    let previous_percent = effective_service_zoom_percent(&previous, &service_id);
    let operation = (|| -> Result<Value, String> {
        let mut value = previous.clone();
        let levels = value
            .get_mut("serviceZoomLevels")
            .and_then(Value::as_object_mut)
            .ok_or_else(|| "Internal service page zoom settings are invalid".to_string())?;
        if zoom_percent == SERVICE_ZOOM_DEFAULT_PERCENT {
            levels.remove(&service_id);
        } else {
            levels.insert(service_id.clone(), Value::from(zoom_percent));
        }
        validate_app_settings_value(&value)?;

        let webview = app.get_webview(&format!("svc-{service_id}"));
        if let Some(webview) = &webview {
            webview
                .set_zoom(f64::from(zoom_percent) / 100.0)
                .map_err(|error| format!("Unable to apply service page zoom: {error}"))?;
        }
        if let Err(error) = persist_app_settings(&app, &state, &value) {
            if let Some(webview) = &webview {
                if let Err(rollback_error) = webview.set_zoom(f64::from(previous_percent) / 100.0) {
                    return Err(format!(
                        "{error}; additionally unable to restore the previous service page zoom: {rollback_error}"
                    ));
                }
            }
            return Err(error);
        }
        Ok(value)
    })();

    match operation {
        Ok(value) => {
            audit::best_effort(
                &app,
                "info",
                "settings",
                "service-zoom",
                "success",
                format!("Set service page zoom to {zoom_percent}%"),
                serde_json::json!({
                    "serviceId": service_id,
                    "before": previous_percent,
                    "after": zoom_percent
                }),
            );
            Ok(value)
        }
        Err(error) => {
            audit::best_effort(
                &app,
                "error",
                "settings",
                "service-zoom",
                "failure",
                error.clone(),
                serde_json::json!({ "serviceId": service_id, "zoomPercent": zoom_percent }),
            );
            Err(error)
        }
    }
}

fn persist_order_setting(
    app: &AppHandle,
    state: &AppState,
    key: &str,
    label: &str,
    ids: Vec<String>,
) -> Result<Value, String> {
    validate_order_ids(&ids, label)?;
    let _settings_write = state.settings_write.lock().unwrap();
    let count = ids.len();
    let mut settings = read_app_settings_value(app);
    let object = settings
        .as_object_mut()
        .ok_or_else(|| "Internal app settings state is invalid".to_string())?;
    object.insert(key.to_string(), serde_json::json!(ids));
    persist_app_settings(app, state, &settings)?;
    audit::best_effort(
        app,
        "info",
        "settings",
        "reorder",
        "success",
        format!("{label} order changed"),
        serde_json::json!({ "setting": key, "count": count }),
    );
    Ok(settings)
}

#[tauri::command]
pub(crate) fn set_service_order(
    app: AppHandle,
    state: State<'_, AppState>,
    service_ids: Vec<String>,
) -> Result<Value, String> {
    persist_order_setting(&app, &state, "serviceOrder", "Service", service_ids)
}

#[tauri::command]
pub(crate) fn set_workspace_order(
    app: AppHandle,
    state: State<'_, AppState>,
    workspace_ids: Vec<String>,
) -> Result<Value, String> {
    persist_order_setting(&app, &state, "workspaceOrder", "Workspace", workspace_ids)
}

#[tauri::command]
pub(crate) fn set_app_settings(
    app: AppHandle,
    state: State<'_, AppState>,
    patch: Value,
) -> Result<Value, String> {
    let patch = patch
        .as_object()
        .ok_or_else(|| "App settings patch must be a JSON object".to_string())?
        .clone();
    let chrome_preference = patch.get("unifiedTitleBar").and_then(Value::as_bool);
    if let Some(enabled) = chrome_preference {
        startup_diagnostics::log(
            "primary",
            "titlebar.preference.request",
            &format!("unified={enabled}"),
        );
    }
    let _settings_write = state.settings_write.lock().unwrap();
    let previous = read_app_settings_value(&app);
    let autostart_changed = patch.contains_key("autostart");
    let operation = (|| -> Result<Value, String> {
        let mut value = previous.clone();
        let base = value
            .as_object_mut()
            .ok_or_else(|| "Internal app settings state is invalid".to_string())?;
        for (key, setting) in &patch {
            base.insert(key.clone(), setting.clone());
        }
        validate_app_settings_value(&value)?;
        if autostart_changed {
            let actual = apply_autostart_setting(&app, &value)?;
            if let Some(object) = value.as_object_mut() {
                object.insert("autostart".into(), Value::Bool(actual));
            }
        }
        if let Err(error) = persist_app_settings(&app, &state, &value) {
            if autostart_changed {
                let _ = apply_autostart_setting(&app, &previous);
            }
            return Err(error);
        }
        if let Some(enabled) = chrome_preference {
            startup_diagnostics::log(
                "primary",
                "titlebar.preference.persisted",
                &format!("unified={enabled}"),
            );
        }
        Ok(value)
    })();

    match operation {
        Ok(value) => {
            download_toast::settings_changed(&app, &previous, &value);
            window_chrome::refresh(&app);
            let changes = patch
                .iter()
                .map(|(key, after)| {
                    (
                        key.clone(),
                        serde_json::json!({
                            "before": previous.get(key).cloned().unwrap_or(Value::Null),
                            "after": after
                        }),
                    )
                })
                .collect::<serde_json::Map<_, _>>();
            audit::best_effort(
                &app,
                "info",
                "settings",
                "change",
                "success",
                format!("Updated {} application setting(s)", patch.len()),
                serde_json::json!({ "changes": changes }),
            );
            Ok(value)
        }
        Err(error) => {
            audit::best_effort(
                &app,
                "error",
                "settings",
                "change",
                "failure",
                error.clone(),
                serde_json::json!({ "keys": patch.keys().collect::<Vec<_>>() }),
            );
            Err(error)
        }
    }
}

#[cfg(test)]
mod tests;
