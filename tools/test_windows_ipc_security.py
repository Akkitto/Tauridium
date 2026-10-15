"""The Windows activation transport must use private DACLs and bounded reads/drains."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WindowsIpcSecurityTests(unittest.TestCase):
  def test_server_and_mutex_use_actual_user_private_security(self):
    source = (ROOT / "src-tauri/src/single_instance.rs").read_text(encoding="utf-8")
    self.assertIn("CreateMutexW(private_security.get()", source)
    pipe = source.split("let pipe = CreateNamedPipeW(", 1)[1].split(");", 1)[0]
    self.assertIn("private_security.get()", pipe)
    self.assertIn("PIPE_REJECT_REMOTE_CLIENTS", pipe)
    security = (ROOT / "src-tauri/src/windows_security.rs").read_text(encoding="utf-8")
    self.assertIn('Self::new("GA")', security)
    self.assertIn("TokenUser", security)

  def test_each_read_has_an_absolute_deadline_and_flush_is_never_unbounded(self):
    source = (ROOT / "src-tauri/src/single_instance.rs").read_text(encoding="utf-8")
    self.assertNotRegex(source, r"\bFlushFileBuffers\s*\(")
    self.assertIn("crate::pipe_security::read_exact_until", source)
    self.assertIn("read_exact(pipe, &mut payload, read_deadline)", source)
    self.assertIn("ACK_RECEIPT_WINDOW", source)
    self.assertIn("MAX_PENDING_ACTIVATIONS", source)
    self.assertIn("pending_activation.deadline <= Instant::now()", source)
    self.assertIn("connected_silent_and_partial_peers_cannot_block_the_native_pipe_forever", source)


if __name__ == "__main__":
  unittest.main()
