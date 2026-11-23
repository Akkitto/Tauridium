//! Settings defaults, validation and backward-compatible merging.

use crate::services::SHORTCUT_ACTIONS;
use crate::{browser_privacy, download_notifications};
use serde_json::Value;
use std::collections::HashSet;

pub(super) const SERVICE_ZOOM_MIN_PERCENT: u16 = 50;
pub(crate) const SERVICE_ZOOM_DEFAULT_PERCENT: u16 = 100;
pub(super) const SERVICE_ZOOM_MAX_PERCENT: u16 = 200;

pub(super) fn valid_service_setting_id(service_id: &str) -> bool {
    !service_id.trim().is_empty()
        && service_id.len() <= 256
        && !service_id.chars().any(char::is_control)
}

pub(crate) fn effective_service_zoom_percent(settings: &Value, service_id: &str) -> u16 {
    settings
        .get("serviceZoomLevels")
        .and_then(Value::as_object)
        .and_then(|levels| levels.get(service_id))
        .and_then(Value::as_u64)
        .and_then(|percent| u16::try_from(percent).ok())
        .filter(|percent| (SERVICE_ZOOM_MIN_PERCENT..=SERVICE_ZOOM_MAX_PERCENT).contains(percent))
        .unwrap_or(SERVICE_ZOOM_DEFAULT_PERCENT)
}

fn validate_service_zoom_levels(value: Option<&Value>) -> Result<(), String> {
    let levels = value
        .and_then(Value::as_object)
        .ok_or_else(|| "App setting serviceZoomLevels must be an object".to_string())?;
    if levels.len() > 10_000
        || levels.iter().any(|(service_id, percent)| {
            !valid_service_setting_id(service_id)
                || !percent.as_u64().is_some_and(|percent| {
                    (u64::from(SERVICE_ZOOM_MIN_PERCENT)..=u64::from(SERVICE_ZOOM_MAX_PERCENT))
                        .contains(&percent)
                })
        })
    {
        return Err("App setting serviceZoomLevels is invalid".into());
    }
    Ok(())
}

