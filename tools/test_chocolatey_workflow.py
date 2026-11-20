"""Require both native package lanes and the keyless decoded scan."""
import unittest
import chocolatey as c

class ChocolateyWorkflowTests(unittest.TestCase):
  def test_workflow_retains_native_acceptance_and_keyless_scanning(self):
    workflow=(c.ROOT/'.github/workflows/chocolatey.yml').read_text(encoding='utf-8')
    for required in ('windows-latest','windows-11-arm','artifact_security.py','contents: read','tools/test_chocolatey_install.ps1'):
      self.assertIn(required,workflow)
    self.assertNotIn('secrets.',workflow);self.assertNotIn('choco push',workflow)
    release=(c.ROOT/'.github/workflows/release.yml').read_text(encoding='utf-8')
    self.assertIn('needs: [security, chocolatey]',release)

  def test_local_packages_do_not_enter_application_publication_inputs(self):
    import release_policy
    self.assertFalse(any(n.endswith('.nupkg') for n in release_policy.public_names('1.0.13')))
    release=(c.ROOT/'.github/workflows/release.yml').read_text(encoding='utf-8')
    self.assertIn('name: release-handoff\n          path: release/inputs/release-handoff',release)
    self.assertIn('pattern: native-*\n          path: release/inputs',release)
