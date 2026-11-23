//! Service orchestration. Commands share one lifecycle, preserving view identity and sessions.

mod badges;
pub(crate) mod commands;
mod downloads;
pub(crate) mod lifecycle;
pub(crate) mod navigation;
mod shortcuts;
mod storage;
mod webview;

pub(crate) use badges::start_badge_poller;
pub(crate) use lifecycle::{hide_service_webviews, service_rect, service_toast_overlay_script};
pub(crate) use shortcuts::SHORTCUT_ACTIONS;

#[cfg(test)]
mod tests;
