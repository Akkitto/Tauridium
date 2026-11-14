//! Runtime orchestration for ad blocking: keeps lists fresh, compiles them into
//! the platform's native filter format and attaches the result to service
//! webviews.
//!
//! Startup and webview creation only ever read the on-disk cache; downloads and
//! compilation happen on background threads and never on an interaction path.

#[cfg(any(target_os = "linux", test))]
use super::compile;
use super::lists;
use crate::AppState;
use serde::Serialize;
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Emitter, Manager};

const EVENT_UPDATED: &str = "adblock-lists-updated";
const EVENT_ERROR: &str = "adblock-error";
const STARTUP_DELAY: Duration = Duration::from_secs(10);
const CHECK_INTERVAL: Duration = Duration::from_secs(3600);

static REFRESH_LOCK: tokio::sync::Mutex<()> = tokio::sync::Mutex::const_new(());
static STATUS: Mutex<Status> = Mutex::new(Status {
    compiling: 0,
    engine_error: None,
    coverage: None,
});

#[derive(Debug, Clone)]
struct Coverage {
    network_total: u32,
    converted: usize,
}

struct Status {
    compiling: usize,
    engine_error: Option<String>,
    coverage: Option<Coverage>,
}

fn now_secs() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |elapsed| elapsed.as_secs())
}

fn adblock_dir(app: &AppHandle) -> Result<PathBuf, String> {
    app.path()
        .app_data_dir()
        .map(|dir| dir.join("adblock"))
        .map_err(|error| format!("Unable to locate the app data directory: {error}"))
}

fn current_settings(app: &AppHandle) -> serde_json::Value {
    app.state::<AppState>().settings.lock().unwrap().clone()
}

/// Blocking is wanted when the engine exists and anything could use it.
fn wanted(settings: &serde_json::Value) -> bool {
    if !super::engine_supported() {
        return false;
    }
    let global = settings
        .get("adblockEnabled")
        .and_then(serde_json::Value::as_bool)
        .unwrap_or(false);
    let any_service = settings
        .get("serviceAdblock")
        .and_then(serde_json::Value::as_object)
        .is_some_and(|map| {
            map.values().any(|entry| {
                entry.get("enabled").and_then(serde_json::Value::as_bool) == Some(true)
            })
        });
    global || any_service
}

