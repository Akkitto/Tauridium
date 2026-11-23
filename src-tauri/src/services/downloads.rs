//! Service download preference resolution and safe destination selection.

use serde_json::Value;
use std::path::Path;
use std::path::PathBuf;
use tauri::{AppHandle, Manager, Url, Wry};

// Download filename derived from the URL (last path segment; the
// query is ignored). Sanitize separators to prevent path traversal.
pub(super) fn download_filename(url: &Url) -> String {
    let raw = url
        .path_segments()
        .and_then(|mut segs| segs.next_back())
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .unwrap_or("download");
    let clean: String = raw.replace(['/', '\\', '\0'], "_");
    if clean.is_empty() {
        "download".to_string()
    } else {
        clean
    }
}

// Choose a non-existing destination path in `dir` (WKDownload fails if the file exists):
// append (1), (2), etc. before the extension when a collision occurs.
pub(super) fn unique_download_path(dir: &Path, name: &str) -> PathBuf {
    let candidate = dir.join(name);
    if !candidate.exists() {
        return candidate;
    }
    let p = Path::new(name);
    let stem = p.file_stem().and_then(|s| s.to_str()).unwrap_or("download");
    let ext = p.extension().and_then(|s| s.to_str());
    for i in 1..10_000 {
        let fname = match ext {
            Some(e) => format!("{stem} ({i}).{e}"),
            None => format!("{stem} ({i})"),
        };
        let candidate = dir.join(fname);
        if !candidate.exists() {
            return candidate;
        }
    }
    dir.join(name)
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(super) struct EffectiveDownloadPreferences {
    pub(super) directory: String,
    pub(super) ask_each_download: bool,
}

fn download_preferences_from_map(
    settings: &Value,
    key: &str,
    id: Option<&str>,
) -> Option<EffectiveDownloadPreferences> {
    let id = id?.trim();
    if id.is_empty() {
        return None;
    }
    let value = settings.get(key)?.as_object()?.get(id)?.as_object()?;
    Some(EffectiveDownloadPreferences {
        directory: value.get("directory")?.as_str()?.to_string(),
        ask_each_download: value.get("askEachDownload")?.as_bool()?,
    })
}

pub(super) fn effective_download_preferences(
    settings: &Value,
    service_id: &str,
    workspace_id: Option<&str>,
) -> EffectiveDownloadPreferences {
    if let Some(preferences) =
        download_preferences_from_map(settings, "serviceDownloadSettings", Some(service_id))
    {
        return preferences;
    }
    if let Some(preferences) =
        download_preferences_from_map(settings, "workspaceDownloadSettings", workspace_id)
    {
        return preferences;
    }
    EffectiveDownloadPreferences {
        directory: settings
            .get("downloadDirectory")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string(),
        ask_each_download: settings
            .get("askEachDownload")
            .and_then(Value::as_bool)
            .unwrap_or(false),
    }
}

pub(super) fn sanitize_download_filename(value: &str) -> String {
    let mut clean: String = value
        .trim()
        .chars()
        .map(|character| {
            if character.is_control()
                || matches!(
                    character,
                    '/' | '\\' | '<' | '>' | ':' | '"' | '|' | '?' | '*'
                )
            {
                '_'
            } else {
                character
            }
        })
        .collect();
    while clean.ends_with(' ') || clean.ends_with('.') {
        clean.pop();
    }
    if clean.is_empty() || clean == "." || clean == ".." {
        return "download".into();
    }
    let reserved_stem = Path::new(&clean)
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_uppercase();
    if matches!(
        reserved_stem.as_str(),
        "CON"
            | "PRN"
            | "AUX"
            | "NUL"
            | "COM1"
            | "COM2"
            | "COM3"
            | "COM4"
            | "COM5"
            | "COM6"
            | "COM7"
            | "COM8"
            | "COM9"
            | "LPT1"
            | "LPT2"
            | "LPT3"
            | "LPT4"
            | "LPT5"
            | "LPT6"
            | "LPT7"
            | "LPT8"
            | "LPT9"
    ) {
        clean.insert(0, '_');
    }
    if clean.chars().count() > 240 {
        let path = Path::new(&clean);
        let extension = path
            .extension()
            .and_then(|value| value.to_str())
            .unwrap_or("");
        let extension_len = if extension.is_empty() {
            0
        } else {
            extension.chars().count() + 1
        };
        let stem_limit = 240usize.saturating_sub(extension_len);
        let stem: String = path
            .file_stem()
            .and_then(|value| value.to_str())
            .unwrap_or("download")
            .chars()
            .take(stem_limit.max(1))
            .collect();
        clean = if extension.is_empty() {
            stem
        } else {
            format!("{stem}.{extension}")
        };
    }
    clean
}

pub(super) fn suggested_download_filename(destination: &Path, url: &Url) -> String {
    destination
        .file_name()
        .and_then(|value| value.to_str())
        .map(sanitize_download_filename)
        .unwrap_or_else(|| sanitize_download_filename(&download_filename(url)))
}

pub(super) fn effective_download_directory(app: &AppHandle, configured: &str) -> PathBuf {
    let configured = configured.trim();
    if !configured.is_empty() {
        let path = PathBuf::from(configured);
        if path.is_absolute() && std::fs::create_dir_all(&path).is_ok() {
            return path;
        }
    }
    app.path()
        .download_dir()
        .or_else(|_| app.path().home_dir())
        .unwrap_or_else(|_| PathBuf::from("."))
}

pub(super) fn ask_download_destination(
    parent: &tauri::Window<Wry>,
    directory: &Path,
    suggested_name: &str,
) -> Option<PathBuf> {
    // Wry requires the final absolute destination synchronously from its download-started
    // callback. Use rfd's synchronous native dialog directly on that callback thread. The
    // tauri-plugin-dialog blocking wrapper cannot be used here: it dispatches back to the main
    // thread and would deadlock while the synchronous download callback is waiting. rfd is
    // already Tauridium's native dialog backend through tauri-plugin-dialog; declaring it
    // directly lets us use the correct synchronous API without changing dialog technology.
    rfd::FileDialog::new()
        .set_parent(parent)
        .set_title("Save download")
        .set_directory(directory)
        .set_file_name(suggested_name)
        .save_file()
}

#[cfg(test)]
mod tests;
