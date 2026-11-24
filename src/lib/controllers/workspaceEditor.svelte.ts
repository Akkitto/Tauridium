import { ownValue, setOwnValue } from "../settingsMaps";
import { serviceLabel, paged } from "../ui";
import { fetchWorkspaceIconUrl, createWorkspace, updateWorkspace, setAppSettings, type Service, type Workspace, type AppSettings } from "../api";

export interface WorkspaceEditorHost {
  readonly MANAGED_SERVICE_PAGE_SIZE: number;
  appSettings: AppSettings;
  readonly confirmAsk: (message: string) => Promise<boolean>;
  readonly displayedServiceIcon: (service: Service) => string;
  error: string | null;
  failedWorkspaceIcons: Set<string>;
  readonly handleDeleteWorkspace: (ws: Workspace) => Promise<void>;
  readonly loadServiceIcon: (service: Service, force?: boolean, report?: boolean, preferWebsiteIcon?: boolean) => Promise<void>;
  readonly preferredWebsiteIcon: (service: Service) => string | null;
  readonly reloadWorkspaces: () => Promise<void>;
  readonly showToast: (message: string, tone?: "default" | "success") => void;
  readonly sorted: Service[];
  readonly sortedWorkspaces: Workspace[];
  readonly toggleServiceInWorkspace: (ws: Workspace, serviceId: string, member: boolean) => Promise<boolean>;
  readonly workspaces: Workspace[];
}