// ---------------------------------------------------------------------------
// State reported to the shell
// ---------------------------------------------------------------------------

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ListStatus {
    id: String,
    name: String,
    url: String,
    custom: bool,
    /// `active`, `waiting` (not downloaded yet) or `error` (no usable copy).
    status: &'static str,
    last_updated: Option<u64>,
    rule_count: u32,
    last_error: Option<String>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct EngineInfo {
    platform: &'static str,
    supported: bool,
    supports_counters: bool,
    coverage_note: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct AdblockState {
    engine: EngineInfo,
    /// `unsupported`, `off`, `waiting`, `compiling`, `ready` or `error`.
    phase: &'static str,
    error: Option<String>,
    catalog: Vec<CatalogItem>,
    lists: Vec<ListStatus>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct CatalogItem {
    id: &'static str,
    name: &'static str,
}

fn platform_name() -> &'static str {
    if cfg!(target_os = "linux") {
        "linux"
    } else if cfg!(windows) {
        "windows"
    } else {
        "macos"
    }
}

pub(crate) fn state(app: &AppHandle) -> AdblockState {
    let settings = current_settings(app);
    let dir = adblock_dir(app).ok();
    let meta = dir.as_deref().map(lists::load_meta).unwrap_or_default();
    let status = STATUS.lock().unwrap();
    let list_status: Vec<ListStatus> = lists::selected_sources(&settings)
        .into_iter()
        .map(|source| {
            let entry = meta.get(&source.id);
            let usable = entry.is_some_and(|meta| !meta.content_hash.is_empty());
            ListStatus {
                status: if usable {
                    "active"
                } else if entry.is_some_and(|meta| meta.last_error.is_some()) {
                    "error"
                } else {
                    "waiting"
                },
                last_updated: entry.and_then(|meta| meta.last_updated),
                rule_count: entry.map_or(0, |meta| meta.network_rules),
                last_error: entry.and_then(|meta| meta.last_error.clone()),
                id: source.id,
                name: source.name,
                url: source.url,
                custom: source.custom,
            }
        })
        .collect();
    let any_usable = list_status.iter().any(|list| list.status == "active");
    let phase = if !super::engine_supported() {
        "unsupported"
    } else if !wanted(&settings) {
        "off"
    } else if status.engine_error.is_some() {
        "error"
    } else if status.compiling > 0 {
        "compiling"
    } else if any_usable {
        "ready"
    } else {
        "waiting"
    };
    let coverage_note = match &status.coverage {
        Some(coverage) if coverage.network_total as usize > coverage.converted => {
            let skipped = coverage.network_total as usize - coverage.converted;
            format!(
                "{skipped} of {} network rules cannot be expressed by this platform's web engine and are skipped, so some blocking differs from desktop browser extensions.",
                coverage.network_total
            )
        }
        _ => "Some filter rules cannot be expressed by this platform's web engine and are skipped, so some blocking differs from desktop browser extensions.".to_string(),
    };
    AdblockState {
        engine: EngineInfo {
            platform: platform_name(),
            supported: super::engine_supported(),
            supports_counters: false,
            coverage_note,
        },
        phase,
        error: status.engine_error.clone(),
        catalog: lists::CATALOG
            .iter()
            .map(|entry| CatalogItem {
                id: entry.id,
                name: entry.name,
            })
            .collect(),
        lists: list_status,
    }
}

fn notify_updated(app: &AppHandle) {
    let _ = app.emit(EVENT_UPDATED, ());
}

fn notify_error(app: &AppHandle, message: &str) {
    crate::startup_diagnostics::log("primary", "adblock.error", message);
    let _ = app.emit(EVENT_ERROR, message.to_string());
}

// ---------------------------------------------------------------------------
// List refresh
// ---------------------------------------------------------------------------

/// Downloads lists that are missing or due. One announcement per failure
/// episode, however many lists or retries are involved.
pub(crate) async fn refresh(app: &AppHandle, force: bool) -> Result<(), String> {
    let _serial = REFRESH_LOCK.lock().await;
    let settings = current_settings(app);
    if !wanted(&settings) {
        return Ok(());
    }
    let dir = adblock_dir(app)?;
    let sources = lists::selected_sources(&settings);
    let keep: Vec<String> = sources.iter().map(|source| source.id.clone()).collect();
    lists::prune(&dir, &keep)?;
    let mut changed = false;
    let mut announcements = Vec::new();
    for source in &sources {
        let meta = lists::load_meta(&dir);
        let entry = meta.get(&source.id);
        let cached = lists::read_cached(&dir, &source.id);
        let due = force
            || cached.is_none()
            || entry
                .and_then(|meta| meta.next_check)
                .is_none_or(|next| next <= now_secs());
        if !due {
            continue;
        }
        let etag = if cached.is_some() {
            entry.and_then(|meta| meta.etag.clone())
        } else {
            None
        };
        let now = now_secs();
        let outcome = match lists::fetch(&source.url, etag.as_deref()).await {
            Ok(lists::Fetched::NotModified) => match &cached {
                Some(text) => lists::mark_unchanged(&dir, &source.id, text, now),
                None => Err("The server reported no changes but no copy is cached".to_string()),
            },
            Ok(lists::Fetched::Body { text, etag }) => lists::validate_list_text(&text)
                .and_then(|stats| {
                    lists::store_list(&dir, &source.id, &source.url, &text, stats, etag, now)
                })
                .map(|did_change| changed |= did_change),
            Err(error) => Err(error),
        };
        if let Err(error) = outcome {
            let message = format!("{}: {error}", source.name);
            if lists::record_failure(&dir, &source.id, &source.url, &message, now)? {
                announcements.push(message);
            }
        }
    }
    if changed {
        reapply_after_change(app);
    }
    notify_updated(app);
    if !announcements.is_empty() {
        let message = if announcements.len() == 1 {
            format!(
                "Ad blocking could not update a filter list. {}",
                announcements[0]
            )
        } else {
            format!(
                "Ad blocking could not update {} filter lists. {}",
                announcements.len(),
                announcements[0]
            )
        };
        notify_error(app, &message);
    }
    Ok(())
}

/// Validates and caches a custom list so adding it gives immediate feedback.
pub(crate) async fn check_list(app: &AppHandle, url: &str) -> Result<lists::ListStats, String> {
    if !super::engine_supported() {
        return Err("Ad blocking is not available on this platform yet".into());
    }
    lists::validate_list_url(url)?;
    let dir = adblock_dir(app)?;
    match lists::fetch(url, None).await? {
        lists::Fetched::NotModified => Err("The server returned no list content".into()),
        lists::Fetched::Body { text, etag } => {
            let stats = lists::validate_list_text(&text)?;
            lists::store_list(
                &dir,
                &lists::custom_list_id(url),
                url,
                &text,
                stats,
                etag,
                now_secs(),
            )?;
            Ok(stats)
        }
    }
}

/// Called after settings that affect blocking changed (or a backup was
/// restored): fetch anything newly selected, then re-apply to running services.
pub(crate) fn settings_changed(app: &AppHandle) {
    if !super::engine_supported() {
        return;
    }
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        if let Err(error) = refresh(&app, false).await {
            notify_error(
                &app,
                &format!("Ad blocking could not update its filter lists. {error}"),
            );
        }
        reapply_after_change(&app);
        notify_updated(&app);
    });
}