pub(crate) fn default_app_settings_value() -> Value {
    // Keep the defaults as direct map inserts rather than one large `json!` invocation.
    // `json!` is recursive for every object entry and eventually exceeds rustc's default
    // macro recursion limit as settings are added. Direct construction scales without a
    // crate-wide recursion-limit override and keeps the serialized shape unchanged.
    let mut settings = serde_json::Map::<String, Value>::new();
    settings.insert("autostart".into(), false.into());
    settings.insert("startMinimized".into(), false.into());
    settings.insert("theme".into(), "system".into());
    settings.insert("accentColor".into(), "#ffc131".into());
    settings.insert("customAccentColors".into(), Value::Array(Vec::new()));
    settings.insert("closeToSystemTray".into(), true.into());
    settings.insert("privateNotifications".into(), false.into());
    settings.insert("showDisabledServices".into(), true.into());
    settings.insert("showServiceName".into(), true.into());
    settings.insert("showMessageBadgeWhenMuted".into(), true.into());
    settings.insert("showWorkspaceInWindowTitle".into(), true.into());
    settings.insert("showWorkspaceInTaskbarTitle".into(), false.into());
    settings.insert("customTitleTemplatesEnabled".into(), false.into());
    settings.insert("unifiedTitleBar".into(), true.into());
    settings.insert("windowTitleTemplate".into(), "{app} ~ {workspace}".into());
    settings.insert("taskbarTitleTemplate".into(), "{app} ~ {workspace}".into());
    settings.insert("userAgentPref".into(), "".into());
    settings.insert("sidebarWidth".into(), 240.into());
    settings.insert("sidebarWidthMode".into(), "pixels".into());
    settings.insert("sidebarWidthPercent".into(), 20.into());
    settings.insert("sidebarCollapsed".into(), false.into());
    settings.insert("defaultSidebarCollapsed".into(), false.into());
    settings.insert("restoreLastSidebarStateOnStartup".into(), true.into());
    settings.insert("customSidebarWidths".into(), Value::Array(Vec::new()));
    settings.insert("collapsedServiceSpacing".into(), 2.into());
    settings.insert("expandedServiceSpacing".into(), 2.into());
    settings.insert("iconSize".into(), 24.into());
    settings.insert("grayscaleServices".into(), false.into());
    settings.insert("grayscaleDim".into(), 50.into());
    settings.insert("sidebarServicesLocation".into(), "top".into());
    settings.insert("hibernationTimer".into(), 0.into());
    settings.insert("preloadServices".into(), true.into());
    settings.insert("fetchMissingServiceIcons".into(), true.into());
    settings.insert("reloadToasts".into(), true.into());
    settings.insert("prettyServiceContextMenu".into(), true.into());
    settings.insert("sidebarServiceDragReorder".into(), true.into());
    settings.insert("captureServiceShortcuts".into(), true.into());
    settings.insert(
        "serviceShortcutCaptureOverrides".into(),
        Value::Object(serde_json::Map::new()),
    );
    settings.insert("customUrlTemplatesEnabled".into(), false.into());
    settings.insert(
        "serviceCustomUrlTemplates".into(),
        Value::Object(serde_json::Map::new()),
    );
    settings.insert(
        "serviceIconInversions".into(),
        Value::Object(serde_json::Map::new()),
    );
    settings.insert(
        "serviceZoomLevels".into(),
        Value::Object(serde_json::Map::new()),
    );
    settings.insert("serviceOrder".into(), Value::Array(Vec::new()));
    settings.insert("workspaceOrder".into(), Value::Array(Vec::new()));
    settings.insert("workspaceQuickSwitchOrder".into(), "custom".into());
    settings.insert("defaultWorkspaceId".into(), "".into());
    settings.insert("restoreLastWorkspaceOnStartup".into(), false.into());
    settings.insert("lastWorkspaceId".into(), "".into());
    settings.insert(
        "workspaceLastUsed".into(),
        Value::Object(serde_json::Map::new()),
    );
    settings.insert(
        "workspaceIcons".into(),
        Value::Object(serde_json::Map::new()),
    );
    settings.insert("downloadDirectory".into(), "".into());
    settings.insert("askEachDownload".into(), false.into());
    settings.insert("downloadToasts".into(), false.into());
    settings.insert("downloadToastLocation".into(), "none".into());
    settings.insert("downloadToastParentLevels".into(), 2.into());
    settings.insert("downloadToastDuration".into(), 8.into());
    settings.insert(
        "serviceDownloadSettings".into(),
        Value::Object(serde_json::Map::new()),
    );
    settings.insert(
        "workspaceDownloadSettings".into(),
        Value::Object(serde_json::Map::new()),
    );
    let mut keybindings = serde_json::Map::<String, Value>::new();
    keybindings.insert("quickWorkspaceSwitch".into(), "Ctrl+D".into());
    keybindings.insert("quickServiceSwitch".into(), "Ctrl+S".into());
    keybindings.insert("openSettings".into(), "Ctrl+,".into());
    keybindings.insert("addService".into(), "Ctrl+N".into());
    keybindings.insert("addWorkspace".into(), "Ctrl+Shift+N".into());
    keybindings.insert("toggleSidebar".into(), "Ctrl+Shift+B".into());
    keybindings.insert("nextService".into(), "Ctrl+Tab".into());
    keybindings.insert("previousService".into(), "Ctrl+Shift+Tab".into());
    keybindings.insert("nextWorkspace".into(), "Ctrl+Alt+ArrowDown".into());
    keybindings.insert("previousWorkspace".into(), "Ctrl+Alt+ArrowUp".into());
    keybindings.insert("reloadService".into(), "Ctrl+R".into());
    keybindings.insert("reloadApp".into(), "Ctrl+Shift+R".into());
    keybindings.insert("zoomIn".into(), "Ctrl+Shift+=".into());
    keybindings.insert("zoomOut".into(), "Ctrl+-".into());
    keybindings.insert("resetZoom".into(), "Ctrl+0".into());
    keybindings.insert("toggleDevtools".into(), "Ctrl+Alt+I".into());
    settings.insert("keybindings".into(), Value::Object(keybindings));
    settings.insert("sandboxes".into(), Value::Array(Vec::new()));
    settings.insert(
        "trackingPreventionExceptions".into(),
        Value::Object(serde_json::Map::new()),
    );
    settings.insert(
        "serviceSandboxes".into(),
        Value::Object(serde_json::Map::new()),
    );
    settings.insert("automaticBackupSchedule".into(), "off".into());
    settings.insert("automaticBackupDirectory".into(), "".into());
    settings.insert("automaticBackupRetentionMode".into(), "count".into());
    settings.insert("automaticBackupRetention".into(), 10.into());
    settings.insert("automaticBackupMaxAgeDays".into(), 90.into());
    settings.insert("lastAutomaticBackupAt".into(), 0.into());
    Value::Object(settings)
}

