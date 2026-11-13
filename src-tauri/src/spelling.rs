//! Spelling check settings, personal dictionary and engine adapters.
//!
//! Tauridium drives each platform's native WebView spellchecker rather than
//! checking text itself, so typed text never leaves the service webview.
//!
//! The personal dictionary is stored once, language-independent, in
//! `spelling-dictionary.json`. On Linux, WebKitGTK checks through Enchant, so
//! Tauridium points Enchant at a private config directory
//! (`<app data>/spelling/enchant`) and mirrors the dictionary into its
//! per-language word lists there. Words learned from the native context menu
//! land in the same directory and are imported back. The user's own
//! `~/.config/enchant` files are never read or modified.
//! See `specs/001-spelling-dictionary/`.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

/// Maximum number of spelling languages selectable at once.
pub(crate) const MAX_LANGUAGES: usize = 8;
const MAX_LANGUAGE_TAG_LEN: usize = 35;
const MAX_SERVICE_OVERRIDES: usize = 10_000;

pub(crate) fn default_languages() -> Value {
    Value::Array(Vec::new())
}

pub(crate) fn default_service_overrides() -> Value {
    Value::Object(Map::new())
}

/// Accepts BCP-47 style tags such as `en`, `en-US` or `zh-Hant-TW`.
fn valid_language_tag(tag: &str) -> bool {
    if tag.is_empty() || tag.len() > MAX_LANGUAGE_TAG_LEN {
        return false;
    }
    let mut parts = tag.split('-');
    let primary_ok = parts.next().is_some_and(|primary| {
        (2..=3).contains(&primary.len()) && primary.bytes().all(|b| b.is_ascii_alphabetic())
    });
    primary_ok
        && parts.all(|part| {
            (1..=8).contains(&part.len()) && part.bytes().all(|b| b.is_ascii_alphanumeric())
        })
}

fn validate_languages(value: &Value, name: &str) -> Result<(), String> {
    let languages = value
        .as_array()
        .ok_or_else(|| format!("{name} must be an array"))?;
    if languages.len() > MAX_LANGUAGES {
        return Err(format!("{name} may list at most {MAX_LANGUAGES} languages"));
    }
    let mut seen = std::collections::HashSet::new();
    for language in languages {
        let tag = language
            .as_str()
            .filter(|tag| valid_language_tag(tag))
            .ok_or_else(|| format!("{name} contains an invalid language tag"))?;
        if !seen.insert(tag.to_ascii_lowercase()) {
            return Err(format!("{name} contains a duplicate language: {tag}"));
        }
    }
    Ok(())
}

fn validate_service_overrides(value: &Value) -> Result<(), String> {
    let overrides = value
        .as_object()
        .ok_or_else(|| "App setting serviceSpellcheck must be an object".to_string())?;
    if overrides.len() > MAX_SERVICE_OVERRIDES {
        return Err("App setting serviceSpellcheck has too many entries".into());
    }
    for (service_id, entry) in overrides {
        if !crate::valid_service_setting_id(service_id) {
            return Err("App setting serviceSpellcheck contains an invalid service id".into());
        }
        let entry = entry
            .as_object()
            .ok_or_else(|| "App setting serviceSpellcheck entries must be objects".to_string())?;
        // An empty entry is a no-op; the UI drops it, so storing one is invalid.
        if entry.is_empty() {
            return Err("App setting serviceSpellcheck contains an empty override".into());
        }
        for (key, field) in entry {
            match key.as_str() {
                "enabled" if field.is_boolean() => {}
                "languages" => {
                    validate_languages(field, "App setting serviceSpellcheck languages")?
                }
                _ => return Err("App setting serviceSpellcheck contains an unknown field".into()),
            }
        }
    }
    Ok(())
}

/// Validates the spelling keys of an app settings object.
pub(crate) fn validate_settings(settings: &Map<String, Value>) -> Result<(), String> {
    if !settings
        .get("spellcheckEnabled")
        .is_some_and(Value::is_boolean)
    {
        return Err("App setting spellcheckEnabled must be boolean".into());
    }
    validate_languages(
        settings
            .get("spellcheckLanguages")
            .ok_or_else(|| "App setting spellcheckLanguages is missing".to_string())?,
        "App setting spellcheckLanguages",
    )?;
    validate_service_overrides(
        settings
            .get("serviceSpellcheck")
            .ok_or_else(|| "App setting serviceSpellcheck is missing".to_string())?,
    )
}

// ---------------------------------------------------------------------------
// Personal dictionary
// ---------------------------------------------------------------------------

const DICTIONARY_FILE: &str = "spelling-dictionary.json";
const DICTIONARY_VERSION: u32 = 1;
pub(crate) const MAX_WORDS: usize = 10_000;
const MAX_WORD_CHARS: usize = 64;
const MAX_NATIVE_LIST_BYTES: u64 = 1024 * 1024;

/// Serializes dictionary reads, writes and native-list mirroring.
static DICTIONARY_LOCK: Mutex<()> = Mutex::new(());