/// Background updater: a delayed first pass, then an hourly check that only
/// downloads lists that are due.
pub(crate) fn start(app: &AppHandle) {
    if !super::engine_supported() {
        return;
    }
    warm(app);
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        tokio::time::sleep(STARTUP_DELAY).await;
        loop {
            if let Err(error) = refresh(&app, false).await {
                notify_error(
                    &app,
                    &format!("Ad blocking could not update its filter lists. {error}"),
                );
            }
            tokio::time::sleep(CHECK_INTERVAL).await;
        }
    });
}

/// User-requested refresh of every selected list.
pub(crate) async fn update_now(app: &AppHandle) -> Result<(), String> {
    if !super::engine_supported() {
        return Err("Ad blocking is not available on this platform yet".into());
    }
    refresh(app, true).await
}

// ---------------------------------------------------------------------------
// Applying to webviews
// ---------------------------------------------------------------------------

/// What one service should have attached.
#[cfg(any(target_os = "linux", test))]
#[derive(Debug, Clone)]
struct Desired {
    key: String,
    allowlist: Vec<String>,
    list_ids: Vec<String>,
}

/// Works out the filter a service needs from settings and the cached list
/// metadata. Pure and offline: it never touches the network or the lists
/// themselves, so webview creation can call it on any thread.
#[cfg(any(target_os = "linux", test))]
fn desired_from_meta(
    settings: &serde_json::Value,
    meta: &std::collections::BTreeMap<String, lists::ListMeta>,
    service_id: &str,
) -> Option<Desired> {
    let effective = super::effective_for_service(settings, service_id);
    if !effective.enabled {
        return None;
    }
    let mut list_ids = Vec::new();
    let mut hashes = Vec::new();
    for source in lists::selected_sources(settings) {
        if let Some(entry) = meta.get(&source.id).filter(|m| !m.content_hash.is_empty()) {
            hashes.push(entry.content_hash.clone());
            list_ids.push(source.id);
        }
    }
    if hashes.is_empty() {
        return None;
    }
    Some(Desired {
        key: compile::filter_id(&hashes, &effective.allowlist),
        allowlist: effective.allowlist,
        list_ids,
    })
}

