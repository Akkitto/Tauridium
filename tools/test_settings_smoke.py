"""Portable locator regressions; the actual Settings gate runs a production GUI."""
import unittest

from settings_smoke import control_phrase


def row(text, left, block=1, top=40):
  return {"text": text, "left": left, "top": top, "width": 20, "height": 20,
          "page_num": "1", "block_num": str(block), "par_num": "1", "line_num": "1"}


class SettingsSmokeTests(unittest.TestCase):
  def test_description_is_not_mistaken_for_a_select_value(self):
    rows = [row("Filename", 10), row("only", 40), row("keeps", 70),
            row("Filename", 100, block=2), row("only", 130, block=2)]
    self.assertEqual(control_phrase(rows, "Filename only"), (125, 50))

  def test_offscreen_or_clipped_value_is_not_clickable(self):
    rows = [row("Filename", 10), row("only", 40), row("keeps", 70)]
    self.assertIsNone(control_phrase(rows, "Filename only"))
    self.assertIsNone(control_phrase([row("Filename", 10)], "Filename only"))

  def test_native_indicator_and_case_preserve_the_value_bounds(self):
    rows = [row("filename", 10), row("ONLY", 40), row("v", 90)]
    self.assertEqual(control_phrase(rows, "Filename only"), (35, 50))

  def test_partial_and_duration_values_require_complete_lines(self):
    self.assertEqual(control_phrase([row("Partial", 10), row("file", 40), row("path", 70)], "Partial file path"), (50, 50))
    self.assertEqual(control_phrase([row("8", 10), row("seconds", 40)], "8 seconds"), (35, 50))
    self.assertIsNone(control_phrase([row("8", 10), row("seconds", 40), row("later", 70)], "8 seconds"))


if __name__ == "__main__":
  unittest.main()
