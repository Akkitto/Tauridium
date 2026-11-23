//! Bounded native notification and unread-badge polling.

use crate::{notification_security, service_badges, show_system_notification, AppState};
use serde_json::Value;
use tauri::{AppHandle, Emitter, Manager};

pub(crate) fn start_badge_poller(app: AppHandle) {
    std::thread::spawn(move || loop {
        std::thread::sleep(std::time::Duration::from_secs(2));
        let services: Vec<String> = app
            .state::<AppState>()
            .created
            .lock()
            .unwrap()
            .iter()
            .cloned()
            .collect();
        for sid in services {
            let Some(wv) = app.get_webview(&format!("svc-{sid}")) else {
                continue;
            };
            let app2 = app.clone();
            let source_host = wv
                .url()
                .ok()
                .and_then(|url| url.host_str().map(str::to_string))
                .unwrap_or_else(|| "Service".into());
            let _ = wv.eval_with_callback(
                "(function(){var q=window.__pakeNotifQueue;window.__pakeNotifQueue=[];return {u: Math.max(0, parseInt(window.__pakeUnread)||0), b:window.__pakeBadge, a:window.__pakeAppBadge, n: Array.isArray(q)?q.slice(0,8).map(function(v){return {title:String(v.title||'').slice(0,160),body:String(v.body||'').slice(0,1024)};}):[]};})()",
                move |res| {
                    if res.len() > 64 * 1024 {
                        return;
                    }
                    let v: serde_json::Value =
                        serde_json::from_str(&res).unwrap_or(serde_json::Value::Null);
                    let st = app2.state::<AppState>();
                    let flags = st.flags.lock().unwrap().get(&sid).copied().unwrap_or_default();
                    let unread = service_badges::unread(&v, flags.indirect_badge).clamp(0, 1_000_000);

                    // Notifications: honor mute and disabled-notification settings.
                    if flags.notif && !flags.muted && st.created.lock().unwrap().contains(&sid) {
                        let private = st
                            .settings
                            .lock()
                            .unwrap()
                            .get("privateNotifications")
                            .and_then(Value::as_bool)
                            .unwrap_or(false);
                        if let Some(arr) = v.get("n").and_then(|x| x.as_array()) {
                            for notif in arr.iter().take(8) {
                                let title = notification_security::text(notif
                                    .get("title")
                                    .and_then(|x| x.as_str())
                                    .unwrap_or("")
                                    , 160);
                                let body = notification_security::text(notif.get("body").and_then(|x| x.as_str()).unwrap_or(""), 1024);
                                if title.is_empty() && body.is_empty() {
                                    continue;
                                }
                                if !st.notification_budget.lock().unwrap().allow(&sid, std::time::Instant::now()) {
                                    break;
                                }
                                let _ = if private {
                                    show_system_notification(&app2, "New message", None)
                                } else {
                                    let source = format!("Tauridium • {}", notification_security::text(&source_host, 120));
                                    let content = if title.is_empty() { body } else if body.is_empty() { title } else { format!("{title}\n{body}") };
                                    show_system_notification(&app2, &source, Some(&content))
                                };
                            }
                        }
                    }

                    // Store raw counts per service for the sidebar and calculate the dock total
                    // with flags applied and emit the unread-count map to the shell.
                    // The service may have been closed/hibernated/deleted between the snapshot and this
                    // async callback; in that case do NOT reinsert it, otherwise it would remain
                    // in the total forever and create a phantom dock badge.
                    let still_exists = st.created.lock().unwrap().contains(&sid);
                    let (map, total) = {
                        let mut m = st.unread.lock().unwrap();
                        if still_exists {
                            m.insert(sid.clone(), unread);
                        } else {
                            m.remove(&sid);
                        }
                        let f = st.flags.lock().unwrap();
                        let total: i64 = m
                            .iter()
                            .map(|(id, &u)| {
                                let fl = f.get(id).copied().unwrap_or_default();
                                if fl.badge && !fl.muted {
                                    u
                                } else {
                                    0
                                }
                            })
                            .sum();
                        (m.clone(), total)
                    };
                    let _ = app2.emit("unread", &map);
                    if let Some(win) = app2.get_window("main") {
                        let _ = win.set_badge_count(if total > 0 { Some(total) } else { None });
                    }
                },
            );
        }
    });
}
