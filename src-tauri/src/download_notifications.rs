//! Privacy-safe completion messages and bounded download-notification state.
//!
//! Formatting happens natively. A remote service never receives a local path.
use serde::Serialize;
use serde_json::Value;
use std::collections::VecDeque;
use std::path::Path;

pub(crate) const MAX_PENDING: usize = 100;

pub(crate) fn validate_settings(settings: &Value) -> Result<(), String> {
    if !settings
        .get("downloadToasts")
        .is_some_and(Value::is_boolean)
    {
        return Err("App setting downloadToasts must be boolean".into());
    }
    if !matches!(
        settings
            .get("downloadToastLocation")
            .and_then(Value::as_str),
        Some("none" | "directory" | "full" | "partial")
    ) {
        return Err("App setting downloadToastLocation is invalid".into());
    }
    if !settings
        .get("downloadToastParentLevels")
        .and_then(Value::as_u64)
        .is_some_and(|levels| (1..=10).contains(&levels))
    {
        return Err("App setting downloadToastParentLevels must be an integer from 1 to 10".into());
    }
    if !settings
        .get("downloadToastDuration")
        .and_then(Value::as_u64)
        .is_some_and(|seconds| matches!(seconds, 0 | 8 | 15 | 30))
    {
        return Err("App setting downloadToastDuration must be 0, 8, 15, or 30 seconds".into());
    }
    Ok(())
}

fn display_text(value: &str) -> String {
    value
        .chars()
        .map(|character| {
            if character.is_control()
                || matches!(character, '\u{202a}'..='\u{202e}' | '\u{2066}'..='\u{2069}')
            {
                '\u{fffd}'
            } else {
                character
            }
        })
        .collect()
}

