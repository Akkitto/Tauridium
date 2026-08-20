"""Regression coverage for Tauridium 0.4.17 shortcut-priority layout."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "App.svelte").read_text(encoding="utf-8")


class Patch0417Tests(unittest.TestCase):
  def shortcut_block(self) -> str:
    return APP.split('<div class="set-title">Keyboard shortcuts</div>', 1)[1].split(
      '<div class="set-title">Workspaces</div>', 1
    )[0]

  def test_shortcut_priority_uses_compact_grid_without_flex_height_reservation(self) -> None:
    block = self.shortcut_block()
    self.assertIn('class="setrow service-shortcut-policy"', block)
    self.assertIn('class="service-shortcut-copy"', block)
    self.assertIn('<strong>Shortcut priority</strong>', block)
    self.assertIn('class="select"', block)
    self.assertIn(
      '.service-shortcut-policy { display: grid; grid-template-columns: minmax(0, 1fr) minmax(230px, 320px);',
      APP,
    )
    self.assertNotIn('.service-shortcut-policy > div { min-width: 0; flex: 1 1 320px; }', APP)

  def test_shortcut_priority_copy_and_control_align_without_inherited_offsets(self) -> None:
    self.assertIn('.service-shortcut-policy .desc { margin-left: 0; }', APP)
    self.assertIn(
      '.service-shortcut-policy .select { width: 100%; min-width: 0; max-width: none; margin-left: 0; }',
      APP,
    )
    self.assertIn('.service-shortcut-effective { grid-column: 1 / -1; margin-top: 0; }', APP)

  def test_shortcut_priority_stacks_cleanly_on_narrow_windows(self) -> None:
    self.assertIn('.service-shortcut-policy { grid-template-columns: 1fr; }', APP)
    self.assertIn('.service-shortcut-effective { grid-column: auto; }', APP)


if __name__ == "__main__":
  unittest.main()
