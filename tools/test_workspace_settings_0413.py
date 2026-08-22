import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "App.svelte").read_text(encoding="utf-8")
API = (ROOT / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
UI = (ROOT / "src" / "lib" / "ui.ts").read_text(encoding="utf-8")
RUST = (ROOT / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")


class WorkspaceSettings0413Tests(unittest.TestCase):
  def test_sidebar_workspace_strip_is_removed(self):
    self.assertNotIn('class="wspills"', APP)
    self.assertNotIn('class="pill mng"', APP)
    self.assertNotIn('view === "workspaces"', APP)

  def test_settings_has_workspace_management_tab(self):
    self.assertIn('["workspaces", "Workspaces"]', APP)
    self.assertIn('settingsTab === "workspaces"', APP)
    self.assertIn('Configured workspaces', APP)
    self.assertIn('Workspace settings ·', APP)
    self.assertIn('Search configured workspaces', APP)
    self.assertIn('Search services in ${selectedWorkspaceName}', APP)
    self.assertIn('toggleManagedWorkspaceService', APP)
    self.assertIn('handleCreateWorkspace', APP)
    self.assertIn('deleteManagedWorkspace', APP)

  def test_workspace_management_scales_and_preserves_canonical_order(self):
    self.assertIn('managedWorkspaceRows', APP)
    self.assertIn('managedWorkspaceServiceRows', APP)
    self.assertIn('MANAGED_SERVICE_PAGE_SIZE', APP)
    self.assertIn('reorderVisibleSubset(', APP)
    self.assertIn('persistWorkspaceIds(nextIds, previousIds)', APP)

  def test_quick_switch_order_is_independent_and_portable(self):
    self.assertIn('workspaceQuickSwitchOrder:', API)
    self.assertIn('workspaceLastUsed: Record<string, number>', API)
    self.assertIn('export function orderWorkspacesForQuickSwitch', UI)
    self.assertIn('...quickSwitcherWorkspaces', APP)
    self.assertIn('? { ...previousWorkspaceLastUsed, [workspaceId]: Date.now() }', APP)
    self.assertIn('workspaceUsagePersist = workspaceUsagePersist.then(async () => {', APP)
    self.assertIn('settings.insert("workspaceQuickSwitchOrder".into(), "custom".into());', RUST)
    self.assertIn('"workspaceLastUsed".into(),', RUST)
    for mode in ['customReverse', 'alphabetical', 'alphabeticalReverse', 'recent', 'recentReverse']:
      self.assertIn(f'"{mode}"', RUST)


  def test_workspace_detail_replaces_long_list_and_confirms_unsaved_rename(self):
    tab = APP.split('{:else if settingsTab === "workspaces"}', 1)[1].split('{:else if settingsTab === "appearance"}', 1)[0]
    self.assertIn('{#if managedWorkspace}', tab)
    self.assertIn('{:else}', tab)
    self.assertLess(tab.index('Workspace settings ·'), tab.index('Quick workspace switcher'))
    self.assertIn('async function closeManagedWorkspace()', APP)
    self.assertIn('Discard unsaved workspace name changes?', APP)
    self.assertIn('← Workspaces', tab)

  def test_workspace_history_is_pruned_and_persisted_serially(self):
    self.assertIn('workspaceIds.has(workspaceId)', APP)
    self.assertIn('workspaceUsagePersist: Promise<void> = Promise.resolve()', APP)
    self.assertIn('workspaceUsagePersist = workspaceUsagePersist.then(async () => {', APP)
    self.assertIn('Unable to save workspace startup state', APP)

  def test_all_services_remains_pinned_first(self):
    self.assertIn('[{ id: "__all__", name: "All services" }, ...quickSwitcherWorkspaces]', APP)


if __name__ == "__main__":
  unittest.main()
