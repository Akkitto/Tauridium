"""Execute production badge bridges with pinned, public, account-free recipe fixtures."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UnreadBadgeRuntimeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is required to execute injected JavaScript")
    def test_real_injected_scripts_and_pinned_recipes(self):
        subprocess.run([shutil.which("node"), str(ROOT / "tools/unread_badges_probe.cjs")],
                       check=True, capture_output=True, text=True, encoding="utf-8", timeout=30)


if __name__ == "__main__":
    unittest.main()
