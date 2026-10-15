"""Every external workflow action and secondary checkout has an immutable owner-verified pin."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ActionPinTests(unittest.TestCase):
  def test_external_actions_use_full_commit_ids(self):
    count = 0
    for path in (ROOT / ".github/workflows").glob("*.yml"):
      source = path.read_text(encoding="utf-8")
      for action in re.findall(r"\buses:\s*([^\s#]+)", source):
        if action.startswith("./"):
          continue
        self.assertRegex(action, r"^[A-Za-z0-9_./-]+@[a-f0-9]{40}$", str(path))
        count += 1
      for block in source.split("- uses: dtolnay/rust-toolchain@")[1:]:
        self.assertIn("toolchain: 1.97.1", block.split("- ", 1)[0])
    self.assertGreater(count, 30)

  def test_scoop_checkout_uses_verified_tag_commit(self):
    source = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    self.assertIn("ref: b588a06e41d920d2123ec70aee682bae14935939", source)


if __name__ == "__main__":
  unittest.main()