#[derive(Serialize, Deserialize)]
struct StoredDictionary {
    version: u32,
    words: Vec<String>,
}

/// Trims and validates a personal dictionary word.
pub(crate) fn validate_word(word: &str) -> Result<String, String> {
    let word = word.trim();
    if word.is_empty() {
        return Err("Enter a word to add to the dictionary".into());
    }
    if word.chars().count() > MAX_WORD_CHARS {
        return Err(format!(
            "Dictionary words may be at most {MAX_WORD_CHARS} characters"
        ));
    }
    if word.chars().any(|c| c.is_whitespace() || c.is_control()) {
        return Err("A dictionary entry must be a single word without spaces".into());
    }
    Ok(word.to_string())
}

fn dictionary_path(app_data: &Path) -> PathBuf {
    app_data.join(DICTIONARY_FILE)
}

fn load_words(app_data: &Path) -> Result<BTreeSet<String>, String> {
    let path = dictionary_path(app_data);
    let text = match crate::read_persistent(&path) {
        Ok(text) => text,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Ok(BTreeSet::new());
        }
        Err(error) => return Err(format!("Unable to read the personal dictionary: {error}")),
    };
    let stored: StoredDictionary = serde_json::from_str(&text)
        .map_err(|error| format!("The personal dictionary file is damaged: {error}"))?;
    if stored.version == 0 || stored.version > DICTIONARY_VERSION {
        return Err(format!(
            "Unsupported personal dictionary version {} (maximum {DICTIONARY_VERSION})",
            stored.version
        ));
    }
    let mut words = BTreeSet::new();
    for word in stored.words {
        words.insert(validate_word(&word)?);
    }
    if words.len() > MAX_WORDS {
        return Err(format!("The personal dictionary exceeds {MAX_WORDS} words"));
    }
    Ok(words)
}

fn save_words(app_data: &Path, words: &BTreeSet<String>) -> Result<(), String> {
    let stored = StoredDictionary {
        version: DICTIONARY_VERSION,
        words: words.iter().cloned().collect(),
    };
    let text = serde_json::to_string_pretty(&stored)
        .map_err(|error| format!("Unable to encode the personal dictionary: {error}"))?;
    crate::write_atomic(&dictionary_path(app_data), &text)
        .map_err(|error| format!("Unable to save the personal dictionary: {error}"))
}

/// Directory Enchant (and therefore WebKitGTK) uses for personal word lists.
pub(crate) fn engine_word_dir(app_data: &Path) -> PathBuf {
    app_data.join("spelling").join("enchant")
}

fn native_list_stems(dir: &Path) -> Vec<String> {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return Vec::new();
    };
    entries
        .filter_map(Result::ok)
        .filter_map(|entry| {
            let path = entry.path();
            (path.extension().and_then(|ext| ext.to_str()) == Some("dic")).then(|| {
                path.file_stem()
                    .and_then(|stem| stem.to_str())
                    .map(str::to_string)
            })?
        })
        .filter(|stem| valid_native_stem(stem))
        .collect()
}

fn valid_native_stem(stem: &str) -> bool {
    !stem.is_empty()
        && stem.len() <= MAX_LANGUAGE_TAG_LEN
        && stem
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
}

/// Words the engine learned itself (context menu "Add to dictionary").
fn import_native_words(dir: &Path) -> BTreeSet<String> {
    let mut words = BTreeSet::new();
    if !engine_controls().dictionary {
        return words;
    }
    for stem in native_list_stems(dir) {
        let path = dir.join(format!("{stem}.dic"));
        let small_enough = std::fs::metadata(&path)
            .map(|meta| meta.len() <= MAX_NATIVE_LIST_BYTES)
            .unwrap_or(false);
        if !small_enough {
            continue;
        }
        if let Ok(text) = std::fs::read_to_string(&path) {
            words.extend(text.lines().filter_map(|line| validate_word(line).ok()));
        }
    }
    words
}

/// Rewrites every existing engine word list, plus one per active language,
/// to the full dictionary so a word applies in every language.
fn write_native_lists(
    dir: &Path,
    languages: &[String],
    words: &BTreeSet<String>,
) -> Result<(), String> {
    if !engine_controls().dictionary {
        // Windows and macOS keep their own dictionaries; there is no list to mirror.
        return Ok(());
    }
    std::fs::create_dir_all(dir)
        .map_err(|error| format!("Unable to prepare the spelling engine directory: {error}"))?;
    let mut stems: BTreeSet<String> = native_list_stems(dir).into_iter().collect();
    stems.extend(
        languages
            .iter()
            .map(|language| to_engine_tag(language))
            .filter(|stem| valid_native_stem(stem)),
    );
    let mut text = String::new();
    for word in words {
        text.push_str(word);
        text.push('\n');
    }
    for stem in stems {
        crate::write_atomic(&dir.join(format!("{stem}.dic")), &text)
            .map_err(|error| format!("Unable to update the {stem} word list: {error}"))?;
    }
    Ok(())
}

