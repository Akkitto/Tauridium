"""Creation-time privacy and shared verified transaction wiring."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PrivateFileTests(unittest.TestCase):
    def test_private_creation_precedes_every_write_and_verification_precedes_replace(self):
        source = (ROOT / "src-tauri/src/private_file.rs").read_text(encoding="utf-8")
        for marker in (".create_new(true)", ".mode(0o600)", "CREATE_NEW",
                       'PrivateAttributes::file()', "FILE_PERSISTENT_ACLS",
                       "getrandom::fill", "MOVEFILE_REPLACE_EXISTING"):
            self.assertIn(marker, source)
        self.assertLess(source.index("create(&temporary)?"), source.index("file.write_all(contents)?"))
        self.assertLess(source.index("verify(&staging.0)?"), source.index("replace(&staging.0, path)?"))
        self.assertNotIn("MOVEFILE_COPY_ALLOWED", source)
        security = (ROOT / "src-tauri/src/windows_security.rs").read_text(encoding="utf-8")
        for marker in ('Self::new("FA")', 'D:P(A;;{rights};;;SY)(A;;{rights};;;{sid})', 'bInheritHandle: 0', 'TokenUser'):
            self.assertIn(marker, security)

    def test_sensitive_export_writers_share_verified_private_transactions(self):
        for name in ("backup", "portable", "service_export"):
            source = (ROOT / f"src-tauri/src/{name}.rs").read_text(encoding="utf-8")
            self.assertIn("private_file::write_verified(path,", source)
            self.assertNotIn(".open(&staging)", source)