#[cfg(target_os = "linux")]
fn desired_for(app: &AppHandle, settings: &serde_json::Value, service_id: &str) -> Option<Desired> {
    let dir = adblock_dir(app).ok()?;
    desired_from_meta(settings, &lists::load_meta(&dir), service_id)
}

/// The label of a service webview. Only these are ever touched; the shell and
/// internal pages never get a filter.
#[cfg(any(target_os = "linux", test))]
fn service_label(service_id: &str) -> String {
    format!("svc-{service_id}")
}

/// Applies the current settings to one service's webview if it exists.
#[cfg(target_os = "linux")]
pub(crate) fn apply_service(app: &AppHandle, service_id: &str, fresh: bool) {
    let settings = current_settings(app);
    let desired = desired_for(app, &settings, service_id);
    let Some(webview) = app.get_webview(&service_label(service_id)) else {
        return;
    };
    apply_platform(app, &webview, desired, fresh);
}

#[cfg(not(target_os = "linux"))]
pub(crate) fn apply_service(_app: &AppHandle, _service_id: &str, _fresh: bool) {}

/// Applies the current settings to every running service webview.
pub(crate) fn apply_all(app: &AppHandle) {
    let created: Vec<String> = app
        .state::<AppState>()
        .created
        .lock()
        .unwrap()
        .iter()
        .cloned()
        .collect();
    for service_id in created {
        apply_service(app, &service_id, false);
    }
}

fn reapply_after_change(app: &AppHandle) {
    warm(app);
    apply_all(app);
}

/// Preloads the filter used by default so a newly created service can have it
/// attached synchronously.
#[cfg(target_os = "linux")]
fn warm(app: &AppHandle) {
    let settings = current_settings(app);
    if !wanted(&settings) {
        return;
    }
    if let Some(desired) = desired_for(app, &settings, "") {
        warm_platform(app, desired);
    }
}

#[cfg(not(target_os = "linux"))]
fn warm(_app: &AppHandle) {}

#[cfg(target_os = "linux")]
fn apply_platform(
    app: &AppHandle,
    webview: &tauri::Webview<tauri::Wry>,
    desired: Option<Desired>,
    fresh: bool,
) {
    let app = app.clone();
    let label = webview.label().to_string();
    if let Err(error) = webview.with_webview(move |platform| {
        use webkit2gtk::WebViewExt;
        let Some(manager) = platform.inner().user_content_manager() else {
            return;
        };
        linux::apply(&app, &label, &manager, desired, fresh);
    }) {
        crate::startup_diagnostics::log(
            "primary",
            "adblock.apply_error",
            &format!("Unable to reach the service webview: {error}"),
        );
    }
}

#[cfg(target_os = "linux")]
fn warm_platform(app: &AppHandle, desired: Desired) {
    let app_for_main = app.clone();
    let _ = app.run_on_main_thread(move || linux::ensure_filter(&app_for_main, desired));
}

#[cfg(target_os = "linux")]
mod linux {
    use super::{
        adblock_dir, apply_all, compile, lists, notify_error, notify_updated, Coverage, Desired,
        STATUS,
    };
    use crate::adblock::linux_filter::{remove_by_id, Filter, FilterStore};
    use std::cell::RefCell;
    use std::collections::{HashMap, HashSet};
    use std::rc::Rc;
    use tauri::{AppHandle, Manager};
    use webkit2gtk::UserContentManager;

    #[derive(Default)]
    struct MainState {
        store: Option<Rc<FilterStore>>,
        filters: HashMap<String, Filter>,
        /// Filter id attached per webview label.
        attached: HashMap<String, String>,
        inflight: HashSet<String>,
        /// Keys being compiled (a subset of `inflight`).
        compiling: HashSet<String>,
    }

    thread_local! {
        // Filters are GTK objects, so all of this lives on the main thread.
        static MAIN: RefCell<MainState> = RefCell::new(MainState::default());
    }