fn to_engine_tag(language: &str) -> String {
    language.replace('-', "_")
}

/// Loads the dictionary, merges words the engine learned, and mirrors the
/// result into the engine word lists.
fn reconcile(app_data: &Path, languages: &[String]) -> Result<BTreeSet<String>, String> {
    let engine_dir = engine_word_dir(app_data);
    let mut words = load_words(app_data)?;
    let learned = import_native_words(&engine_dir);
    let before = words.len();
    words.extend(learned);
    if words.len() > MAX_WORDS {
        return Err(format!(
            "The personal dictionary would exceed {MAX_WORDS} words"
        ));
    }
    if words.len() != before {
        save_words(app_data, &words)?;
    }
    write_native_lists(&engine_dir, languages, &words)?;
    Ok(words)
}

/// Returns all personal dictionary words, sorted.
pub(crate) fn list_words(app_data: &Path, languages: &[String]) -> Result<Vec<String>, String> {
    let _guard = DICTIONARY_LOCK.lock().unwrap();
    Ok(reconcile(app_data, languages)?.into_iter().collect())
}

pub(crate) fn add_word(
    app_data: &Path,
    languages: &[String],
    word: &str,
) -> Result<Vec<String>, String> {
    let word = validate_word(word)?;
    let _guard = DICTIONARY_LOCK.lock().unwrap();
    let mut words = reconcile(app_data, languages)?;
    if words.contains(&word) {
        return Err(format!("\"{word}\" is already in the dictionary"));
    }
    if words.len() >= MAX_WORDS {
        return Err(format!(
            "The personal dictionary is full ({MAX_WORDS} words)"
        ));
    }
    words.insert(word);
    save_words(app_data, &words)?;
    write_native_lists(&engine_word_dir(app_data), languages, &words)?;
    Ok(words.into_iter().collect())
}

pub(crate) fn remove_word(
    app_data: &Path,
    languages: &[String],
    word: &str,
) -> Result<Vec<String>, String> {
    let _guard = DICTIONARY_LOCK.lock().unwrap();
    let mut words = reconcile(app_data, languages)?;
    if !words.remove(word) {
        return Err(format!("\"{word}\" is not in the dictionary"));
    }
    save_words(app_data, &words)?;
    write_native_lists(&engine_word_dir(app_data), languages, &words)?;
    Ok(words.into_iter().collect())
}

/// Replaces the dictionary (used by backup restore).
pub(crate) fn replace_words(
    app_data: &Path,
    languages: &[String],
    new_words: &[String],
) -> Result<(), String> {
    let mut words = BTreeSet::new();
    for word in new_words {
        words.insert(validate_word(word)?);
    }
    if words.len() > MAX_WORDS {
        return Err(format!("A dictionary may hold at most {MAX_WORDS} words"));
    }
    let _guard = DICTIONARY_LOCK.lock().unwrap();
    save_words(app_data, &words)?;
    write_native_lists(&engine_word_dir(app_data), languages, &words)
}

/// Current words without touching the engine lists (backup creation).
pub(crate) fn snapshot_words(app_data: &Path) -> Result<Vec<String>, String> {
    let _guard = DICTIONARY_LOCK.lock().unwrap();
    let mut words = load_words(app_data)?;
    words.extend(import_native_words(&engine_word_dir(app_data)));
    Ok(words.into_iter().collect())
}

// ---------------------------------------------------------------------------
// Languages
// ---------------------------------------------------------------------------

#[derive(Serialize, Clone, Debug, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub(crate) struct SpellingLanguage {
    pub tag: String,
    pub display_name: String,
    pub available: bool,
    pub reason: Option<String>,
}

const LANGUAGE_NAMES: &[(&str, &str)] = &[
    ("ar", "Arabic"),
    ("bg", "Bulgarian"),
    ("ca", "Catalan"),
    ("cs", "Czech"),
    ("da", "Danish"),
    ("de", "German"),
    ("el", "Greek"),
    ("en", "English"),
    ("es", "Spanish"),
    ("et", "Estonian"),
    ("fi", "Finnish"),
    ("fr", "French"),
    ("he", "Hebrew"),
    ("hr", "Croatian"),
    ("hu", "Hungarian"),
    ("it", "Italian"),
    ("lt", "Lithuanian"),
    ("lv", "Latvian"),
    ("nb", "Norwegian Bokm\u{e5}l"),
    ("nl", "Dutch"),
    ("nn", "Norwegian Nynorsk"),
    ("pl", "Polish"),
    ("pt", "Portuguese"),
    ("ro", "Romanian"),
    ("ru", "Russian"),
    ("sk", "Slovak"),
    ("sl", "Slovenian"),
    ("sv", "Swedish"),
    ("tr", "Turkish"),
    ("uk", "Ukrainian"),
];

