"""The privileged shell never admits remote/eval script or production HMR."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ShellCspTests(unittest.TestCase):
  def test_shell_csp_keeps_native_ipc_and_icons_but_rejects_injected_code(self):
    config = json.loads((ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    security = config["app"]["security"]
    for name in ("csp", "devCsp"):
      csp = security[name]
      self.assertEqual(csp["script-src"], "'self'")
      self.assertNotIn("dangerousDisableAssetCspModification", security)
      for directive in ("object-src", "frame-src", "worker-src", "base-uri", "form-action"):
        self.assertEqual(csp[directive], "'none'")
      self.assertIn("http://ipc.localhost", csp["connect-src"])
      self.assertIn("https:", csp["img-src"])
    self.assertNotIn("ws:", security["csp"]["connect-src"])
    self.assertNotIn("localhost:1420", security["csp"]["connect-src"])
    self.assertIn("ws://localhost:1420", security["devCsp"]["connect-src"])


if __name__ == "__main__":
  unittest.main()