    fn store(app: &AppHandle) -> Result<Rc<FilterStore>, String> {
        if let Some(existing) = MAIN.with(|m| m.borrow().store.clone()) {
            return Ok(existing);
        }
        let dir = adblock_dir(app)?.join("filters");
        std::fs::create_dir_all(&dir)
            .map_err(|error| format!("Unable to create the filter store: {error}"))?;
        let created = Rc::new(FilterStore::new(&dir)?);
        MAIN.with(|m| m.borrow_mut().store = Some(created.clone()));
        Ok(created)
    }

    pub(super) fn apply(
        app: &AppHandle,
        label: &str,
        manager: &UserContentManager,
        desired: Option<Desired>,
        fresh: bool,
    ) {
        enum Action {
            Nothing,
            Detach(String),
            Attach(Filter, Option<String>),
            Build(Desired),
        }
        let action = MAIN.with(|m| {
            let mut m = m.borrow_mut();
            if fresh {
                // A new webview under an old label has none of the old attachments.
                m.attached.remove(label);
            }
            let current = m.attached.get(label).cloned();
            match desired {
                None => current.map_or(Action::Nothing, Action::Detach),
                Some(wanted) => {
                    if current.as_deref() == Some(wanted.key.as_str()) {
                        Action::Nothing
                    } else if let Some(filter) = m.filters.get(&wanted.key) {
                        Action::Attach(filter.clone(), current)
                    } else {
                        Action::Build(wanted)
                    }
                }
            }
        });
        match action {
            Action::Nothing => {}
            Action::Detach(id) => {
                if let Err(error) = remove_by_id(manager, &id) {
                    crate::startup_diagnostics::log("primary", "adblock.detach_error", &error);
                }
                MAIN.with(|m| m.borrow_mut().attached.remove(label));
            }
            Action::Attach(filter, previous) => {
                if let Some(previous) = previous {
                    let _ = remove_by_id(manager, &previous);
                }
                filter.add_to(manager);
                let key = filter.identifier();
                MAIN.with(|m| m.borrow_mut().attached.insert(label.to_string(), key));
            }
            Action::Build(wanted) => ensure_filter(app, wanted),
        }
    }

    /// Makes sure the compiled filter for `desired` is in memory: load it from
    /// the store, or compile it on a worker thread and save it.
    pub(super) fn ensure_filter(app: &AppHandle, desired: Desired) {
        let first = MAIN.with(|m| {
            let mut m = m.borrow_mut();
            !m.filters.contains_key(&desired.key) && m.inflight.insert(desired.key.clone())
        });
        if !first {
            return;
        }
        let store = match store(app) {
            Ok(store) => store,
            Err(error) => return fail(app, &desired.key, &error),
        };
        let app = app.clone();
        let key = desired.key.clone();
        store.load(&key, move |loaded| match loaded {
            Ok(filter) => finish(&app, &desired.key, Ok(filter)),
            Err(_) => compile_in_background(&app, desired),
        });
    }

