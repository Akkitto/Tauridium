<script lang="ts">
  import { createAppSettingsDefaults } from "./lib/appSettingsDefaults";
  import type { AppView } from "./lib/navigation";

  import SessionScreen from "./components/SessionScreen.svelte";
  import ServiceSidebar from "./components/ServiceSidebar.svelte";
  import ServiceRow from "./components/ServiceRow.svelte";
  import QuickSwitcher from "./components/QuickSwitcher.svelte";
  import { createWorkspaceEditorController } from "./lib/controllers/workspaceEditor.svelte";
  import { createServiceEditorController } from "./lib/controllers/serviceEditor.svelte";
  import { createAuthController } from "./lib/controllers/auth.svelte";
  import { createBackupsController } from "./lib/controllers/backups.svelte";
  import { createAuditController } from "./lib/controllers/audit.svelte";
  import { createUpdatesController } from "./lib/controllers/updates.svelte";
  import { createAppearanceController } from "./lib/controllers/appearance.svelte";
  import type { AppView as View, AddServiceMode as AddMode, QuickSwitcherMode } from "./lib/navigation";
  import SettingsGeneral from "./components/SettingsGeneral.svelte";
  import SettingsServices from "./components/SettingsServices.svelte";
  import SettingsWorkspaces from "./components/SettingsWorkspaces.svelte";
  import SettingsAppearance from "./components/SettingsAppearance.svelte";
  import SettingsKeybindings from "./components/SettingsKeybindings.svelte";
  import SettingsSandbox from "./components/SettingsSandbox.svelte";
  import SettingsPrivacy from "./components/SettingsPrivacy.svelte";
  import SettingsBackup from "./components/SettingsBackup.svelte";
  import SettingsAudit from "./components/SettingsAudit.svelte";
  import SettingsAdvanced from "./components/SettingsAdvanced.svelte";
  import SettingsUpdates from "./components/SettingsUpdates.svelte";
  import SettingsAbout from "./components/SettingsAbout.svelte";
  import ServicePicker from "./components/ServicePicker.svelte";
  import ServiceSettingsPanel from "./components/ServiceSettingsPanel.svelte";
  import { onDestroy, onMount, tick } from "svelte";
  import SettingsSearch from "./SettingsSearch.svelte";
  import { SETTINGS_TABS, settingsTabLabel, type SettingsTab, type SettingsSearchEntry } from "./lib/settingsSearch";

  import { downloadToastPreview } from "./lib/downloadToast";
  import { browserProfileNamespace, retainedTrackingExceptions } from "./lib/browserPrivacy";
  import { ownValue, setOwnValue, copyOwnEntry, downloadOverride } from "./lib/settingsMaps";

  import { listen } from "@tauri-apps/api/event";
  import { PhysicalPosition } from "@tauri-apps/api/dpi";
  import { getCurrentWebview } from "@tauri-apps/api/webview";
  import { prepareServiceMenu, presentServiceMenu, closeServiceMenu } from "./lib/api";
  import { ServiceMenuController, captureMenuPointer, type ServiceMenuAction, type ServiceMenuRequest } from "./lib/serviceMenu";
  import { Menu } from "@tauri-apps/api/menu";
  import { accentFg, iconSrc, filterRecipes, snapIconSize, recipeIdFromName, recipeSourceLabel, normalizeWebsiteUrl, websiteName, looksLikeWebsite, orderedBySavedIds, orderWorkspacesForQuickSwitch, resolveStartupWorkspaceId, resolveStartupSidebarCollapsed, reorderVisibleSubset, reorderVisibleSubsetAt, reorderVisibleGroupAt, contiguousIdRange, type ReorderPlacement, serviceLabel, backupTimestamp, COLLAPSED_SIDEBAR_WIDTH_PX, DEFAULT_KEYBINDINGS, bindingStrokes, keyStrokeFromEvent, normalizeServiceZoomPercent, paged, duplicateServiceName, shortcutConflicts, stepServiceZoomPercent, sameDownloadPreference, type KeybindingAction } from "./lib/ui";
  import { DEFAULT_TASKBAR_TITLE_TEMPLATE, DEFAULT_WINDOW_TITLE_TEMPLATE, renderTitleTemplate } from "./lib/title-template";
  import { appVersion } from "./lib/updater";
  import { ask, open, save as saveDialog } from "@tauri-apps/plugin-dialog";

  // window.confirm() does not work in WKWebView (wry does not implement the JavaScript panel).
  // Use the native dialog provided by the dialog plugin instead.
  function confirmAsk(message: string): Promise<boolean> {
    return ask(message, { title: "Tauridium", kind: "warning" });
  }
  import { getServices, getWorkspaces, logout, showService, preloadService, closeService, closeServices, hideServices, setServiceFlags, updateService, createService, createCustomWebsiteService, deleteService, clearServiceCache, getServiceIcon, copyServiceIconCache, clearSandbox, listRecipes, getRecipeStorageInfo, saveCustomRecipe, importCustomRecipe, updateWorkspace, deleteWorkspace, getAppSettings, getWindowChrome, getDistributionInfo, setAppSettings, setServiceOrder, setWorkspaceOrder, syncServicesMenu, setSidebarWidth, setPresentationTitles, exportPortableBundle, exportServiceBundle, getAppMetadata, openExternalUrl, reloadTauridium, showServiceToastOverlay, setServiceZoom, toggleDeveloperTools, type MeUser, type Service, type Workspace, type RecipePreview, type RecipeDraft, type RecipeStorageInfo, type AppSettings, type DistributionInfo, type SandboxDefinition, type PortablePayload, type AppMetadata, type DownloadPreferenceOverride } from "./lib/api";

    const auth = createAuthController({
    get error() { return error; },
    set error(value: string | null) { error = value; },
    get loadAfterAuth() { return loadAfterAuth; },
    get me() { return me; },
    set me(value: MeUser | null) { me = value; },
  });

  let booting = $state(true);

  let error = $state<string | null>(null);

  // Automatically reconnect when the server is unreachable (Ferdium outage, network issue, etc.).

  let me = $state<MeUser | null>(null);
  let services = $state<Service[]>([]);
  let workspaces = $state<Workspace[]>([]);
  let activeId = $state<string | null>(null);
  let unreadMap = $state<Record<string, number>>({});
  let failedIcons = $state<Set<string>>(new Set());
  let failedWorkspaceIcons = $state<Set<string>>(new Set());
  let serviceIcons = $state<Record<string, string>>({});
  let iconFetchAttempted = new Set<string>();
  // Per-service loading state emitted by the backend through on_page_load.
  let statusMap = $state<Record<string, "loading" | "ready">>({});
  // Error opening the active service (showService rejected it: broken recipe, invalid URL, etc.).
  let serviceLoadError = $state<string | null>(null);
  // Reorder services with drag and drop.
  let dragId = $state<string | null>(null);
  let dragIds = $state<string[]>([]);
  let dragOverId = $state<string | null>(null);
  let dragPlacement = $state<ReorderPlacement | null>(null);
  let serviceDragSelection = $state<string[]>([]);
  let serviceOrderBusy = $state(false);
  let activeWorkspace = $state<string | null>(null);

  let view = $state<View>("service");
    const serviceEditor = createServiceEditorController({
    get MANAGED_SERVICE_PAGE_SIZE() { return MANAGED_SERVICE_PAGE_SIZE; },
    get RELOAD_FIELDS() { return RELOAD_FIELDS; },
    get activeId() { return activeId; },
    get appSettings() { return appSettings; },
    set appSettings(value: AppSettings) { appSettings = value; },
    get backToService() { return backToService; },
    get clearHibTimer() { return clearHibTimer; },
    get closeServiceContextMenu() { return closeServiceContextMenu; },
    get confirmAsk() { return confirmAsk; },
    get error() { return error; },
    set error(value: string | null) { error = value; },
    get failedIcons() { return failedIcons; },
    set failedIcons(value: Set<string>) { failedIcons = value; },
    get iconFetchAttempted() { return iconFetchAttempted; },
    get loadServiceIcon() { return loadServiceIcon; },
    get preferredWebsiteIcon() { return preferredWebsiteIcon; },
    get reconcileSavedOrders() { return reconcileSavedOrders; },
    get refreshNativeServicesMenu() { return refreshNativeServicesMenu; },
    get reloadWorkspaces() { return reloadWorkspaces; },
    get scheduleHibernation() { return scheduleHibernation; },
    get serviceIcons() { return serviceIcons; },
    set serviceIcons(value: Record<string, string>) { serviceIcons = value; },
    get serviceSandboxId() { return serviceSandboxId; },
    get services() { return services; },
    set services(value: Service[]) { services = value; },
    get settingsTab() { return settingsTab; },
    set settingsTab(value: "general" | "services" | "workspaces" | "appearance" | "keybindings" | "sandbox" | "privacy" | "backup" | "audit" | "advanced" | "updates" | "about") { settingsTab = value; },
    get showServiceSettingsSaved() { return showServiceSettingsSaved; },
    get showToast() { return showToast; },
    get sortedWorkspaces() { return sortedWorkspaces; },
    get statusMap() { return statusMap; },
    set statusMap(value: Record<string, "loading" | "ready">) { statusMap = value; },
    get toggleServiceInWorkspace() { return toggleServiceInWorkspace; },
    get view() { return view; },
    set view(value: AppView) { view = value; },
    get workspaces() { return workspaces; },
    set workspaces(value: Workspace[]) { workspaces = value; },
  });
   // Service settings changed but not saved yet.
   // A field requiring reload (URL/team/UA) changed.

  let sandboxAssignmentBusy = $state(false);

    const workspaceEditor = createWorkspaceEditorController({
    get MANAGED_SERVICE_PAGE_SIZE() { return MANAGED_SERVICE_PAGE_SIZE; },
    get appSettings() { return appSettings; },
    set appSettings(value: AppSettings) { appSettings = value; },
    get confirmAsk() { return confirmAsk; },
    get displayedServiceIcon() { return displayedServiceIcon; },
    get error() { return error; },
    set error(value: string | null) { error = value; },
    get failedWorkspaceIcons() { return failedWorkspaceIcons; },
    set failedWorkspaceIcons(value: Set<string>) { failedWorkspaceIcons = value; },
    get handleDeleteWorkspace() { return handleDeleteWorkspace; },
    get loadServiceIcon() { return loadServiceIcon; },
    get preferredWebsiteIcon() { return preferredWebsiteIcon; },
    get reloadWorkspaces() { return reloadWorkspaces; },
    get showToast() { return showToast; },
    get sorted() { return sorted; },
    get sortedWorkspaces() { return sortedWorkspaces; },
    get toggleServiceInWorkspace() { return toggleServiceInWorkspace; },
    get workspaces() { return workspaces; },
  });

  type Tab = SettingsTab;
  let settingsTab = $state<Tab>("general");
  let settingsSearch: { focus: () => void; dismiss: () => void } | undefined = $state();
  let settingsSearchIntent = 0;
  let settingsSearchHighlight: HTMLElement | null = null;
  let settingsSearchTimer: ReturnType<typeof setTimeout> | undefined;

  function clearSettingsSearchHighlight() {
    if (settingsSearchTimer) clearTimeout(settingsSearchTimer);
    settingsSearchTimer = undefined;
    settingsSearchHighlight?.removeAttribute("data-settings-search-highlight");
    settingsSearchHighlight = null;
  }

  function cancelSettingsSearchNavigation() {
    settingsSearchIntent++;
    clearSettingsSearchHighlight();
  }

  async function revealSetting(entry: SettingsSearchEntry): Promise<string | null> {
    const intent = ++settingsSearchIntent;
    clearSettingsSearchHighlight();
    // Reuse the editor's existing discard warning rather than silently losing a draft.
    if (entry.workspaceList && workspaceEditor.managedWorkspace) {
      await workspaceEditor.closeManagedWorkspace();
      if (intent !== settingsSearchIntent || view !== "appSettings") return null;
      if (workspaceEditor.managedWorkspace) return "Navigation canceled. Your workspace name changes were kept.";
    }
    selectSettingsTab(entry.tab);
    await tick();
    if (intent !== settingsSearchIntent || view !== "appSettings" || settingsTab !== entry.tab) return null;
    let destination = document.getElementById(entry.target);
    let hint = "";
    if (!destination && entry.fallback) {
      destination = document.getElementById(entry.fallback.target);
      hint = entry.fallback.message;
    }
    if (destination?.closest(".download-toast-options:disabled")) {
      destination = document.getElementById("settings-option-downloadToasts");
      hint = destination?.querySelector<HTMLInputElement>("input")?.checked
        ? "Download notification settings are being saved. Try this option again shortly."
        : "Enable download completion toasts to configure notification details.";
    }
    if (!destination) return "This setting is not currently available. Choose its Settings tab to review the available options.";
    settingsSearchHighlight = destination;
    destination.setAttribute("data-settings-search-highlight", "true");
    // Focus never clicks an action button or changes a preference. This also prevents
    // a held Enter key from starting a backup or shortcut recording after navigation.
    const control = entry.focusContainer ? null : destination.querySelector<HTMLElement>(
      'input:not(:disabled):not([type="hidden"]), select:not(:disabled), textarea:not(:disabled)',
    );
    const focus = control ?? destination;
    if (!control) focus.tabIndex = -1;
    focus.focus({ preventScroll: true });
    const tabDestination = entry.target === `settings-tab-${entry.tab}`;
    destination.scrollIntoView({ block: tabDestination ? "start" : "center", behavior: "auto" });
    settingsSearchTimer = setTimeout(clearSettingsSearchHighlight, 2500);
    return hint || `Opened ${settingsTabLabel(entry.tab)}: ${entry.label}.`;
  }

  let managedServiceQuery = $state("");
  let managedWorkspaceFilter = $state("all");
  let managedServicePage = $state(0);
  let serviceExportSelection = $state<Set<string>>(new Set());
  let serviceExportIncludeAllPersonalRecipes = $state(false);
  let serviceExportIncludeSensitiveRecipeScripts = $state(false);
  let serviceExportBusy = $state(false);
  let serviceExportStatus = $state("");

  let downloadSettingsBusy = $state(false);
  let workspaceUsagePersist: Promise<void> = Promise.resolve();
  const MANAGED_SERVICE_PAGE_SIZE = 100;
  const MAX_SIDEBAR_WIDTH_PX = 1200;

    const appearance = createAppearanceController({
    get appSettings() { return appSettings; },
    set appSettings(value: AppSettings) { appSettings = value; },
    get applyLayout() { return applyLayout; },
    get applyTheme() { return applyTheme; },
    get error() { return error; },
    set error(value: string | null) { error = value; },
    get saveAppSetting() { return saveAppSetting; },
    get showToast() { return showToast; },
  });

  let recordingAction = $state<KeybindingAction | null>(null);
  let recordingStrokes = $state<string[]>([]);
  let recordingTimer: ReturnType<typeof setTimeout> | null = null;
  let shortcutPending = $state<{ stroke: string; at: number } | null>(null);

  let quickSwitcherMode = $state<QuickSwitcherMode | null>(null);
  let quickSwitcherQuery = $state("");
  let quickSwitcherIndex = $state(0);
  let lastQuickSwitcherShortcutToggle: { mode: QuickSwitcherMode | null; at: number } = { mode: null, at: 0 };

  let serviceMenuOpener: HTMLElement | null = null;
  let nativeMenuIntent = 0;
  let unlistenServiceMenuAction: (() => void) | undefined;
  let unlistenServiceMenuClosed: (() => void) | undefined;
  const serviceMenu = new ServiceMenuController({
    prepare: prepareServiceMenu,
    present: (id) => document.hasFocus() ? presentServiceMenu(id) : Promise.resolve(false),
    close: closeServiceMenu,
    fallback: async (request, isCurrent) => {
      const service = services.find((item) => item.id === request.serviceId);
      if (service) {
        try { await popupNativeServiceContextMenu(service, request.x, request.y, isCurrent, request.pixelRatio); }
        catch (failure) { error = `Unable to open service menu: ${failure}`; throw failure; }
      }
    },
    error: (failure) => console.warn(`Service menu: ${failure}`),
  });
  let toastMessage = $state("");
  let toastTone = $state<"default" | "success">("default");
  let toastTimer: ReturnType<typeof setTimeout> | null = null;
  const pendingReloadToasts = new Map<string, string>();
  let appMetadata = $state<AppMetadata | null>(null);
  const projectRepository = $derived((appMetadata?.repository || "https://github.com/Akkitto/Tauridium").replace(/\/$/, ""));

  let newSandboxName = $state("");
  let sandboxServiceQuery = $state("");
  let sandboxServicePage = $state(0);

  const nativeDistribution: DistributionInfo = {
    mode: "native",
    updaterManagedExternally: false,
    portalFileAccess: false,
    portalNotifications: false,
    portalAutostart: false,
    downloadsRequireDestination: false,
    automaticBackupsUsePrivateStorage: false,
  };
  let distributionInfo = $state<DistributionInfo>(nativeDistribution);

  // Updates (native packages only; Flatpak delegates updates to the package manager).
  let appVer = $state("");
    const updates = createUpdatesController({
    get distributionInfo() { return distributionInfo; },
  });

  // Portable backup/export state.
    const backups = createBackupsController({
    get appSettings() { return appSettings; },
    set appSettings(value: AppSettings) { appSettings = value; },
    get confirmAsk() { return confirmAsk; },
    get error() { return error; },
    set error(value: string | null) { error = value; },
    get saveAppSetting() { return saveAppSetting; },
  });

  let automaticBackupTimer: ReturnType<typeof setInterval> | null = null;

  let portableExportStatus = $state("");
    const audit = createAuditController({
    get confirmAsk() { return confirmAsk; },
  });

  let sidebarResizeFrame: number | null = null;

  let appSettings = $state<AppSettings>(createAppSettingsDefaults());

  // Hibernation: suspended services have their webview closed while retaining the session.
  let hibernated = $state<Set<string>>(new Set());
  const hibTimers = new Map<string, ReturnType<typeof setTimeout>>();
  const serviceZoomOperations = new Map<string, Promise<void>>();
  let preloadGeneration = 0; // Invalidates older delayed preload chains without races.

  // Add service / local recipe management.

  let addMode = $state<AddMode>("catalog");
  let recipeQuery = $state("");
  let allRecipes = $state<RecipePreview[]>([]);
  let recipesLoading = $state(false);
  let newServiceName = $state("");
  let customWebsiteUrl = $state("");
  let recipeStorage = $state<RecipeStorageInfo | null>(null);
  let recipeAdvanced = $state(false);
  let recipeIdEdited = $state(false);
  let recipeSaving = $state(false);
  let recipeDraft = $state<RecipeDraft>({
    id: "",
    name: "",
    serviceUrl: "",
    description: "",
    hasCustomUrl: false,
    hasTeamId: false,
    iconSvg: "",
    webviewJs: "",
  });

  const activeService = $derived(
    services.find((s) => s.id === activeId) ?? null,
  );
  const sorted = $derived(orderedBySavedIds(services, appSettings.serviceOrder));
  const sortedWorkspaces = $derived(
    orderedBySavedIds(workspaces, appSettings.workspaceOrder),
  );
  const quickSwitcherWorkspaces = $derived(
    orderWorkspacesForQuickSwitch(
      sortedWorkspaces,
      appSettings.workspaceQuickSwitchOrder,
      appSettings.workspaceLastUsed,
    ),
  );

  const activeWorkspaceName = $derived(
    activeWorkspace
      ? workspaces.find((workspace) => workspace.id === activeWorkspace)?.name ?? "All services"
      : "All services",
  );

  let lastAppliedWindowTitle = "";
  let lastAppliedTaskbarTitle = "";

  function desiredPresentationTitles(): { windowTitle: string; taskbarTitle: string } {
    const context = {
      app: "Tauridium",
      workspace: activeWorkspaceName,
      service: activeService ? serviceLabel(activeService) : "No service",
    };
    const custom = appSettings.customTitleTemplatesEnabled;
    const windowTitle = appSettings.showWorkspaceInWindowTitle
      ? renderTitleTemplate(
          custom ? appSettings.windowTitleTemplate : DEFAULT_WINDOW_TITLE_TEMPLATE,
          context,
        )
      : context.app;
    const taskbarTitle = appSettings.showWorkspaceInTaskbarTitle
      ? renderTitleTemplate(
          custom ? appSettings.taskbarTitleTemplate : DEFAULT_TASKBAR_TITLE_TEMPLATE,
          context,
        )
      : context.app;
    return { windowTitle, taskbarTitle };
  }

  function syncPresentationTitles() {
    const { windowTitle, taskbarTitle } = desiredPresentationTitles();
    if (windowTitle === lastAppliedWindowTitle && taskbarTitle === lastAppliedTaskbarTitle) return;
    lastAppliedWindowTitle = windowTitle;
    lastAppliedTaskbarTitle = taskbarTitle;
    setPresentationTitles(windowTitle, taskbarTitle).catch((err) => {
      lastAppliedWindowTitle = "";
      lastAppliedTaskbarTitle = "";
      console.warn("Unable to update native Tauridium titles", err);
    });
  }

  $effect(() => {
    syncPresentationTitles();
  });
  const visibleServices = $derived.by(() => {
    let list = sorted;
    if (activeWorkspace) {
      const ws = workspaces.find((w) => w.id === activeWorkspace);
      const ids = new Set(ws?.services ?? []);
      list = list.filter((s) => ids.has(s.id));
    }
    if (!appSettings.showDisabledServices) {
      list = list.filter((s) => s.isEnabled !== false);
    }
    return list;
  });
  const managedServices = $derived.by(() => {
    let list = sorted;
    if (managedWorkspaceFilter !== "all") {
      const workspace = workspaces.find((candidate) => candidate.id === managedWorkspaceFilter);
      const memberIds = new Set(workspace?.services ?? []);
      list = list.filter((service) => memberIds.has(service.id));
    }
    const query = managedServiceQuery.trim().toLowerCase();
    if (query) {
      list = list.filter((service) =>
        `${serviceLabel(service)} ${service.recipeId}`.toLowerCase().includes(query),
      );
    }
    return list;
  });
  const managedServicePageCount = $derived(
    Math.max(1, Math.ceil(managedServices.length / MANAGED_SERVICE_PAGE_SIZE)),
  );
  const managedServiceRows = $derived(
    paged(managedServices, managedServicePage, MANAGED_SERVICE_PAGE_SIZE),
  );
  const selectedServiceExports = $derived(
    sorted.filter((service) => serviceExportSelection.has(service.id)),
  );
  const keybindingConflicts = $derived(shortcutConflicts(appSettings.keybindings));
  const quickSwitcherItems = $derived.by(() => {
    const query = quickSwitcherQuery.trim().toLowerCase();
    if (quickSwitcherMode === "workspace") {
      return [{ id: "__all__", name: "All services" }, ...quickSwitcherWorkspaces]
        .filter((workspace) => !query || workspace.name.toLowerCase().includes(query))
        .map((workspace) => ({ id: workspace.id, label: workspace.name, kind: "workspace" as const }));
    }
    if (quickSwitcherMode === "service") {
      return visibleServices
        .filter((service) => service.isEnabled !== false)
        .filter((service) => !query || `${serviceLabel(service)} ${service.recipeId}`.toLowerCase().includes(query))
        .map((service) => ({ id: service.id, label: serviceLabel(service), kind: "service" as const }));
    }
    return [];
  });
  const sandboxServices = $derived.by(() => {
    const query = sandboxServiceQuery.trim().toLowerCase();
    return sorted.filter((service) =>
      !query || `${serviceLabel(service)} ${service.recipeId}`.toLowerCase().includes(query),
    );
  });
  const sandboxServicePageCount = $derived(
    Math.max(1, Math.ceil(sandboxServices.length / MANAGED_SERVICE_PAGE_SIZE)),
  );
  const sandboxServiceRows = $derived(
    paged(sandboxServices, sandboxServicePage, MANAGED_SERVICE_PAGE_SIZE),
  );

  const darkMq =
    typeof window !== "undefined"
      ? window.matchMedia("(prefers-color-scheme: dark)")
      : null;

  // OS-specific wording used by settings descriptions.
  const osKind: "mac" | "win" | "linux" = /Mac|iPhone|iPad/.test(
    navigator.userAgent,
  )
    ? "mac"
    : /Win/.test(navigator.userAgent)
      ? "win"
      : "linux";
  const trayWord = osKind === "mac" ? "menu bar" : "system tray";
  const dockWord = osKind === "mac" ? "Dock" : "taskbar";
  const loginText =
    osKind === "mac"
      ? "when you sign in to your Mac"
      : osKind === "win"
        ? "when you sign in to Windows"
        : "when you log in";

  let unifiedTitleBarAtStartup = $state<boolean | null>(null);
  let unifiedTitleBarFallback = $state(false);
  let unifiedTitleBarBusy = $state(false);
  async function saveUnifiedTitleBar(value: boolean) {
    if (unifiedTitleBarBusy) return;
    const previous = appSettings.unifiedTitleBar;
    unifiedTitleBarBusy = true;
    appSettings = { ...appSettings, unifiedTitleBar: value };
    try {
      const saved = await setAppSettings({ unifiedTitleBar: value });
      if (saved.unifiedTitleBar !== value) throw new Error("Unable to verify the title-bar preference");
      appSettings = saved;
      showToast("Saved. Quit and reopen Tauridium to apply.", "success");
    } catch (err) {
      appSettings = { ...appSettings, unifiedTitleBar: previous };
      error = `Unable to save the title-bar preference: ${err}`;
    } finally { unifiedTitleBarBusy = false; }
  }

  let downloadToastSettingsBusy = $state(false);
  let downloadToastHeight = $state(0);
  let unlistenWindowChrome: (() => void) | null = null;
  let unlistenDownloadToastGeometry: (() => void) | null = null;
  const downloadToastExample = $derived(downloadToastPreview(appSettings.downloadToastLocation, appSettings.downloadToastParentLevels, osKind === "win"));

  async function saveDownloadToastSetting<K extends "downloadToasts" | "downloadToastLocation" | "downloadToastParentLevels" | "downloadToastDuration">(key: K, value: AppSettings[K]) {
    if (downloadToastSettingsBusy || appSettings[key] === value) return;
    const previous = appSettings[key];
    downloadToastSettingsBusy = true;
    appSettings = { ...appSettings, [key]: value };
    try {
      const persisted = await setAppSettings({ [key]: value });
      if (persisted[key] !== value) throw new Error("Tauridium could not verify the saved download notification setting");
      appSettings = persisted;
      showToast("Saved", "success");
    } catch (err) {
      appSettings = { ...appSettings, [key]: previous };
      error = `Unable to save download notification settings: ${err}`;
    } finally {
      downloadToastSettingsBusy = false;
    }
  }

  function saveDownloadToastParentLevels(event: Event) {
    if (!(event.currentTarget instanceof HTMLInputElement)) return;
    const value = event.currentTarget.valueAsNumber;
    if (!Number.isInteger(value) || value < 1 || value > 10) {
      event.currentTarget.value = String(appSettings.downloadToastParentLevels);
      error = "Choose between 1 and 10 parent folders for the download notification.";
      return;
    }
    void saveDownloadToastSetting("downloadToastParentLevels", value);
  }

  onDestroy(() => {
    auth.cancelReconnect();
    unlistenDownloadToastGeometry?.();
    unlistenServiceMenuAction?.();
    unlistenServiceMenuClosed?.();
    closeServiceContextMenu();
    window.removeEventListener("pointerdown", closeServiceContextMenu, true);
    window.removeEventListener("pointerup", releaseServiceMenuPointer, true);
    window.removeEventListener("mouseup", releaseServiceMenuPointer, true);
    window.removeEventListener("pointercancel", cancelServiceMenuPointer, true);
    window.removeEventListener("blur", blurServiceMenuOwner);
    unlistenWindowChrome?.();
    if (automaticBackupTimer) clearInterval(automaticBackupTimer);
    if (recordingTimer) clearTimeout(recordingTimer);
    if (toastTimer) clearTimeout(toastTimer);
    if (sidebarResizeFrame !== null) cancelAnimationFrame(sidebarResizeFrame);
    window.removeEventListener("keydown", handleGlobalKeydown, true);
    window.removeEventListener("resize", handleWindowResize);
  });

  onMount(async () => {
    unlistenServiceMenuAction = await listen<{ id: number; serviceId: string; action: ServiceMenuAction }>("service-menu-action", (event) => {
      dispatchServiceMenuAction(event.payload.id, event.payload.serviceId, event.payload.action);
    });
    unlistenServiceMenuClosed = await listen<{ id: number; restoreFocus: boolean }>("service-menu-closed", (event) => {
      if (serviceMenu.closed(event.payload.id) && event.payload.restoreFocus) serviceMenuOpener?.focus();
    });
    window.addEventListener("pointerdown", closeServiceContextMenu, true);
    window.addEventListener("pointerup", releaseServiceMenuPointer, true);
    window.addEventListener("mouseup", releaseServiceMenuPointer, true);
    window.addEventListener("pointercancel", cancelServiceMenuPointer, true);
    window.addEventListener("blur", blurServiceMenuOwner);
    const unlistenChrome = await listen<{ enabled: boolean; fallback: boolean }>("window-chrome-changed", (event) => {
      unifiedTitleBarAtStartup = event.payload.enabled;
      unifiedTitleBarFallback = event.payload.fallback;
    });
    unlistenWindowChrome = unlistenChrome;
    unlistenDownloadToastGeometry = await listen<number>("download-toast-geometry", (event) => {
      downloadToastHeight = Number.isFinite(event.payload) ? Math.max(0, event.payload) : 0;
    });
    darkMq?.addEventListener("change", () => {
      if (appSettings.theme === "system") applyTheme();
    });
    listen<Record<string, number>>("unread", (e) => {
      unreadMap = e.payload;
    });
    listen<{ id: string; status: "loading" | "ready" }>("svc-status", (e) => {
      statusMap = { ...statusMap, [e.payload.id]: e.payload.status };
      if (e.payload.status === "ready") {
        // Start reload notifications only after the replacement service page is actually ready.
        // This prevents the notification from being destroyed together with the old webview.
        const reloadToast = pendingReloadToasts.get(e.payload.id);
        if (reloadToast) {
          pendingReloadToasts.delete(e.payload.id);
          showToast(reloadToast);
        }
        // The requested service loaded, so clear any previous opening error.
        if (e.payload.id === activeId) serviceLoadError = null;
      }
    });
    // Native Services menu events use stable IDs so filtering/workspace changes cannot
    // make a numbered menu item select the wrong service.
    listen<string>("select-service-id", (e) => {
      const service = services.find((candidate) => candidate.id === e.payload);
      if (service && service.isEnabled !== false) selectService(service);
    });
    // Native menu actions always route through the shell so service webviews cannot cover them.
    listen("open-settings", openAppSettings);
    listen("open-add-service", openAdd);
    listen("open-add-workspace", openAddWorkspace);
    listen("open-about", openAbout);
    listen("sign-out", handleLogout);
    listen<string>("shortcut-action", (event) => executeShortcutAction(event.payload as KeybindingAction));
    window.addEventListener("keydown", handleGlobalKeydown, true);
    window.addEventListener("resize", handleWindowResize);
    try {
      distributionInfo = await getDistributionInfo();
    } catch {
      distributionInfo = nativeDistribution;
    }
    try {
      appSettings = await getAppSettings();
      const startupSidebarCollapsed = resolveStartupSidebarCollapsed(
        appSettings.defaultSidebarCollapsed,
        appSettings.restoreLastSidebarStateOnStartup,
        appSettings.sidebarCollapsed,
      );
      if (startupSidebarCollapsed !== appSettings.sidebarCollapsed) {
        appSettings.sidebarCollapsed = startupSidebarCollapsed;
        setAppSettings({ sidebarCollapsed: startupSidebarCollapsed }).catch(() => {});
      }
      // Snap iconSize to a valid level for compatibility with older arbitrary values.
      const snapped = snapIconSize(appSettings.iconSize);
      if (snapped !== appSettings.iconSize) {
        appSettings.iconSize = snapped;
        setAppSettings({ iconSize: snapped }).catch(() => {});
      }
      applyTheme();
      syncSidebarWidth();
    } catch {
      /* defaults */
    }
    if (osKind === "win") {
      try {
        const chrome = await getWindowChrome();
        unifiedTitleBarAtStartup = chrome.enabled;
        unifiedTitleBarFallback = chrome.fallback;
      } catch (err) {
        error = `Unable to read the current title-bar mode: ${err}`;
      }
    }
    // Restore the session. If the server is unreachable (Ferdium outage, network issue, etc.),
    // do NOT show login; a reconnect screen retries automatically every 30 seconds.
    const restored = await auth.attemptRestore();
    booting = false;
    if (!restored) auth.startReconnect(auth.attemptRestore);
    await backups.maybeRunAutomaticBackup(true);
    automaticBackupTimer = setInterval(() => {
      void backups.maybeRunAutomaticBackup(false);
    }, 60 * 60 * 1000);
    appVersion()
      .then((v) => (appVer = v))
      .catch(() => {});
    getAppMetadata()
      .then((metadata) => (appMetadata = metadata))
      .catch(() => {});
    if (!distributionInfo.updaterManagedExternally) {
      updates.checkUpdates(true); // Silent native-package startup check.
    }
  });

  function applyTheme() {
    const dark =
      appSettings.theme === "dark" ||
      appSettings.theme === "oled" ||
      (appSettings.theme === "system" && (darkMq?.matches ?? true));
    document.body.classList.toggle("light", !dark);
    document.body.classList.toggle("oled", appSettings.theme === "oled");
    document.body.style.setProperty("--accent", appSettings.accentColor);
    document.body.style.setProperty("--accent-fg", accentFg(appSettings.accentColor));
  }

  function effectiveSidebarWidthPx(): number {
    if (appSettings.sidebarCollapsed) return COLLAPSED_SIDEBAR_WIDTH_PX;
    if (appSettings.sidebarWidthMode !== "percent") return appSettings.sidebarWidth;
    const preferred = window.innerWidth * (appSettings.sidebarWidthPercent / 100);
    // Preserve a useful service viewport and the same backend width ceiling on every display.
    const availableMax = Math.max(160, Math.min(MAX_SIDEBAR_WIDTH_PX, window.innerWidth - 360));
    return Math.max(160, Math.min(availableMax, preferred));
  }

  // Sidebar customization: width, icon size, grayscale/dimming, and alignment.
  function applyLayout() {
    const b = document.body;
    b.style.setProperty("--sidebar-w", `${effectiveSidebarWidthPx()}px`);
    b.style.setProperty("--icon-size", `${appSettings.iconSize}px`);
    b.style.setProperty("--collapsed-service-gap", `${appSettings.collapsedServiceSpacing}px`);
    b.style.setProperty("--expanded-service-gap", `${appSettings.expandedServiceSpacing}px`);
    b.classList.toggle("sidebar-collapsed", !!appSettings.sidebarCollapsed);
    b.classList.toggle("grayscale", !!appSettings.grayscaleServices);
    // dim 0..100 controls grayscale icon opacity (100 = heavily faded).
    const op = Math.max(0.2, 1 - (appSettings.grayscaleDim ?? 50) / 130);
    b.style.setProperty("--gray-op", String(op));
    b.dataset.svcloc = appSettings.sidebarServicesLocation ?? "top";
  }

  function syncSidebarWidth() {
    applyLayout();
    setSidebarWidth(effectiveSidebarWidthPx()).catch(() => {});
  }

  function handleWindowResize() {
    closeServiceContextMenu();
    if (appSettings.sidebarCollapsed || appSettings.sidebarWidthMode !== "percent" || sidebarResizeFrame !== null) return;
    sidebarResizeFrame = requestAnimationFrame(() => {
      sidebarResizeFrame = null;
      syncSidebarWidth();
    });
  }

  function serviceSandboxId(serviceId: string): string | null {
    return ownValue(appSettings.serviceSandboxes, serviceId) || null;
  }

  function showToast(message: string, tone: "default" | "success" = "default") {
    toastMessage = message;
    toastTone = tone;
    // Service webviews are native child webviews and render above the shell DOM. Mirror the
    // shell toast into Tauridium's isolated service overlay so notifications remain visible
    // without depending on the hosted website's layout or reload lifecycle.
    if (view === "service" && activeId) {
      void showServiceToastOverlay(activeId, message).catch(() => {});
    }
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toastMessage = "";
      toastTone = "default";
      toastTimer = null;
    }, 2600);
  }

  function showServiceSettingsSaved(serviceId: string) {
    if (view === "svcSettings" && serviceEditor.settingsSvc?.id === serviceId) {
      showToast("Saved", "success");
    }
  }

  function preferredWebsiteIcon(service: Service): string | null {
    if (service.useFavicon !== true) return null;
    return ownValue(serviceIcons, service.id) ?? null;
  }

  function displayedServiceIcon(service: Service): string {
    return preferredWebsiteIcon(service) ?? iconSrc(service);
  }

  function serviceIconInverted(serviceId: string): boolean {
    return ownValue(appSettings.serviceIconInversions, serviceId) === true;
  }

  function serviceZoomPercent(serviceId: string): number {
    return normalizeServiceZoomPercent(ownValue(appSettings.serviceZoomLevels, serviceId) ?? 100);
  }

  function queueServiceZoom(
    service: Service,
    resolveNext: (current: number) => number,
  ): Promise<void> {
    const preceding = serviceZoomOperations.get(service.id) ?? Promise.resolve();
    const operation = preceding.then(async () => {
      const current = serviceZoomPercent(service.id);
      const next = normalizeServiceZoomPercent(resolveNext(current));
      if (next === current) {
        showToast(service.id === activeId ? `Zoom: ${next}%` : `${serviceLabel(service)} zoom: ${next}%`);
        return;
      }
      try {
        appSettings = await setServiceZoom(service.id, next);
        showToast(
          service.id === activeId ? `Zoom: ${next}%` : `${serviceLabel(service)} zoom: ${next}%`,
          "success",
        );
      } catch (err) {
        error = `Unable to set page zoom for ${serviceLabel(service)}: ${err}`;
      }
    });
    serviceZoomOperations.set(service.id, operation);
    void operation.finally(() => {
      if (serviceZoomOperations.get(service.id) === operation) serviceZoomOperations.delete(service.id);
    });
    return operation;
  }

  function increaseServiceZoom(service: Service): Promise<void> {
    return queueServiceZoom(service, (current) => stepServiceZoomPercent(current, 1));
  }

  function decreaseServiceZoom(service: Service): Promise<void> {
    return queueServiceZoom(service, (current) => stepServiceZoomPercent(current, -1));
  }

  function resetServiceZoom(service: Service): Promise<void> {
    return queueServiceZoom(service, () => 100);
  }

  function chooseServiceZoom(service: Service | null, zoomPercent: number): Promise<void> {
    if (!service) {
      error = "Unable to set page zoom because the service is no longer available.";
      return Promise.resolve();
    }
    return queueServiceZoom(service, () => zoomPercent);
  }

  async function saveServiceIconInversion(serviceId: string, inverted: boolean) {
    const previous = { ...appSettings.serviceIconInversions };
    const serviceIconInversions = { ...previous };
    if (inverted) setOwnValue(serviceIconInversions, serviceId, true);
    else delete serviceIconInversions[serviceId];
    if ((ownValue(previous, serviceId) === true) === inverted) return;

    appSettings = { ...appSettings, serviceIconInversions };
    try {
      const persisted = await setAppSettings({ serviceIconInversions });
      if ((ownValue(persisted.serviceIconInversions, serviceId) === true) !== inverted) {
        throw new Error("Tauridium could not verify the service icon inversion setting");
      }
      appSettings = persisted;
      showServiceSettingsSaved(serviceId);
    } catch (err) {
      appSettings = { ...appSettings, serviceIconInversions: previous };
      error = `Unable to save service icon inversion setting: ${err}`;
    }
  }

  async function saveTrackingException(serviceId: string, enabled: boolean) {
    if (serviceEditor.trackingPrivacyBusy || sandboxAssignmentBusy) return;
    const namespace = browserProfileNamespace(serviceId, appSettings.serviceSandboxes);
    const shared = namespace.startsWith("sandbox:");
    const previous = { ...appSettings.trackingPreventionExceptions };
    if ((ownValue(previous, namespace) === true) === enabled) return;
    serviceEditor.trackingPrivacyBusy = true;
    try {
      if (enabled && !(await confirmAsk(`Reduce Windows tracking protection for ${shared ? "every service in this shared sandbox" : "this service's isolated browser profile"}? This can help embedded sign-in challenges but reduces privacy. SmartScreen stays enabled. The change applies only after restarting Tauridium.`))) return;
      const trackingPreventionExceptions = { ...previous };
      if (enabled) setOwnValue(trackingPreventionExceptions, namespace, true);
      else delete trackingPreventionExceptions[namespace];
      const persisted = await setAppSettings({ trackingPreventionExceptions });
      if ((ownValue(persisted.trackingPreventionExceptions, namespace) === true) !== enabled) {
        throw new Error("Tauridium could not verify the browser profile privacy setting");
      }
      appSettings = persisted;
      showToast("Saved — restart Tauridium to apply browser privacy changes", "success");
    } catch (err) {
      error = `Unable to save browser privacy setting: ${err}`;
    } finally {
      serviceEditor.trackingPrivacyBusy = false;
    }
  }

  function workspaceIcon(workspace: Workspace): string | null {
    return ownValue(appSettings.workspaceIcons, workspace.id) ?? null;
  }

  function serviceDownloadOverride(serviceId: string): DownloadPreferenceOverride | null {
    return downloadOverride(appSettings.serviceDownloadSettings, serviceId);
  }

  function workspaceDownloadOverride(workspaceId: string): DownloadPreferenceOverride | null {
    return downloadOverride(appSettings.workspaceDownloadSettings, workspaceId);
  }

  function inheritedDownloadPreference(): DownloadPreferenceOverride {
    return {
      directory: appSettings.downloadDirectory,
      askEachDownload: appSettings.askEachDownload,
    };
  }

  async function chooseDownloadDirectory(current: string, title: string): Promise<string | null> {
    const selected = await open({
      directory: true,
      multiple: false,
      title,
      defaultPath: current.trim() || appSettings.downloadDirectory.trim() || undefined,
    });
    return Array.isArray(selected) ? (selected[0] ?? null) : selected;
  }

  async function saveServiceDownloadOverride(serviceId: string, preference: DownloadPreferenceOverride | null) {
    if (downloadSettingsBusy) return;
    const previous = { ...appSettings.serviceDownloadSettings };
    const serviceDownloadSettings = { ...previous };
    if (preference) setOwnValue(serviceDownloadSettings, serviceId, preference);
    else delete serviceDownloadSettings[serviceId];
    if (sameDownloadPreference(ownValue(previous, serviceId), preference)) return;

    downloadSettingsBusy = true;
    appSettings = { ...appSettings, serviceDownloadSettings };
    try {
      const persisted = await setAppSettings({ serviceDownloadSettings });
      if (!sameDownloadPreference(ownValue(persisted.serviceDownloadSettings, serviceId), preference)) {
        throw new Error("Tauridium could not verify the service download settings");
      }
      appSettings = persisted;
      showServiceSettingsSaved(serviceId);
    } catch (err) {
      appSettings = { ...appSettings, serviceDownloadSettings: previous };
      error = `Unable to save service download settings: ${err}`;
    } finally {
      downloadSettingsBusy = false;
    }
  }

  async function saveWorkspaceDownloadOverride(workspaceId: string, preference: DownloadPreferenceOverride | null) {
    if (downloadSettingsBusy) return;
    const previous = { ...appSettings.workspaceDownloadSettings };
    const workspaceDownloadSettings = { ...previous };
    if (preference) setOwnValue(workspaceDownloadSettings, workspaceId, preference);
    else delete workspaceDownloadSettings[workspaceId];
    if (sameDownloadPreference(ownValue(previous, workspaceId), preference)) return;

    downloadSettingsBusy = true;
    appSettings = { ...appSettings, workspaceDownloadSettings };
    try {
      const persisted = await setAppSettings({ workspaceDownloadSettings });
      if (!sameDownloadPreference(ownValue(persisted.workspaceDownloadSettings, workspaceId), preference)) {
        throw new Error("Tauridium could not verify the workspace download settings");
      }
      appSettings = persisted;
      showToast("Saved", "success");
    } catch (err) {
      appSettings = { ...appSettings, workspaceDownloadSettings: previous };
      error = `Unable to save workspace download settings: ${err}`;
    } finally {
      downloadSettingsBusy = false;
    }
  }

  async function chooseGlobalDownloadDirectory() {
    if (downloadSettingsBusy) return;
    try {
      const selected = await chooseDownloadDirectory(appSettings.downloadDirectory, "Choose default download folder");
      if (selected) await saveAppSetting("downloadDirectory", selected);
    } catch (err) {
      error = `Unable to choose download folder: ${err}`;
    }
  }

  async function chooseServiceDownloadDirectory(serviceId: string) {
    const current = serviceDownloadOverride(serviceId) ?? inheritedDownloadPreference();
    try {
      const selected = await chooseDownloadDirectory(current.directory, "Choose download folder for this service");
      if (selected) await saveServiceDownloadOverride(serviceId, { ...current, directory: selected });
    } catch (err) {
      error = `Unable to choose service download folder: ${err}`;
    }
  }

  async function chooseWorkspaceDownloadDirectory(workspaceId: string) {
    const current = workspaceDownloadOverride(workspaceId) ?? inheritedDownloadPreference();
    try {
      const selected = await chooseDownloadDirectory(current.directory, "Choose download folder for this workspace");
      if (selected) await saveWorkspaceDownloadOverride(workspaceId, { ...current, directory: selected });
    } catch (err) {
      error = `Unable to choose workspace download folder: ${err}`;
    }
  }

  function markWorkspaceIconFailed(workspaceId: string) {
    failedWorkspaceIcons = new Set(failedWorkspaceIcons).add(workspaceId);
  }

  function serviceIconFailed(service: Service): boolean {
    return failedIcons.has(service.id) && preferredWebsiteIcon(service) === null;
  }

  async function loadServiceIcon(
    service: Service,
    force = false,
    report = false,
    preferWebsiteIcon = service.useFavicon === true,
  ) {
    const attemptKey = `${service.id}:${preferWebsiteIcon ? "website" : "default"}`;
    if (!force && iconFetchAttempted.has(attemptKey)) return;
    iconFetchAttempted.add(attemptKey);
    try {
      const icon = await getServiceIcon(service, force, preferWebsiteIcon);
      if (icon) {
        serviceIcons = { ...serviceIcons, [service.id]: icon };
        const next = new Set(failedIcons);
        next.delete(service.id);
        failedIcons = next;
        if (report) showToast(`Refetched icon for ${serviceLabel(service)}.`);
      } else if (report) {
        showToast(`No website icon found for ${serviceLabel(service)}.`);
      }
    } catch (err) {
      if (report) error = `Unable to refetch icon for ${serviceLabel(service)}: ${err}`;
    }
  }

  function hydrateServiceIcons() {
    if (!appSettings.fetchMissingServiceIcons) return;
    for (const service of services) {
      if (service.useFavicon === true) void loadServiceIcon(service);
    }
  }

  function markIconFailed(service: Service) {
    failedIcons = new Set(failedIcons).add(service.id);
    if (appSettings.fetchMissingServiceIcons && service.useFavicon === true) {
      void loadServiceIcon(service, false, false, true);
    }
  }

  function closeServiceContextMenu() {
    nativeMenuIntent++;
    serviceMenu.cancel();
  }

  function openContextServiceSettings(service: Service) {
    closeServiceContextMenu();
    serviceEditor.openServiceSettings(service);
  }

  function dispatchServiceMenuAction(id: number, serviceId: string, action: ServiceMenuAction) {
    if (!serviceMenu.takeAction(id, serviceId)) return;
    const service = services.find((item) => item.id === serviceId);
    if (!service) return;
    if (action === "settings") openContextServiceSettings(service);
    else if (action === "reload" && service.isEnabled !== false) void reloadServiceFromUi(service);
    else if (action === "zoom-in") void increaseServiceZoom(service);
    else if (action === "zoom-out") void decreaseServiceZoom(service);
    else if (action === "zoom-reset") void resetServiceZoom(service);
    else if (action === "duplicate") void duplicateServiceFromUi(service);
    else if (action === "toggle") void toggleServiceEnabled(service);
  }

  async function popupNativeServiceContextMenu(service: Service, x: number, y: number, isCurrent = () => true, pixelRatio = window.devicePixelRatio) {
    const zoomPercent = serviceZoomPercent(service.id);
    const menu = await Menu.new({
      items: [
        { id: `settings-${service.id}`, text: "Settings", action: () => openContextServiceSettings(service) },
        { id: `reload-${service.id}`, text: "Reload", enabled: service.isEnabled !== false, action: () => void reloadServiceFromUi(service) },
        { item: "Separator" },
        { id: `zoom-in-${service.id}`, text: `Zoom in (${stepServiceZoomPercent(zoomPercent, 1)}%)`, enabled: zoomPercent < 200, action: () => void increaseServiceZoom(service) },
        { id: `zoom-out-${service.id}`, text: `Zoom out (${stepServiceZoomPercent(zoomPercent, -1)}%)`, enabled: zoomPercent > 50, action: () => void decreaseServiceZoom(service) },
        { id: `zoom-reset-${service.id}`, text: "Reset zoom (100%)", enabled: zoomPercent !== 100, action: () => void resetServiceZoom(service) },
        { item: "Separator" },
        { id: `duplicate-${service.id}`, text: "Duplicate", action: () => void duplicateServiceFromUi(service) },
        { id: `toggle-${service.id}`, text: service.isEnabled === false ? "Enable" : "Disable", action: () => void toggleServiceEnabled(service) },
      ],
    });
    try {
      const origin = await getCurrentWebview().position();
      if (isCurrent()) await menu.popup(new PhysicalPosition(Math.round(origin.x + x * pixelRatio), Math.round(origin.y + y * pixelRatio)));
    } finally {
      await menu.close().catch(() => {});
    }
  }

  function showStyledServiceMenu(service: Service, x: number, y: number, opener: EventTarget | null, held = false) {
    closeServiceContextMenu();
    serviceMenuOpener = opener instanceof HTMLElement ? opener : null;
    serviceMenuOpener?.focus({ preventScroll: true });
    if (!appSettings.prettyServiceContextMenu) {
      const intent = nativeMenuIntent;
      void popupNativeServiceContextMenu(service, x, y, () => nativeMenuIntent === intent).catch((err) => { error = `Unable to open service menu: ${err}`; });
      return;
    }
    const request: ServiceMenuRequest = {
      serviceId: service.id, label: serviceLabel(service), enabled: service.isEnabled !== false,
      zoomPercent: serviceZoomPercent(service.id), x, y, pixelRatio: window.devicePixelRatio,
      theme: document.body.classList.contains("light") ? "light" : document.body.classList.contains("oled") ? "oled" : "dark",
    };
    void serviceMenu.open(request, held);
  }

  function openServiceContextMenu(event: MouseEvent, service: Service) {
    event.preventDefault();
    event.stopPropagation();
    showStyledServiceMenu(service, event.clientX, event.clientY, event.currentTarget, event.buttons !== 0);
  }

  function captureServiceMenuPointer(event: PointerEvent) {
    if (captureMenuPointer(event.button, event.ctrlKey, navigator.platform) && event.currentTarget instanceof HTMLElement) {
      event.currentTarget.setPointerCapture(event.pointerId);
    }
  }

  function openServiceContextMenuFromKeyboard(event: KeyboardEvent, service: Service) {
    if (!(event.key === "ContextMenu" || (event.shiftKey && event.key === "F10"))) return;
    event.preventDefault();
    const rect = event.currentTarget instanceof HTMLElement ? event.currentTarget.getBoundingClientRect() : null;
    showStyledServiceMenu(service, rect ? rect.left + 28 : 12, rect ? rect.bottom : 12, event.currentTarget);
  }

  function blurServiceMenuOwner() { nativeMenuIntent++; serviceMenu.ownerBlur(); }

  function releaseServiceMenuPointer(event: MouseEvent) { serviceMenu.releasePointer(event.buttons); }
  function cancelServiceMenuPointer() { closeServiceContextMenu(); }

  function sameIds(left: string[], right: string[]): boolean {
    return left.length === right.length && left.every((id, index) => id === right[index]);
  }

  async function refreshNativeServicesMenu() {
    try {
      await syncServicesMenu(
        orderedBySavedIds(services, appSettings.serviceOrder).map((service) => ({
          id: service.id,
          name: serviceLabel(service),
          enabled: service.isEnabled !== false,
        })),
      );
    } catch (err) {
      error = `Unable to refresh the native Services menu: ${err}`;
    }
  }

  async function reconcileSavedOrders() {
    const serviceOrder = orderedBySavedIds(services, appSettings.serviceOrder).map((service) => service.id);
    const workspaceOrder = orderedBySavedIds(workspaces, appSettings.workspaceOrder).map((workspace) => workspace.id);
    const serviceIds = new Set(services.map((service) => service.id));
    const workspaceIds = new Set(workspaces.map((workspace) => workspace.id));
    const defaultWorkspaceId = !appSettings.defaultWorkspaceId || workspaceIds.has(appSettings.defaultWorkspaceId)
      ? appSettings.defaultWorkspaceId
      : "";
    const lastWorkspaceId = !appSettings.lastWorkspaceId || workspaceIds.has(appSettings.lastWorkspaceId)
      ? appSettings.lastWorkspaceId
      : defaultWorkspaceId;
    const workspaceLastUsed = Object.fromEntries(
      Object.entries(appSettings.workspaceLastUsed).filter(([workspaceId]) => workspaceIds.has(workspaceId)),
    );
    const workspaceIcons = Object.fromEntries(
      Object.entries(appSettings.workspaceIcons).filter(([workspaceId]) => workspaceIds.has(workspaceId)),
    );
    const serviceIconInversions = Object.fromEntries(
      Object.entries(appSettings.serviceIconInversions).filter(([serviceId]) => serviceIds.has(serviceId)),
    );
    const trackingPreventionExceptions = retainedTrackingExceptions(
      appSettings.trackingPreventionExceptions, serviceIds, new Set(appSettings.sandboxes.map((sandbox) => sandbox.id)),
    );
    const serviceDownloadSettings = Object.fromEntries(
      Object.entries(appSettings.serviceDownloadSettings).filter(([serviceId]) => serviceIds.has(serviceId)),
    );
    const workspaceDownloadSettings = Object.fromEntries(
      Object.entries(appSettings.workspaceDownloadSettings).filter(([workspaceId]) => workspaceIds.has(workspaceId)),
    );
    const startupWorkspaceChanged = defaultWorkspaceId !== appSettings.defaultWorkspaceId || lastWorkspaceId !== appSettings.lastWorkspaceId;
    const usageHistoryChanged = Object.keys(workspaceLastUsed).length !== Object.keys(appSettings.workspaceLastUsed).length;
    const workspaceIconsChanged = Object.keys(workspaceIcons).length !== Object.keys(appSettings.workspaceIcons).length;
    const serviceIconInversionsChanged = Object.keys(serviceIconInversions).length !== Object.keys(appSettings.serviceIconInversions).length;
    const trackingExceptionsChanged = Object.keys(trackingPreventionExceptions).length !== Object.keys(appSettings.trackingPreventionExceptions).length;
    const serviceDownloadSettingsChanged = Object.keys(serviceDownloadSettings).length !== Object.keys(appSettings.serviceDownloadSettings).length;
    const workspaceDownloadSettingsChanged = Object.keys(workspaceDownloadSettings).length !== Object.keys(appSettings.workspaceDownloadSettings).length;
    if (
      sameIds(serviceOrder, appSettings.serviceOrder) &&
      sameIds(workspaceOrder, appSettings.workspaceOrder) &&
      !startupWorkspaceChanged &&
      !usageHistoryChanged &&
      !workspaceIconsChanged &&
      !serviceIconInversionsChanged &&
      !trackingExceptionsChanged &&
      !serviceDownloadSettingsChanged &&
      !workspaceDownloadSettingsChanged
    ) return;
    try {
      const persisted = await setAppSettings({
        serviceOrder,
        workspaceOrder,
        defaultWorkspaceId,
        lastWorkspaceId,
        workspaceLastUsed,
        workspaceIcons,
        serviceIconInversions,
        trackingPreventionExceptions,
        serviceDownloadSettings,
        workspaceDownloadSettings,
      });
      if (!sameIds(persisted.serviceOrder, serviceOrder) || !sameIds(persisted.workspaceOrder, workspaceOrder)) {
        throw new Error("Tauridium could not verify the reconciled service/workspace order");
      }
      appSettings = persisted;
    } catch (err) {
      error = `Unable to reconcile saved service/workspace order: ${err}`;
    }
  }

  async function loadAfterAuth() {
    [services, workspaces] = await Promise.all([getServices(), getWorkspaces()]);
    await reconcileSavedOrders();
    await refreshNativeServicesMenu();
    await Promise.all(services.map((s) => setServiceFlags(s).catch(() => {})));
    const startupWorkspace = resolveStartupWorkspaceId(
      workspaces.map((workspace) => workspace.id),
      appSettings.defaultWorkspaceId,
      appSettings.restoreLastWorkspaceOnStartup,
      appSettings.lastWorkspaceId,
    );
    const first = selectWorkspace(startupWorkspace, false);
    preloadRest(first?.id);
    hydrateServiceIcons();
  }

  // Gradually preload other active services in off-screen webviews,
  // making later switches nearly instantaneous. Skip services destined for
  // hibernation because they would be unloaded, and respect the setting.
  function cancelPreloading() {
    preloadGeneration += 1;
  }

  function preloadRest(firstId: string | undefined) {
    if (!appSettings.preloadServices) return;
    const generation = ++preloadGeneration;
    const list = sorted.filter(
      (s) =>
        s.isEnabled !== false &&
        s.id !== firstId &&
        !(appSettings.hibernationTimer > 0 && s.isHibernationEnabled === true),
    );
    let i = 0;
    const step = () => {
      if (generation !== preloadGeneration) return; // Stop stale chains after logout/settings changes.
      const s = list[i++];
      if (!s) return;
      preloadService(s)
        .catch(() => {})
        .finally(() => setTimeout(step, 700));
    };
    setTimeout(step, 1500); // Let the active service load first.
  }

  // Start a reconnection loop that calls attempt every RECONNECT_SECS.
  // attempt returns true when finished (success OR definitive error), so stop;
  // false means the server is still unreachable, so retry later.

  // Try to restore the session. true = finished (connected OR expired session ->
  // login screen); false = server unreachable (retry later).

  // Try login with pending credentials. false means the server is unreachable.

  function clearHibTimer(sid: string) {
    const t = hibTimers.get(sid);
    if (t) {
      clearTimeout(t);
      hibTimers.delete(sid);
    }
  }

  // Schedule hibernation for an eligible inactive service.
  function scheduleHibernation(sid: string) {
    clearHibTimer(sid);
    const secs = appSettings.hibernationTimer;
    const svc = services.find((s) => s.id === sid);
    if (!secs || secs <= 0 || svc?.isHibernationEnabled !== true) return;
    hibTimers.set(
      sid,
      setTimeout(() => {
        hibTimers.delete(sid);
        if (activeId === sid) return; // It became active again in the meantime.
        closeService(sid)
          .then(() => {
            hibernated = new Set(hibernated).add(sid);
            // The webview was destroyed, so its status is stale (show spinner on wake).
            const { [sid]: _, ...rest } = statusMap;
            statusMap = rest;
          })
          .catch(() => {});
      }, secs * 1000),
    );
  }

  function reconcileHibernationTimers() {
    for (const id of [...hibTimers.keys()]) clearHibTimer(id);
    if (!(appSettings.hibernationTimer > 0)) {
      // With hibernation disabled, there must be no delayed close left from an older setting.
      hibernated = new Set();
      if (appSettings.preloadServices) preloadRest(activeId ?? undefined);
      return;
    }
    for (const service of services) {
      if (
        service.id !== activeId &&
        service.isEnabled !== false &&
        service.isHibernationEnabled === true &&
        ownValue(statusMap, service.id)
      ) {
        scheduleHibernation(service.id);
      }
    }
  }

  function selectService(s: Service) {
    closeServiceContextMenu();
    if (s.isEnabled === false) return;
    clearServiceDragSelection();
    const prev = activeId;
    error = null;
    serviceLoadError = null;
    view = "service";
    activeId = s.id;
    clearHibTimer(s.id);
    if (hibernated.has(s.id)) {
      const next = new Set(hibernated);
      next.delete(s.id);
      hibernated = next;
    }
    if (prev && prev !== s.id) scheduleHibernation(prev);
    showService(s, activeWorkspace).catch((err) => {
      // Display the error only if this service is still on screen.
      if (activeId === s.id) serviceLoadError = `${err}`;
    });
  }

  function clearServiceDragSelection() {
    serviceDragSelection = [];
  }

  function onServiceRowClick(event: MouseEvent, service: Service) {
    if (event.shiftKey && appSettings.sidebarServiceDragReorder && !serviceOrderBusy) {
      const anchorId = activeId;
      const visibleIds = visibleServices.map((candidate) => candidate.id);
      if (anchorId && anchorId !== service.id) {
        const range = contiguousIdRange(visibleIds, anchorId, service.id);
        if (range.length > 1) {
          serviceDragSelection = range;
          return;
        }
      }
      clearServiceDragSelection();
      return;
    }

    if (serviceDragSelection.length) {
      clearServiceDragSelection();
      if (service.id === activeId) return;
    }
    selectService(service);
  }

  function retryActiveService() {
    const s = activeService;
    if (s) {
      statusMap = { ...statusMap, [s.id]: "loading" };
      selectService(s);
    }
  }

  // --- Service reordering ------------------------------------------------------
  async function persistServiceIds(nextIds: string[], previousIds: string[]) {
    if (serviceOrderBusy) return;
    serviceOrderBusy = true;
    appSettings = { ...appSettings, serviceOrder: nextIds };
    try {
      const persistedSettings = await setServiceOrder(nextIds);
      const persisted = persistedSettings.serviceOrder ?? [];
      if (persisted.length !== nextIds.length || persisted.some((id, i) => id !== nextIds[i])) {
        throw new Error("Tauridium could not verify the saved service order");
      }
      appSettings = { ...appSettings, serviceOrder: persisted };
      await refreshNativeServicesMenu();
      showToast("Saved", "success");
    } catch (err) {
      appSettings = { ...appSettings, serviceOrder: previousIds };
      error = `Unable to save service order: ${err}`;
      throw err;
    } finally {
      serviceOrderBusy = false;
    }
  }

  async function moveService(serviceId: string, delta: number) {
    if (serviceOrderBusy) return;
    const previousIds = sorted.map((service) => service.id);
    const index = previousIds.indexOf(serviceId);
    const target = index + delta;
    if (index < 0 || target < 0 || target >= previousIds.length) return;
    const nextIds = [...previousIds];
    [nextIds[index], nextIds[target]] = [nextIds[target], nextIds[index]];
    await persistServiceIds(nextIds, previousIds).catch(() => {});
  }

  function clearServiceDragState() {
    dragId = null;
    dragIds = [];
    dragOverId = null;
    dragPlacement = null;
  }

  function dragSelectionFor(serviceId: string): string[] {
    const visibleIds = visibleServices.map((service) => service.id);
    const selected = serviceDragSelection.includes(serviceId) ? serviceDragSelection : [serviceId];
    const selectedSet = new Set(selected);
    return visibleIds.filter((id) => selectedSet.has(id));
  }

  function onDragStart(e: DragEvent, s: Service) {
    if (!appSettings.sidebarServiceDragReorder || serviceOrderBusy) {
      e.preventDefault();
      clearServiceDragState();
      return;
    }
    const movingIds = dragSelectionFor(s.id);
    if (!serviceDragSelection.includes(s.id)) clearServiceDragSelection();
    dragId = s.id;
    dragIds = movingIds;
    dragOverId = null;
    dragPlacement = null;
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", s.id);
    }
  }

  function onDragOver(e: DragEvent, s: Service) {
    if (!appSettings.sidebarServiceDragReorder || serviceOrderBusy || !dragId) return;
    if (dragIds.includes(s.id)) {
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
      return;
    }
    const target = e.currentTarget instanceof HTMLElement ? e.currentTarget : null;
    if (!target) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
    const rect = target.getBoundingClientRect();
    const placement: ReorderPlacement = e.clientY < rect.top + rect.height / 2 ? "before" : "after";
    if (dragOverId !== s.id) dragOverId = s.id;
    if (dragPlacement !== placement) dragPlacement = placement;
  }

  function onDragLeave(e: DragEvent, s: Service) {
    if (dragOverId !== s.id) return;
    const next = e.relatedTarget;
    if (next instanceof Node && e.currentTarget instanceof Node && e.currentTarget.contains(next)) return;
    const area = e.currentTarget instanceof HTMLElement ? e.currentTarget.closest(".svcarea") : null;
    if (next instanceof Node && area instanceof Node && area.contains(next)) return;
    dragOverId = null;
    dragPlacement = null;
  }

  function onDragEnd() {
    clearServiceDragState();
  }

  function setTrailingDropTarget(e: DragEvent): Service | null {
    if (!appSettings.sidebarServiceDragReorder || serviceOrderBusy || !dragId || !visibleServices.length) return null;
    const list = e.currentTarget instanceof HTMLElement ? e.currentTarget.querySelector<HTMLElement>(".svclist") : null;
    if (!list) return null;
    const rect = list.getBoundingClientRect();
    if (e.clientY < rect.bottom) return null;
    const last = visibleServices.at(-1) ?? null;
    if (!last) return null;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
    dragOverId = last.id;
    dragPlacement = "after";
    return last;
  }

  function onServiceAreaDragOver(e: DragEvent) {
    setTrailingDropTarget(e);
  }

  async function persistServiceDrop(target: Service, placement: ReorderPlacement) {
    const previousIds = sorted.map((service) => service.id);
    const visibleIds = visibleServices.map((service) => service.id);
    const movingIds = dragIds.length ? dragIds : (dragId ? [dragId] : []);
    if (!movingIds.length) return;
    const nextIds = movingIds.length === 1
      ? reorderVisibleSubsetAt(previousIds, visibleIds, movingIds[0], target.id, placement)
      : reorderVisibleGroupAt(previousIds, visibleIds, movingIds, target.id, placement);
    if (nextIds.every((id, index) => id === previousIds[index])) return;
    await persistServiceIds(nextIds, previousIds).catch(() => {});
  }

  async function onServiceAreaDrop(e: DragEvent) {
    const target = setTrailingDropTarget(e);
    if (!target) return;
    const placement = dragPlacement;
    e.preventDefault();
    if (!placement) {
      clearServiceDragState();
      return;
    }
    await persistServiceDrop(target, placement);
    clearServiceDragState();
  }

  async function onDrop(e: DragEvent, target: Service) {
    e.preventDefault();
    if (!appSettings.sidebarServiceDragReorder || serviceOrderBusy) {
      clearServiceDragState();
      return;
    }
    const from = dragId ?? e.dataTransfer?.getData("text/plain") ?? null;
    const placement = dragOverId === target.id ? dragPlacement : null;
    if (!from || !placement || dragIds.includes(target.id)) {
      clearServiceDragState();
      return;
    }
    await persistServiceDrop(target, placement);
    clearServiceDragState();
  }

  // Handlers modify ONLY local state; Save persists everything at once.
  // Fields whose changes require recreating the webview (script injected at creation).
  const RELOAD_FIELDS = new Set<keyof Service>([
    "trapLinkClicks",
    "isDarkModeEnabled",
    "darkReaderBrightness",
    "darkReaderContrast",
    "darkReaderSepia",
  ]);

  async function setServiceEnabled(service: Service, enabled: boolean) {
    if ((service.isEnabled !== false) === enabled) return;
    try {
      await updateService(service.id, { isEnabled: enabled });
      services = services.map((candidate) => candidate.id === service.id ? { ...candidate, isEnabled: enabled } : candidate);
      if (serviceEditor.settingsSvc?.id === service.id) serviceEditor.settingsSvc = { ...serviceEditor.settingsSvc, isEnabled: enabled };
      await refreshNativeServicesMenu();
      if (!enabled) {
        clearHibTimer(service.id);
        await closeService(service.id).catch(() => {});
        const { [service.id]: _, ...rest } = statusMap;
        statusMap = rest;
        hibernated = new Set([...hibernated].filter((id) => id !== service.id));
        if (activeId === service.id) {
          activeId = null;
          const keepServiceSettingsOpen = view === "svcSettings" && serviceEditor.settingsSvc?.id === service.id;
          if (!keepServiceSettingsOpen) {
            const scoped = visibleServices.find((candidate) => candidate.id !== service.id && candidate.isEnabled !== false);
            const fallback = sorted.find((candidate) => candidate.id !== service.id && candidate.isEnabled !== false);
            const next = scoped ?? fallback ?? null;
            if (next) selectService(next);
            else {
              view = "service";
              await hideServices();
            }
          }
        }
      }
      if (view === "svcSettings" && serviceEditor.settingsSvc?.id === service.id) showServiceSettingsSaved(service.id);
      else showToast(`${serviceLabel(service)} ${enabled ? "enabled" : "disabled"}.`);
    } catch (err) {
      error = `Unable to ${enabled ? "enable" : "disable"} ${serviceLabel(service)}: ${err}`;
    }
  }

  async function toggleServiceEnabled(service: Service) {
    await setServiceEnabled(service, service.isEnabled === false);
  }

  function duplicatedServicePatch(service: Service): Record<string, unknown> {
    const patch: Record<string, unknown> = {
      isEnabled: service.isEnabled !== false,
      isNotificationEnabled: service.isNotificationEnabled,
      isMuted: service.isMuted,
      isBadgeEnabled: service.isBadgeEnabled,
      isMediaBadgeEnabled: service.isMediaBadgeEnabled,
      isIndirectMessageBadgeEnabled: service.isIndirectMessageBadgeEnabled,
      isHibernationEnabled: service.isHibernationEnabled,
      isWakeUpEnabled: service.isWakeUpEnabled,
      trapLinkClicks: service.trapLinkClicks,
      useFavicon: service.useFavicon,
      isDarkModeEnabled: service.isDarkModeEnabled,
      isProgressbarEnabled: service.isProgressbarEnabled,
      onlyShowFavoritesInUnreadCount: service.onlyShowFavoritesInUnreadCount,
      darkReaderBrightness: service.darkReaderBrightness,
      darkReaderContrast: service.darkReaderContrast,
      darkReaderSepia: service.darkReaderSepia,
      isProxyFeatureEnabled: service.isProxyFeatureEnabled,
      proxyHost: service.proxyHost ?? "",
      proxyPort: service.proxyPort ?? "",
      proxyUser: service.proxyUser ?? "",
      proxyPassword: service.proxyPassword ?? "",
      customUrl: service.customUrl ?? "",
      team: service.team ?? "",
      userAgentPref: service.userAgentPref ?? "",
    };
    if (service.isLocalRecipe === true) patch.iconUrl = service.iconUrl ?? null;
    return patch;
  }

  function createdServiceId(result: unknown): string | null {
    const value = result as { id?: string; data?: { id?: string }; service?: { id?: string } };
    return value?.id ?? value?.data?.id ?? value?.service?.id ?? null;
  }

  function createDuplicateService(service: Service, name: string): Promise<unknown> {
    if (service.isLocalRecipe === true && service.recipeId === "custom-website") {
      const url = service.customUrl?.trim();
      if (!url) return Promise.reject(new Error("Custom website service has no URL to duplicate"));
      return createCustomWebsiteService(name, url);
    }
    return createService(name, service.recipeId);
  }

  async function duplicateServiceFromUi(service: Service) {
    error = null;
    const name = duplicateServiceName(serviceLabel(service), services.map((candidate) => serviceLabel(candidate)));
    let newId: string | null = null;
    const changedWorkspaces: Workspace[] = [];
    const previousTemplates = { ...appSettings.serviceCustomUrlTemplates };
    const previousSandboxes = { ...appSettings.serviceSandboxes };
    const previousShortcutOverrides = { ...appSettings.serviceShortcutCaptureOverrides };
    const previousDownloadSettings = { ...appSettings.serviceDownloadSettings };
    const previousIconInversions = { ...appSettings.serviceIconInversions };
    const previousZoomLevels = { ...appSettings.serviceZoomLevels };
    let copiedAppSettings = false;
    try {
      const result = await createDuplicateService(service, name);
      newId = createdServiceId(result);
      if (!newId) {
        const refreshed = await getServices();
        newId = [...refreshed].reverse().find((candidate) => candidate.name === name && candidate.recipeId === service.recipeId)?.id ?? null;
      }
      if (!newId) throw new Error("Duplicated service did not return a service id");

      await updateService(newId, duplicatedServicePatch(service));
      if (service.useFavicon === true) {
        await copyServiceIconCache(service.id, newId);
        const icon = ownValue(serviceIcons, service.id);
        if (icon) serviceIcons = { ...serviceIcons, [newId]: icon };
      }

      for (const workspace of workspaces.filter((candidate) => candidate.services.includes(service.id))) {
        const members = [...workspace.services];
        const sourceIndex = members.indexOf(service.id);
        members.splice(sourceIndex + 1, 0, newId);
        await updateWorkspace(workspace.id, workspace.name, members);
        changedWorkspaces.push(workspace);
      }

      const serviceCustomUrlTemplates = { ...appSettings.serviceCustomUrlTemplates };
      const serviceSandboxes = { ...appSettings.serviceSandboxes };
      const serviceShortcutCaptureOverrides = { ...appSettings.serviceShortcutCaptureOverrides };
      const serviceDownloadSettings = { ...appSettings.serviceDownloadSettings };
      const serviceIconInversions = { ...appSettings.serviceIconInversions };
      const serviceZoomLevels = { ...appSettings.serviceZoomLevels };
      copyOwnEntry(serviceCustomUrlTemplates, service.id, newId);
      copyOwnEntry(serviceSandboxes, service.id, newId);
      copyOwnEntry(serviceShortcutCaptureOverrides, service.id, newId);
      copyOwnEntry(serviceDownloadSettings, service.id, newId);
      copyOwnEntry(serviceIconInversions, service.id, newId);
      copyOwnEntry(serviceZoomLevels, service.id, newId);
      if (ownValue(serviceCustomUrlTemplates, newId) || ownValue(serviceSandboxes, newId) || Object.hasOwn(serviceShortcutCaptureOverrides, newId) || ownValue(serviceDownloadSettings, newId) || ownValue(serviceIconInversions, newId) === true || ownValue(serviceZoomLevels, newId)) {
        appSettings = await setAppSettings({
          serviceCustomUrlTemplates,
          serviceSandboxes,
          serviceShortcutCaptureOverrides,
          serviceDownloadSettings,
          serviceIconInversions,
          serviceZoomLevels,
        });
        copiedAppSettings = true;
      }

      [services, workspaces] = await Promise.all([getServices(), getWorkspaces()]);
      await reconcileSavedOrders();
      const previousIds = orderedBySavedIds(services, appSettings.serviceOrder).map((candidate) => candidate.id);
      const nextIds = previousIds.filter((id) => id !== newId);
      const sourceIndex = nextIds.indexOf(service.id);
      nextIds.splice(sourceIndex >= 0 ? sourceIndex + 1 : nextIds.length, 0, newId);
      await persistServiceIds(nextIds, previousIds);
      await Promise.all(services.map((candidate) => setServiceFlags(candidate).catch(() => {})));
      const duplicate = services.find((candidate) => candidate.id === newId) ?? null;
      if (duplicate && service.useFavicon === true) await loadServiceIcon(duplicate, false, false, true);
      if (duplicate && duplicate.isEnabled !== false) selectService(duplicate);
      showToast(`Duplicated ${serviceLabel(service)} as ${name}.`);
    } catch (err) {
      for (const workspace of [...changedWorkspaces].reverse()) {
        await updateWorkspace(workspace.id, workspace.name, workspace.services).catch(() => {});
      }
      if (copiedAppSettings) {
        appSettings = await setAppSettings({
          serviceCustomUrlTemplates: previousTemplates,
          serviceSandboxes: previousSandboxes,
          serviceShortcutCaptureOverrides: previousShortcutOverrides,
          serviceDownloadSettings: previousDownloadSettings,
          serviceIconInversions: previousIconInversions,
          serviceZoomLevels: previousZoomLevels,
        }).catch(() => appSettings);
      }
      if (newId) await deleteService(newId).catch(() => {});
      try {
        [services, workspaces] = await Promise.all([getServices(), getWorkspaces()]);
      } catch {
        // Keep the last known in-memory state if rollback refresh itself is unavailable.
      }
      await reconcileSavedOrders().catch(() => {});
      await refreshNativeServicesMenu().catch(() => {});
      error = `Unable to duplicate ${serviceLabel(service)}: ${err}`;
    }
  }

  async function reloadServiceFromUi(service: Service) {
    if (service.isEnabled === false) return;
    if (appSettings.reloadToasts) pendingReloadToasts.set(service.id, `${serviceLabel(service)} reloaded.`);
    else pendingReloadToasts.delete(service.id);
    try {
      statusMap = { ...statusMap, [service.id]: "loading" };
      await closeService(service.id);
      const { [service.id]: _, ...rest } = statusMap;
      statusMap = rest;
      if (activeId === service.id) selectService(service);
      else await preloadService(service);
    } catch (err) {
      pendingReloadToasts.delete(service.id);
      error = `Unable to reload ${serviceLabel(service)}: ${err}`;
    }
  }

  async function refetchAllServiceIcons() {
    const preferred = services.filter((service) => service.useFavicon === true);
    if (preferred.length === 0) {
      showToast("No services currently prefer website icons.");
      return;
    }
    if (!(await confirmAsk(`Refetch website icons for ${preferred.length} service${preferred.length === 1 ? "" : "s"} that currently prefer them?`))) return;
    let success = 0;
    const failures: string[] = [];
    for (const service of preferred) {
      iconFetchAttempted.delete(`${service.id}:default`);
      iconFetchAttempted.delete(`${service.id}:website`);
      try {
        const icon = await getServiceIcon(service, true, true);
        if (icon) {
          serviceIcons = { ...serviceIcons, [service.id]: icon };
          success += 1;
        } else failures.push(serviceLabel(service));
      } catch {
        failures.push(serviceLabel(service));
      }
    }
    showToast(`Refetched ${success} of ${preferred.length} preferred website icons.`);
    if (failures.length) error = `No website icon was available for ${failures.length} service${failures.length === 1 ? "" : "s"}.`;
  }

  async function handleDelete(s: Service) {
    if (!(await confirmAsk(`Delete service "${s.name}"?`))) return;
    try {
      await deleteService(s.id);
      clearHibTimer(s.id); // Prevent a hibernation timer from re-adding a deleted service.
      const { [s.id]: _, ...rest } = statusMap;
      statusMap = rest;
      services = services.filter((x) => x.id !== s.id);
      if (
        ownValue(appSettings.serviceSandboxes, s.id) ||
        ownValue(appSettings.serviceCustomUrlTemplates, s.id) ||
        Object.hasOwn(appSettings.serviceShortcutCaptureOverrides, s.id) ||
        ownValue(appSettings.serviceDownloadSettings, s.id) ||
        ownValue(appSettings.serviceIconInversions, s.id) === true ||
        ownValue(appSettings.serviceZoomLevels, s.id)
      ) {
        const serviceSandboxes = { ...appSettings.serviceSandboxes };
        const serviceCustomUrlTemplates = { ...appSettings.serviceCustomUrlTemplates };
        const serviceShortcutCaptureOverrides = { ...appSettings.serviceShortcutCaptureOverrides };
        const serviceDownloadSettings = { ...appSettings.serviceDownloadSettings };
        const serviceIconInversions = { ...appSettings.serviceIconInversions };
        const serviceZoomLevels = { ...appSettings.serviceZoomLevels };
        delete serviceSandboxes[s.id];
        delete serviceCustomUrlTemplates[s.id];
        delete serviceShortcutCaptureOverrides[s.id];
        delete serviceDownloadSettings[s.id];
        delete serviceIconInversions[s.id];
        delete serviceZoomLevels[s.id];
        appSettings = await setAppSettings({
          serviceSandboxes,
          serviceCustomUrlTemplates,
          serviceShortcutCaptureOverrides,
          serviceDownloadSettings,
          serviceIconInversions,
          serviceZoomLevels,
        });
      }
      await reconcileSavedOrders();
      await refreshNativeServicesMenu();
      backToService();
    } catch (err) {
      error = String(err);
    }
  }

  async function handleClearCache(s: Service) {
    const sandboxId = serviceSandboxId(s.id);
    const sandbox = sandboxId
      ? appSettings.sandboxes.find((candidate) => candidate.id === sandboxId)
      : null;
    if (
      !(await confirmAsk(
        sandbox
          ? `Clear shared cache & session for sandbox “${sandbox.name}”? Every assigned service will be signed out.`
          : `Clear cache & session for "${s.name}"? You'll be signed out of this service.`,
      ))
    )
      return;
    try {
      await clearServiceCache(s.id);
      const affectedIds = sandboxId
        ? Object.entries(appSettings.serviceSandboxes)
            .filter(([, assigned]) => assigned === sandboxId)
            .map(([serviceId]) => serviceId)
        : [s.id];
      for (const serviceId of affectedIds) clearHibTimer(serviceId);
      statusMap = Object.fromEntries(
        Object.entries(statusMap).filter(([serviceId]) => !affectedIds.includes(serviceId)),
      );
      hibernated = new Set([...hibernated].filter((id) => !affectedIds.includes(id)));
      backToService(); // Reopens cleanly in a signed-out state.
    } catch (err) {
      error = String(err);
    }
  }

  async function reloadWorkspaces() {
    workspaces = await getWorkspaces();
    await reconcileSavedOrders();
    if (workspaceEditor.managedWorkspaceId && !workspaces.some((workspace) => workspace.id === workspaceEditor.managedWorkspaceId)) {
      workspaceEditor.managedWorkspaceId = null;
      workspaceEditor.managedWorkspaceNameDraft = "";
    }
    const query = workspaceEditor.managedWorkspaceQuery.trim().toLowerCase();
    const matchingCount = workspaces.filter((workspace) => !query || workspace.name.toLowerCase().includes(query)).length;
    const lastPage = Math.max(0, Math.ceil(matchingCount / MANAGED_SERVICE_PAGE_SIZE) - 1);
    workspaceEditor.managedWorkspacePage = Math.min(workspaceEditor.managedWorkspacePage, lastPage);
  }

  async function persistWorkspaceIds(nextIds: string[], previousIds: string[]) {
    appSettings = { ...appSettings, workspaceOrder: nextIds };
    try {
      appSettings = await setWorkspaceOrder(nextIds);
      const persisted = appSettings.workspaceOrder ?? [];
      if (persisted.length !== nextIds.length || persisted.some((id, i) => id !== nextIds[i])) {
        throw new Error("Tauridium could not verify the saved workspace order");
      }
      showToast("Saved", "success");
    } catch (err) {
      appSettings = { ...appSettings, workspaceOrder: previousIds };
      error = `Unable to save workspace order: ${err}`;
      throw err;
    }
  }

  async function moveManagedWorkspace(workspaceId: string, delta: number) {
    const visibleIds = workspaceEditor.managedWorkspaces.map((workspace) => workspace.id);
    const index = visibleIds.indexOf(workspaceId);
    const target = index + delta;
    if (index < 0 || target < 0 || target >= visibleIds.length) return;
    const previousIds = sortedWorkspaces.map((workspace) => workspace.id);
    const nextIds = reorderVisibleSubset(
      previousIds,
      visibleIds,
      workspaceId,
      visibleIds[target],
    );
    await persistWorkspaceIds(nextIds, previousIds).catch(() => {});
  }

  async function resetWorkspaceUsageHistory() {
    await saveAppSetting("workspaceLastUsed", {});
  }

  async function toggleServiceInWorkspace(
    ws: Workspace,
    serviceId: string,
    member: boolean,
  ): Promise<boolean> {
    const previous = [...ws.services];
    const set = new Set(previous);
    if (member) set.add(serviceId);
    else set.delete(serviceId);
    const list = [...set];
    workspaces = workspaces.map((candidate) => candidate.id === ws.id ? { ...candidate, services: list } : candidate);
    try {
      await updateWorkspace(ws.id, ws.name, list);
      return true;
    } catch (err) {
      workspaces = workspaces.map((candidate) => candidate.id === ws.id ? { ...candidate, services: previous } : candidate);
      error = `Unable to update workspace ${ws.name}: ${err}`;
      return false;
    }
  }

  async function renameWorkspace(ws: Workspace, name: string) {
    if (!name.trim() || name === ws.name) return;
    try {
      await updateWorkspace(ws.id, name.trim(), ws.services);
      await reloadWorkspaces();
    } catch (err) {
      error = String(err);
    }
  }

  async function handleDeleteWorkspace(ws: Workspace) {
    if (!(await confirmAsk(`Delete workspace "${ws.name}"?`))) return;
    try {
      await deleteWorkspace(ws.id);
      if (activeWorkspace === ws.id) activeWorkspace = null;
      if (workspaceEditor.managedWorkspaceId === ws.id) {
        workspaceEditor.managedWorkspaceId = null;
        workspaceEditor.managedWorkspaceNameDraft = "";
      }
      const workspaceLastUsed = { ...appSettings.workspaceLastUsed };
      const workspaceIcons = { ...appSettings.workspaceIcons };
      const workspaceDownloadSettings = { ...appSettings.workspaceDownloadSettings };
      const defaultWorkspaceId = appSettings.defaultWorkspaceId === ws.id ? "" : appSettings.defaultWorkspaceId;
      const lastWorkspaceId = appSettings.lastWorkspaceId === ws.id ? "" : appSettings.lastWorkspaceId;
      delete workspaceLastUsed[ws.id];
      delete workspaceIcons[ws.id];
      delete workspaceDownloadSettings[ws.id];
      appSettings = await setAppSettings({
        defaultWorkspaceId,
        lastWorkspaceId,
        workspaceLastUsed,
        workspaceIcons,
        workspaceDownloadSettings,
      });
      await reloadWorkspaces();
    } catch (err) {
      error = String(err);
    }
  }

  async function refreshRecipes() {
    recipesLoading = true;
    error = null;
    try {
      allRecipes = await listRecipes();
    } catch (err) {
      error = String(err);
    } finally {
      recipesLoading = false;
    }
  }

  async function openAdd() {
    closeServiceContextMenu();
    error = null;
    view = "add";
    addMode = "catalog";
    recipeQuery = "";
    newServiceName = "";
    customWebsiteUrl = "";
    hideServices();
    if (allRecipes.length === 0) await refreshRecipes();
    if (!recipeStorage) {
      try {
        recipeStorage = await getRecipeStorageInfo();
      } catch (err) {
        error = String(err);
      }
    }
  }

  const filteredRecipes = $derived(filterRecipes(allRecipes, recipeQuery));
  const customRecipes = $derived(allRecipes.filter((recipe) => recipe.source === "custom"));

  async function activateCreated(result: unknown, recipeId: string, preferWebsiteIcon = false) {
    const newId = createdServiceId(result);
    [services, workspaces] = await Promise.all([getServices(), getWorkspaces()]);
    let created =
      (newId ? services.find((service) => service.id === newId) : null) ??
      [...services].reverse().find((service) => service.recipeId === recipeId) ??
      null;
    if (created && preferWebsiteIcon && created.useFavicon !== true) {
      const createdId = created.id;
      await updateService(createdId, { useFavicon: true });
      services = services.map((service) => service.id === createdId ? { ...service, useFavicon: true } : service);
      created = services.find((service) => service.id === createdId) ?? created;
    }
    if (created && activeWorkspace) {
      const workspace = workspaces.find((candidate) => candidate.id === activeWorkspace);
      if (!workspace) {
        throw new Error("The active workspace no longer exists; the new service was created but could not be added to it.");
      }
      if (!workspace.services.includes(created.id)) {
        const members = [...workspace.services, created.id];
        await updateWorkspace(workspace.id, workspace.name, members);
        workspaces = workspaces.map((candidate) =>
          candidate.id === workspace.id ? { ...candidate, services: members } : candidate,
        );
      }
    }
    await reconcileSavedOrders();
    await refreshNativeServicesMenu();
    await Promise.all(services.map((service) => setServiceFlags(service).catch(() => {})));
    if (created) {
      if (created.useFavicon === true && appSettings.fetchMissingServiceIcons) void loadServiceIcon(created);
      selectService(created);
    } else view = "service";
  }

  function openCustomWebsite(prefill = "") {
    addMode = "website";
    error = null;
    const candidate = prefill || (looksLikeWebsite(recipeQuery) ? recipeQuery : "");
    customWebsiteUrl = candidate ? normalizeWebsiteUrl(candidate) : "";
    if (!newServiceName.trim() && candidate) newServiceName = websiteName(candidate);
  }

  async function createWebsite() {
    const url = normalizeWebsiteUrl(customWebsiteUrl);
    if (!url) {
      error = "Website URL is required.";
      return;
    }
    try {
      error = null;
      const result = await createCustomWebsiteService(
        newServiceName.trim() || websiteName(url),
        url,
      );
      await activateCreated(result, "custom-website", true);
    } catch (err) {
      error = String(err);
    }
  }

  function resetRecipeDraft() {
    recipeDraft = {
      id: "",
      name: "",
      serviceUrl: "",
      description: "",
      hasCustomUrl: false,
      hasTeamId: false,
      iconSvg: "",
      webviewJs: "",
    };
    recipeIdEdited = false;
    recipeAdvanced = false;
  }

  function openRecipeCreator() {
    addMode = "creator";
    error = null;
    resetRecipeDraft();
  }

  function setRecipeName(name: string) {
    recipeDraft.name = name;
    if (!recipeIdEdited) recipeDraft.id = recipeIdFromName(name);
  }

  async function saveRecipe(addService: boolean) {
    const draft: RecipeDraft = {
      ...recipeDraft,
      id: recipeDraft.id.trim().toLowerCase(),
      name: recipeDraft.name.trim(),
      serviceUrl: normalizeWebsiteUrl(recipeDraft.serviceUrl),
      description: recipeDraft.description.trim(),
    };
    if (!draft.name || !draft.id || !draft.serviceUrl) {
      error = "Recipe name, id, and service URL are required.";
      return;
    }
    recipeSaving = true;
    error = null;
    try {
      await saveCustomRecipe(draft);
      await refreshRecipes();
      if (addService) {
        const result = await createService(newServiceName.trim() || draft.name, draft.id);
        await activateCreated(result, draft.id, true);
      } else {
        addMode = "catalog";
        recipeQuery = draft.id;
      }
    } catch (err) {
      error = String(err);
    } finally {
      recipeSaving = false;
    }
  }

  async function importRecipe(directory: boolean) {
    try {
      const selected = await open(
        directory
          ? { directory: true, multiple: false, title: "Select recipe folder" }
          : {
              directory: false,
              multiple: false,
              title: "Select recipe package.json",
              filters: [{ name: "Recipe package", extensions: ["json"] }],
            },
      );
      const path = Array.isArray(selected) ? selected[0] : selected;
      if (!path) return;
      error = null;
      if (!(await confirmAsk("Import this recipe only if you trust its author and have reviewed its webview.js code. Recipe scripts can read or change pages and access your signed-in service data. Continue?"))) return;
      const imported = await importCustomRecipe(path, true);
      await refreshRecipes();
      addMode = "catalog";
      recipeQuery = imported.id;
    } catch (err) {
      error = String(err);
    }
  }

  async function pickRecipe(r: RecipePreview) {
    if (r.id === "custom-website") {
      openCustomWebsite();
      return;
    }
    try {
      error = null;
      const result = await createService(newServiceName.trim() || r.name, r.id);
      await activateCreated(result, r.id, r.source === "custom" || !r.icons?.svg);
    } catch (err) {
      error = String(err);
    }
  }

  function openAppSettings() {
    closeServiceContextMenu();
    error = null;
    view = "appSettings";
    hideServices();
    if ("services" === settingsTab && allRecipes.length === 0) void refreshRecipes();
  }

  function openAddWorkspace() {
    error = null;
    workspaceEditor.managedWorkspaceId = null;
    workspaceEditor.managedWorkspaceNameDraft = "";
    settingsTab = "workspaces";
    openAppSettings();
    setTimeout(() => document.querySelector<HTMLInputElement>(".workspace-create-row input")?.focus(), 0);
  }

  function openAbout() {
    closeServiceContextMenu();
    error = null;
    hideServices().catch(() => {});
    settingsTab = "about";
    view = "appSettings";
  }

  async function openProjectLink(url: string) {
    try {
      error = null;
      await openExternalUrl(url);
    } catch (err) {
      error = String(err);
    }
  }

  function portableSlug(value: string): string {
    return value
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 60) || "export";
  }

  function portablePayloadForServices(
    selectedServices: Service[],
    selectedWorkspaces: Workspace[],
    selectedSandboxes?: SandboxDefinition[],
  ): PortablePayload {
    const serviceIds = new Set(selectedServices.map((service) => service.id));
    const assignments = Object.fromEntries(
      Object.entries(appSettings.serviceSandboxes).filter(([serviceId]) => serviceIds.has(serviceId)),
    );
    const sandboxIds = new Set(Object.values(assignments));
    const sandboxes = selectedSandboxes ?? appSettings.sandboxes.filter((sandbox) => sandboxIds.has(sandbox.id));
    return {
      services: selectedServices,
      workspaces: selectedWorkspaces,
      sandboxes,
      serviceSandboxes: assignments,
    };
  }

  function sandboxPortablePayload(sandboxId?: string): PortablePayload {
    const sandboxes = sandboxId
      ? appSettings.sandboxes.filter((sandbox) => sandbox.id === sandboxId)
      : [...appSettings.sandboxes];
    const sandboxIds = new Set(sandboxes.map((sandbox) => sandbox.id));
    const selectedServices = sorted.filter((service) => sandboxIds.has(serviceSandboxId(service.id) ?? ""));
    const serviceIds = new Set(selectedServices.map((service) => service.id));
    const selectedWorkspaces = sortedWorkspaces
      .filter((workspace) => workspace.services.some((serviceId) => serviceIds.has(serviceId)))
      .map((workspace) => portableWorkspace({
        ...workspace,
        services: workspace.services.filter((serviceId) => serviceIds.has(serviceId)),
      }));
    return portablePayloadForServices(selectedServices, selectedWorkspaces, sandboxes);
  }

  function portableWorkspace(workspace: Workspace): Workspace {
    const iconUrl = workspaceIcon(workspace);
    return iconUrl ? { ...workspace, iconUrl } : { ...workspace, iconUrl: null };
  }

  function workspacePortablePayload(workspaceId?: string): PortablePayload {
    const selectedWorkspaces = (workspaceId
      ? sortedWorkspaces.filter((workspace) => workspace.id === workspaceId)
      : [...sortedWorkspaces]).map(portableWorkspace);
    const serviceIds = new Set(selectedWorkspaces.flatMap((workspace) => workspace.services));
    const selectedServices = sorted.filter((service) => serviceIds.has(service.id));
    return portablePayloadForServices(selectedServices, selectedWorkspaces);
  }

  async function doPortableExport(
    kind: "sandbox" | "sandboxes" | "workspace" | "workspaces",
    label: string,
    payload: PortablePayload,
  ) {
    portableExportStatus = "";
    error = null;
    try {
      if (!(await confirmAsk("This portable export contains private service configuration, possibly proxy credentials, personal URLs and executable recipe scripts. Store it privately and review every file before sharing. Continue?"))) return;
      const path = await saveDialog({
        title: `Export Tauridium ${label}`,
        defaultPath: `tauridium-${portableSlug(label)}-${backupTimestamp()}.json`,
        filters: [{ name: "Tauridium portable export", extensions: ["json"] }],
      });
      if (!path) return;
      const summary = await exportPortableBundle(path, kind, payload);
      portableExportStatus = `Exported ${summary.serviceCount} service(s), ${summary.workspaceCount} workspace(s), ${summary.sandboxCount} sandbox(es), and ${summary.customRecipeCount} referenced custom recipe(s); integrity verified.`;
    } catch (err) {
      error = `Portable export failed: ${err}`;
    }
  }

  function selectSettingsTab(id: Tab) {
    if (id === "about") {
      openAbout();
      return;
    }
    settingsTab = id;
    if (settingsTab === "audit" && !audit.auditInitialized) void audit.refreshAuditLog();
    if (settingsTab === "services" && allRecipes.length === 0) void refreshRecipes();
  }

  async function saveRestoreLastSidebarStateOnStartup(enabled: boolean) {
    const previous = {
      restoreLastSidebarStateOnStartup: appSettings.restoreLastSidebarStateOnStartup,
      sidebarCollapsed: appSettings.sidebarCollapsed,
    };
    const update = enabled
      ? { restoreLastSidebarStateOnStartup: true, sidebarCollapsed: appSettings.sidebarCollapsed }
      : { restoreLastSidebarStateOnStartup: false };
    appSettings = { ...appSettings, ...update };
    try {
      appSettings = await setAppSettings(update);
      showToast("Saved", "success");
    } catch (err) {
      appSettings = { ...appSettings, ...previous };
      error = String(err);
    }
  }

  async function saveRestoreLastWorkspaceOnStartup(enabled: boolean) {
    const previous = {
      restoreLastWorkspaceOnStartup: appSettings.restoreLastWorkspaceOnStartup,
      lastWorkspaceId: appSettings.lastWorkspaceId,
    };
    const lastWorkspaceId = enabled ? (activeWorkspace ?? "") : appSettings.lastWorkspaceId;
    appSettings = { ...appSettings, restoreLastWorkspaceOnStartup: enabled, lastWorkspaceId };
    try {
      appSettings = await setAppSettings({ restoreLastWorkspaceOnStartup: enabled, lastWorkspaceId });
      showToast("Saved", "success");
    } catch (err) {
      appSettings = { ...appSettings, ...previous };
      error = String(err);
    }
  }

  async function saveAppSetting(key: keyof AppSettings, value: unknown) {
    const previous = (appSettings as Record<string, unknown>)[key];
    (appSettings as Record<string, unknown>)[key] = value;
    if (key === "sidebarServiceDragReorder" && value === false) {
      clearServiceDragState();
      clearServiceDragSelection();
    }
    if (key === "theme" || key === "accentColor") applyTheme();
    applyLayout();
    if (key === "sidebarWidth" || key === "sidebarWidthMode" || key === "sidebarWidthPercent" || key === "sidebarCollapsed") {
      syncSidebarWidth();
    }

    try {
      appSettings = await setAppSettings({
        [key]: value,
      } as Partial<AppSettings>);
    } catch (err) {
      (appSettings as Record<string, unknown>)[key] = previous;
      applyTheme();
      applyLayout();
      if (key === "sidebarWidth" || key === "sidebarWidthMode" || key === "sidebarWidthPercent" || key === "sidebarCollapsed") {
        syncSidebarWidth();
      }
      error = String(err);
      return;
    }

    applyTheme();
    applyLayout();
    showToast("Saved", "success");
    try {
      if (key === "automaticBackupSchedule" && value !== "startup") {
        void backups.maybeRunAutomaticBackup(false);
      }
      if (key === "keybindings" || key === "captureServiceShortcuts") {
        if (key === "keybindings") await refreshNativeServicesMenu();
        const restore = view === "service" ? activeService : null;
        await closeServices();
        statusMap = {};
        if (restore && restore.isEnabled !== false) selectService(restore);
        preloadRest(restore?.id);
      }
      if (key === "preloadServices") {
        if (value === true) preloadRest(activeId ?? undefined);
        else cancelPreloading();
      }
      if (key === "hibernationTimer") reconcileHibernationTimers();
    } catch (err) {
      error = `Setting was saved, but Tauridium could not fully apply it immediately: ${err}`;
    }
  }

  function toggleSidebarCollapsed() {
    void saveAppSetting("sidebarCollapsed", !appSettings.sidebarCollapsed);
  }

  function previewServiceSpacing(key: "collapsedServiceSpacing" | "expandedServiceSpacing", value: number, collapsed: boolean) {
    appSettings.sidebarCollapsed = collapsed;
    appSettings[key] = value;
    syncSidebarWidth();
  }

  async function saveServiceSpacing(key: "collapsedServiceSpacing" | "expandedServiceSpacing", collapsed: boolean) {
    const value = appSettings[key];
    try {
      appSettings = await setAppSettings({
        [key]: value,
        sidebarCollapsed: collapsed,
      } as Partial<AppSettings>);
      applyLayout();
      syncSidebarWidth();
      showToast("Saved", "success");
    } catch (err) {
      try {
        appSettings = await getAppSettings();
        applyLayout();
        syncSidebarWidth();
      } catch {
        // Keep the current preview if persisted settings cannot be reloaded either.
      }
      error = String(err);
    }
  }

  function setServiceExportSelected(serviceId: string, selected: boolean) {
    const next = new Set(serviceExportSelection);
    if (selected) next.add(serviceId);
    else next.delete(serviceId);
    serviceExportSelection = next;
  }

  function configuredServiceRecipeLabel(service: Service): string {
    if (service.recipeId === "custom-website") return "Custom website";
    const recipe = allRecipes.find((candidate) => candidate.id === service.recipeId);
    if (recipe?.source) return recipeSourceLabel(recipe.source);
    return service.isLocalRecipe ? "Recipe source unavailable" : "Ferdium recipe";
  }

  function selectAllServiceExports() {
    serviceExportSelection = new Set(sorted.map((service) => service.id));
  }

  function clearServiceExportSelection() {
    serviceExportSelection = new Set();
  }

  async function doServiceExport(selectedServices: Service[]) {
    if (serviceExportBusy || (selectedServices.length === 0 && !serviceExportIncludeAllPersonalRecipes)) return;
    serviceExportBusy = true;
    serviceExportStatus = "";
    error = null;
    try {
      if (serviceExportIncludeSensitiveRecipeScripts && !(await confirmAsk("Include personal executable recipe scripts? They are copied unchanged and may contain credentials or other private literals. Inspect every included script before sharing. Continue?"))) return;
      const path = await saveDialog({
        title: "Export Tauridium services",
        defaultPath: `tauridium-services-${backupTimestamp()}.zip`,
        filters: [{ name: "Tauridium service export", extensions: ["zip"] }],
      });
      if (!path) return;
      const summary = await exportServiceBundle(path, {
        services: selectedServices,
        includeAllPersonalRecipes: serviceExportIncludeAllPersonalRecipes,
        includeSensitiveRecipeScripts: serviceExportIncludeSensitiveRecipeScripts,
      });
      serviceExportStatus = `Exported ${summary.serviceCount} service(s), ${summary.serviceIconCount} locally available service icon(s), and ${summary.portableRecipeCount} portable recipe(s) to a verified ZIP bundle.`;
    } catch (err) {
      error = `Service export failed: ${err}`;
    } finally {
      serviceExportBusy = false;
    }
  }

  async function moveManagedService(serviceId: string, delta: number) {
    if (serviceOrderBusy) return;
    const visibleIds = managedServices.map((service) => service.id);
    const index = visibleIds.indexOf(serviceId);
    const target = index + delta;
    if (index < 0 || target < 0 || target >= visibleIds.length) return;
    const previousIds = sorted.map((service) => service.id);
    const nextIds = reorderVisibleSubset(
      previousIds,
      visibleIds,
      serviceId,
      visibleIds[target],
    );
    await persistServiceIds(nextIds, previousIds).catch(() => {});
  }

  async function saveKeybinding(action: KeybindingAction, binding: string) {
    const keybindings = { ...appSettings.keybindings, [action]: binding };
    await saveAppSetting("keybindings", keybindings);
  }

  function stopRecording() {
    if (recordingTimer) clearTimeout(recordingTimer);
    recordingTimer = null;
    recordingAction = null;
    recordingStrokes = [];
  }

  function beginRecording(action: KeybindingAction) {
    stopRecording();
    recordingAction = action;
  }

  function finishRecordedBinding(action: KeybindingAction, strokes: string[]) {
    stopRecording();
    void saveKeybinding(action, strokes.join(" "));
  }

  function openQuickSwitcher(mode: QuickSwitcherMode) {
    closeServiceContextMenu();
    const now = Date.now();
    if (lastQuickSwitcherShortcutToggle.mode === mode && now - lastQuickSwitcherShortcutToggle.at < 120) return;
    lastQuickSwitcherShortcutToggle = { mode, at: now };
    if (quickSwitcherMode === mode) {
      closeQuickSwitcher();
      return;
    }
    quickSwitcherMode = mode;
    quickSwitcherQuery = "";
    quickSwitcherIndex = 0;
    shortcutPending = null;
    void hideServices();
    setTimeout(() => document.querySelector<HTMLInputElement>(".quick-switcher input")?.focus(), 0);
  }

  function closeQuickSwitcher(restore = true) {
    quickSwitcherMode = null;
    quickSwitcherQuery = "";
    quickSwitcherIndex = 0;
    shortcutPending = null;
    if (restore && view === "service" && activeService) selectService(activeService);
  }

  function selectWorkspace(workspaceId: string | null, remember = true): Service | null {
    clearServiceDragSelection();
    clearServiceDragState();
    activeWorkspace = workspaceId;
    if (remember) {
      const previousLastWorkspaceId = appSettings.lastWorkspaceId;
      const previousWorkspaceLastUsed = appSettings.workspaceLastUsed;
      const lastWorkspaceId = workspaceId ?? "";
      const workspaceLastUsed = workspaceId
        ? { ...previousWorkspaceLastUsed, [workspaceId]: Date.now() }
        : previousWorkspaceLastUsed;
      appSettings = { ...appSettings, lastWorkspaceId, workspaceLastUsed };
      workspaceUsagePersist = workspaceUsagePersist.then(async () => {
        try {
          await setAppSettings({ lastWorkspaceId, workspaceLastUsed });
        } catch (err) {
          if (appSettings.lastWorkspaceId === lastWorkspaceId && appSettings.workspaceLastUsed === workspaceLastUsed) {
            appSettings = { ...appSettings, lastWorkspaceId: previousLastWorkspaceId, workspaceLastUsed: previousWorkspaceLastUsed };
          }
          error = `Unable to save workspace startup state: ${err}`;
        }
      });
    }
    const candidate = sorted.find(
      (service) =>
        service.isEnabled !== false &&
        (!workspaceId ||
          (workspaces.find((workspace) => workspace.id === workspaceId)?.services ?? []).includes(
            service.id,
          )),
    ) ?? null;
    if (candidate) {
      selectService(candidate);
    } else {
      activeId = null;
      serviceLoadError = null;
      void hideServices();
    }
    return candidate;
  }

  function chooseWorkspace(workspaceId: string | null) {
    selectWorkspace(workspaceId, true);
  }

  function chooseQuickSwitcherItem(item: { id: string; kind: QuickSwitcherMode }) {
    quickSwitcherMode = null;
    quickSwitcherQuery = "";
    quickSwitcherIndex = 0;
    if (item.kind === "service") {
      const service = services.find((candidate) => candidate.id === item.id);
      if (service) selectService(service);
    } else {
      chooseWorkspace(item.id === "__all__" ? null : item.id);
    }
  }

  function cycleService(delta: number) {
    const candidates = visibleServices.filter((service) => service.isEnabled !== false);
    if (!candidates.length) return;
    const current = candidates.findIndex((service) => service.id === activeId);
    const index = current < 0 ? 0 : (current + delta + candidates.length) % candidates.length;
    selectService(candidates[index]);
  }

  function cycleWorkspace(delta: number) {
    if (!sortedWorkspaces.length) return;
    const current = sortedWorkspaces.findIndex((workspace) => workspace.id === activeWorkspace);
    const index = current < 0 ? (delta > 0 ? 0 : sortedWorkspaces.length - 1) : (current + delta + sortedWorkspaces.length) % sortedWorkspaces.length;
    chooseWorkspace(sortedWorkspaces[index].id);
  }

  function handleQuickSwitcherToggleShortcut(event: KeyboardEvent): boolean {
    if (!quickSwitcherMode) return false;
    const mode = quickSwitcherMode;
    const action: KeybindingAction = mode === "workspace"
      ? "quickWorkspaceSwitch"
      : "quickServiceSwitch";
    const strokes = bindingStrokes(appSettings.keybindings[action] ?? "");
    const stroke = keyStrokeFromEvent(event);
    if (!stroke || strokes.length === 0) return false;

    if (shortcutPending && Date.now() - shortcutPending.at < 1800) {
      const matchesChord = strokes.length === 2
        && strokes[0] === shortcutPending.stroke
        && strokes[1] === stroke;
      shortcutPending = null;
      if (matchesChord) {
        event.preventDefault();
        event.stopPropagation();
        openQuickSwitcher(mode);
        return true;
      }
    }

    if (strokes.length === 2 && strokes[0] === stroke) {
      event.preventDefault();
      event.stopPropagation();
      shortcutPending = { stroke, at: Date.now() };
      setTimeout(() => {
        if (shortcutPending?.stroke === stroke && Date.now() - shortcutPending.at >= 1700) {
          shortcutPending = null;
        }
      }, 1800);
      return true;
    }

    if (strokes.length === 1 && strokes[0] === stroke) {
      event.preventDefault();
      event.stopPropagation();
      openQuickSwitcher(mode);
      return true;
    }

    return false;
  }

  function executeShortcutAction(action: KeybindingAction) {
    switch (action) {
      case "quickWorkspaceSwitch": openQuickSwitcher("workspace"); break;
      case "quickServiceSwitch": openQuickSwitcher("service"); break;
      case "openSettings": openAppSettings(); break;
      case "addService": openAdd(); break;
      case "addWorkspace": openAddWorkspace(); break;
      case "toggleSidebar": toggleSidebarCollapsed(); break;
      case "nextService": cycleService(1); break;
      case "previousService": cycleService(-1); break;
      case "nextWorkspace": cycleWorkspace(1); break;
      case "previousWorkspace": cycleWorkspace(-1); break;
      case "reloadService": if (activeService) void reloadServiceFromUi(activeService); break;
      case "reloadApp": void reloadTauridium(); break;
      case "zoomIn": if (activeService) void increaseServiceZoom(activeService); break;
      case "zoomOut": if (activeService) void decreaseServiceZoom(activeService); break;
      case "resetZoom": if (activeService) void resetServiceZoom(activeService); break;
      case "toggleDevtools": void toggleDeveloperTools(); break;
    }
  }

  function handleGlobalKeydown(event: KeyboardEvent) {
    if (event.key === "Escape" && serviceMenu.isOpen) {
      event.preventDefault();
      closeServiceContextMenu();
      return;
    }
    if (recordingAction) {
      if (event.key === "Escape") {
        event.preventDefault();
        stopRecording();
        return;
      }
      if (event.key === "Backspace" || event.key === "Delete") {
        event.preventDefault();
        const action = recordingAction;
        stopRecording();
        void saveKeybinding(action, "");
        return;
      }
      const stroke = keyStrokeFromEvent(event);
      if (!stroke) return;
      event.preventDefault();
      event.stopPropagation();
      const action = recordingAction;
      const next = [...recordingStrokes, stroke].slice(0, 2);
      recordingStrokes = next;
      if (recordingTimer) clearTimeout(recordingTimer);
      if (next.length === 2) {
        finishRecordedBinding(action, next);
      } else {
        recordingTimer = setTimeout(() => finishRecordedBinding(action, next), 1800);
      }
      return;
    }

    if (quickSwitcherMode) {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        closeQuickSwitcher();
      } else if (handleQuickSwitcherToggleShortcut(event)) {
        return;
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        const lastVisible = Math.max(0, Math.min(quickSwitcherItems.length, 100) - 1);
        quickSwitcherIndex = Math.min(lastVisible, quickSwitcherIndex + 1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        quickSwitcherIndex = Math.max(0, quickSwitcherIndex - 1);
      } else if (event.key === "Enter" && quickSwitcherItems[quickSwitcherIndex]) {
        event.preventDefault();
        chooseQuickSwitcherItem(quickSwitcherItems[quickSwitcherIndex]);
      }
      return;
    }

    if (view === "appSettings" && !event.isComposing && (event.ctrlKey || event.metaKey)
      && !event.altKey && !event.shiftKey && event.key.toLowerCase() === "f") {
      event.preventDefault(); event.stopPropagation();
      shortcutPending = null;
      settingsSearch?.focus();
      return;
    }

    const target = event.target as HTMLElement | null;
    if (target?.matches("input, textarea, select") || target?.isContentEditable) return;
    const stroke = keyStrokeFromEvent(event);
    if (!stroke) return;
    const entries = Object.entries(appSettings.keybindings) as [KeybindingAction, string][];
    if (shortcutPending && Date.now() - shortcutPending.at < 1800) {
      const match = entries.find(([, binding]) => {
        const strokes = bindingStrokes(binding);
        return strokes.length === 2 && strokes[0] === shortcutPending?.stroke && strokes[1] === stroke;
      });
      shortcutPending = null;
      if (match) {
        event.preventDefault();
        executeShortcutAction(match[0]);
        return;
      }
    }
    const chordPrefix = entries.some(([, binding]) => {
      const strokes = bindingStrokes(binding);
      return strokes.length === 2 && strokes[0] === stroke;
    });
    if (chordPrefix) {
      event.preventDefault();
      shortcutPending = { stroke, at: Date.now() };
      setTimeout(() => {
        if (shortcutPending?.stroke === stroke && Date.now() - shortcutPending.at >= 1700) {
          shortcutPending = null;
        }
      }, 1800);
      return;
    }
    const single = entries.find(([, binding]) => {
      const strokes = bindingStrokes(binding);
      return strokes.length === 1 && strokes[0] === stroke;
    });
    if (single) {
      event.preventDefault();
      executeShortcutAction(single[0]);
    }
  }

  async function createSandboxGroup() {
    const name = newSandboxName.trim();
    if (!name) return;
    const sandbox: SandboxDefinition = { id: `sandbox-${crypto.randomUUID()}`, name };
    await saveAppSetting("sandboxes", [...appSettings.sandboxes, sandbox]);
    newSandboxName = "";
  }

  async function renameSandboxGroup(sandboxId: string, name: string) {
    const trimmed = name.trim();
    if (!trimmed) return;
    await saveAppSetting(
      "sandboxes",
      appSettings.sandboxes.map((sandbox) => sandbox.id === sandboxId ? { ...sandbox, name: trimmed } : sandbox),
    );
  }

  async function assignServiceSandbox(serviceId: string, sandboxId: string) {
    if (sandboxAssignmentBusy || serviceEditor.trackingPrivacyBusy) return;
    const previous = { ...appSettings.serviceSandboxes };
    const serviceSandboxes = { ...previous };
    if (sandboxId) setOwnValue(serviceSandboxes, serviceId, sandboxId);
    else delete serviceSandboxes[serviceId];
    if ((ownValue(previous, serviceId) ?? "") === (ownValue(serviceSandboxes, serviceId) ?? "")) return;

    sandboxAssignmentBusy = true;
    appSettings = { ...appSettings, serviceSandboxes };
    try {
      const persisted = await setAppSettings({ serviceSandboxes });
      const actual = ownValue(persisted.serviceSandboxes, serviceId) ?? "";
      if (actual !== (sandboxId || "")) throw new Error("Tauridium could not verify the saved sandbox assignment");
      appSettings = persisted;
      if (view === "svcSettings" && serviceEditor.settingsSvc?.id === serviceId) showServiceSettingsSaved(serviceId);
      else showToast("Saved", "success");
    } catch (err) {
      appSettings = { ...appSettings, serviceSandboxes: previous };
      error = `Unable to assign sandbox: ${err}`;
      sandboxAssignmentBusy = false;
      return;
    }

    try {
      await closeService(serviceId);
      const { [serviceId]: _, ...rest } = statusMap;
      statusMap = rest;
      if (view === "service" && activeId === serviceId) {
        const service = services.find((candidate) => candidate.id === serviceId);
        if (service) selectService(service);
      }
    } catch (err) {
      error = `Sandbox assignment was saved, but the existing service webview could not be closed: ${err}`;
    } finally {
      sandboxAssignmentBusy = false;
    }
  }

  async function clearSandboxGroup(sandbox: SandboxDefinition) {
    if (!(await confirmAsk(`Clear cache & session for sandbox “${sandbox.name}”? Every assigned service will be signed out.`))) return;
    await clearSandbox(sandbox.id);
    if (activeService && serviceSandboxId(activeService.id) === sandbox.id) selectService(activeService);
  }

  async function deleteSandboxGroup(sandbox: SandboxDefinition) {
    if (!(await confirmAsk(`Delete sandbox “${sandbox.name}”? Its shared cache/session will be cleared and assigned services will return to isolated storage.`))) return;
    const activeWasAssigned = activeService ? serviceSandboxId(activeService.id) === sandbox.id : false;
    await clearSandbox(sandbox.id);
    const serviceSandboxes = Object.fromEntries(
      Object.entries(appSettings.serviceSandboxes).filter(([, value]) => value !== sandbox.id),
    );
    appSettings = await setAppSettings({
      sandboxes: appSettings.sandboxes.filter((candidate) => candidate.id !== sandbox.id),
      trackingPreventionExceptions: Object.fromEntries(Object.entries(appSettings.trackingPreventionExceptions)
        .filter(([key]) => key !== `sandbox:${sandbox.id}`)),
      serviceSandboxes,
    });
    if (activeWasAssigned && activeService) selectService(activeService);
  }

  function backToService() {
    error = null;
    const target = (activeService?.isEnabled !== false ? activeService : null) ?? sorted.find((s) => s.isEnabled !== false) ?? null;
    if (target) selectService(target);
    else view = "service";
  }

  async function handleLogout() {
    closeServiceContextMenu();
    // Cleanup prevents hibernation timers, preloading, or reconnection from the
    // previous session from continuing and recreating webviews afterward.
    cancelPreloading();
    for (const id of [...hibTimers.keys()]) clearHibTimer(id);
    hibernated = new Set();
    auth.stopReconnect();
    await closeServices();
    let cleanupError: string | null = null;
    try { await logout(); } catch (e) { cleanupError = String(e); }
    me = null;
    services = [];
    workspaces = [];
    await refreshNativeServicesMenu();
    allRecipes = [];
    activeId = null;
    view = "service";
    error = cleanupError;
  }
