"""Run the real notification shim and assert authoritative native limits remain."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NotificationSecurityTests(unittest.TestCase):
  @unittest.skipUnless(shutil.which("node"), "Node required")
  def test_real_service_shim_keeps_only_eight_bounded_notifications(self):
    source = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    script = re.search(r'const IPC_SHIM_JS: &str = r#"(.*?)"#;', source, re.S).group(1)
    probe = f"""
      const vm = require('node:vm');
      const window = {{}};
      vm.runInNewContext({json.dumps(script)}, {{window}});
      for (let i=0;i<1000;i++) new window.Notification('T'.repeat(10000), {{body:'B'.repeat(10000)}});
      const q = window.__pakeNotifQueue;
      if (q.length !== 8 || q.some(n=>n.title.length!==160 || n.body.length!==1024)) process.exit(1);
    """
    subprocess.run([shutil.which("node"), "-e", probe], check=True, capture_output=True, timeout=20)

  def test_native_poller_rechecks_bounds_rate_and_authoritative_source(self):
    source = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
    poller = source.split("fn start_badge_poller", 1)[1].split("fn default_app_settings", 1)[0]
    self.assertIn("source_host=wv.url()", re.sub(r"\s+", "", poller))
    for guard in ("res.len() > 64 * 1024", "arr.iter().take(8)", "notification_budget",
                  "notification_security::text", ".clamp(0, 1_000_000)"):
      self.assertIn(guard, poller)


if __name__ == "__main__":
  unittest.main()