    fn compile_in_background(app: &AppHandle, desired: Desired) {
        MAIN.with(|m| {
            let mut m = m.borrow_mut();
            m.compiling.insert(desired.key.clone());
            STATUS.lock().unwrap().compiling = m.compiling.len();
        });
        notify_updated(app);
        let app = app.clone();
        std::thread::spawn(move || {
            let result = (|| {
                let dir = adblock_dir(&app)?;
                let mut texts = Vec::new();
                let mut network_total = 0u32;
                let meta = lists::load_meta(&dir);
                for id in &desired.list_ids {
                    let text = lists::read_cached(&dir, id).ok_or_else(|| {
                        "A cached filter list changed while compiling".to_string()
                    })?;
                    network_total = network_total
                        .saturating_add(meta.get(id).map_or(0, |entry| entry.network_rules));
                    texts.push(text);
                }
                let compiled = compile::compile(&texts, &desired.allowlist)?;
                Ok::<_, String>((compiled, network_total))
            })();
            let app_for_main = app.clone();
            let _ = app.run_on_main_thread(move || match result {
                Err(error) => fail(&app_for_main, &desired.key, &error),
                Ok((compiled, network_total)) => {
                    crate::startup_diagnostics::log(
                        "primary",
                        "adblock.compiled",
                        &format!(
                            "rules={} converted={} network={network_total}",
                            compiled.rule_count, compiled.converted
                        ),
                    );
                    STATUS.lock().unwrap().coverage = Some(Coverage {
                        network_total,
                        converted: compiled.converted,
                    });
                    match store(&app_for_main) {
                        Err(error) => fail(&app_for_main, &desired.key, &error),
                        Ok(store) => {
                            let app_done = app_for_main.clone();
                            let key = desired.key.clone();
                            let save_key = key.clone();
                            store.save(&save_key, &compiled.json, move |saved| match saved {
                                Ok(filter) => finish(&app_done, &key, Ok(filter)),
                                Err(error) => fail(&app_done, &key, &error),
                            });
                        }
                    }
                }
            });
        });
    }

    fn finish(app: &AppHandle, key: &str, result: Result<Filter, String>) {
        MAIN.with(|m| {
            let mut m = m.borrow_mut();
            m.inflight.remove(key);
            m.compiling.remove(key);
            let mut status = STATUS.lock().unwrap();
            status.compiling = m.compiling.len();
            status.engine_error = None;
            if let Ok(filter) = result {
                m.filters.insert(key.to_string(), filter);
            }
        });
        apply_all(app);
        collect_garbage(app);
        notify_updated(app);
    }