/// Lexical display only: never resolve, read, or reveal an ancestor unnecessarily.
fn location_text(path: &str, mode: &str, parent_levels: usize, windows: bool) -> Option<String> {
    if mode == "none" {
        return None;
    }
    if mode == "full" {
        return Some(display_text(path));
    }
    let separator = if windows { '\\' } else { '/' };
    let normalized = if windows {
        path.replace('/', "\\")
    } else {
        path.to_string()
    };
    let components: Vec<_> = normalized
        .split(separator)
        .filter(|part| !part.is_empty())
        .collect();
    // Roots, drive letters and UNC server/share names are not parent directories.
    let root_parts = if windows && normalized.starts_with("\\\\") {
        2
    } else if windows && components.first().is_some_and(|part| part.ends_with(':')) {
        1
    } else {
        0
    };
    let directory_count = components.len().saturating_sub(root_parts + 1);
    if mode == "directory" {
        return Some(if components.len() < 2 {
            if normalized.starts_with(separator) {
                separator.to_string()
            } else {
                ".".into()
            }
        } else {
            let parent = components[components.len() - 2];
            if windows && parent.ends_with(':') {
                format!("{parent}{separator}")
            } else {
                display_text(parent)
            }
        });
    }
    if mode != "partial" {
        return None;
    }
    if directory_count <= parent_levels {
        return Some(display_text(path));
    }
    let suffix = components[components.len() - parent_levels - 1..].join(&separator.to_string());
    Some(format!("…{separator}{}", display_text(&suffix)))
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub(crate) struct Completion {
    pub(crate) id: u64,
    pub(crate) filename: String,
    pub(crate) location: Option<String>,
    pub(crate) location_label: &'static str,
    pub(crate) count: u64,
}

pub(crate) fn completion(
    settings: &Value,
    path: Option<&Path>,
    fallback: &str,
) -> Option<Completion> {
    if settings.get("downloadToasts").and_then(Value::as_bool) != Some(true) {
        return None;
    }
    let mode = settings
        .get("downloadToastLocation")
        .and_then(Value::as_str)
        .unwrap_or("none");
    let levels = settings
        .get("downloadToastParentLevels")
        .and_then(Value::as_u64)
        .unwrap_or(2)
        .clamp(1, 10) as usize;
    let filename = path
        .and_then(Path::file_name)
        .map(|name| display_text(&name.to_string_lossy()))
        .filter(|name| !name.is_empty())
        .unwrap_or_else(|| display_text(fallback));
    Some(Completion {
        id: 0,
        filename,
        location: path
            .and_then(|path| location_text(&path.to_string_lossy(), mode, levels, cfg!(windows))),
        location_label: if mode == "directory" {
            "Folder"
        } else {
            "Saved to"
        },
        count: 1,
    })
}

#[derive(Default)]
pub(crate) struct Pending {
    entries: VecDeque<Completion>,
    next_id: u64,
}

impl Pending {
    pub(crate) fn enqueue(&mut self, mut completion: Completion) {
        self.next_id += 1;
        completion.id = self.next_id;
        if self.entries.len() < MAX_PENDING {
            self.entries.push_back(completion);
        } else if let Some(summary) = self.entries.back_mut() {
            // Retain every completion count without unbounded memory growth. Never
            // replace the currently displayed item or misattribute a summary path.
            summary.count += 1;
            summary.filename.clear();
            summary.location = None;
        }
    }

    pub(crate) fn current(&self) -> Option<Completion> {
        self.entries.front().cloned()
    }

    pub(crate) fn waiting(&self) -> u64 {
        self.entries.iter().skip(1).map(|entry| entry.count).sum()
    }

    pub(crate) fn dismiss(&mut self, id: u64) -> bool {
        if self.entries.front().is_some_and(|entry| entry.id == id) {
            self.entries.pop_front();
            true
        } else {
            false
        }
    }

    pub(crate) fn clear(&mut self) {
        self.entries.clear();
    }

    pub(crate) fn redact_locations(&mut self) {
        for entry in &mut self.entries {
            entry.location = None;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn settings() -> Value {
        json!({ "downloadToasts": true, "downloadToastLocation": "none",
            "downloadToastParentLevels": 2, "downloadToastDuration": 8 })
    }

    #[test]
    fn disabled_and_legacy_settings_never_notify() {
        assert!(completion(&json!({}), Some(Path::new("/private/file.pdf")), "download").is_none());
        let mut value = settings();
        value["downloadToasts"] = false.into();
        assert!(completion(&value, None, "download").is_none());
    }

    #[test]
    fn filename_only_does_not_retain_paths() {
        let value = completion(
            &settings(),
            Some(Path::new(
                "/private/Reports/Gr\u{fc}\u{df}e \u{65e5}\u{672c}\u{8a9e}.pdf",
            )),
            "download",
        )
        .unwrap();
        assert_eq!(
            value.filename,
            "Gr\u{fc}\u{df}e \u{65e5}\u{672c}\u{8a9e}.pdf"
        );
        assert!(value.location.is_none());
        assert!(!serde_json::to_string(&value).unwrap().contains("private"));
    }

    #[test]
    fn unknown_destinations_never_invent_a_saved_location() {
        let mut value = settings();
        value["downloadToastLocation"] = "full".into();
        let result = completion(&value, None, "attachment.pdf").unwrap();
        assert_eq!(result.filename, "attachment.pdf");
        assert!(result.location.is_none());
    }

    #[test]
    fn paths_are_lexically_formatted_without_reading_files() {
        let unix = "/home/akito/Downloads/Reports/report.pdf";
        assert_eq!(
            location_text(unix, "directory", 2, false).as_deref(),
            Some("Reports")
        );
        assert_eq!(
            location_text(unix, "partial", 2, false).as_deref(),
            Some("…/Downloads/Reports/report.pdf")
        );
        assert_eq!(
            location_text(unix, "partial", 1, false).as_deref(),
            Some("…/Reports/report.pdf")
        );
        assert_eq!(
            location_text(unix, "partial", 10, false).as_deref(),
            Some(unix)
        );
        assert_eq!(location_text(unix, "full", 2, false).as_deref(), Some(unix));
        assert_eq!(
            location_text("/report.pdf", "directory", 2, false).as_deref(),
            Some("/")
        );
        assert_eq!(
            location_text("report.pdf", "directory", 2, false).as_deref(),
            Some(".")
        );
        assert_eq!(
            location_text("/folder\\name/report.pdf", "directory", 2, false).as_deref(),
            Some("folder\\name")
        );
    }

    #[test]
    fn windows_drive_unc_mixed_separators_and_roots_are_supported() {
        let windows = r"C:\Users\Akito\Downloads\Reports\report.pdf";
        assert_eq!(
            location_text(windows, "partial", 2, true).as_deref(),
            Some(r"…\Downloads\Reports\report.pdf")
        );
        assert_eq!(
            location_text(windows, "directory", 2, true).as_deref(),
            Some("Reports")
        );
        assert_eq!(
            location_text(r"C:\report.pdf", "directory", 2, true).as_deref(),
            Some("C:\\")
        );
        let unc = r"\\server\share\Projects\Reports\report.pdf";
        assert_eq!(location_text(unc, "partial", 2, true).as_deref(), Some(unc));
        assert_eq!(
            location_text(unc, "partial", 1, true).as_deref(),
            Some(r"…\Reports\report.pdf")
        );
        assert_eq!(
            location_text("D:/Projects/Reports/report.pdf", "partial", 1, true).as_deref(),
            Some(r"…\Reports\report.pdf")
        );
    }

    #[test]
    fn control_and_bidi_characters_cannot_spoof_toast_content() {
        assert_eq!(display_text("a\nb\u{202e}pdf"), "a�b�pdf");
        let unicode = "Gr\u{fc}\u{df}e \u{65e5}\u{672c}\u{8a9e}.pdf";
        assert_eq!(display_text(unicode), unicode);
    }

    #[test]
    fn invalid_settings_are_rejected_even_when_disabled() {
        assert!(validate_settings(&settings()).is_ok());
        for (key, bad) in [
            ("downloadToasts", json!(1)),
            ("downloadToastLocation", json!("bad")),
            ("downloadToastParentLevels", json!(0)),
            ("downloadToastParentLevels", json!(11)),
            ("downloadToastParentLevels", json!(2.5)),
            ("downloadToastDuration", json!(4)),
            ("downloadToastDuration", json!(-1)),
        ] {
            let mut value = settings();
            value[key] = bad;
            assert!(validate_settings(&value).is_err(), "{key}");
        }
        for seconds in [0, 8, 15, 30] {
            let mut value = settings();
            value["downloadToastDuration"] = seconds.into();
            assert!(validate_settings(&value).is_ok());
        }
    }

    #[test]
    fn concurrent_completions_queue_and_stale_dismissals_do_not_skip_files() {
        let mut queue = Pending::default();
        for filename in ["one.pdf", "two.pdf", "three.pdf"] {
            queue.enqueue(completion(&settings(), None, filename).unwrap());
        }
        let first = queue.current().unwrap();
        assert_eq!(first.filename, "one.pdf");
        assert_eq!(queue.waiting(), 2);
        assert!(!queue.dismiss(first.id + 1));
        assert!(queue.dismiss(first.id));
        assert!(!queue.dismiss(first.id));
        assert_eq!(queue.current().unwrap().filename, "two.pdf");
        queue.clear();
        assert!(queue.current().is_none());
    }

    #[test]
    fn bursts_are_bounded_and_all_completion_counts_are_preserved() {
        let mut queue = Pending::default();
        for index in 0..150 {
            queue.enqueue(completion(&settings(), None, &format!("file-{index}")).unwrap());
        }
        assert_eq!(queue.entries.len(), MAX_PENDING);
        assert_eq!(queue.current().unwrap().filename, "file-0");
        assert_eq!(queue.waiting(), 149);
        assert_eq!(queue.entries.back().unwrap().count, 51);
        assert!(queue.entries.back().unwrap().location.is_none());
        assert!(queue.entries.back().unwrap().filename.is_empty());
    }

    #[test]
    fn reducing_path_detail_preserves_notifications_without_retaining_old_locations() {
        let mut value = settings();
        value["downloadToastLocation"] = "full".into();
        let mut queue = Pending::default();
        queue.enqueue(
            completion(&value, Some(Path::new("/private/report.pdf")), "download").unwrap(),
        );
        queue.enqueue(
            completion(&value, Some(Path::new("/private/second.pdf")), "download").unwrap(),
        );
        let id = queue.current().unwrap().id;
        queue.redact_locations();
        assert_eq!(queue.current().unwrap().id, id);
        assert_eq!(queue.current().unwrap().filename, "report.pdf");
        assert!(queue.entries.iter().all(|entry| entry.location.is_none()));
        assert_eq!(queue.waiting(), 1);
    }
}