fn is_hex_color(value: &str) -> bool {
    value.len() == 7
        && value.starts_with('#')
        && value.as_bytes()[1..]
            .iter()
            .all(|byte| byte.is_ascii_hexdigit())
}

fn validate_keybindings(value: Option<&Value>) -> Result<(), String> {
    let bindings = value
        .and_then(Value::as_object)
        .ok_or_else(|| "App setting keybindings must be an object".to_string())?;
    for action in SHORTCUT_ACTIONS {
        let binding = bindings
            .get(action)
            .and_then(Value::as_str)
            .ok_or_else(|| format!("App keybinding {action} must be a string"))?
            .trim();
        if binding.len() > 80 {
            return Err(format!("App keybinding {action} is too long"));
        }
        if !binding.is_empty() && binding.split_whitespace().count() > 2 {
            return Err(format!("App keybinding {action} has more than two strokes"));
        }
    }
    Ok(())
}

fn validate_sandboxes(
    sandboxes: Option<&Value>,
    assignments: Option<&Value>,
) -> Result<(), String> {
    let sandboxes = sandboxes
        .and_then(Value::as_array)
        .ok_or_else(|| "App setting sandboxes must be an array".to_string())?;
    if sandboxes.len() > 256 {
        return Err("App setting sandboxes contains too many entries".into());
    }
    let mut ids = HashSet::with_capacity(sandboxes.len());
    for sandbox in sandboxes {
        let object = sandbox
            .as_object()
            .ok_or_else(|| "Sandbox entries must be objects".to_string())?;
        let id = object
            .get("id")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|id| !id.is_empty() && id.len() <= 80)
            .ok_or_else(|| "Sandbox id is invalid".to_string())?;
        if !id
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
        {
            return Err(format!("Sandbox id contains unsupported characters: {id}"));
        }
        if !ids.insert(id.to_string()) {
            return Err(format!("Duplicate sandbox id: {id}"));
        }
        let name = object
            .get("name")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|name| !name.is_empty() && name.chars().count() <= 80)
            .ok_or_else(|| format!("Sandbox {id} has an invalid name"))?;
        if name.chars().any(char::is_control) {
            return Err(format!("Sandbox {id} name contains control characters"));
        }
    }

    let assignments = assignments
        .and_then(Value::as_object)
        .ok_or_else(|| "App setting serviceSandboxes must be an object".to_string())?;
    if assignments.len() > 10_000 {
        return Err("App setting serviceSandboxes contains too many entries".into());
    }
    for (service_id, sandbox_id) in assignments {
        if service_id.trim().is_empty() {
            return Err("App setting serviceSandboxes contains an empty service id".into());
        }
        let sandbox_id = sandbox_id
            .as_str()
            .ok_or_else(|| "App setting serviceSandboxes values must be strings".to_string())?;
        if !ids.contains(sandbox_id) {
            return Err(format!(
                "Service {service_id} references unknown sandbox: {sandbox_id}"
            ));
        }
    }
    Ok(())
}

