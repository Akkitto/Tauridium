#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.4.4 backup, audit, export, and layout hardening."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Patch0404Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    cls.backup = (ROOT / "src-tauri/src/backup.rs").read_text(encoding="utf-8")
    cls.audit = (ROOT / "src-tauri/src/audit.rs").read_text(encoding="utf-8")
    cls.portable = (ROOT / "src-tauri/src/portable.rs").read_text(encoding="utf-8")
    cls.api = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
    cls.app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")

  def test_restore_does_not_roll_back_machine_autostart(self) -> None:
    body = self.main.split("fn perform_restore_backup", 1)[1].split("#[tauri::command]\nfn restore_backup", 1)[0]
    rollback = body.split("if let Err(error) = commit", 1)[1].split("*state.local_profile.lock().unwrap() = local_profile", 1)[0]
    self.assertNotIn("apply_autostart_setting", rollback)
    self.assertLess(
      body.index("*state.local_profile.lock().unwrap() = local_profile"),
      body.index("apply_autostart_setting(app, &app_settings)"),
    )
    self.assertIn("Backup data restored successfully", body)
    self.assertIn("with_warning", body)

  def test_autostart_updates_are_idempotent(self) -> None:
    body = self.main.split("fn apply_autostart_setting", 1)[1].split("fn persist_app_settings", 1)[0]
    self.assertIn(".autolaunch()", body)
    self.assertIn(".is_enabled()", body)
    self.assertNotIn(".is_enabled().ok()", body)
    self.assertIn("Unable to inspect autostart state", body)
    self.assertIn("autostart_needs_update", body)
    self.assertIn("return Ok(())", body)
    self.assertIn("autostart_application_is_idempotent_when_os_state_already_matches", self.main)

  def test_automatic_backup_directory_is_persisted_validated_and_user_selectable(self) -> None:
    for marker in (
      'settings.insert("automaticBackupDirectory".into(), "".into());',
      'automaticBackupDirectory: string;',
      'automatic_backup_root(&app, &app_settings)',
      'title: "Choose automatic backup folder"',
      'directory: true',
      'saveAppSetting("automaticBackupDirectory", path)',
      'useDefaultAutomaticBackupDirectory',
    ):
      self.assertIn(marker, self.main + self.api + self.app)

  def test_automatic_backup_directory_rejects_invalid_persisted_values(self) -> None:
    validation = self.main.split("fn validate_app_settings_value", 1)[1].split("fn merge_app_settings_value", 1)[0]
    self.assertIn('get("automaticBackupDirectory")', validation)
    self.assertIn("backup_directory.len() > 4096", validation)
    self.assertIn("char::is_control", validation)

  def test_settings_panel_uses_wider_dynamic_width_and_wrapping_tabs(self) -> None:
    panel = self.app.split(".settings-panel {", 1)[1].split(".settings-head", 1)[0]
    tabs = self.app.split(".settings-tabs {", 1)[1].split(".setting-tab {", 1)[0]
    self.assertIn("min(1180px, calc(100% - 32px))", panel)
    self.assertIn("flex-wrap: wrap", tabs)
    self.assertIn("overflow: visible", tabs)
    self.assertNotIn("overflow-x: auto", tabs)
    tab = self.app.split(".setting-tab {", 1)[1].split(".setting-tab:hover", 1)[0]
    self.assertIn("flex: 1 1 auto", tab)
    self.assertIn("min-width: max-content", tab)

  def test_backup_retention_supports_count_age_combined_and_tiered_modes(self) -> None:
    for marker in (
      '"count" => Ok(Self::Count)',
      '"age" => Ok(Self::Age)',
      '"countAndAge" => Ok(Self::CountAndAge)',
      '"tiered" => Ok(Self::Tiered)',
      '<option value="count">Newest backup count</option>',
      '<option value="age">Maximum age</option>',
      '<option value="countAndAge">Count and maximum age</option>',
      '<option value="tiered">Tiered history (GFS-style)</option>',
    ):
      self.assertIn(marker, self.backup + self.app)

  def test_tiered_retention_preserves_daily_weekly_monthly_yearly_history(self) -> None:
    body = self.backup.split("RetentionMode::Tiered =>", 1)[1].split("}\n    }", 1)[0]
    for marker in ("days <= 7", "days <= 35", "days <= 400", "5 * 366", 'format!("day:', 'format!("week-age:', 'format!("month:', 'format!("year:'):
      self.assertIn(marker, body)
    self.assertIn("Tiered history", self.app)
    self.assertIn("Daily → weekly → monthly → yearly", self.app)

  def test_retention_never_runs_before_new_backup_verifies(self) -> None:
    body = self.main.split("fn create_automatic_backup", 1)[1].split("fn restore_recovery_backup_path", 1)[0]
    save = body.index("backup::save(&path, &document)?")
    prune = body.index("prune_automatic_backups(&root, retention_mode, retention, max_age_days, &path)")
    self.assertLess(save, prune)
    self.assertIn("Backup was created and verified, but retention cleanup failed", body)
    self.assertIn("summary = summary.with_warning(warning)", body)

  def test_automatic_retention_only_targets_exact_tauridium_backup_names(self) -> None:
    validator = self.main.split("fn validate_automatic_backup_filename", 1)[1].split("fn prune_automatic_backups", 1)[0]
    prune = self.main.split("fn prune_automatic_backups", 1)[1].split("#[tauri::command]", 1)[0]
    self.assertIn("stamp.len() != 21", validator)
    self.assertIn("days_in_month(year, month)", validator)
    self.assertIn("validate_automatic_backup_filename(name).is_ok()", prune)
    self.assertIn("protected_path: &Path", prune)
    self.assertIn("Some(protected_path)", prune)

  def test_backup_module_has_expanded_corruption_and_atomicity_tests(self) -> None:
    for marker in (
      "backup_save_replaces_existing_valid_target_with_verified_content",
      "backup_save_clears_stale_staging_file_before_verified_write",
      "backup_load_rejects_truncated_json_and_integrity_tampering",
      "backup_summary_accumulates_nonfatal_warnings",
      "count_retention_is_deterministic_when_timestamps_match",
      "future_modified_time_is_treated_as_recent_not_expired",
      "count_retention_protects_just_created_backup_from_future_mtime",
      "calendar_keys_require_expected_automatic_backup_prefix_and_shape",
    ):
      self.assertIn(marker, self.backup)

  def test_audit_log_is_rotated_redacted_and_flushes_events(self) -> None:
    for marker in (
      'const MAX_AUDIT_FILE_BYTES: u64 = 5 * 1024 * 1024;',
      'const AUDIT_ROTATIONS: usize = 4;',
      "fn sensitive_key",
      'Value::String("[redacted]".into())',
      "rotate_if_needed(&path)?",
      "file.sync_data()",
      "audit_redaction_matches_secret_like_keys_case_insensitively",
      "static AUDIT_LOCK: Mutex<()> = Mutex::new(())",
      "read_all_entries(app)?",
    ):
      self.assertIn(marker, self.audit)

  def test_audit_tab_can_filter_refresh_export_and_clear(self) -> None:
    for marker in (
      '["audit", "Audit log"]',
      '{:else if settingsTab === "audit"}',
      'placeholder="Search audit events…"',
      "Filter audit events by level",
      "refreshAuditLog",
      "doExportAuditLog",
      "doClearAuditLog",
      'invoke("get_audit_log", { limit })',
      'invoke("export_audit_log", { path })',
      'invoke("clear_audit_log")',
    ):
      self.assertIn(marker, self.app + self.api)

  def test_settings_backup_and_portable_operations_are_audited(self) -> None:
    for marker in (
      '"settings",\n                "change"',
      '"settings",\n        "reorder"',
      '"backup",\n                "export"',
      '"backup",\n                "restore"',
      '"backup",\n                "automatic"',
      '"export",\n                "portable"',
    ):
      self.assertIn(marker, self.main)

  def test_sandbox_exports_support_individual_and_all_with_referenced_services(self) -> None:
    for marker in (
      "sandboxPortablePayload(sandboxId?: string)",
      'doPortableExport("sandboxes", "all sandboxes", sandboxPortablePayload())',
      'doPortableExport("sandbox", `sandbox ${sandbox.name}`, sandboxPortablePayload(sandbox.id))',
      "serviceSandboxId(service.id)",
      "workspace.services.filter((serviceId) => serviceIds.has(serviceId))",
      "select_custom_recipes",
      'service.get("recipeId")',
    ):
      self.assertIn(marker, self.app + self.portable)

  def test_workspace_exports_support_individual_and_all(self) -> None:
    for marker in (
      "workspacePortablePayload(workspaceId?: string)",
      'doPortableExport("workspaces", "all workspaces", workspacePortablePayload())',
      'doPortableExport("workspace", `workspace ${selectedWorkspaceName}`, workspacePortablePayload(selectedWorkspaceId))',
      "selectedWorkspaces.flatMap((workspace) => workspace.services)",
    ):
      self.assertIn(marker, self.app)

  def test_portable_exports_are_integrity_protected_and_atomically_replaced(self) -> None:
    for marker in (
      'const PORTABLE_FORMAT: &str = "tauridium-portable-collection";',
      'payload_sha256',
      'Sha256::digest',
      "file.sync_all()",
      "verified.validate()?",
      "replace_file(&staging, path)",
      "portable_export_detects_payload_tampering",
      "portable_export_clears_stale_staging_and_replaces_existing_file",
      "portable_export_rejects_dangling_workspace_service_references",
      "portable_export_rejects_dangling_sandbox_assignments",
    ):
      self.assertIn(marker, self.portable)

  def test_percentage_sidebar_width_is_bounded_and_resize_throttled(self) -> None:
    for marker in (
      'sidebarWidthMode: "pixels"',
      'sidebarWidthPercent: 20',
      '"pixels" | "percent"',
      'window.innerWidth * (appSettings.sidebarWidthPercent / 100)',
      'requestAnimationFrame',
      'window.addEventListener("resize", handleWindowResize)',
      'window.removeEventListener("resize", handleWindowResize)',
      'appSettings.sidebarWidthMode !== "percent"',
    ):
      self.assertIn(marker, self.main + self.api + self.app)
    self.assertIn('("sidebarWidthPercent", 10.0, 40.0)', self.main)

  def test_percentage_sidebar_ui_discloses_resize_cost(self) -> None:
    self.assertIn("Relative mode recalculates the service viewport while the window is resized", self.app)
    self.assertIn("animation-frame throttled", self.app)
    self.assertIn("automaticBackupRunning = $state(false)", self.app)

  def test_service_position_wording_is_replaced(self) -> None:
    self.assertIn("Service list alignment", self.app)
    self.assertNotIn("Service position", self.app)

  def test_new_settings_are_part_of_app_settings_and_therefore_backup_payload(self) -> None:
    for marker in (
      'settings.insert("sidebarWidthMode".into(), "pixels".into());',
      'settings.insert("sidebarWidthPercent".into(), 20.into());',
      'settings.insert("automaticBackupDirectory".into(), "".into());',
      'settings.insert("automaticBackupRetentionMode".into(), "count".into());',
      'settings.insert("automaticBackupMaxAgeDays".into(), 90.into());',
    ):
      self.assertIn(marker, self.main)
    export = self.main.split("fn export_backup", 1)[1].split("fn automatic_backup_root", 1)[0]
    self.assertIn("effective_app_settings_value(&app)", export)
    self.assertIn("BackupDocument::new", export)

  def test_new_backend_commands_are_registered(self) -> None:
    handler = self.main.split("tauri::generate_handler![", 1)[1].split("]", 1)[0]
    for command in ("export_portable_bundle", "get_audit_log", "export_audit_log", "clear_audit_log"):
      self.assertIn(command, handler)

  def test_audit_details_do_not_render_as_unbounded_single_line_content(self) -> None:
    css = self.app.split(".audit-entry pre {", 1)[1].split("}", 1)[0]
    self.assertIn("max-height", css)
    self.assertIn("overflow: auto", css)
    self.assertIn("white-space: pre-wrap", css)
    self.assertIn("overflow-wrap: anywhere", css)

  def test_long_automatic_backup_paths_cannot_overflow_settings_card(self) -> None:
    self.assertIn("backup-location-row code", self.app)
    self.assertIn("text-overflow: ellipsis", self.app)
    self.assertIn("white-space: nowrap", self.app)
    self.assertIn("title={appSettings.automaticBackupDirectory", self.app)


if __name__ == "__main__":
  unittest.main()
