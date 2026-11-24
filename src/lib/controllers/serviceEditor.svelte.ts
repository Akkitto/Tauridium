import { ownValue, setOwnValue } from "../settingsMaps";
import { normalizeWebsiteUrl, serviceLabel, paged } from "../ui";
import { closeService, hideServices, setServiceFlags, updateService, fetchServiceIconUrl, createWorkspace, updateWorkspace, deleteWorkspace, setAppSettings, type Service, type Workspace, type AppSettings, type ServiceCustomUrlTemplate } from "../api";
import type { AppView } from "../navigation";

export interface ServiceEditorHost {
  readonly MANAGED_SERVICE_PAGE_SIZE: number;
  readonly RELOAD_FIELDS: Set<keyof Service>;
  readonly activeId: string | null;
  appSettings: AppSettings;
  readonly backToService: () => void;
  readonly clearHibTimer: (sid: string) => void;
  readonly closeServiceContextMenu: () => void;
  readonly confirmAsk: (message: string) => Promise<boolean>;
  error: string | null;
  failedIcons: Set<string>;
  readonly iconFetchAttempted: Set<string>;
  readonly loadServiceIcon: (service: Service, force?: boolean, report?: boolean, preferWebsiteIcon?: boolean) => Promise<void>;
  readonly preferredWebsiteIcon: (service: Service) => string | null;
  readonly reconcileSavedOrders: () => Promise<void>;
  readonly refreshNativeServicesMenu: () => Promise<void>;
  readonly reloadWorkspaces: () => Promise<void>;
  readonly scheduleHibernation: (sid: string) => void;
  serviceIcons: Record<string, string>;
  readonly serviceSandboxId: (serviceId: string) => string | null;
  services: Service[];
  settingsTab: "general" | "services" | "workspaces" | "appearance" | "keybindings" | "sandbox" | "privacy" | "backup" | "audit" | "advanced" | "updates" | "about";
  readonly showServiceSettingsSaved: (serviceId: string) => void;
  readonly showToast: (message: string, tone?: "default" | "success") => void;
  readonly sortedWorkspaces: Workspace[];
  statusMap: Record<string, "loading" | "ready">;
  readonly toggleServiceInWorkspace: (ws: Workspace, serviceId: string, member: boolean) => Promise<boolean>;
  view: AppView;
  workspaces: Workspace[];
}