</script>

{#if booting || auth.reconnecting || !me}
  <SessionScreen
    {auth}
    {booting}
    {error}
  />
{:else}
  <div class="shell">
    <ServiceSidebar
      {activeWorkspaceName}
      {appSettings}
      {appVer}
      {me}
      {onServiceAreaDragOver}
      {onServiceAreaDrop}
      {services}
      {toggleSidebarCollapsed}
      {visibleServices}
      {workspaces}
      {row}
    />

    <section class="stage">
      {#if view === "service"}
        {#if activeService}
          {#if serviceLoadError}
            <div class="placeholder">
              <h2>{serviceLabel(activeService)}</h2>
              <p class="load-err">Couldn't load this service.</p>
              <p class="load-err-detail">{serviceLoadError}</p>
              <button class="primary" onclick={retryActiveService}>Reload</button>
            </div>
          {:else if ownValue(statusMap, activeService.id) !== "ready"}
            <div class="placeholder">
              <div class="spinner" aria-hidden="true"></div>
              <p>Loading {serviceLabel(activeService)}…</p>
            </div>
          {:else}
            <div class="placeholder"><h2>{serviceLabel(activeService)}</h2></div>
          {/if}
        {:else}
          <div class="placeholder"><p>No service selected.</p></div>
        {/if}
      {:else if view === "svcSettings" && serviceEditor.settingsSvc}
      <ServiceSettingsPanel
        {MANAGED_SERVICE_PAGE_SIZE}
        {appSettings}
        {serviceEditor}
        {assignServiceSandbox}
        {chooseServiceDownloadDirectory}
        {chooseServiceZoom}
        {dockWord}
        {downloadSettingsBusy}
        {error}
        {failedWorkspaceIcons}
        {handleClearCache}
        {handleDelete}
        {inheritedDownloadPreference}
        {loadServiceIcon}
        {markWorkspaceIconFailed}
        {osKind}
        {sandboxAssignmentBusy}
        {saveServiceDownloadOverride}
        {saveServiceIconInversion}
        {saveTrackingException}
        {serviceDownloadOverride}
        {serviceIconInverted}
        {serviceSandboxId}
        {serviceZoomPercent}
        settingsSvc={serviceEditor.settingsSvc}
        {toggleServiceEnabled}
        {workspaceIcon}
        {workspaces}
      />
      {:else if view === "add"}
      <ServicePicker
        bind:addMode
        {allRecipes}
        {backToService}
        {createWebsite}
        {customRecipes}
        bind:customWebsiteUrl
        {error}
        {filteredRecipes}
        {importRecipe}
        bind:newServiceName
        {openCustomWebsite}
        {openRecipeCreator}
        {pickRecipe}
        bind:recipeAdvanced
        bind:recipeDraft
        bind:recipeIdEdited
        bind:recipeQuery
        {recipeSaving}
        {recipeStorage}
        {recipesLoading}
        {refreshRecipes}
        {saveRecipe}
        {setRecipeName}
      />
      {:else if view === "appSettings"}
        <div class="panel settings-panel">
          <div class="panel-head settings-head">
            <div>
              <h2>Settings</h2>
              <p class="panel-subtitle">Configure Tauridium's application-wide behavior.</p>
            </div>
            <button class="icon-button" title="Close settings" aria-label="Close settings" onclick={backToService}>✕</button>
          </div>

          <SettingsSearch
            bind:this={settingsSearch}
            context={{ windows: osKind === "win", flatpak: distributionInfo.mode === "flatpak", portalDownloads: distributionInfo.downloadsRequireDestination }}
            mac={osKind === "mac"}
            onchoose={revealSetting}
            onsearchfocus={stopRecording}
            oncancel={cancelSettingsSearchNavigation}
          />

          <nav class="settings-tabs" aria-label="Settings sections">
            {#each SETTINGS_TABS as [id, label] (id)}
              <button
                class="setting-tab"
                class:on={settingsTab === id}
                aria-current={settingsTab === id ? "page" : undefined}
                onclick={() => { settingsSearch?.dismiss(); cancelSettingsSearchNavigation(); selectSettingsTab(id); }}>{label}</button>
            {/each}
          </nav>

          <div class="settings-content" id={`settings-tab-${settingsTab}`}>
            {#if settingsTab === "general"}
              <SettingsGeneral
                {appSettings}
                {distributionInfo}
                {loginText}
                {saveAppSetting}
                {trayWord}
              />
            {:else if settingsTab === "services"}
              <SettingsServices
                {MANAGED_SERVICE_PAGE_SIZE}
                bind:appSettings
                {clearServiceExportSelection}
                {configuredServiceRecipeLabel}
                {displayedServiceIcon}
                {doServiceExport}
                bind:managedServicePage
                {managedServicePageCount}
                bind:managedServiceQuery
                {managedServiceRows}
                {managedServices}
                bind:managedWorkspaceFilter
                {markIconFailed}
                {moveManagedService}
                {openAdd}
                openServiceSettings={serviceEditor.openServiceSettings}
                {saveAppSetting}
                {selectAllServiceExports}
                {selectedServiceExports}
                {serviceExportBusy}
                bind:serviceExportIncludeAllPersonalRecipes
                bind:serviceExportIncludeSensitiveRecipeScripts
                {serviceExportSelection}
                {serviceExportStatus}
                {serviceIconFailed}
                {serviceIconInverted}
                {serviceOrderBusy}
                {services}
                {setServiceExportSelected}
                {sortedWorkspaces}
              />
            {:else if settingsTab === "workspaces"}
              <SettingsWorkspaces
                {MANAGED_SERVICE_PAGE_SIZE}
                bind:appSettings
                {workspaceEditor}
                {chooseWorkspaceDownloadDirectory}
                {displayedServiceIcon}
                {doPortableExport}
                {downloadSettingsBusy}
                {failedWorkspaceIcons}
                {inheritedDownloadPreference}
                managedWorkspace={workspaceEditor.managedWorkspace}
                {markIconFailed}
                {markWorkspaceIconFailed}
                {moveManagedWorkspace}
                {portableExportStatus}
                {resetWorkspaceUsageHistory}
                {saveAppSetting}
                {saveRestoreLastWorkspaceOnStartup}
                {saveWorkspaceDownloadOverride}
                {serviceIconFailed}
                {serviceIconInverted}
                {sorted}
                {sortedWorkspaces}
                {workspaceDownloadOverride}
                {workspaceIcon}
                {workspacePortablePayload}
                {workspaces}
              />
            {:else if settingsTab === "appearance"}
              <SettingsAppearance
                {activeService}
                {activeWorkspaceName}
                bind:appSettings
                {appearance}
                {dockWord}
                {previewServiceSpacing}
                {saveAppSetting}
                {saveRestoreLastSidebarStateOnStartup}
                {saveServiceSpacing}
                {syncSidebarWidth}
              />
            {:else if settingsTab === "keybindings"}
              <SettingsKeybindings
                {appSettings}
                {beginRecording}
                {keybindingConflicts}
                {recordingAction}
                {recordingStrokes}
                {saveAppSetting}
                {saveKeybinding}
              />
            {:else if settingsTab === "sandbox"}
              <SettingsSandbox
                {MANAGED_SERVICE_PAGE_SIZE}
                {appSettings}
                {assignServiceSandbox}
                {clearSandboxGroup}
                {createSandboxGroup}
                {deleteSandboxGroup}
                {doPortableExport}
                bind:newSandboxName
                {portableExportStatus}
                {renameSandboxGroup}
                {sandboxAssignmentBusy}
                {sandboxPortablePayload}
                bind:sandboxServicePage
                {sandboxServicePageCount}
                bind:sandboxServiceQuery
                {sandboxServiceRows}
                {sandboxServices}
                {serviceSandboxId}
                {services}
              />
            {:else if settingsTab === "privacy"}
              <SettingsPrivacy
                {appSettings}
                {saveAppSetting}
              />
            {:else if settingsTab === "backup"}
              <SettingsBackup
                {appSettings}
                {backups}
                {distributionInfo}
                {saveAppSetting}
              />
            {:else if settingsTab === "audit"}
              <SettingsAudit
                {audit}

              />

            {:else if settingsTab === "advanced"}
              <SettingsAdvanced
                {appSettings}
                {chooseGlobalDownloadDirectory}
                {distributionInfo}
                {downloadToastExample}
                {downloadToastSettingsBusy}
                {me}
                {osKind}
                {refetchAllServiceIcons}
                {saveAppSetting}
                {saveDownloadToastParentLevels}
                {saveDownloadToastSetting}
                {saveUnifiedTitleBar}
                server={auth.server}
                {unifiedTitleBarAtStartup}
                {unifiedTitleBarBusy}
                {unifiedTitleBarFallback}
              />
            {:else if settingsTab === "updates"}
              <SettingsUpdates
                {appVer}
                {updates}
                {distributionInfo}
              />
            {:else if settingsTab === "about"}
              <SettingsAbout
                {appMetadata}
                {appVer}
                {openProjectLink}
                {projectRepository}
              />
            {/if}
          </div>
          {#if error}<p class="error">{error}</p>{/if}
        </div>
      {/if}
    </section>
  </div>
{/if}

{#if toastMessage}
  <div class="toast" class:success={toastTone === "success"} style:bottom={`${downloadToastHeight > 0 ? downloadToastHeight + 36 : 24}px`} role="status" aria-live="polite">{toastMessage}</div>
{/if}

<QuickSwitcher
    {activeId}
    {activeWorkspace}
    {chooseQuickSwitcherItem}
    {closeQuickSwitcher}
    bind:quickSwitcherIndex
    {quickSwitcherItems}
    {quickSwitcherMode}
    bind:quickSwitcherQuery
  />

{#snippet row(s: Service)}
  <ServiceRow
    {activeId}
    {appSettings}
    {captureServiceMenuPointer}
    {displayedServiceIcon}
    {dragIds}
    {dragOverId}
    {dragPlacement}
    {hibernated}
    {markIconFailed}
    {onDragEnd}
    {onDragLeave}
    {onDragOver}
    {onDragStart}
    {onDrop}
    {onServiceRowClick}
    {openServiceContextMenu}
    {openServiceContextMenuFromKeyboard}
    {serviceDragSelection}
    {serviceIconFailed}
    {serviceIconInverted}
    {serviceOrderBusy}
    {unreadMap}
    {view}
    service={s}
  />
{/snippet}

<style>
  :global(:root) {
    color-scheme: dark;
    --bg: #1f2230; --sidebar: #1b1d28; --card: #282b3a; --panel: #232633;
    --input: #1f2230; --border: #2f3445; --border2: #3a3f55;
    --text: #e8e8ef; --text2: #d6d9e6; --muted: #9aa0b5; --muted2: #6b7193;
    --hover: #262a3a; --accent: #ffc131; --accent-fg: #1f2230; --accent-soft: #b9b2ff; --link: #7a82a8;
  }
  :global(body.light) {
    color-scheme: light;
    --bg: #f3f4f8; --sidebar: #e9ebf1; --card: #ffffff; --panel: #ffffff;
    --input: #ffffff; --border: #d6dae6; --border2: #c8cddc;
    --text: #1c2030; --text2: #2a2f40; --muted: #5b6280; --muted2: #818aa6;
    --hover: #e4e7f0; --accent-soft: #5b52d6; --link: #6d75a0;
  }
  :global(body.oled) {
    --bg: #000000; --sidebar: #000000; --card: #050505; --panel: #050505;
    --input: #0a0a0a; --border: #242424; --border2: #343434;
    --text: #f5f5f5; --text2: #dedede; --muted: #a3a3a3; --muted2: #777777;
    --hover: #121212; --accent-soft: #d0cbff; --link: #a9b0d0;
  }
  :global(body) {
    margin: 0;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: var(--bg);
    color: var(--text);
  }
  button { font-family: inherit; }
  .primary {
    padding: 10px 14px; border: none; border-radius: 8px; background: var(--accent);
    color: var(--accent-fg); font-weight: 700; cursor: pointer;
  }
  .primary:disabled { opacity: 0.6; cursor: default; }
  .error { color: #ff8a8a; font-size: 13px; margin: 4px 0; }

  .shell { display: grid; grid-template-columns: var(--sidebar-w, 240px) 1fr; height: 100vh; }

  .stage { display: grid; place-items: center; overflow: auto; }
  .placeholder { text-align: center; color: var(--muted); display: flex; flex-direction: column; align-items: center; gap: 12px; }
  .placeholder .spinner {
    width: 32px; height: 32px; border-radius: 50%;
    border: 3px solid var(--border); border-top-color: var(--accent);
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .placeholder .load-err { color: var(--danger, #d9534f); font-weight: 600; margin: 0; }
  .placeholder .load-err-detail { font-size: 12px; max-width: 420px; word-break: break-word; margin: 0; opacity: 0.8; }
  .panel {
    width: min(560px, 90%); align-self: start; margin: 40px auto;
    background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 22px;
    display: flex; flex-direction: column; gap: 14px;
  }
  .panel-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  .panel-head h2 { margin: 0; font-size: 18px; }

  .settings-panel {
    width: min(1180px, calc(100% - 32px)); margin: 16px auto 40px; padding: 0; gap: 0; overflow: hidden;
  }
  .settings-head { padding: 22px 24px 18px; align-items: flex-start; }
  .settings-head h2 { font-size: 22px; line-height: 1.2; }
  .panel-subtitle { margin: 5px 0 0; color: var(--muted); font-size: 13px; line-height: 1.4; }
  .icon-button {
    width: 34px; height: 34px; display: inline-grid; place-items: center; flex: none;
    border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--muted);
    cursor: pointer; font-size: 15px; line-height: 1;
  }
  .icon-button:hover { background: var(--hover); color: var(--text); border-color: var(--border); }
  .icon-button:focus-visible, .setting-tab:focus-visible, .primary:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 2px;
  }
  .settings-tabs {
    display: flex; flex-wrap: wrap; gap: 4px; overflow: visible; margin: 0 18px 10px; padding: 4px;
    border: 1px solid var(--border); border-radius: 11px;
    background: color-mix(in srgb, var(--input) 76%, transparent);
  }
  .setting-tab {
    flex: 1 1 auto; min-width: max-content; min-height: 34px; padding: 7px 12px; border: 1px solid transparent; border-radius: 8px;
    background: transparent; color: var(--muted); cursor: pointer; font: inherit;
    font-size: 13px; font-weight: 650; line-height: 1.2;
    transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease, box-shadow 0.12s ease;
  }
  .setting-tab:hover { background: var(--hover); color: var(--text2); }
  .setting-tab.on {
    background: var(--accent); border-color: color-mix(in srgb, var(--accent) 72%, var(--border2));
    color: var(--accent-fg); box-shadow: 0 1px 5px rgba(0, 0, 0, 0.16);
  }
  .settings-content { display: flex; flex-direction: column; gap: 26px; padding: 24px; min-height: 260px; }
  .settings-content:global([data-settings-search-highlight="true"]), .settings-content :global([data-settings-search-highlight="true"]) { outline: 2px solid var(--accent); outline-offset: 4px; scroll-margin-block: 20px; }
  .toast { position: fixed; z-index: 1400; left: 50%; bottom: 24px; transform: translateX(-50%); max-width: min(520px, calc(100vw - 32px)); padding: 10px 14px; border: 1px solid var(--border2); border-radius: 9px; background: var(--panel); color: var(--text); box-shadow: 0 10px 34px rgba(0, 0, 0, 0.42); font-size: 13px; }
  .toast.success { background: #187a45; border-color: #2ca866; color: #fff; }
  @media (max-width: 760px) {
    .settings-panel { width: calc(100% - 24px); margin: 12px auto 24px; }
    .settings-head { padding: 18px 18px 14px; }
    .settings-tabs { margin: 0 12px 9px; padding: 4px; }
    .settings-content { padding: 18px; gap: 22px; }
  }

</style>