fn validate_download_settings_map(value: Option<&Value>, label: &str) -> Result<(), String> {
    let map = value
        .and_then(Value::as_object)
        .ok_or_else(|| format!("App setting {label} must be an object"))?;
    if map.len() > 10_000 {
        return Err(format!("App setting {label} contains too many entries"));
    }
    for (id, preferences) in map {
        if id.trim().is_empty() || id.len() > 256 {
            return Err(format!("App setting {label} contains an invalid id"));
        }
        let preferences = preferences
            .as_object()
            .ok_or_else(|| format!("App setting {label} values must be objects"))?;
        let directory = preferences
            .get("directory")
            .and_then(Value::as_str)
            .ok_or_else(|| format!("App setting {label} directory must be a string"))?;
        if directory.len() > 4096 || directory.chars().any(char::is_control) {
            return Err(format!("App setting {label} directory is invalid"));
        }
        if !preferences
            .get("askEachDownload")
            .is_some_and(Value::is_boolean)
        {
            return Err(format!(
                "App setting {label} askEachDownload must be boolean"
            ));
        }
    }
    Ok(())
}

pub(crate) fn validate_app_settings_value(settings: &Value) -> Result<(), String> {
    download_notifications::validate_settings(settings)?;
    let object = settings
        .as_object()
        .ok_or_else(|| "App settings must be a JSON object".to_string())?;
    for key in [
        "autostart",
        "startMinimized",
        "closeToSystemTray",
        "privateNotifications",
        "showDisabledServices",
        "showServiceName",
        "showMessageBadgeWhenMuted",
        "showWorkspaceInWindowTitle",
        "showWorkspaceInTaskbarTitle",
        "customTitleTemplatesEnabled",
        "unifiedTitleBar",
        "grayscaleServices",
        "preloadServices",
        "fetchMissingServiceIcons",
        "reloadToasts",
        "prettyServiceContextMenu",
        "askEachDownload",
        "sidebarServiceDragReorder",
        "captureServiceShortcuts",
        "customUrlTemplatesEnabled",
        "restoreLastWorkspaceOnStartup",
        "sidebarCollapsed",
        "defaultSidebarCollapsed",
        "restoreLastSidebarStateOnStartup",
    ] {
        if !object.get(key).is_some_and(Value::is_boolean) {
            return Err(format!("App setting {key} must be boolean"));
        }
    }
    for key in ["windowTitleTemplate", "taskbarTitleTemplate"] {
        let template = object
            .get(key)
            .and_then(Value::as_str)
            .ok_or_else(|| format!("App setting {key} must be a string"))?;
        if template.chars().count() > 240 || template.chars().any(char::is_control) {
            return Err(format!("App setting {key} is invalid"));
        }
    }
    let theme = object
        .get("theme")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !matches!(theme, "system" | "dark" | "oled" | "light") {
        return Err("App setting theme is invalid".into());
    }
    let location = object
        .get("sidebarServicesLocation")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !matches!(location, "top" | "center" | "bottom") {
        return Err("App setting sidebarServicesLocation is invalid".into());
    }
    let sidebar_width_mode = object
        .get("sidebarWidthMode")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !matches!(sidebar_width_mode, "pixels" | "percent") {
        return Err("App setting sidebarWidthMode is invalid".into());
    }
    let workspace_quick_switch_order = object
        .get("workspaceQuickSwitchOrder")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !matches!(
        workspace_quick_switch_order,
        "custom"
            | "customReverse"
            | "alphabetical"
            | "alphabeticalReverse"
            | "recent"
            | "recentReverse"
    ) {
        return Err("App setting workspaceQuickSwitchOrder is invalid".into());
    }
    for key in ["defaultWorkspaceId", "lastWorkspaceId"] {
        let workspace_id = object
            .get(key)
            .and_then(Value::as_str)
            .ok_or_else(|| format!("App setting {key} must be a string"))?;
        if workspace_id.len() > 256
            || workspace_id.chars().any(char::is_control)
            || (!workspace_id.is_empty() && workspace_id.trim().is_empty())
        {
            return Err(format!("App setting {key} is invalid"));
        }
    }
    let workspace_last_used = object
        .get("workspaceLastUsed")
        .and_then(Value::as_object)
        .ok_or_else(|| "App setting workspaceLastUsed must be an object".to_string())?;
    if workspace_last_used.len() > 10_000 {
        return Err("App setting workspaceLastUsed contains too many entries".into());
    }
    for (workspace_id, timestamp) in workspace_last_used {
        if workspace_id.trim().is_empty()
            || !timestamp
                .as_f64()
                .is_some_and(|number| number.is_finite() && number >= 0.0)
        {
            return Err("App setting workspaceLastUsed is invalid".into());
        }
    }
    let workspace_icons = object
        .get("workspaceIcons")
        .and_then(Value::as_object)
        .ok_or_else(|| "App setting workspaceIcons must be an object".to_string())?;
    if workspace_icons.len() > 10_000 {
        return Err("App setting workspaceIcons contains too many entries".into());
    }
    let mut workspace_icon_bytes = 0usize;
    for (workspace_id, icon) in workspace_icons {
        let icon = icon
            .as_str()
            .ok_or_else(|| "App setting workspaceIcons values must be strings".to_string())?;
        workspace_icon_bytes = workspace_icon_bytes.saturating_add(icon.len());
        let supported = icon.starts_with("https://")
            || icon.starts_with("http://")
            || icon.starts_with("data:image/");
        if workspace_id.trim().is_empty()
            || workspace_id.len() > 256
            || icon.is_empty()
            || icon.len() > 768 * 1024
            || !supported
        {
            return Err("App setting workspaceIcons is invalid".into());
        }
    }
    if workspace_icon_bytes > 16 * 1024 * 1024 {
        return Err("App setting workspaceIcons exceeds the supported total size".into());
    }
    let download_directory = object
        .get("downloadDirectory")
        .and_then(Value::as_str)
        .ok_or_else(|| "App setting downloadDirectory must be a string".to_string())?;
    if download_directory.len() > 4096 || download_directory.chars().any(char::is_control) {
        return Err("App setting downloadDirectory is invalid".into());
    }
    validate_download_settings_map(
        object.get("serviceDownloadSettings"),
        "serviceDownloadSettings",
    )?;
    validate_download_settings_map(
        object.get("workspaceDownloadSettings"),
        "workspaceDownloadSettings",
    )?;
    let backup_schedule = object
        .get("automaticBackupSchedule")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !matches!(
        backup_schedule,
        "off" | "startup" | "daily" | "weekly" | "monthly"
    ) {
        return Err("App setting automaticBackupSchedule is invalid".into());
    }
    let backup_retention_mode = object
        .get("automaticBackupRetentionMode")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !matches!(
        backup_retention_mode,
        "count" | "age" | "countAndAge" | "tiered"
    ) {
        return Err("App setting automaticBackupRetentionMode is invalid".into());
    }
    let backup_directory = object
        .get("automaticBackupDirectory")
        .and_then(Value::as_str)
        .ok_or_else(|| "App setting automaticBackupDirectory must be a string".to_string())?;
    if backup_directory.len() > 4096 || backup_directory.chars().any(char::is_control) {
        return Err("App setting automaticBackupDirectory is invalid".into());
    }
    if !object.get("accentColor").is_some_and(Value::is_string)
        || !object.get("userAgentPref").is_some_and(Value::is_string)
    {
        return Err("App string settings are invalid".into());
    }
    let accent_color = object
        .get("accentColor")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !is_hex_color(accent_color) {
        return Err("App setting accentColor must be a #RRGGBB color".into());
    }
    let custom_colors = object
        .get("customAccentColors")
        .and_then(Value::as_array)
        .ok_or_else(|| "App setting customAccentColors must be an array".to_string())?;
    if custom_colors.len() > 32
        || custom_colors
            .iter()
            .any(|color| !color.as_str().is_some_and(is_hex_color))
    {
        return Err("App setting customAccentColors is invalid".into());
    }
    for (key, min, max) in [
        ("sidebarWidth", 160.0, 420.0),
        ("sidebarWidthPercent", 10.0, 40.0),
        ("collapsedServiceSpacing", 2.0, 24.0),
        ("expandedServiceSpacing", 2.0, 24.0),
        ("iconSize", 12.0, 64.0),
        ("grayscaleDim", 0.0, 100.0),
        ("hibernationTimer", 0.0, 86_400.0),
    ] {
        let number = object
            .get(key)
            .and_then(Value::as_f64)
            .ok_or_else(|| format!("App setting {key} must be numeric"))?;
        if !(min..=max).contains(&number) {
            return Err(format!("App setting {key} is outside its supported range"));
        }
    }
    let custom_widths = object
        .get("customSidebarWidths")
        .and_then(Value::as_array)
        .ok_or_else(|| "App setting customSidebarWidths must be an array".to_string())?;
    if custom_widths.len() > 16
        || custom_widths.iter().any(|width| {
            !width
                .as_f64()
                .is_some_and(|number| (160.0..=420.0).contains(&number))
        })
    {
        return Err("App setting customSidebarWidths is invalid".into());
    }
    let shortcut_overrides = object
        .get("serviceShortcutCaptureOverrides")
        .and_then(Value::as_object)
        .ok_or_else(|| {
            "App setting serviceShortcutCaptureOverrides must be an object".to_string()
        })?;
    if shortcut_overrides.len() > 10_000
        || shortcut_overrides.iter().any(|(service_id, capture)| {
            service_id.trim().is_empty()
                || service_id.len() > 256
                || service_id.chars().any(char::is_control)
                || !capture.is_boolean()
        })
    {
        return Err("App setting serviceShortcutCaptureOverrides is invalid".into());
    }

    let service_templates = object
        .get("serviceCustomUrlTemplates")
        .and_then(Value::as_object)
        .ok_or_else(|| "App setting serviceCustomUrlTemplates must be an object".to_string())?;
    if service_templates.len() > 10_000 {
        return Err("App setting serviceCustomUrlTemplates contains too many entries".into());
    }
    for (service_id, entry) in service_templates {
        if service_id.trim().is_empty() {
            return Err(
                "App setting serviceCustomUrlTemplates contains an empty service id".into(),
            );
        }
        let entry = entry.as_object().ok_or_else(|| {
            format!("Custom URL template settings for {service_id} must be an object")
        })?;
        if !entry.get("enabled").is_some_and(Value::is_boolean) {
            return Err(format!(
                "Custom URL template enabled flag for {service_id} must be boolean"
            ));
        }
        for key in ["customId1", "customId2"] {
            let value = entry.get(key).and_then(Value::as_str).ok_or_else(|| {
                format!("Custom URL template {key} for {service_id} must be a string")
            })?;
            if value.len() > 2048 || value.chars().any(char::is_control) {
                return Err(format!(
                    "Custom URL template {key} for {service_id} is invalid"
                ));
            }
        }
    }
    let icon_inversions = object
        .get("serviceIconInversions")
        .and_then(Value::as_object)
        .ok_or_else(|| "App setting serviceIconInversions must be an object".to_string())?;
    if icon_inversions.len() > 10_000
        || icon_inversions.iter().any(|(service_id, inverted)| {
            service_id.trim().is_empty()
                || service_id.len() > 256
                || service_id.chars().any(char::is_control)
                || !inverted.is_boolean()
        })
    {
        return Err("App setting serviceIconInversions is invalid".into());
    }
    validate_service_zoom_levels(object.get("serviceZoomLevels"))?;
    browser_privacy::validate(object.get("trackingPreventionExceptions"))?;
    validate_keybindings(object.get("keybindings"))?;
    validate_sandboxes(object.get("sandboxes"), object.get("serviceSandboxes"))?;
    let backup_retention = object
        .get("automaticBackupRetention")
        .and_then(Value::as_u64)
        .ok_or_else(|| "App setting automaticBackupRetention must be an integer".to_string())?;
    if !(1..=365).contains(&backup_retention) {
        return Err("App setting automaticBackupRetention is outside its supported range".into());
    }
    let backup_max_age = object
        .get("automaticBackupMaxAgeDays")
        .and_then(Value::as_u64)
        .ok_or_else(|| "App setting automaticBackupMaxAgeDays must be an integer".to_string())?;
    if !(1..=3650).contains(&backup_max_age) {
        return Err("App setting automaticBackupMaxAgeDays is outside its supported range".into());
    }
    if !object
        .get("lastAutomaticBackupAt")
        .is_some_and(|value| value.as_f64().is_some_and(|number| number >= 0.0))
    {
        return Err("App setting lastAutomaticBackupAt must be a non-negative number".into());
    }
    for (key, label) in [("serviceOrder", "Service"), ("workspaceOrder", "Workspace")] {
        let values = object
            .get(key)
            .and_then(Value::as_array)
            .ok_or_else(|| format!("App setting {key} must be an array"))?;
        let ids = values
            .iter()
            .map(|value| {
                value
                    .as_str()
                    .map(str::to_string)
                    .ok_or_else(|| format!("App setting {key} contains a non-string id"))
            })
            .collect::<Result<Vec<_>, _>>()?;
        validate_order_ids(&ids, label)?;
    }
    Ok(())
}