pub(crate) fn language_display_name(tag: &str) -> String {
    let base = tag.split('-').next().unwrap_or(tag).to_ascii_lowercase();
    match LANGUAGE_NAMES.iter().find(|(code, _)| *code == base) {
        Some((_, name)) if tag.contains('-') => format!("{name} ({tag})"),
        Some((_, name)) => (*name).to_string(),
        None => tag.to_string(),
    }
}

/// Converts a dictionary file stem such as `en_US` to a settings tag (`en-US`).
fn stem_to_tag(stem: &str) -> Option<String> {
    let tag = stem.replace('_', "-");
    valid_language_tag(&tag).then_some(tag)
}

/// Directories that may hold Hunspell dictionaries.
fn dictionary_dirs() -> Vec<PathBuf> {
    let mut dirs: Vec<PathBuf> = Vec::new();
    if let Some(data) = dirs::data_dir() {
        dirs.push(data.join("hunspell"));
    }
    let data_dirs = std::env::var("XDG_DATA_DIRS")
        .ok()
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "/usr/local/share:/usr/share".to_string());
    for base in data_dirs.split(':').filter(|base| !base.is_empty()) {
        dirs.push(Path::new(base).join("hunspell"));
        dirs.push(Path::new(base).join("myspell"));
    }
    dirs.push(PathBuf::from("/usr/share/hunspell"));
    dirs.push(PathBuf::from("/usr/share/myspell"));
    dirs.dedup();
    dirs
}

/// Language tags with an installed Hunspell dictionary (`.dic` and `.aff`).
pub(crate) fn installed_languages_in(dirs: &[PathBuf]) -> BTreeSet<String> {
    let mut tags = BTreeSet::new();
    for dir in dirs {
        let Ok(entries) = std::fs::read_dir(dir) else {
            continue;
        };
        for entry in entries.filter_map(Result::ok) {
            let path = entry.path();
            if path.extension().and_then(|ext| ext.to_str()) != Some("dic") {
                continue;
            }
            // Follows symlinks, which distributions use for aliases.
            if !path.with_extension("aff").is_file() || !path.is_file() {
                continue;
            }
            if let Some(tag) = path
                .file_stem()
                .and_then(|stem| stem.to_str())
                .and_then(stem_to_tag)
            {
                tags.insert(tag);
            }
        }
    }
    tags
}

/// Language list for the settings UI: every installed dictionary, plus any
/// selected language that is not installed (shown as unavailable).
pub(crate) fn language_list(
    installed: &BTreeSet<String>,
    selected: &[String],
) -> Vec<SpellingLanguage> {
    let mut languages: Vec<SpellingLanguage> = installed
        .iter()
        .map(|tag| SpellingLanguage {
            tag: tag.clone(),
            display_name: language_display_name(tag),
            available: true,
            reason: None,
        })
        .collect();
    for tag in selected {
        if !installed
            .iter()
            .any(|candidate| candidate.eq_ignore_ascii_case(tag))
        {
            languages.push(SpellingLanguage {
                tag: tag.clone(),
                display_name: language_display_name(tag),
                available: false,
                reason: Some(
                    "No dictionary for this language is installed on this system. Install the matching Hunspell dictionary package."
                        .into(),
                ),
            });
        }
    }
    languages
}

pub(crate) fn installed_languages() -> BTreeSet<String> {
    installed_languages_in(&dictionary_dirs())
}

/// The desktop language as a settings tag, from the standard locale variables.
pub(crate) fn system_language() -> String {
    for name in ["LC_ALL", "LC_MESSAGES", "LANG"] {
        if let Ok(value) = std::env::var(name) {
            if let Some(tag) = locale_to_tag(&value) {
                return tag;
            }
        }
    }
    "en-US".to_string()
}

fn locale_to_tag(locale: &str) -> Option<String> {
    let base = locale.split(['.', '@']).next()?;
    if base.is_empty() || base == "C" || base == "POSIX" {
        return None;
    }
    stem_to_tag(base)
}

// ---------------------------------------------------------------------------
// Effective settings and engine adapter
// ---------------------------------------------------------------------------

#[derive(Debug, PartialEq, Eq)]
pub(crate) struct EffectiveSpellcheck {
    pub enabled: bool,
    /// Settings tags (`en-US`); never empty (falls back to the system language).
    pub languages: Vec<String>,
}

pub(crate) fn effective_for_service(settings: &Value, service_id: &str) -> EffectiveSpellcheck {
    let global_enabled = settings
        .get("spellcheckEnabled")
        .and_then(Value::as_bool)
        .unwrap_or(true);
    let global_languages = string_list(settings.get("spellcheckLanguages"));
    let entry = settings
        .get("serviceSpellcheck")
        .and_then(Value::as_object)
        .and_then(|overrides| overrides.get(service_id));
    let enabled = entry
        .and_then(|entry| entry.get("enabled"))
        .and_then(Value::as_bool)
        .unwrap_or(global_enabled);
    let languages = entry
        .and_then(|entry| entry.get("languages"))
        .map(|value| string_list(Some(value)))
        .unwrap_or(global_languages);
    EffectiveSpellcheck {
        enabled,
        languages: if languages.is_empty() {
            vec![system_language()]
        } else {
            languages
        },
    }
}