/** Feature state is created once per application instance; host accessors stay live. */
export function createWorkspaceEditorController(host: WorkspaceEditorHost) {

  let newWorkspaceName = $state("");

  let managedWorkspaceQuery = $state("");

  let managedWorkspacePage = $state(0);

  let managedWorkspaceId = $state<string | null>(null);

  let managedWorkspaceServiceQuery = $state("");

  let managedWorkspaceServicePage = $state(0);

  let managedWorkspaceBusy = $state(false);

  let managedWorkspaceNameDraft = $state("");

  let managedWorkspaceIconUrlDraft = $state("");

  const managedWorkspaces = $derived.by(() => {
    const query = managedWorkspaceQuery.trim().toLowerCase();
    return host.sortedWorkspaces.filter((workspace) =>
      !query || workspace.name.toLowerCase().includes(query),
    );
  });

  const managedWorkspacePageCount = $derived(
    Math.max(1, Math.ceil(managedWorkspaces.length / host.MANAGED_SERVICE_PAGE_SIZE)),
  );

  const managedWorkspaceRows = $derived(
    paged(managedWorkspaces, managedWorkspacePage, host.MANAGED_SERVICE_PAGE_SIZE),
  );

  const managedWorkspace = $derived(
    host.workspaces.find((workspace) => workspace.id === managedWorkspaceId) ?? null,
  );

  const managedWorkspaceServices = $derived.by(() => {
    const query = managedWorkspaceServiceQuery.trim().toLowerCase();
    return host.sorted.filter((service) =>
      !query || `${serviceLabel(service)} ${service.recipeId}`.toLowerCase().includes(query),
    );
  });

  const managedWorkspaceServicePageCount = $derived(
    Math.max(1, Math.ceil(managedWorkspaceServices.length / host.MANAGED_SERVICE_PAGE_SIZE)),
  );

  const managedWorkspaceServiceRows = $derived(
    paged(managedWorkspaceServices, managedWorkspaceServicePage, host.MANAGED_SERVICE_PAGE_SIZE),
  );

  function manageWorkspace(workspace: Workspace) {
    managedWorkspaceId = workspace.id;
    managedWorkspaceNameDraft = workspace.name;
    managedWorkspaceIconUrlDraft = "";
    managedWorkspaceServiceQuery = "";
    managedWorkspaceServicePage = 0;
  }

  async function closeManagedWorkspace() {
    if (
      managedWorkspace &&
      managedWorkspaceNameDraft.trim() !== managedWorkspace.name &&
      !(await host.confirmAsk("Discard unsaved workspace name changes?"))
    ) return;
    managedWorkspaceId = null;
    managedWorkspaceNameDraft = "";
    managedWorkspaceIconUrlDraft = "";
    managedWorkspaceServiceQuery = "";
    managedWorkspaceServicePage = 0;
  }

  async function saveManagedWorkspaceName() {
    if (!managedWorkspace || managedWorkspaceBusy) return;
    const name = managedWorkspaceNameDraft.trim();
    if (!name || name === managedWorkspace.name) return;
    managedWorkspaceBusy = true;
    try {
      await updateWorkspace(managedWorkspace.id, name, managedWorkspace.services);
      await host.reloadWorkspaces();
      managedWorkspaceNameDraft = name;
      host.showToast("Saved", "success");
    } catch (err) {
      host.error = `Unable to rename workspace: ${err}`;
      managedWorkspaceNameDraft = managedWorkspace.name;
    } finally {
      managedWorkspaceBusy = false;
    }
  }

  async function toggleManagedWorkspaceService(serviceId: string, member: boolean) {
    if (!managedWorkspace || managedWorkspaceBusy) return;
    managedWorkspaceBusy = true;
    try {
      if (await host.toggleServiceInWorkspace(managedWorkspace, serviceId, member)) {
        host.showToast("Saved", "success");
      }
    } finally {
      managedWorkspaceBusy = false;
    }
  }

  async function persistManagedWorkspaceIcon(iconUrl: string | null, busyAlready = false) {
    if (!managedWorkspace || (!busyAlready && managedWorkspaceBusy)) return;
    const previous = { ...host.appSettings.workspaceIcons };
    const workspaceIcons = { ...previous };
    if (iconUrl) setOwnValue(workspaceIcons, managedWorkspace.id, iconUrl);
    else delete workspaceIcons[managedWorkspace.id];
    if ((ownValue(previous, managedWorkspace.id) ?? null) === (ownValue(workspaceIcons, managedWorkspace.id) ?? null)) return;

    if (!busyAlready) managedWorkspaceBusy = true;
    host.appSettings = { ...host.appSettings, workspaceIcons };
    try {
      const persisted = await setAppSettings({ workspaceIcons });
      if ((ownValue(persisted.workspaceIcons, managedWorkspace.id) ?? null) !== (iconUrl ?? null)) {
        throw new Error("Tauridium could not verify the saved workspace icon");
      }
      host.appSettings = persisted;
      const nextFailed = new Set(host.failedWorkspaceIcons);
      nextFailed.delete(managedWorkspace.id);
      host.failedWorkspaceIcons = nextFailed;
      host.showToast("Saved", "success");
    } catch (err) {
      host.appSettings = { ...host.appSettings, workspaceIcons: previous };
      host.error = `Unable to save workspace icon: ${err}`;
    } finally {
      if (!busyAlready) managedWorkspaceBusy = false;
    }
  }

  async function saveManagedWorkspaceIcon(iconUrl: string | null) {
    await persistManagedWorkspaceIcon(iconUrl);
  }

  async function assignManagedWorkspaceIconFromService(service: Service) {
    if (!managedWorkspace || managedWorkspaceBusy) return;
    if (service.useFavicon === true && !host.preferredWebsiteIcon(service)) {
      await host.loadServiceIcon(service, false, false, true);
    }
    await saveManagedWorkspaceIcon(host.displayedServiceIcon(service));
  }

  async function assignManagedWorkspaceIconFromUrl() {
    if (!managedWorkspace || managedWorkspaceBusy) return;
    const url = managedWorkspaceIconUrlDraft.trim();
    if (!url) return;
    managedWorkspaceBusy = true;
    try {
      const icon = await fetchWorkspaceIconUrl(url);
      await persistManagedWorkspaceIcon(icon, true);
      managedWorkspaceIconUrlDraft = "";
    } catch (err) {
      host.error = `Unable to fetch workspace icon: ${err}`;
    } finally {
      managedWorkspaceBusy = false;
    }
  }

  async function deleteManagedWorkspace() {
    if (!managedWorkspace) return;
    await host.handleDeleteWorkspace(managedWorkspace);
  }

  async function handleCreateWorkspace() {
    const name = newWorkspaceName.trim();
    if (!name) return;
    try {
      const created = await createWorkspace(name);
      newWorkspaceName = "";
      await host.reloadWorkspaces();
      const workspace = host.workspaces.find((candidate) => candidate.id === created.id) ?? created;
      manageWorkspace(workspace);
    } catch (err) {
      host.error = String(err);
    }
  }

  return {
    get managedWorkspace() { return managedWorkspace; },
    closeManagedWorkspace,
    get managedWorkspaceId() { return managedWorkspaceId; },
    set managedWorkspaceId(value: typeof managedWorkspaceId) { managedWorkspaceId = value; },
    get managedWorkspaceNameDraft() { return managedWorkspaceNameDraft; },
    set managedWorkspaceNameDraft(value: typeof managedWorkspaceNameDraft) { managedWorkspaceNameDraft = value; },
    get managedWorkspaceQuery() { return managedWorkspaceQuery; },
    set managedWorkspaceQuery(value: typeof managedWorkspaceQuery) { managedWorkspaceQuery = value; },
    get managedWorkspacePage() { return managedWorkspacePage; },
    set managedWorkspacePage(value: typeof managedWorkspacePage) { managedWorkspacePage = value; },
    get managedWorkspaces() { return managedWorkspaces; },
    assignManagedWorkspaceIconFromService,
    assignManagedWorkspaceIconFromUrl,
    deleteManagedWorkspace,
    handleCreateWorkspace,
    manageWorkspace,
    get managedWorkspaceBusy() { return managedWorkspaceBusy; },
    get managedWorkspaceIconUrlDraft() { return managedWorkspaceIconUrlDraft; },
    set managedWorkspaceIconUrlDraft(value: typeof managedWorkspaceIconUrlDraft) { managedWorkspaceIconUrlDraft = value; },
    get managedWorkspacePageCount() { return managedWorkspacePageCount; },
    get managedWorkspaceRows() { return managedWorkspaceRows; },
    get managedWorkspaceServicePage() { return managedWorkspaceServicePage; },
    set managedWorkspaceServicePage(value: typeof managedWorkspaceServicePage) { managedWorkspaceServicePage = value; },
    get managedWorkspaceServicePageCount() { return managedWorkspaceServicePageCount; },
    get managedWorkspaceServiceQuery() { return managedWorkspaceServiceQuery; },
    set managedWorkspaceServiceQuery(value: typeof managedWorkspaceServiceQuery) { managedWorkspaceServiceQuery = value; },
    get managedWorkspaceServiceRows() { return managedWorkspaceServiceRows; },
    get managedWorkspaceServices() { return managedWorkspaceServices; },
    get newWorkspaceName() { return newWorkspaceName; },
    set newWorkspaceName(value: typeof newWorkspaceName) { newWorkspaceName = value; },
    saveManagedWorkspaceIcon,
    saveManagedWorkspaceName,
    toggleManagedWorkspaceService,
  };
}

export type WorkspaceEditorController = ReturnType<typeof createWorkspaceEditorController>;
