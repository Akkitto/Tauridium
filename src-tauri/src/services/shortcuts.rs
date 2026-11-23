//! Authenticated shortcut bridge for service webviews.

use serde_json::Value;
use sha2::{Digest, Sha256};
use std::sync::atomic::AtomicU64;
use std::sync::atomic::Ordering;
use std::time::SystemTime;
use std::time::UNIX_EPOCH;
use tauri::Url;

pub(crate) const SHORTCUT_ACTIONS: [&str; 16] = [
    "quickWorkspaceSwitch",
    "quickServiceSwitch",
    "openSettings",
    "addService",
    "addWorkspace",
    "toggleSidebar",
    "nextService",
    "previousService",
    "nextWorkspace",
    "previousWorkspace",
    "reloadService",
    "reloadApp",
    "zoomIn",
    "zoomOut",
    "resetZoom",
    "toggleDevtools",
];

static SERVICE_SHORTCUT_NONCE_COUNTER: AtomicU64 = AtomicU64::new(0);

pub(super) fn next_service_shortcut_nonce(service_id: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(service_id.as_bytes());
    hasher.update(std::process::id().to_le_bytes());
    hasher.update(
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
            .to_le_bytes(),
    );
    hasher.update(
        SERVICE_SHORTCUT_NONCE_COUNTER
            .fetch_add(1, Ordering::Relaxed)
            .to_le_bytes(),
    );
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let digest = hasher.finalize();
    let mut nonce = String::with_capacity(digest.len() * 2);
    for byte in digest.iter().copied() {
        nonce.push(char::from(HEX[(byte >> 4) as usize]));
        nonce.push(char::from(HEX[(byte & 0x0f) as usize]));
    }
    nonce
}

pub(super) fn service_shortcut_action_from_url(url: &Url, expected_nonce: &str) -> Option<String> {
    if url.scheme() != "tauridium-shortcut" || url.host_str() != Some("bridge") {
        return None;
    }
    let mut segments = url.path_segments()?;
    let nonce = segments.next()?;
    let action = segments.next()?;
    if segments.next().is_some() || nonce != expected_nonce || !SHORTCUT_ACTIONS.contains(&action) {
        return None;
    }
    Some(action.to_string())
}

fn effective_service_shortcut_capture(settings: &Value, service_id: &str) -> bool {
    let global = settings
        .get("captureServiceShortcuts")
        .and_then(Value::as_bool)
        .unwrap_or(true);
    settings
        .get("serviceShortcutCaptureOverrides")
        .and_then(Value::as_object)
        .and_then(|overrides| overrides.get(service_id))
        .and_then(Value::as_bool)
        .unwrap_or(global)
}

pub(super) fn service_shortcut_bridge_js(
    settings: &Value,
    service_id: &str,
    nonce: &str,
) -> Option<String> {
    if !effective_service_shortcut_capture(settings, service_id) {
        return None;
    }
    let bindings = settings.get("keybindings").and_then(Value::as_object)?;
    let mut captured = serde_json::Map::new();
    for action in SHORTCUT_ACTIONS {
        if let Some(binding) = bindings
            .get(action)
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|binding| !binding.is_empty())
        {
            captured.insert(action.to_string(), Value::String(binding.to_string()));
        }
    }
    if captured.is_empty() {
        return None;
    }
    let bindings_json = serde_json::to_string(&captured).ok()?;
    let nonce_json = serde_json::to_string(nonce).ok()?;
    Some(format!(
        r#"(function(){{
  var bindings = {bindings_json};
  var token = {nonce_json};
  var pending = null;
  var pendingAt = 0;
  var timeoutMs = 1800;
  function strokes(binding){{ return String(binding || '').trim().split(/\s+/).filter(Boolean).slice(0, 2); }}
  function stroke(e){{
    if (['Control','Shift','Alt','Meta'].indexOf(e.key) !== -1) return null;
    var parts = [];
    if (e.ctrlKey) parts.push('Ctrl');
    if (e.altKey) parts.push('Alt');
    if (e.shiftKey) parts.push('Shift');
    if (e.metaKey) parts.push('Meta');
    var code = String(e.code || '');
    var codeKeys = {{Comma:',',Period:'.',Minus:'-',Equal:'=',Semicolon:';',Quote:"'",BracketLeft:'[',BracketRight:']',Backslash:'\\',Backquote:'`',Space:'Space',Tab:'Tab',ArrowDown:'ArrowDown',ArrowUp:'ArrowUp',ArrowLeft:'ArrowLeft',ArrowRight:'ArrowRight'}};
    var key = /^Key[A-Z]$/.test(code) ? code.slice(3) : (/^Digit[0-9]$/.test(code) ? code.slice(5) : codeKeys[code]);
    if (!key) key = e.key === ' ' ? 'Space' : (e.key && e.key.length === 1 ? e.key.toUpperCase() : e.key);
    if (!key) return null;
    parts.push(key);
    return parts.join('+');
  }}
  function dispatch(action){{
    try {{
      window.location.href = 'tauridium-shortcut://bridge/' + token + '/' + action;
    }} catch (_) {{}}
  }}
  window.addEventListener('keydown', function(e){{
    if (!e.isTrusted) return;
    var current = stroke(e);
    if (!current) return;
    var entries = Object.entries(bindings);
    var now = Date.now();
    if (pending && now - pendingAt >= timeoutMs) pending = null;
    if (pending) {{
      var chord = entries.find(function(entry){{ var seq = strokes(entry[1]); return seq.length === 2 && seq[0] === pending && seq[1] === current; }});
      pending = null;
      if (chord) {{
        e.preventDefault();
        e.stopImmediatePropagation();
        dispatch(chord[0]);
        return;
      }}
    }}
    var hasPrefix = entries.some(function(entry){{ var seq = strokes(entry[1]); return seq.length === 2 && seq[0] === current; }});
    if (hasPrefix) {{
      e.preventDefault();
      e.stopImmediatePropagation();
      pending = current;
      pendingAt = now;
      return;
    }}
    var single = entries.find(function(entry){{ var seq = strokes(entry[1]); return seq.length === 1 && seq[0] === current; }});
    if (single) {{
      e.preventDefault();
      e.stopImmediatePropagation();
      dispatch(single[0]);
    }}
  }}, true);
}})();"#
    ))
}

#[cfg(test)]
mod tests;
