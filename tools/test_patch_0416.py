"""Regression coverage for Tauridium 0.4.16 Service Settings workspace UX."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "App.svelte").read_text(encoding="utf-8")


class Patch0416Tests(unittest.TestCase):
  def workspace_block(self) -> str:
    return APP.split('<div class="set-title">Workspaces</div>', 1)[1].split(
      '<div class="set-title">Appearance</div>', 1
    )[0]

  def test_workspace_membership_uses_full_row_checkbox_targets(self) -> None:
    block = self.workspace_block()
    self.assertIn('<ul class="service-workspace-list"', block)
    self.assertIn('<label class="service-workspace-option"', block)
    self.assertIn('class="service-workspace-checkbox"', block)
    self.assertIn('type="checkbox"', block)
    self.assertIn(
      'onchange={(event) => toggleCurrentServiceWorkspace(workspace, event.currentTarget.checked)}',
      block,
    )
    self.assertNotIn('{joined ? "Remove" : "Add"}', block)
    self.assertNotIn('class="service-workspace-row"', block)

  def test_workspace_rows_have_stable_alignment_and_membership_state(self) -> None:
    block = self.workspace_block()
    self.assertIn('{joined ? "Included" : "Not included"}', block)
    self.assertIn('{serviceWorkspaceJoinedCount} of {workspaces.length} included', block)
    self.assertIn(
      'grid-template-columns: 20px 34px minmax(0, 1fr) auto',
      APP,
    )
    self.assertIn('.service-workspace-state { min-width: 74px;', APP)
    self.assertNotIn('.workspace-membership-badge {', APP)

  def test_workspace_filter_is_large_segmented_control(self) -> None:
    block = self.workspace_block()
    self.assertIn('class="service-workspace-filters" role="group"', block)
    self.assertIn('aria-pressed={serviceWorkspaceFilter === "all"}', block)
    self.assertIn('aria-pressed={serviceWorkspaceFilter === "joined"}', block)
    self.assertIn('aria-pressed={serviceWorkspaceFilter === "available"}', block)
    self.assertIn('setServiceWorkspaceFilter("all")', block)
    self.assertIn('setServiceWorkspaceFilter("joined")', block)
    self.assertIn('setServiceWorkspaceFilter("available")', block)
    self.assertIn('>Included</button>', block)
    self.assertIn('>Not included</button>', block)
    self.assertIn('.service-workspace-search { min-width: 0; min-height: 40px;', APP)
    self.assertIn('.service-workspace-filters button { min-height: 32px;', APP)

  def test_workspace_manager_explains_direct_interaction_and_scales(self) -> None:
    block = self.workspace_block()
    self.assertIn('Click anywhere in a row to change membership', block)
    self.assertIn('serviceWorkspacePageCount', block)
    self.assertIn('max-height: min(42vh, 460px); overflow-y: auto', APP)
    self.assertIn('Create and include', block)

  def test_workspace_layout_has_narrow_screen_fallback(self) -> None:
    self.assertIn('.service-workspace-toolbar { flex-direction: column; }', APP)
    self.assertIn(
      '.service-workspace-filters { width: 100%; grid-template-columns: repeat(3, minmax(0, 1fr)); }',
      APP,
    )
    self.assertIn(
      '.service-workspace-option { grid-template-columns: 20px 34px minmax(0, 1fr); }',
      APP,
    )
    self.assertIn('.service-workspace-overview { flex-direction: column; }', APP)
    self.assertIn('.service-workspace-state { display: none; }', APP)


if __name__ == "__main__":
  unittest.main()
