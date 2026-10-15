"""Credential-vault persistence and explicit authentication transport policy."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CredentialTests(unittest.TestCase):
    def test_os_vaults_are_explicit_and_retried_without_plaintext_fallback(self):
        source = (ROOT / "src-tauri/src/credentials.rs").read_text(encoding="utf-8")
        for marker in ("windows_native_keyring_store::Store::new()?",
                       "apple_native_keyring_store::keychain::Store::new()?",
                       "zbus_secret_service_keyring_store::Store::new()?",
                       "Saved plaintext session migration could not finish",
                       "unavailable_vault_never_silently_falls_back_to_plaintext"):
            self.assertIn(marker, source)
        self.assertNotIn("LazyLock", source)
        self.assertIn("retired_credential_accounts", source)

    def test_login_and_ui_expose_storage_and_transport_choices(self):
        main = (ROOT / "src-tauri/src/main.rs").read_text(encoding="utf-8")
        app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
        login = main.split("async fn login(", 1)[1].split("#[tauri::command]", 1)[0]
        self.assertLess(login.index("credentials::validate_server"), login.index(".basic_auth"))
        self.assertLess(login.index("credentials::save("), login.index("*state.token"))
        for marker in ('let rememberSession = $state(true)', 'let allowInsecureServer = $state(false)',
                       'Remember using OS credential store', 'await showSessionWarning()',
                       'error = cleanupError'):
            self.assertIn(marker, app)

    def test_nix_includes_explicit_native_command_permissions(self):
        source = (ROOT / "packaging/nix/package.nix").read_text(encoding="utf-8")
        self.assertIn("../../src-tauri/permissions", source)
