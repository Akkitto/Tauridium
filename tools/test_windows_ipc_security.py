"""The Windows activation transport must use private DACLs and bounded reads/drains."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WindowsIpcSecurityTests(unittest.TestCase):
  def test_server_and_mutex_use_actual_user_private_security(self):
    source = (ROOT / "src-tauri/src/single_instance.rs").read_text(encoding="utf-8")
    self.assertIn("CreateMutexW(private_security.get()", source)
    pipe = source.split("fn reserve_activation_pipe", 1)[1].split("if pipe == INVALID_HANDLE_VALUE", 1)[0]
    self.assertIn("private_security.get()", pipe)
    self.assertIn("PIPE_REJECT_REMOTE_CLIENTS", pipe)
    self.assertIn("FILE_FLAG_FIRST_PIPE_INSTANCE", pipe)
    security = (ROOT / "src-tauri/src/windows_security.rs").read_text(encoding="utf-8")
    self.assertIn('Self::new("GA")', security)
    self.assertIn("TokenUser", security)

  def test_context_is_sent_only_after_owner_user_and_session_checks(self):
    source = (ROOT / "src-tauri/src/single_instance.rs").read_text(encoding="utf-8")
    send = source.split("unsafe fn send_activation_request", 1)[1].split("unsafe fn verify_pipe_peer", 1)[0]
    self.assertLess(send.index("verify_pipe_peer(pipe, true)?"), send.index("AllowSetForegroundWindow"))
    self.assertLess(send.index("verify_pipe_peer(pipe, true)?"), send.index("write_all(pipe"))
    peer = source.split("unsafe fn verify_pipe_peer", 1)[1].split("fn activation_server_loop", 1)[0]
    for check in ("require_current_user_owner", "require_current_user_process", "current_windows_session_id"):
      self.assertIn(check, peer)
    self.assertIn("SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION", source)
    listener = source.split("fn activation_server_loop", 1)[1].split("unsafe fn handle_activation_client", 1)[0]
    self.assertNotIn("CreateNamedPipeW", listener)
    self.assertNotIn("CloseHandle", listener)
    self.assertIn("exclusive_endpoint_rejects_squatting_and_stays_reserved_between_clients", source)
    self.assertIn("activation_client_limits_impersonation_to_identification", source)

  def test_each_read_has_an_absolute_deadline_and_flush_is_never_unbounded(self):
    source = (ROOT / "src-tauri/src/single_instance.rs").read_text(encoding="utf-8")
    self.assertNotRegex(source, r"\bFlushFileBuffers\s*\(")
    self.assertIn("crate::pipe_security::read_exact_until", source)
    self.assertIn("read_exact(pipe, &mut payload, read_deadline)", source)
    self.assertIn("ACK_RECEIPT_WINDOW", source)
    self.assertIn("MAX_PENDING_ACTIVATIONS", source)
    self.assertIn("pending_activation.deadline <= Instant::now()", source)
    self.assertIn("connected_silent_and_partial_peers_cannot_block_the_native_pipe_forever", source)

  def test_writes_use_overlapped_deadlines_and_drain_cancellation_before_dropping_storage(self):
    source = (ROOT / "src-tauri/src/single_instance.rs").read_text(encoding="utf-8")
    self.assertIn("PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED", source)
    self.assertIn("GetOverlappedResultEx", source)
    self.assertIn("CancelIoEx(self.pipe, self.overlapped.as_ref())", source)
    self.assertIn("write_all(pipe, payload, deadline)", source)
    self.assertIn("large_native_write_to_a_nonreading_peer_times_out_and_cancels_safely", source)
    self.assertIn("large_native_overlapped_transfers_preserve_every_byte", source)

  def test_release_executes_native_windows_quality_and_vault_controls_before_bundling(self):
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    build = workflow.split("  build:\n", 1)[1].split("  scoop:\n", 1)[0]
    self.assertIn("components: rustfmt, clippy", build)
    position = build.index("name: Run native Windows security and application gates")
    self.assertLess(position, build.index("name: Build native bundles"))
    self.assertIn("if: runner.os == 'Windows'\n        run: just quality", build[position:])
    credentials = (ROOT / "src-tauri/src/credentials.rs").read_text(encoding="utf-8")
    self.assertIn("native_windows_vault_migrates_and_removes_only_its_synthetic_session", credentials)


if __name__ == "__main__":
  unittest.main()
