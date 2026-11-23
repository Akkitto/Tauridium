use super::*;
use crate::app_settings::validation::{default_app_settings_value, validate_app_settings_value};
use serde_json::json;

#[test]
fn feature_0425_download_settings_validate_and_resolve_precedence() {
    let mut settings = default_app_settings_value();
    settings["downloadDirectory"] = json!(r"C:\Users\Akito\Downloads");
    settings["askEachDownload"] = json!(false);
    settings["workspaceDownloadSettings"] = json!({
        "workspace-a": { "directory": r"D:\Workspace", "askEachDownload": true }
    });
    settings["serviceDownloadSettings"] = json!({
        "service-a": { "directory": r"E:\Service", "askEachDownload": false }
    });
    assert!(validate_app_settings_value(&settings).is_ok());

    assert_eq!(
        effective_download_preferences(&settings, "service-a", Some("workspace-a")),
        EffectiveDownloadPreferences {
            directory: r"E:\Service".into(),
            ask_each_download: false
        },
    );
    assert_eq!(
        effective_download_preferences(&settings, "service-b", Some("workspace-a")),
        EffectiveDownloadPreferences {
            directory: r"D:\Workspace".into(),
            ask_each_download: true
        },
    );
    assert_eq!(
        effective_download_preferences(&settings, "service-b", None),
        EffectiveDownloadPreferences {
            directory: r"C:\Users\Akito\Downloads".into(),
            ask_each_download: false
        },
    );

    settings["serviceDownloadSettings"] =
        json!({ "service-a": { "directory": 3, "askEachDownload": false } });
    assert!(validate_app_settings_value(&settings).is_err());
    settings["serviceDownloadSettings"] =
        json!({ "service-a": { "directory": "", "askEachDownload": "yes" } });
    assert!(validate_app_settings_value(&settings).is_err());
}
#[test]
fn feature_0425_download_uses_server_suggested_filename_and_sanitizes_safely() {
    let opaque = Url::parse("https://mail.example.test/api/attachments/download?id=123").unwrap();
    assert_eq!(
        suggested_download_filename(Path::new("/tmp/quarterly-report.zip"), &opaque),
        "quarterly-report.zip",
    );
    assert_eq!(
        sanitize_download_filename("../bad:name?.zip"),
        ".._bad_name_.zip"
    );
    assert_eq!(sanitize_download_filename("NUL.txt"), "_NUL.txt");
    assert_eq!(sanitize_download_filename("report.zip. "), "report.zip");
    assert_eq!(
        suggested_download_filename(Path::new(""), &opaque),
        "download"
    );
}
