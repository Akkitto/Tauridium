#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.5.2 sidebar identity and sign-out UX."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
MAIN = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")


class Patch0502Tests(unittest.TestCase):
  def test_sidebar_reclaims_sign_out_space_for_workspace_scope(self) -> None:
    sidebar = APP.split('<aside class="sidebar"', 1)[1].split('<div class="svcarea"', 1)[0]

    self.assertNotIn("handleLogout", sidebar)
    self.assertNotIn(">sign out</button>", sidebar)
    self.assertIn('class="workspace-scope"', sidebar)
    self.assertIn("{activeWorkspaceName}", sidebar)

  def test_workspace_scope_tracks_active_workspace_and_all_services(self) -> None:
    derived = APP.split("const activeWorkspaceName = $derived(", 1)[1].split("const visibleServices", 1)[0]

    self.assertIn("activeWorkspace", derived)
    self.assertIn("workspaces.find", derived)
    self.assertIn('?.name ?? "All services"', derived)
    self.assertIn(': "All services"', derived)
    self.assertIn("text-overflow: ellipsis", APP.split(".workspace-scope", 1)[1].split("}", 1)[0])

  def test_tauridium_menu_places_sign_out_between_show_all_and_exit(self) -> None:
    builder = MAIN.split("fn build_native_application_menu", 1)[1].split("let edit =", 1)[0]

    self.assertIn('MenuItem::with_id(app, "sign-out", "Sign out", signed_in', builder)
    show_all = builder.index("PredefinedMenuItem::show_all")
    sign_out = builder.index("&sign_out_item")
    quit_item = builder.index("PredefinedMenuItem::quit")
    self.assertLess(show_all, sign_out)
    self.assertLess(sign_out, quit_item)
    between_show_and_signout = builder[show_all:sign_out]
    between_signout_and_quit = builder[sign_out:quit_item]
    self.assertIn("PredefinedMenuItem::separator", between_show_and_signout)
    self.assertIn("PredefinedMenuItem::separator", between_signout_and_quit)

  def test_native_sign_out_is_session_aware_and_routes_through_frontend_cleanup(self) -> None:
    builder = MAIN.split("fn build_native_application_menu", 1)[1].split("let edit =", 1)[0]
    events = MAIN.split("// Native application menu", 1)[1].split("// Request notification", 1)[0]

    self.assertIn("*state.local_mode.lock().unwrap() || state.token.lock().unwrap().is_some()", builder)
    self.assertIn('"sign-out" => {', events)
    self.assertIn('app.emit("sign-out", ())', events)
    self.assertIn('listen("sign-out", handleLogout);', APP)
    logout_body = APP.split("async function handleLogout()", 1)[1].split("function cancelReconnect", 1)[0]
    self.assertIn("await closeServices();", logout_body)
    self.assertIn("await logout();", logout_body)
    self.assertIn("await refreshNativeServicesMenu();", logout_body)


if __name__ == "__main__":
  unittest.main()