pub(crate) fn resolve_startup_sidebar_collapsed(settings: &Value) -> bool {
    let default_collapsed = settings
        .get("defaultSidebarCollapsed")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let restore_last = settings
        .get("restoreLastSidebarStateOnStartup")
        .and_then(Value::as_bool)
        .unwrap_or(true);
    let last_collapsed = settings
        .get("sidebarCollapsed")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    if restore_last {
        last_collapsed
    } else {
        default_collapsed
    }
}

pub(crate) fn merge_app_settings_value(stored: &Value) -> Result<Value, String> {
    let stored = stored
        .as_object()
        .ok_or_else(|| "App settings must be a JSON object".to_string())?;
    let mut value = default_app_settings_value();
    let base = value
        .as_object_mut()
        .ok_or_else(|| "Internal app settings defaults are invalid".to_string())?;
    for (key, setting) in stored {
        if key == "keybindings" {
            let stored_bindings = setting
                .as_object()
                .ok_or_else(|| "App setting keybindings must be an object".to_string())?;
            let default_bindings = base
                .get_mut("keybindings")
                .and_then(Value::as_object_mut)
                .ok_or_else(|| "Internal app keybinding defaults are invalid".to_string())?;
            for (action, binding) in stored_bindings {
                default_bindings.insert(action.clone(), binding.clone());
            }
        } else if key != "reuseExistingSessionOnLaunch" {
            // 0.7.8 made single-instance reuse mandatory on Windows. Ignore the
            // retired opt-out when reading older app_settings.json files.
            base.insert(key.clone(), setting.clone());
        }
    }
    validate_app_settings_value(&value)?;
    Ok(value)
}

pub(crate) fn validate_order_ids(ids: &[String], label: &str) -> Result<(), String> {
    if ids.len() > 10_000 {
        return Err(format!("Too many {label} ids in order state"));
    }
    let mut seen = HashSet::with_capacity(ids.len());
    for id in ids {
        let id = id.trim();
        if id.is_empty() {
            return Err(format!("{label} order contains an empty id"));
        }
        if !seen.insert(id) {
            return Err(format!("{label} order contains duplicate id: {id}"));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests;