fn string_list(value: Option<&Value>) -> Vec<String> {
    value
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default()
}

/// Every language any service may use, so the dictionary is mirrored into
/// each of their engine word lists.
pub(crate) fn active_languages(settings: &Value) -> Vec<String> {
    let mut languages: BTreeSet<String> = string_list(settings.get("spellcheckLanguages"))
        .into_iter()
        .collect();
    if let Some(overrides) = settings.get("serviceSpellcheck").and_then(Value::as_object) {
        for entry in overrides.values() {
            languages.extend(string_list(entry.get("languages")));
        }
    }
    if languages.is_empty() {
        languages.insert(system_language());
    }
    languages.into_iter().collect()
}

/// Points the engine at Tauridium's private word-list directory. Must run
/// before the first service webview starts so its web process inherits it.
pub(crate) fn prepare_engine(app_data: &Path) -> Result<(), String> {
    #[cfg(target_os = "linux")]
    {
        let dir = engine_word_dir(app_data);
        std::fs::create_dir_all(&dir)
            .map_err(|error| format!("Unable to prepare the spelling engine directory: {error}"))?;
        std::env::set_var("ENCHANT_CONFIG_DIR", &dir);
    }
    #[cfg(not(target_os = "linux"))]
    let _ = app_data;
    Ok(())
}

/// macOS: WebKit only underlines misspellings when the app default
/// `WebContinuousSpellCheckingEnabled` is true, and treats a missing key as
/// false. Register it in this process so it applies whichever preferences
/// domain the process uses (the bundle identifier when packaged, the executable
/// name when run unbundled), and still yields to a value the user has stored
/// from the context menu. Never fails.
#[cfg(target_os = "macos")]
pub(crate) fn register_macos_defaults() {
    use objc2::rc::Retained;
    use objc2::runtime::AnyObject;
    use objc2_foundation::{NSDictionary, NSNumber, NSString, NSUserDefaults};
    let key = NSString::from_str("WebContinuousSpellCheckingEnabled");
    let defaults = NSUserDefaults::standardUserDefaults();
    let enabled: Retained<AnyObject> =
        Retained::into_super(Retained::into_super(Retained::into_super(NSNumber::new_bool(true))));
    let registration = NSDictionary::from_retained_objects(&[&*key], &[enabled]);
    // SAFETY: the dictionary holds an NSString key and an NSNumber value, both
    // valid property-list types.
    unsafe { defaults.registerDefaults(&registration) };
}

#[cfg(not(target_os = "macos"))]
pub(crate) fn register_macos_defaults() {}

/// Which spelling controls the platform engine really honours. Where a control
/// is not available the UI explains that the operating system manages it,
/// instead of offering a setting that would do nothing.
#[derive(Serialize, Clone, Copy, Debug, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub(crate) struct EngineControls {
    /// Per-service on/off.
    pub toggle: bool,
    /// App-chosen spelling languages.
    pub languages: bool,
    /// App-managed personal dictionary.
    pub dictionary: bool,
    /// Short platform name used in UI text.
    pub platform: &'static str,
}

pub(crate) const fn engine_controls() -> EngineControls {
    EngineControls {
        toggle: true,
        languages: cfg!(target_os = "linux"),
        dictionary: cfg!(target_os = "linux"),
        platform: if cfg!(target_os = "linux") {
            "Linux"
        } else if cfg!(windows) {
            "Windows"
        } else {
            "macOS"
        },
    }
}

/// Script for engines without a native on/off control. `None` on Linux, where
/// the WebKitGTK context controls checking.
pub(crate) fn toggle_init_script(enabled: bool) -> Option<String> {
    if cfg!(target_os = "linux") {
        return None;
    }
    Some(format!(
        "window.__tauridiumSpellcheckState = {{ enabled: {enabled} }};\n{}",
        include_str!("spellcheck_toggle.js")
    ))
}

/// Applies enable/disable and languages to one service webview.
#[cfg(target_os = "linux")]
pub(crate) fn apply_to_webview(
    webview: &tauri::Webview<tauri::Wry>,
    effective: &EffectiveSpellcheck,
) -> Result<(), String> {
    let enabled = effective.enabled;
    let languages: Vec<String> = effective
        .languages
        .iter()
        .map(|language| to_engine_tag(language))
        .collect();
    webview
        .with_webview(move |platform| {
            use webkit2gtk::{WebContextExt, WebViewExt};
            if let Some(context) = platform.inner().context() {
                context.set_spell_checking_enabled(enabled);
                let refs: Vec<&str> = languages.iter().map(String::as_str).collect();
                context.set_spell_checking_languages(&refs);
            }
        })
        .map_err(|error| format!("Unable to apply spelling settings: {error}"))
}

