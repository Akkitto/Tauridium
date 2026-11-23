use super::*;
use crate::{backup, local_profile::LocalProfile, validate_native_title};
use serde_json::json;

#[test]
fn unified_title_bar_defaults_migrate_and_preserve_the_classic_opt_out() {
    let migrated = merge_app_settings_value(&serde_json::json!({ "theme": "oled" })).unwrap();
    assert_eq!(migrated["unifiedTitleBar"], true);
    assert_eq!(migrated["theme"], "oled");
    let classic =
        merge_app_settings_value(&serde_json::json!({ "unifiedTitleBar": false })).unwrap();
    assert_eq!(classic["unifiedTitleBar"], false);
    for invalid in [
        serde_json::json!("false"),
        serde_json::json!(0),
        serde_json::Value::Null,
    ] {
        assert!(
            merge_app_settings_value(&serde_json::json!({ "unifiedTitleBar": invalid })).is_err()
        );
    }
}
#[test]
fn patch_0901_download_toast_defaults_migrate_without_enabling_notifications() {
    let defaults = default_app_settings_value();
    assert_eq!(defaults["downloadToasts"], false);
    assert_eq!(defaults["downloadToastLocation"], "none");
    assert_eq!(defaults["downloadToastParentLevels"], 2);
    assert_eq!(defaults["downloadToastDuration"], 8);
    let migrated =
        merge_app_settings_value(&json!({"downloadDirectory": "/old/downloads", "theme": "light"}))
            .unwrap();
    assert_eq!(migrated["downloadToasts"], false);
    assert_eq!(migrated["downloadDirectory"], "/old/downloads");
    assert_eq!(migrated["theme"], "light");
}
#[test]
fn patch_0901_download_toast_settings_survive_serialization_and_backup() {
    let mut settings = default_app_settings_value();
    settings["downloadToasts"] = true.into();
    settings["downloadToastLocation"] = "partial".into();
    settings["downloadToastParentLevels"] = 3.into();
    settings["downloadToastDuration"] = 0.into();
    let stored = serde_json::from_str(&serde_json::to_string(&settings).unwrap()).unwrap();
    assert_eq!(merge_app_settings_value(&stored).unwrap(), settings);
    let backup = backup::BackupDocument::new(
        env!("CARGO_PKG_VERSION"),
        settings.clone(),
        serde_json::to_value(LocalProfile::default()).unwrap(),
        Vec::new(),
    );
    assert_eq!(
        merge_app_settings_value(&backup.app_settings()).unwrap(),
        settings
    );
}
#[test]
fn patch_0504_hibernation_remains_disabled_by_default() {
    let defaults = default_app_settings_value();
    assert_eq!(defaults["hibernationTimer"], json!(0));
    assert_eq!(defaults["preloadServices"], json!(true));
}
#[test]
fn automatic_backup_settings_accept_only_supported_schedule_and_retention() {
    let mut settings = default_app_settings_value();
    assert!(validate_app_settings_value(&settings).is_ok());
    settings["automaticBackupSchedule"] = json!("hourly");
    assert!(validate_app_settings_value(&settings).is_err());
    settings["automaticBackupSchedule"] = json!("daily");
    settings["automaticBackupRetention"] = json!(0);
    assert!(validate_app_settings_value(&settings).is_err());
    settings["automaticBackupRetention"] = json!(365);
    assert!(validate_app_settings_value(&settings).is_ok());
}
#[test]
fn feature_0413_settings_validate_workspace_quick_switch_order_and_recency() {
    let mut settings = default_app_settings_value();
    settings["workspaceQuickSwitchOrder"] = json!("recent");
    settings["workspaceLastUsed"] = json!({"workspace-a": 1_766_000_000_000_f64});
    assert!(validate_app_settings_value(&settings).is_ok());

    settings["workspaceQuickSwitchOrder"] = json!("unsupported");
    assert!(validate_app_settings_value(&settings).is_err());
    settings["workspaceQuickSwitchOrder"] = json!("custom");
    settings["workspaceLastUsed"] = json!({"": 1});
    assert!(validate_app_settings_value(&settings).is_err());
    settings["workspaceLastUsed"] = json!({"workspace-a": -1});
    assert!(validate_app_settings_value(&settings).is_err());
}
#[test]
fn feature_0503_settings_validate_workspace_startup_preferences() {
    let mut settings = default_app_settings_value();
    assert_eq!(settings["defaultWorkspaceId"], json!(""));
    assert_eq!(settings["restoreLastWorkspaceOnStartup"], json!(false));
    assert_eq!(settings["lastWorkspaceId"], json!(""));

    settings["defaultWorkspaceId"] = json!("workspace-a");
    settings["restoreLastWorkspaceOnStartup"] = json!(true);
    settings["lastWorkspaceId"] = json!("workspace-b");
    assert!(validate_app_settings_value(&settings).is_ok());

    settings["restoreLastWorkspaceOnStartup"] = json!("yes");
    assert!(validate_app_settings_value(&settings).is_err());
    settings["restoreLastWorkspaceOnStartup"] = json!(true);
    settings["lastWorkspaceId"] = json!("   ");
    assert!(validate_app_settings_value(&settings).is_err());
}
#[test]
fn feature_0424_settings_validate_workspace_icons() {
    let mut settings = default_app_settings_value();
    settings["workspaceIcons"] = json!({
        "workspace-a": "https://example.com/icon.svg",
        "workspace-b": "data:image/svg+xml;base64,PHN2Zy8+"
    });
    assert!(validate_app_settings_value(&settings).is_ok());

    settings["workspaceIcons"] = json!({ "workspace-a": "javascript:alert(1)" });
    assert!(validate_app_settings_value(&settings).is_err());
    settings["workspaceIcons"] = json!({ "": "https://example.com/icon.svg" });
    assert!(validate_app_settings_value(&settings).is_err());
}
#[test]
fn feature_0428_settings_validate_service_icon_inversions() {
    let mut settings = default_app_settings_value();
    settings["serviceIconInversions"] = json!({
        "service-a": true,
        "service-b": false
    });
    assert!(validate_app_settings_value(&settings).is_ok());

    settings["serviceIconInversions"] = json!({ "": true });
    assert!(validate_app_settings_value(&settings).is_err());
    settings["serviceIconInversions"] = json!({ "service-a": "yes" });
    assert!(validate_app_settings_value(&settings).is_err());
}
#[test]
fn feature_0404_settings_validate_backup_retention_and_relative_sidebar_width() {
    let mut settings = default_app_settings_value();
    settings["sidebarWidthMode"] = json!("percent");
    settings["sidebarWidthPercent"] = json!(28);
    settings["automaticBackupDirectory"] = json!(r"C:\Backups\Tauridium");
    settings["automaticBackupRetentionMode"] = json!("tiered");
    settings["automaticBackupMaxAgeDays"] = json!(3650);
    assert!(validate_app_settings_value(&settings).is_ok());

    settings["sidebarWidthPercent"] = json!(50);
    assert!(validate_app_settings_value(&settings).is_err());
    settings["sidebarWidthPercent"] = json!(20);
    settings["automaticBackupRetentionMode"] = json!("unknown");
    assert!(validate_app_settings_value(&settings).is_err());
    settings["automaticBackupRetentionMode"] = json!("age");
    settings["automaticBackupMaxAgeDays"] = json!(0);
    assert!(validate_app_settings_value(&settings).is_err());
}
#[test]
fn app_settings_merge_preserves_existing_keybindings_and_adds_new_defaults() {
    let merged = merge_app_settings_value(&json!({
        "keybindings": {
            "addService": "Alt+N",
            "quickWorkspaceSwitch": "Ctrl+K Ctrl+W"
        }
    }))
    .unwrap();

    assert_eq!(merged["keybindings"]["addService"], json!("Alt+N"));
    assert_eq!(
        merged["keybindings"]["quickWorkspaceSwitch"],
        json!("Ctrl+K Ctrl+W")
    );
    assert_eq!(merged["keybindings"]["addWorkspace"], json!("Ctrl+Shift+N"));
    assert_eq!(
        merged["keybindings"]["toggleSidebar"],
        json!("Ctrl+Shift+B")
    );
    assert_eq!(merged["sidebarCollapsed"], json!(false));
    assert!(validate_app_settings_value(&merged).is_ok());
}
#[test]
fn patch_0805_service_zoom_defaults_persist_and_validate_safely() {
    let defaults = merge_app_settings_value(&json!({})).unwrap();
    assert_eq!(defaults["serviceZoomLevels"], json!({}));
    assert_eq!(
        effective_service_zoom_percent(&defaults, "service-a"),
        SERVICE_ZOOM_DEFAULT_PERCENT
    );

    let mut settings = defaults.clone();
    settings["serviceZoomLevels"] = json!({
        "service-a": 50,
        "service-b": 125,
        "service-c": 200
    });
    assert!(validate_app_settings_value(&settings).is_ok());
    assert_eq!(effective_service_zoom_percent(&settings, "service-b"), 125);

    for invalid in [
        json!({ "service-a": 49 }),
        json!({ "service-a": 201 }),
        json!({ "service-a": 110.5 }),
        json!({ "service-a": "125" }),
        json!({ "": 125 }),
    ] {
        settings["serviceZoomLevels"] = invalid;
        assert!(validate_app_settings_value(&settings).is_err());
    }

    assert!(!valid_service_setting_id(""));
    assert!(!valid_service_setting_id("\n"));
    assert!(valid_service_setting_id("service-a"));
}
#[test]
fn patch_0605_title_settings_default_and_validate_safely() {
    let defaults = merge_app_settings_value(&json!({})).unwrap();
    assert_eq!(defaults["showWorkspaceInWindowTitle"], json!(true));
    assert_eq!(defaults["showWorkspaceInTaskbarTitle"], json!(false));
    assert_eq!(defaults["customTitleTemplatesEnabled"], json!(false));
    assert_eq!(
        defaults["windowTitleTemplate"],
        json!("{app} ~ {workspace}")
    );
    assert_eq!(
        defaults["taskbarTitleTemplate"],
        json!("{app} ~ {workspace}")
    );
    assert!(validate_app_settings_value(&defaults).is_ok());
    assert!(validate_native_title("Tauridium ~ Engineering", "Window title").is_ok());
    assert!(validate_native_title("", "Window title").is_err());

    let mut invalid = defaults.clone();
    invalid["windowTitleTemplate"] = json!("x".repeat(241));
    assert!(validate_app_settings_value(&invalid).is_err());
    invalid = defaults;
    invalid["taskbarTitleTemplate"] = json!("bad\nvalue");
    assert!(validate_app_settings_value(&invalid).is_err());
}
#[test]
fn patch_0602_sidebar_spacing_defaults_and_bounds_are_safe() {
    let defaults = merge_app_settings_value(&json!({})).unwrap();
    assert_eq!(defaults["collapsedServiceSpacing"], json!(2));
    assert_eq!(defaults["expandedServiceSpacing"], json!(2));

    let mut settings = defaults.clone();
    settings["collapsedServiceSpacing"] = json!(24);
    settings["expandedServiceSpacing"] = json!(24);
    assert!(validate_app_settings_value(&settings).is_ok());

    settings["collapsedServiceSpacing"] = json!(1);
    assert!(validate_app_settings_value(&settings).is_err());
    settings["collapsedServiceSpacing"] = json!(2);
    settings["expandedServiceSpacing"] = json!(25);
    assert!(validate_app_settings_value(&settings).is_err());
}
#[test]
fn patch_0601_sidebar_startup_preferences_default_and_restore_last() {
    let defaults = merge_app_settings_value(&json!({})).unwrap();
    assert_eq!(defaults["defaultSidebarCollapsed"], json!(false));
    assert_eq!(defaults["restoreLastSidebarStateOnStartup"], json!(true));
    assert!(!resolve_startup_sidebar_collapsed(&defaults));

    let restore_last = merge_app_settings_value(&json!({
        "defaultSidebarCollapsed": false,
        "restoreLastSidebarStateOnStartup": true,
        "sidebarCollapsed": true
    }))
    .unwrap();
    assert!(resolve_startup_sidebar_collapsed(&restore_last));

    let use_default = merge_app_settings_value(&json!({
        "defaultSidebarCollapsed": true,
        "restoreLastSidebarStateOnStartup": false,
        "sidebarCollapsed": false
    }))
    .unwrap();
    assert!(resolve_startup_sidebar_collapsed(&use_default));
}
#[test]
fn sidebar_service_drag_reorder_defaults_on_and_preserves_saved_opt_out() {
    let defaults = merge_app_settings_value(&json!({})).unwrap();
    assert_eq!(defaults["sidebarServiceDragReorder"], json!(true));

    let opted_out = merge_app_settings_value(&json!({
        "sidebarServiceDragReorder": false
    }))
    .unwrap();
    assert_eq!(opted_out["sidebarServiceDragReorder"], json!(false));
    assert!(validate_app_settings_value(&opted_out).is_ok());

    let mut invalid = default_app_settings_value();
    invalid["sidebarServiceDragReorder"] = json!("yes");
    assert!(validate_app_settings_value(&invalid).is_err());
}
#[test]
fn feature_0400_settings_validate_oled_colors_keybindings_and_sandboxes() {
    let mut settings = default_app_settings_value();
    settings["theme"] = json!("oled");
    settings["accentColor"] = json!("#123abc");
    settings["customAccentColors"] = json!(["#000000", "#ffffff"]);
    settings["customSidebarWidths"] = json!([180, 276, 320]);
    settings["keybindings"]["quickServiceSwitch"] = json!("Ctrl+K Ctrl+S");
    settings["sandboxes"] = json!([{ "id": "proton", "name": "Proton" }]);
    settings["serviceSandboxes"] = json!({ "service-a": "proton", "service-b": "proton" });
    assert!(validate_app_settings_value(&settings).is_ok());

    settings["customAccentColors"] = json!(["black"]);
    assert!(validate_app_settings_value(&settings).is_err());
    settings["customAccentColors"] = json!([]);
    settings["keybindings"]["quickServiceSwitch"] = json!("Ctrl+K Ctrl+S Ctrl+P");
    assert!(validate_app_settings_value(&settings).is_err());
    settings["keybindings"]["quickServiceSwitch"] = json!("Ctrl+S");
    settings["serviceSandboxes"] = json!({ "service-a": "missing" });
    assert!(validate_app_settings_value(&settings).is_err());
}
