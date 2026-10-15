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

pub(crate) fn cache_directory(app_data: &Path) -> PathBuf {
    // Never execute an old unversioned cache from a mutable upstream branch.
    app_data.join("recipes").join(revision())
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
    fn cache_reads_are_bounded_and_do_not_follow_leaf_links() {
        let path =
            std::env::temp_dir().join(format!("tauridium-recipe-budget-{}", std::process::id()));
        std::fs::write(&path, b"123456789").unwrap();
        assert!(read_cache(&path, 8).is_none());
        assert_eq!(read_cache(&path, 9).unwrap(), "123456789");
        std::fs::remove_file(path).unwrap();
    }
}
