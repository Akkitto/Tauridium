//! Immutable runtime recipe source, shared with the frontend icon resolver.
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::LazyLock;

static REVISION: LazyLock<String> = LazyLock::new(|| {
    let source: serde_json::Value =
        serde_json::from_str(include_str!("../../data/recipe-source.json"))
            .expect("Bundled recipe source JSON must be valid");
    assert_eq!(source["repository"], "ferdium/ferdium-recipes");
    let revision = source["revision"]
        .as_str()
        .expect("Bundled recipe revision is missing");
    assert!(revision.len() == 40 && revision.bytes().all(|c| c.is_ascii_hexdigit()));
    revision.to_owned()
});

pub(crate) fn revision() -> &'static str {
    &REVISION
}

pub(crate) fn asset_url(recipe_id: &str, filename: &str) -> String {
    format!("https://raw.githubusercontent.com/ferdium/ferdium-recipes/{}/recipes/{recipe_id}/{filename}", revision())
}

pub(crate) fn catalog_url() -> String {
    format!(
        "https://api.github.com/repos/ferdium/ferdium-recipes/contents/recipes?ref={}",
        revision()
    )
}

pub(crate) fn cache_directory(cache_root: &Path) -> PathBuf {
    // Keep remote caches separate even when platform config/data/cache roots alias.
    cache_root.join("remote-recipes").join(revision())
}

pub(crate) fn legacy_cache_directory(app_data: &Path) -> PathBuf {
    app_data.join("recipes").join(revision())
}

pub(crate) fn read_cache_with_legacy(
    primary: &Path,
    legacy: &Path,
    limit: usize,
) -> Option<String> {
    if let Some(text) = read_cache(primary, limit) {
        return Some(text);
    }
    // Only the pinned revision is eligible. Preserve offline upgrades without
    // moving/deleting custom recipes or touching unrelated profile data.
    let text = read_cache(legacy, limit)?;
    match primary.parent() {
        Some(parent) if std::fs::create_dir_all(parent).is_ok() => {
            // Cache persistence is best-effort; a failed copy must not discard
            // an already-readable legacy recipe while the user is offline.
            let _ = crate::write_atomic(primary, &text);
        }
        _ => {}
    }
    Some(text)
}

pub(crate) fn read_cache(path: &Path, limit: usize) -> Option<String> {
    let metadata = std::fs::symlink_metadata(path).ok()?;
    if !metadata.is_file() || metadata.file_type().is_symlink() || metadata.len() > limit as u64 {
        return None;
    }
    let file = std::fs::File::open(path).ok()?;
    let mut text = String::new();
    file.take(limit as u64 + 1).read_to_string(&mut text).ok()?;
    (text.len() <= limit).then_some(text)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn upstream_code_and_caches_are_bound_to_a_full_immutable_revision() {
        assert_eq!(revision().len(), 40);
        assert!(!asset_url("mail", "webview.js").contains("/main/"));
        assert!(asset_url("mail", "webview.js").contains(revision()));
        assert!(catalog_url().ends_with(revision()));
        assert!(cache_directory(Path::new("profile")).ends_with(revision()));
    }
    #[test]
    fn legacy_cache_upgrades_preserve_offline_reads_in_a_separate_namespace() {
        let mut bytes = [0_u8; 16];
        getrandom::fill(&mut bytes).unwrap();
        let suffix = bytes
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>();
        let root = std::env::temp_dir().join(format!("tauridium-cache-upgrade-{suffix}"));
        let primary = cache_directory(&root).join("mail.json");
        let legacy = legacy_cache_directory(&root).join("mail.json");
        assert!(!primary.starts_with(root.join("recipes")));
        fs_create_legacy_fixture(&legacy);
        let original = read_cache_with_legacy(&primary, &legacy, 1024).unwrap();
        assert_eq!(original, r#"{"name":"cached mail"}"#);
        assert_eq!(std::fs::read_to_string(&primary).unwrap(), original);
        assert_eq!(std::fs::read_to_string(&legacy).unwrap(), original);
        std::fs::write(&primary, "new cache").unwrap();
        assert_eq!(
            read_cache_with_legacy(&primary, &legacy, 1024).unwrap(),
            "new cache"
        );
        assert!(read_cache_with_legacy(&primary, &legacy, 2).is_none());
        assert_eq!(std::fs::read_to_string(&primary).unwrap(), "new cache");
        std::fs::remove_dir_all(root).unwrap();
    }

    fn fs_create_legacy_fixture(path: &Path) {
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, r#"{"name":"cached mail"}"#).unwrap();
    }

    #[test]
    fn cache_reads_are_bounded_and_do_not_follow_leaf_links() {
        let path =
            std::env::temp_dir().join(format!("tauridium-recipe-budget-{}", std::process::id()));
        std::fs::write(&path, b"123456789").unwrap();
        assert!(read_cache(&path, 8).is_none());
        assert_eq!(read_cache(&path, 9).unwrap(), "123456789");
        std::fs::remove_file(path).unwrap();
    }
}