/// WebKitGTK keeps offering spelling suggestions in the context menu even when
/// its spell checking flag is off. When a service has checking disabled, strip
/// those items so nothing spelling-related appears (User Story 4). The handler
/// reads the live flag, so later toggles need no reinstall. Install once per
/// webview, at creation.
#[cfg(target_os = "linux")]
pub(crate) fn install_menu_filter(webview: &tauri::Webview<tauri::Wry>) -> Result<(), String> {
    webview
        .with_webview(|platform| {
            use webkit2gtk::{
                ContextMenuAction, ContextMenuExt, ContextMenuItemExt, WebContextExt, WebViewExt,
            };
            platform
                .inner()
                .connect_context_menu(|view, menu, _event, _hit| {
                    let enabled = view
                        .context()
                        .is_none_or(|context| context.is_spell_checking_enabled());
                    if !enabled {
                        for item in menu.items() {
                            if matches!(
                                item.stock_action(),
                                ContextMenuAction::SpellingGuess
                                    | ContextMenuAction::NoGuessesFound
                                    | ContextMenuAction::IgnoreSpelling
                                    | ContextMenuAction::LearnSpelling
                            ) {
                                menu.remove(&item);
                            }
                        }
                    }
                    // Let the default menu (now filtered) show.
                    false
                });
        })
        .map_err(|error| format!("Unable to install the spelling menu filter: {error}"))
}

#[cfg(not(target_os = "linux"))]
pub(crate) fn install_menu_filter(_webview: &tauri::Webview<tauri::Wry>) -> Result<(), String> {
    Ok(())
}

/// Windows and macOS: the engine has no per-service control, so flip the page
/// level switch installed at creation. Languages and the dictionary stay with
/// the operating system.
#[cfg(not(target_os = "linux"))]
pub(crate) fn apply_to_webview(
    webview: &tauri::Webview<tauri::Wry>,
    effective: &EffectiveSpellcheck,
) -> Result<(), String> {
    webview
        .eval(format!(
            "window.__tauridiumSpellcheckSet && window.__tauridiumSpellcheckSet({});",
            effective.enabled
        ))
        .map_err(|error| format!("Unable to apply spelling settings: {error}"))
}