    /// Removes compiled filters that no service needs any more (for example
    /// after a list update or an allowlist change).
    fn collect_garbage(app: &AppHandle) {
        let settings = super::current_settings(app);
        let mut keep: HashSet<String> = HashSet::new();
        let services: Vec<String> = app
            .state::<crate::AppState>()
            .created
            .lock()
            .unwrap()
            .iter()
            .cloned()
            .collect();
        for service_id in services
            .iter()
            .map(String::as_str)
            .chain(std::iter::once(""))
        {
            if let Some(desired) = super::desired_for(app, &settings, service_id) {
                keep.insert(desired.key);
            }
        }
        let Ok(dir) = adblock_dir(app).map(|dir| dir.join("filters")) else {
            return;
        };
        let Ok(entries) = std::fs::read_dir(&dir) else {
            return;
        };
        let Ok(store) = store(app) else {
            return;
        };
        let busy = MAIN.with(|m| m.borrow().inflight.clone());
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().to_string();
            let Some(id) = name.strip_prefix("ContentRuleList-") else {
                continue;
            };
            if !id.starts_with("tauridium-") || keep.contains(id) || busy.contains(id) {
                continue;
            }
            let id = id.to_string();
            MAIN.with(|m| m.borrow_mut().filters.remove(&id));
            let log_id = id.clone();
            store.remove(&id, move |result| {
                if let Err(error) = result {
                    crate::startup_diagnostics::log(
                        "primary",
                        "adblock.gc_error",
                        &format!("{log_id}: {error}"),
                    );
                }
            });
        }
    }

    fn fail(app: &AppHandle, key: &str, error: &str) {
        MAIN.with(|m| {
            let mut m = m.borrow_mut();
            m.inflight.remove(key);
            m.compiling.remove(key);
            let mut status = STATUS.lock().unwrap();
            status.compiling = m.compiling.len();
            status.engine_error = Some(error.to_string());
        });
        notify_error(
            app,
            &format!("Ad blocking could not prepare its filter rules. {error}"),
        );
        notify_updated(app);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::collections::BTreeMap;

    fn cached(ids: &[&str]) -> BTreeMap<String, lists::ListMeta> {
        ids.iter()
            .map(|id| {
                (
                    (*id).to_string(),
                    lists::ListMeta {
                        content_hash: format!("hash-{id}"),
                        ..lists::ListMeta::default()
                    },
                )
            })
            .collect()
    }

    fn enabled_settings() -> serde_json::Value {
        json!({
            "adblockEnabled": true,
            "adblockLists": ["easylist", "easyprivacy"],
            "adblockCustomLists": [],
            "adblockAllowlist": [],
            "serviceAdblock": {}
        })
    }

    #[test]
    fn nothing_is_desired_before_any_list_is_cached() {
        // First run with no cache and no network: blocking waits, it does not fail.
        assert!(desired_from_meta(&enabled_settings(), &BTreeMap::new(), "svc").is_none());
    }

    #[test]
    fn cached_lists_alone_are_enough_to_block_offline() {
        // Startup and webview creation depend only on cached metadata.
        let meta = cached(&["easylist", "easyprivacy"]);
        let first = desired_from_meta(&enabled_settings(), &meta, "svc");
        let second = desired_from_meta(&enabled_settings(), &meta, "other");
        if super::super::engine_supported() {
            let first = first.expect("cached lists should produce a filter");
            assert_eq!(first.list_ids, ["easylist", "easyprivacy"]);
            assert_eq!(first.key, second.expect("same lists").key);
        } else {
            assert!(first.is_none());
        }
    }

    #[test]
    fn one_cached_list_is_used_while_another_is_still_missing() {
        let desired = desired_from_meta(&enabled_settings(), &cached(&["easyprivacy"]), "svc");
        if super::super::engine_supported() {
            assert_eq!(desired.unwrap().list_ids, ["easyprivacy"]);
        }
    }

    #[test]
    fn the_filter_changes_when_a_list_or_the_allowlist_changes() {
        if !super::super::engine_supported() {
            return;
        }
        let meta = cached(&["easylist", "easyprivacy"]);
        let base = desired_from_meta(&enabled_settings(), &meta, "svc")
            .unwrap()
            .key;

        let mut updated = meta.clone();
        updated.get_mut("easylist").unwrap().content_hash = "hash-new".into();
        assert_ne!(
            base,
            desired_from_meta(&enabled_settings(), &updated, "svc")
                .unwrap()
                .key
        );

        let mut with_service_allowlist = enabled_settings();
        with_service_allowlist["serviceAdblock"] = json!({ "svc": { "allowlist": ["a.com"] } });
        assert_ne!(
            base,
            desired_from_meta(&with_service_allowlist, &meta, "svc")
                .unwrap()
                .key
        );
        // Other services keep the shared filter, so no extra compile is needed.
        assert_eq!(
            base,
            desired_from_meta(&with_service_allowlist, &meta, "other")
                .unwrap()
                .key
        );
    }

    #[test]
    fn services_sharing_a_sandbox_resolve_independently() {
        let mut settings = enabled_settings();
        settings["serviceSandboxes"] = json!({ "a": "box", "b": "box" });
        settings["serviceAdblock"] = json!({ "a": { "enabled": false } });
        let meta = cached(&["easylist"]);
        assert!(desired_from_meta(&settings, &meta, "a").is_none());
        if super::super::engine_supported() {
            assert!(desired_from_meta(&settings, &meta, "b").is_some());
        }
    }

    #[test]
    fn a_disabled_setting_never_produces_a_filter() {
        let mut settings = enabled_settings();
        settings["adblockEnabled"] = json!(false);
        assert!(desired_from_meta(&settings, &cached(&["easylist"]), "svc").is_none());
        settings["serviceAdblock"] = json!({ "svc": { "enabled": true } });
        let on = desired_from_meta(&settings, &cached(&["easylist"]), "svc");
        assert_eq!(on.is_some(), super::super::engine_supported());
    }

    #[test]
    fn only_service_webviews_are_addressed_never_the_shell() {
        assert_eq!(service_label("abc"), "svc-abc");
        assert_ne!(service_label(""), "main");
        assert!(service_label("main").starts_with("svc-"));
    }
}
