"""Regression coverage for Tauridium 0.4.11 Service Settings nullability."""

from frontend_source import read_frontend_file, read_frontend_source
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Patch0411Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.app = read_frontend_source(ROOT)

  def test_service_settings_captures_non_nullable_service_id_for_workspace_callbacks(self) -> None:
    block = read_frontend_file(ROOT, "src/components/ServiceSettingsPanel.svelte")
    self.assertIn('const settingsServiceId = $derived(settingsSvc.id)', block)
    self.assertIn('workspace.services.includes(serviceId)).length', self.app)
    self.assertIn('serviceWorkspaceJoinedCount', block)
    self.assertIn('{@const joined = workspace.services.includes(settingsServiceId)}', block)
    self.assertNotIn('workspace.services.includes(settingsSvc.id)', block)

  def test_fix_does_not_use_non_null_assertion_or_type_suppression(self) -> None:
    block = read_frontend_file(ROOT, "src/components/ServiceSettingsPanel.svelte")
    self.assertNotIn('settingsSvc!.id', block)
    self.assertNotIn('@ts-ignore', block)
    self.assertNotIn('@ts-expect-error', block)


if __name__ == "__main__":
  unittest.main()
