"""Keep the runtime security fixes and compatibility patches selected together."""
import json
from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RuntimeSecurityUpgradeTests(unittest.TestCase):
  def test_client_requires_version_bound_signatures_without_insecure_overrides(self):
    config = json.loads((ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    updater = config["plugins"]["updater"]
    self.assertIs(updater["requireSignedVersion"], True)
    for key in ("allowDowngrades", "dangerousAcceptInvalidCerts", "dangerousAcceptInvalidHostnames",
                "dangerousInsecureTransportProtocol"):
      self.assertFalse(updater.get(key, False), key)
    manifest = tomllib.loads((ROOT / "src-tauri/Cargo.toml").read_text(encoding="utf-8"))
    self.assertEqual(manifest["dependencies"]["tauri-plugin-updater"]["version"], "=2.14.0")

  def test_channel_fetch_is_bound_to_actual_caller_and_upstream_regressions_remain(self):
    source = (ROOT / "vendor/tauri/src/ipc/channel.rs").read_text(encoding="utf-8")
    fetch = source.split("fn fetch<R: Runtime>(", 1)[1].split("pub fn plugin", 1)[0]
    self.assertIn("webview: Webview<R>", fetch)
    self.assertIn("cache.remove(webview.label(), id)", fetch)
    for test in ("queue_entries_are_scoped_to_the_owning_webview", "ids_are_scoped_per_webview",
                 "channel_data_is_not_queued_after_the_webview_closes"):
      self.assertIn("fn " + test, source)

  def test_glib_backport_uses_mutable_c_out_argument_and_path_dependency(self):
    source = (ROOT / "vendor/glib/src/variant_iter.rs").read_text(encoding="utf-8")
    implementation = source.split("fn impl_get(", 1)[1].split("impl<'a> Iterator", 1)[0]
    self.assertIn("let mut p:", implementation)
    self.assertIn("&mut p,", implementation)
    manifest = tomllib.loads((ROOT / "src-tauri/Cargo.toml").read_text(encoding="utf-8"))
    self.assertEqual(manifest["patch"]["crates-io"]["glib"]["path"], "../vendor/glib")


if __name__ == "__main__":
  unittest.main()
