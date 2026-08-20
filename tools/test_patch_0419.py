"""Regression coverage for Tauridium 0.4.19 service-toast encoding test."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")


class Patch0419Tests(unittest.TestCase):
  def test_service_toast_security_test_uses_canonical_json_encoding(self) -> None:
    test_block = MAIN.split(
      "fn service_toast_overlay_script_encodes_untrusted_text_without_page_global()", 1
    )[1].split("#[test]", 1)[0]

    self.assertIn('let encoded = serde_json::to_string(message).unwrap();', test_block)
    self.assertIn('assert!(script.contains(&format!(\")({encoded},2600);\")));', test_block)
    self.assertIn('assert!(!script.contains(message));', test_block)

  def test_service_toast_overlay_still_encodes_before_native_eval(self) -> None:
    function_block = MAIN.split("fn service_toast_overlay_script(", 1)[1].split(
      "const SHORTCUT_ACTIONS", 1
    )[0]

    self.assertIn("serde_json::to_string(message)", function_block)
    self.assertIn("})({encoded},{duration_ms});", function_block)
    self.assertNotIn("window.__tauridiumShowToast", function_block)
    self.assertIn("attachShadow", function_block)


if __name__ == "__main__":
  unittest.main()