/** Feature state is created once per application instance; host accessors stay live. */
export function createServiceEditorController(host: ServiceEditorHost) {

  let settingsSvc = $state<Service | null>(null);

  let svcDirty = $state(false);
 // Service settings changed but not saved yet.
  let svcReload = $state(false);
 // A field requiring reload (URL/team/UA) changed.
  let serviceSettingsReturnToSettings = $state(false);

  let serviceTemplateDraft = $state<ServiceCustomUrlTemplate>({ enabled: false, customId1: "", customId2: "" });

  let serviceTemplateDirty = $state(false);

  let serviceWorkspaceQuery = $state("");

  let serviceWorkspaceNewName = $state("");

  let serviceWorkspaceBusy = $state(false);

  let serviceWorkspaceFilter = $state<"all" | "joined" | "available">("all");

  let serviceWorkspacePage = $state(0);

  let serviceSandboxQuery = $state("");

  let serviceSandboxPage = $state(0);

  let trackingPrivacyBusy = $state(false);

  let serviceIconUrlDraft = $state("");

  let serviceIconUrlBusy = $state(false);

  const serviceWorkspaceJoinedCount = $derived.by(() => {
    const serviceId = settingsSvc?.id;
    if (!serviceId) return 0;
    return host.workspaces.filter((workspace) => workspace.services.includes(serviceId)).length;
  });

  const serviceWorkspaceCandidates = $derived.by(() => {
    const serviceId = settingsSvc?.id;
    if (!serviceId) return [];
    const query = serviceWorkspaceQuery.trim().toLowerCase();
    return host.sortedWorkspaces.filter((workspace) => {
      const joined = workspace.services.includes(serviceId);
      if (serviceWorkspaceFilter === "joined" && !joined) return false;
      if (serviceWorkspaceFilter === "available" && joined) return false;
      return !query || workspace.name.toLowerCase().includes(query);
    });
  });

  const serviceWorkspacePageCount = $derived(
    Math.max(1, Math.ceil(serviceWorkspaceCandidates.length / host.MANAGED_SERVICE_PAGE_SIZE)),
  );

  const serviceWorkspaceRows = $derived(
    paged(serviceWorkspaceCandidates, serviceWorkspacePage, host.MANAGED_SERVICE_PAGE_SIZE),
  );

  const serviceSandboxCandidates = $derived.by(() => {
    if (!settingsSvc) return [];
    const query = serviceSandboxQuery.trim().toLowerCase();
    return [
      { id: "", name: "Isolated" },
      ...host.appSettings.sandboxes.map((sandbox) => ({ id: sandbox.id, name: sandbox.name })),
    ].filter((sandbox) => !query || sandbox.name.toLowerCase().includes(query));
  });

  const serviceSandboxPageCount = $derived(
    Math.max(1, Math.ceil(serviceSandboxCandidates.length / host.MANAGED_SERVICE_PAGE_SIZE)),
  );

  const serviceSandboxRows = $derived(
    paged(serviceSandboxCandidates, serviceSandboxPage, host.MANAGED_SERVICE_PAGE_SIZE),
  );

  const currentServiceSandboxName = $derived.by(() => {
    const serviceId = settingsSvc?.id;
    if (!serviceId) return "Isolated";
    const sandboxId = host.serviceSandboxId(serviceId);
    return host.appSettings.sandboxes.find((sandbox) => sandbox.id === sandboxId)?.name ?? "Isolated";
  });

  async function assignServiceIconFromUrl() {
    if (!settingsSvc || serviceIconUrlBusy) return;
    const serviceId = settingsSvc.id;
    const sourceUrl = normalizeWebsiteUrl(serviceIconUrlDraft);
    if (!sourceUrl) return;

    serviceIconUrlBusy = true;
    host.error = null;
    try {
      if (settingsSvc.useFavicon !== true) {
        await updateService(serviceId, { useFavicon: true });
        settingsSvc = { ...settingsSvc, useFavicon: true };
        host.services = host.services.map((service) =>
          service.id === serviceId ? { ...service, useFavicon: true } : service,
        );
      }

      const icon = await fetchServiceIconUrl(serviceId, sourceUrl);
      host.serviceIcons = { ...host.serviceIcons, [serviceId]: icon };
      const nextFailed = new Set(host.failedIcons);
      nextFailed.delete(serviceId);
      host.failedIcons = nextFailed;
      host.iconFetchAttempted.add(`${serviceId}:website`);
      serviceIconUrlDraft = "";
      host.showServiceSettingsSaved(serviceId);
    } catch (err) {
      const { [serviceId]: _, ...remainingIcons } = host.serviceIcons;
      host.serviceIcons = remainingIcons;
      host.iconFetchAttempted.delete(`${serviceId}:website`);

      // A rejected custom icon source must visibly fall back to the recipe/default icon rather
      // than retaining the website-icon preference and silently rediscovering another favicon.
      if (settingsSvc?.id === serviceId && settingsSvc.useFavicon === true) {
        try {
          await updateService(serviceId, { useFavicon: false });
          settingsSvc = { ...settingsSvc, useFavicon: false };
          host.services = host.services.map((service) =>
            service.id === serviceId ? { ...service, useFavicon: false } : service,
          );
        } catch (fallbackError) {
          host.error = `Unable to fetch custom icon: ${err}. The cached icon was removed, but Tauridium could not persist the default-icon fallback: ${fallbackError}`;
          return;
        }
      }
      host.error = `Unable to fetch custom icon: ${err}. The service is using its default icon.`;
    } finally {
      serviceIconUrlBusy = false;
    }
  }

  function openServiceSettings(s: Service, returnToSettings = false) {
    host.closeServiceContextMenu();
    host.error = null;
    serviceSettingsReturnToSettings = returnToSettings;
    settingsSvc = { ...s }; // Editable copy; applied to the server on Save.
    serviceTemplateDraft = { ...(ownValue(host.appSettings.serviceCustomUrlTemplates, s.id) ?? { enabled: false, customId1: "", customId2: "" }) };
    serviceTemplateDirty = false;
    serviceWorkspaceQuery = "";
    serviceWorkspaceNewName = "";
    serviceWorkspaceFilter = "all";
    serviceWorkspacePage = 0;
    serviceWorkspaceBusy = false;
    serviceSandboxQuery = "";
    serviceSandboxPage = 0;
    serviceIconUrlDraft = "";
    serviceIconUrlBusy = false;
    svcDirty = false;
    svcReload = false;
    host.view = "svcSettings";
    hideServices();
  }

  async function closeServiceSettings() {
    if (svcDirty || serviceTemplateDirty) {
      const discard = await host.confirmAsk("Discard unsaved service changes?");
      if (!discard) return;
    }
    host.error = null;
    if (serviceSettingsReturnToSettings) {
      serviceSettingsReturnToSettings = false;
      settingsSvc = null;
      serviceTemplateDirty = false;
      svcDirty = false;
      svcReload = false;
      host.settingsTab = "services";
      host.view = "appSettings";
      hideServices().catch(() => {});
      return;
    }
    host.backToService();
  }

  async function persistService(reload = false): Promise<boolean> {
    if (!settingsSvc) return false;
    const s = { ...settingsSvc };
    try {
      await updateService(s.id, {
        name: s.name,
        isEnabled: s.isEnabled,
        isNotificationEnabled: s.isNotificationEnabled,
        isMuted: s.isMuted,
        isBadgeEnabled: s.isBadgeEnabled,
        isMediaBadgeEnabled: s.isMediaBadgeEnabled,
        isIndirectMessageBadgeEnabled: s.isIndirectMessageBadgeEnabled,
        isHibernationEnabled: s.isHibernationEnabled,
        isWakeUpEnabled: s.isWakeUpEnabled,
        trapLinkClicks: s.trapLinkClicks,
        useFavicon: s.useFavicon,
        isDarkModeEnabled: s.isDarkModeEnabled,
        isProgressbarEnabled: s.isProgressbarEnabled,
        onlyShowFavoritesInUnreadCount: s.onlyShowFavoritesInUnreadCount,
        darkReaderBrightness: s.darkReaderBrightness,
        darkReaderContrast: s.darkReaderContrast,
        darkReaderSepia: s.darkReaderSepia,
        isProxyFeatureEnabled: s.isProxyFeatureEnabled,
        proxyHost: s.proxyHost ?? "",
        proxyPort: s.proxyPort ?? "",
        proxyUser: s.proxyUser ?? "",
        proxyPassword: s.proxyPassword ?? "",
        customUrl: s.customUrl ?? "",
        team: s.team ?? "",
        userAgentPref: s.userAgentPref ?? "",
      });
      const idx = host.services.findIndex((candidate) => candidate.id === s.id);
      const previous = idx >= 0 ? host.services[idx] : null;
      if (idx >= 0) host.services = host.services.map((candidate, index) => index === idx ? { ...s } : candidate);
      if (
        s.useFavicon === true &&
        host.appSettings.fetchMissingServiceIcons &&
        (previous?.useFavicon !== true || !host.preferredWebsiteIcon(s))
      ) {
        void host.loadServiceIcon(s);
      }
      await setServiceFlags(s);
      await host.refreshNativeServicesMenu();
      if (previous?.isHibernationEnabled !== s.isHibernationEnabled) {
        host.clearHibTimer(s.id);
        if (s.id !== host.activeId && s.isHibernationEnabled === true && ownValue(host.statusMap, s.id)) {
          host.scheduleHibernation(s.id);
        }
      }
      if (reload) {
        await closeService(s.id);
        const { [s.id]: _, ...rest } = host.statusMap;
        host.statusMap = rest;
      }
      return true;
    } catch (err) {
      host.error = `Unable to save ${serviceLabel(s)}: ${err}`;
      return false;
    }
  }

  function saveSetting(key: keyof Service, value: boolean) {
    if (!settingsSvc) return;
    (settingsSvc as Record<string, unknown>)[key] = value;
    svcDirty = true;
    if (host.RELOAD_FIELDS.has(key)) svcReload = true;
  }

  function saveText(key: keyof Service, value: string, reload = false) {
    if (!settingsSvc) return;
    (settingsSvc as Record<string, unknown>)[key] = value;
    svcDirty = true;
    if (reload) svcReload = true;
  }

  function saveServiceTemplateField<K extends keyof ServiceCustomUrlTemplate>(
    key: K,
    value: ServiceCustomUrlTemplate[K],
  ) {
    serviceTemplateDraft = { ...serviceTemplateDraft, [key]: value };
    serviceTemplateDirty = true;
    svcReload = true;
  }

  function saveNum(key: keyof Service, value: string) {
    if (!settingsSvc) return;
    const n = Number.parseInt(value, 10);
    (settingsSvc as Record<string, unknown>)[key] = Number.isNaN(n) ? undefined : n;
    svcDirty = true;
    if (host.RELOAD_FIELDS.has(key)) svcReload = true;
  }

  async function saveServiceSettings() {
    host.error = null;
    const needsServiceSave = svcDirty || svcReload;
    if (needsServiceSave) {
      const saved = await persistService(svcReload);
      if (!saved) return;
      svcDirty = false;
    }
    if (settingsSvc && serviceTemplateDirty) {
      try {
        host.appSettings = await setAppSettings({
          serviceCustomUrlTemplates: {
            ...host.appSettings.serviceCustomUrlTemplates,
            [settingsSvc.id]: { ...serviceTemplateDraft },
          },
        });
        serviceTemplateDirty = false;
      } catch (err) {
        host.error = `Unable to save custom URL placeholders: ${err}`;
        return;
      }
    }
    svcReload = false;
  }

  function serviceShortcutCaptureMode(serviceId: string): "inherit" | "tauridium" | "website" {
    if (!Object.hasOwn(host.appSettings.serviceShortcutCaptureOverrides, serviceId)) return "inherit";
    return ownValue(host.appSettings.serviceShortcutCaptureOverrides, serviceId) ? "tauridium" : "website";
  }

  function effectiveServiceShortcutCapture(serviceId: string): boolean {
    return ownValue(host.appSettings.serviceShortcutCaptureOverrides, serviceId) ?? host.appSettings.captureServiceShortcuts;
  }

  async function setServiceShortcutCaptureMode(
    serviceId: string,
    mode: "inherit" | "tauridium" | "website",
  ) {
    const previous = { ...host.appSettings.serviceShortcutCaptureOverrides };
    const serviceShortcutCaptureOverrides = { ...previous };
    if (mode === "inherit") delete serviceShortcutCaptureOverrides[serviceId];
    else setOwnValue(serviceShortcutCaptureOverrides, serviceId, mode === "tauridium");
    host.appSettings = { ...host.appSettings, serviceShortcutCaptureOverrides };
    try {
      host.appSettings = await setAppSettings({ serviceShortcutCaptureOverrides });
      await closeService(serviceId).catch(() => {});
      const { [serviceId]: _, ...rest } = host.statusMap;
      host.statusMap = rest;
      host.showServiceSettingsSaved(serviceId);
    } catch (err) {
      host.appSettings = { ...host.appSettings, serviceShortcutCaptureOverrides: previous };
      host.error = `Unable to save shortcut handling: ${err}`;
    }
  }

  function setServiceWorkspaceFilter(filter: "all" | "joined" | "available") {
    serviceWorkspaceFilter = filter;
    serviceWorkspacePage = 0;
  }

  async function toggleCurrentServiceWorkspace(workspace: Workspace, member: boolean) {
    if (!settingsSvc || serviceWorkspaceBusy) return;
    serviceWorkspaceBusy = true;
    try {
      const saved = await host.toggleServiceInWorkspace(workspace, settingsSvc.id, member);
      if (saved) {
        serviceWorkspacePage = 0;
        host.showToast("Saved", "success");
      }
    } finally {
      serviceWorkspaceBusy = false;
    }
  }

  async function createWorkspaceForCurrentService() {
    if (!settingsSvc || serviceWorkspaceBusy) return;
    const name = serviceWorkspaceNewName.trim();
    if (!name) return;
    serviceWorkspaceBusy = true;
    let created: Workspace | null = null;
    try {
      created = await createWorkspace(name);
      const updated = await updateWorkspace(created.id, created.name, [settingsSvc.id]);
      host.workspaces = [...host.workspaces, updated];
      serviceWorkspaceNewName = "";
      serviceWorkspaceFilter = "joined";
      serviceWorkspacePage = 0;
      await host.reconcileSavedOrders();
      host.showToast("Saved", "success");
    } catch (err) {
      if (created) await deleteWorkspace(created.id).catch(() => {});
      host.error = `Unable to create workspace and add ${serviceLabel(settingsSvc)}: ${err}`;
      await host.reloadWorkspaces().catch(() => {});
    } finally {
      serviceWorkspaceBusy = false;
    }
  }

  return {
    get settingsSvc() { return settingsSvc; },
    set settingsSvc(value: typeof settingsSvc) { settingsSvc = value; },
    get trackingPrivacyBusy() { return trackingPrivacyBusy; },
    set trackingPrivacyBusy(value: typeof trackingPrivacyBusy) { trackingPrivacyBusy = value; },
    openServiceSettings,
    assignServiceIconFromUrl,
    closeServiceSettings,
    createWorkspaceForCurrentService,
    get currentServiceSandboxName() { return currentServiceSandboxName; },
    effectiveServiceShortcutCapture,
    saveNum,
    saveServiceSettings,
    saveServiceTemplateField,
    saveSetting,
    saveText,
    get serviceIconUrlBusy() { return serviceIconUrlBusy; },
    get serviceIconUrlDraft() { return serviceIconUrlDraft; },
    set serviceIconUrlDraft(value: typeof serviceIconUrlDraft) { serviceIconUrlDraft = value; },
    get serviceSandboxCandidates() { return serviceSandboxCandidates; },
    get serviceSandboxPage() { return serviceSandboxPage; },
    set serviceSandboxPage(value: typeof serviceSandboxPage) { serviceSandboxPage = value; },
    get serviceSandboxPageCount() { return serviceSandboxPageCount; },
    get serviceSandboxQuery() { return serviceSandboxQuery; },
    set serviceSandboxQuery(value: typeof serviceSandboxQuery) { serviceSandboxQuery = value; },
    get serviceSandboxRows() { return serviceSandboxRows; },
    serviceShortcutCaptureMode,
    get serviceTemplateDirty() { return serviceTemplateDirty; },
    get serviceTemplateDraft() { return serviceTemplateDraft; },
    get serviceWorkspaceBusy() { return serviceWorkspaceBusy; },
    get serviceWorkspaceCandidates() { return serviceWorkspaceCandidates; },
    get serviceWorkspaceFilter() { return serviceWorkspaceFilter; },
    get serviceWorkspaceJoinedCount() { return serviceWorkspaceJoinedCount; },
    get serviceWorkspaceNewName() { return serviceWorkspaceNewName; },
    set serviceWorkspaceNewName(value: typeof serviceWorkspaceNewName) { serviceWorkspaceNewName = value; },
    get serviceWorkspacePage() { return serviceWorkspacePage; },
    set serviceWorkspacePage(value: typeof serviceWorkspacePage) { serviceWorkspacePage = value; },
    get serviceWorkspacePageCount() { return serviceWorkspacePageCount; },
    get serviceWorkspaceQuery() { return serviceWorkspaceQuery; },
    set serviceWorkspaceQuery(value: typeof serviceWorkspaceQuery) { serviceWorkspaceQuery = value; },
    get serviceWorkspaceRows() { return serviceWorkspaceRows; },
    setServiceShortcutCaptureMode,
    setServiceWorkspaceFilter,
    get svcDirty() { return svcDirty; },
    toggleCurrentServiceWorkspace,
  };
}

export type ServiceEditorController = ReturnType<typeof createServiceEditorController>;