/// Applies the effective settings to one service's webview if it exists.
pub(crate) fn apply_service(
    app: &tauri::AppHandle,
    settings: &Value,
    service_id: &str,
) -> Result<(), String> {
    use tauri::Manager;
    match app.get_webview(&format!("svc-{service_id}")) {
        Some(webview) => apply_to_webview(&webview, &effective_for_service(settings, service_id)),
        None => Ok(()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn settings(languages: Value, overrides: Value) -> Map<String, Value> {
        let mut map = Map::new();
        map.insert("spellcheckEnabled".into(), true.into());
        map.insert("spellcheckLanguages".into(), languages);
        map.insert("serviceSpellcheck".into(), overrides);
        map
    }

    #[test]
    fn defaults_are_valid() {
        let map = settings(default_languages(), default_service_overrides());
        assert!(validate_settings(&map).is_ok());
    }

    #[test]
    fn accepts_valid_tags_and_overrides() {
        let map = settings(
            json!(["en-US", "de", "zh-Hant-TW"]),
            json!({
                "svc-a": { "enabled": false },
                "svc-b": { "languages": ["fr"] },
                "svc-c": { "enabled": true, "languages": [] }
            }),
        );
        assert!(validate_settings(&map).is_ok());
    }

    #[test]
    fn rejects_invalid_languages() {
        for languages in [
            json!("en"),
            json!([1]),
            json!([""]),
            json!(["e"]),
            json!(["en_US"]),
            json!(["en-"]),
            json!(["en", "EN"]),
            json!(["a1"]),
            json!(["en", "de", "fr", "es", "it", "pt", "nl", "sv", "pl"]),
        ] {
            let map = settings(languages.clone(), default_service_overrides());
            assert!(
                validate_settings(&map).is_err(),
                "{languages} must be rejected"
            );
        }
    }

    #[test]
    fn rejects_invalid_overrides() {
        for overrides in [
            json!([]),
            json!({ "": { "enabled": true } }),
            json!({ "svc": {} }),
            json!({ "svc": true }),
            json!({ "svc": { "enabled": "yes" } }),
            json!({ "svc": { "languages": ["bad_tag"] } }),
            json!({ "svc": { "extra": 1 } }),
        ] {
            let map = settings(default_languages(), overrides.clone());
            assert!(
                validate_settings(&map).is_err(),
                "{overrides} must be rejected"
            );
        }
    }

    #[test]
    fn rejects_missing_or_non_boolean_enabled() {
        let mut map = settings(default_languages(), default_service_overrides());
        map.insert("spellcheckEnabled".into(), "yes".into());
        assert!(validate_settings(&map).is_err());
        map.remove("spellcheckEnabled");
        assert!(validate_settings(&map).is_err());
    }

    fn langs(tags: &[&str]) -> Vec<String> {
        tags.iter().map(|tag| (*tag).to_string()).collect()
    }

    #[test]
    fn word_validation_trims_and_rejects_bad_input() {
        assert_eq!(validate_word("  Tauridium ").unwrap(), "Tauridium");
        assert_eq!(validate_word("na\u{ef}ve").unwrap(), "na\u{ef}ve");
        for bad in [
            "",
            "   ",
            "two words",
            "tab\tbed",
            "new\nline",
            &"x".repeat(65),
        ] {
            assert!(validate_word(bad).is_err(), "{bad:?} must be rejected");
        }
        assert!(validate_word(&"x".repeat(64)).is_ok());
    }

    #[test]
    fn dictionary_add_remove_round_trip_and_mirror_to_engine_lists() {
        let dir = tempfile::tempdir().unwrap();
        let languages = langs(&["en-US", "de-DE"]);
        assert!(list_words(dir.path(), &languages).unwrap().is_empty());

        let words = add_word(dir.path(), &languages, " Zorblax ").unwrap();
        assert_eq!(words, vec!["Zorblax"]);
        assert!(add_word(dir.path(), &languages, "Zorblax").is_err());
        add_word(dir.path(), &languages, "Aardvark").unwrap();

        // Both active languages get the full list in Enchant's file format.
        let engine = engine_word_dir(dir.path());
        for stem in ["en_US", "de_DE"] {
            let text = std::fs::read_to_string(engine.join(format!("{stem}.dic"))).unwrap();
            assert_eq!(text, "Aardvark\nZorblax\n");
        }

        let words = remove_word(dir.path(), &languages, "Zorblax").unwrap();
        assert_eq!(words, vec!["Aardvark"]);
        assert!(remove_word(dir.path(), &languages, "Zorblax").is_err());
        let text = std::fs::read_to_string(engine.join("en_US.dic")).unwrap();
        assert_eq!(text, "Aardvark\n");
    }

    #[test]
    fn words_learned_by_the_engine_are_imported_and_shared_across_languages() {
        let dir = tempfile::tempdir().unwrap();
        let languages = langs(&["en-US", "fr-FR"]);
        let engine = engine_word_dir(dir.path());
        std::fs::create_dir_all(&engine).unwrap();
        // The native context menu wrote a word to one language only.
        std::fs::write(engine.join("en_US.dic"), "Kubernetes\n\nbad word\n").unwrap();

        let words = list_words(dir.path(), &languages).unwrap();
        assert_eq!(words, vec!["Kubernetes"]);
        let french = std::fs::read_to_string(engine.join("fr_FR.dic")).unwrap();
        assert_eq!(french, "Kubernetes\n");
        // And it is persisted in Tauridium's own file.
        assert_eq!(snapshot_words(dir.path()).unwrap(), vec!["Kubernetes"]);
    }

    #[test]
    fn removed_words_are_not_resurrected_from_stale_language_lists() {
        let dir = tempfile::tempdir().unwrap();
        add_word(dir.path(), &langs(&["en-US"]), "Zorblax").unwrap();
        // The language set later changes; the old en_US list must still be purged.
        remove_word(dir.path(), &langs(&["de-DE"]), "Zorblax").unwrap();
        assert!(list_words(dir.path(), &langs(&["en-US"]))
            .unwrap()
            .is_empty());
    }

    #[test]
    fn damaged_or_future_dictionary_files_fail_without_being_overwritten() {
        let dir = tempfile::tempdir().unwrap();
        let path = dictionary_path(dir.path());
        std::fs::write(&path, "{not json").unwrap();
        assert!(list_words(dir.path(), &langs(&["en-US"])).is_err());
        assert!(add_word(dir.path(), &langs(&["en-US"]), "word").is_err());
        assert_eq!(std::fs::read_to_string(&path).unwrap(), "{not json");

        std::fs::write(&path, r#"{"version":99,"words":[]}"#).unwrap();
        let error = list_words(dir.path(), &langs(&["en-US"])).unwrap_err();
        assert!(error.contains("Unsupported"), "{error}");
    }

    #[test]
    fn dictionary_is_capped() {
        let dir = tempfile::tempdir().unwrap();
        let words: Vec<String> = (0..=MAX_WORDS).map(|n| format!("w{n}")).collect();
        assert!(replace_words(dir.path(), &langs(&["en-US"]), &words).is_err());
        assert!(replace_words(dir.path(), &langs(&["en-US"]), &words[..MAX_WORDS]).is_ok());
        assert!(add_word(dir.path(), &langs(&["en-US"]), "one-more").is_err());
    }

    #[test]
    fn replace_words_deduplicates_and_validates() {
        let dir = tempfile::tempdir().unwrap();
        replace_words(dir.path(), &langs(&["en-US"]), &langs(&["b", "a", "b"])).unwrap();
        assert_eq!(snapshot_words(dir.path()).unwrap(), vec!["a", "b"]);
        assert!(replace_words(dir.path(), &langs(&["en-US"]), &langs(&["bad word"])).is_err());
        assert_eq!(snapshot_words(dir.path()).unwrap(), vec!["a", "b"]);
    }

    #[test]
    fn installed_languages_need_both_dic_and_aff_and_convert_tags() {
        let dir = tempfile::tempdir().unwrap();
        for name in [
            "en_US.dic",
            "en_US.aff",
            "de_DE.dic",
            "fr.dic",
            "fr.aff",
            "weird name.dic",
            "weird name.aff",
            "pt_BR.aff",
        ] {
            std::fs::write(dir.path().join(name), "").unwrap();
        }
        let tags = installed_languages_in(&[dir.path().to_path_buf(), dir.path().join("missing")]);
        assert_eq!(tags.into_iter().collect::<Vec<_>>(), vec!["en-US", "fr"]);
    }

    #[test]
    fn language_list_marks_missing_selected_languages_unavailable() {
        let installed: BTreeSet<String> = ["en-US".to_string()].into();
        let list = language_list(&installed, &langs(&["en-US", "de-DE"]));
        assert_eq!(list.len(), 2);
        assert!(list[0].available && list[0].reason.is_none());
        assert_eq!(list[0].display_name, "English (en-US)");
        assert!(!list[1].available);
        assert!(list[1].reason.as_deref().unwrap().contains("No dictionary"));
        assert_eq!(language_display_name("en"), "English");
        assert_eq!(language_display_name("xx-YY"), "xx-YY");
    }

    #[test]
    fn locale_variables_map_to_language_tags() {
        assert_eq!(locale_to_tag("en_US.UTF-8").as_deref(), Some("en-US"));
        assert_eq!(locale_to_tag("de_DE@euro").as_deref(), Some("de-DE"));
        assert_eq!(locale_to_tag("fr").as_deref(), Some("fr"));
        assert_eq!(locale_to_tag("C"), None);
        assert_eq!(locale_to_tag("POSIX"), None);
        assert_eq!(locale_to_tag(""), None);
        assert!(!system_language().is_empty());
    }

    #[test]
    fn effective_settings_inherit_and_override_per_field() {
        let settings = json!({
            "spellcheckEnabled": true,
            "spellcheckLanguages": ["en-US"],
            "serviceSpellcheck": {
                "off": { "enabled": false },
                "de": { "languages": ["de-DE", "en-US"] },
                "sys": { "languages": [] }
            }
        });
        let inherit = effective_for_service(&settings, "other");
        assert_eq!(
            inherit,
            EffectiveSpellcheck {
                enabled: true,
                languages: langs(&["en-US"])
            }
        );
        let off = effective_for_service(&settings, "off");
        assert!(!off.enabled);
        assert_eq!(off.languages, langs(&["en-US"]));
        let de = effective_for_service(&settings, "de");
        assert!(de.enabled);
        assert_eq!(de.languages, langs(&["de-DE", "en-US"]));
        // An empty override means "system language", not "inherit".
        let sys = effective_for_service(&settings, "sys");
        assert_eq!(sys.languages, vec![system_language()]);
    }

    #[test]
    fn active_languages_cover_global_and_service_overrides() {
        let settings = json!({
            "spellcheckLanguages": ["en-US"],
            "serviceSpellcheck": { "a": { "languages": ["de-DE"] }, "b": { "enabled": false } }
        });
        assert_eq!(active_languages(&settings), langs(&["de-DE", "en-US"]));
        assert_eq!(active_languages(&json!({})), vec![system_language()]);
    }

    #[test]
    fn engine_controls_match_what_each_platform_can_honour() {
        let controls = engine_controls();
        assert!(controls.toggle, "every platform has a per-service switch");
        assert_eq!(controls.languages, cfg!(target_os = "linux"));
        assert_eq!(controls.dictionary, cfg!(target_os = "linux"));
        assert!(["Linux", "Windows", "macOS"].contains(&controls.platform));
    }

    #[test]
    fn toggle_script_exists_only_where_the_engine_has_no_native_switch() {
        if cfg!(target_os = "linux") {
            assert!(toggle_init_script(true).is_none());
            return;
        }
        let on = toggle_init_script(true).unwrap();
        let off = toggle_init_script(false).unwrap();
        assert!(on.starts_with("window.__tauridiumSpellcheckState = { enabled: true };"));
        assert!(off.starts_with("window.__tauridiumSpellcheckState = { enabled: false };"));
        assert!(on.contains("__tauridiumSpellcheckSet"));
    }

    #[test]
    fn dictionary_is_not_mirrored_where_the_system_owns_it() {
        // On Linux the engine lists are managed; elsewhere writes must be no-ops.
        let dir = tempfile::tempdir().unwrap();
        let engine = engine_word_dir(dir.path());
        add_word(dir.path(), &langs(&["en-US"]), "Zorblax").unwrap();
        assert_eq!(engine.join("en_US.dic").exists(), cfg!(target_os = "linux"));
    }
}
