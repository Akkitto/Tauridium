"""Regression checks for the spelling feature that run without a GUI."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SpellingCoreTests(unittest.TestCase):
    def test_toggle_script_behaviour_in_fake_dom(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        result = subprocess.run(
            [node, "tools/spellcheck_toggle_probe.cjs"],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_spelling_is_applied_at_webview_creation_and_on_settings_change(self):
        main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
        self.assertIn("spelling::toggle_init_script(", main)
        self.assertIn("spelling::apply_to_webview(", main)
        self.assertIn("spelling::install_menu_filter(", main)
        self.assertIn("apply_spelling_settings(&app, &state, &value)", main)
        self.assertIn("spelling::prepare_engine(", main)

    def test_spelling_commands_are_allowlisted_for_the_shell_only(self):
        permissions = (ROOT / "src-tauri/permissions/application.toml").read_text(encoding="utf-8")
        app_ui = permissions.split("[[permission]]")[1]
        for command in ("spelling_get_state", "spelling_add_word", "spelling_remove_word"):
            self.assertIn(f'"{command}"', app_ui)
        for other in permissions.split("[[permission]]")[2:]:
            self.assertNotIn("spelling_", other)

    def test_no_spelling_code_sends_typed_text_over_the_network(self):
        source = (ROOT / "src-tauri/src/spelling.rs").read_text(encoding="utf-8")
        for needle in ("reqwest", "http://", "https://", "TcpStream", "UdpSocket"):
            self.assertNotIn(needle, source)
        script = (ROOT / "src-tauri/src/spellcheck_toggle.js").read_text(encoding="utf-8")
        for needle in ("fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket"):
            self.assertNotIn(needle, script)


if __name__ == "__main__":
    unittest.main()
