<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import tauridiumLogo from "./assets/tauridium.svg";
  import { listen } from "@tauri-apps/api/event";
  import { LogicalPosition } from "@tauri-apps/api/dpi";
  import { Menu } from "@tauri-apps/api/menu";
  import {
    accentFg,
    iconSrc,
    filterRecipes,
    snapIconSize,
    recipeIdFromName,
    normalizeWebsiteUrl,
    websiteName,
    looksLikeWebsite,
    orderedBySavedIds,
    orderWorkspacesForQuickSwitch,
    resolveStartupWorkspaceId,
    resolveStartupSidebarCollapsed,
    reorderVisibleSubset,
    reorderVisibleSubsetAt,
    reorderVisibleGroupAt,
    contiguousIdRange,
    type ReorderPlacement,
    serviceLabel,
    backupTimestamp,
    automaticBackupDue,
    COLLAPSED_SIDEBAR_WIDTH_PX,
    DEFAULT_KEYBINDINGS,
    bindingStrokes,
    hexToHsl,
    hslToHex,
    keyStrokeFromEvent,
    normalizeHexColor,
    paged,
    duplicateServiceName,
    shortcutConflicts,
    sameDownloadPreference,
    type KeybindingAction,
  } from "./lib/ui";
  import {
    DEFAULT_TASKBAR_TITLE_TEMPLATE,
    DEFAULT_WINDOW_TITLE_TEMPLATE,
    renderTitleTemplate,
  } from "./lib/title-template";
  import { appVersion, checkForUpdate, installUpdate, type Update } from "./lib/updater";
  import { ask, open, save as saveDialog } from "@tauri-apps/plugin-dialog";

  // window.confirm() does not work in WKWebView (wry does not implement the JavaScript panel).
  // Use the native dialog provided by the dialog plugin instead.
  function confirmAsk(message: string): Promise<boolean> {
    return ask(message, { title: "Tauridium", kind: "warning" });
  }
  import {
    login,
    startLocalSession,
    restoreSession,
    getServices,
    getWorkspaces,
    logout,
    showService,
    preloadService,
    closeService,
    closeServices,
    hideServices,
    setServiceFlags,
    updateService,
    createService,
    createCustomWebsiteService,
    deleteService,
    clearServiceCache,
    getServiceIcon,
    copyServiceIconCache,
    fetchWorkspaceIconUrl,
    clearSandbox,
    listRecipes,
    getRecipeStorageInfo,
    saveCustomRecipe,
    importCustomRecipe,
    createWorkspace,
    updateWorkspace,
    deleteWorkspace,
    getAppSettings,
    setAppSettings,
    setServiceOrder,
    setWorkspaceOrder,
    syncServicesMenu,
    setSidebarWidth,
    setPresentationTitles,
    exportBackup,
    restoreBackup,
    createAutomaticBackup,
    exportPortableBundle,
    getAuditLog,
    exportAuditLog,
    clearAuditLog,
    getAppMetadata,
    openExternalUrl,
    reloadTauridium,
    showServiceToastOverlay,
    toggleDeveloperTools,
    DEFAULT_SERVER,
    type MeUser,
    type Service,
    type Workspace,
    type RecipePreview,
    type RecipeDraft,
    type RecipeStorageInfo,
    type AppSettings,
    type BackupSummary,
    type SandboxDefinition,
    type PortablePayload,
    type AuditEntry,
    type AppMetadata,
    type ServiceCustomUrlTemplate,
    type DownloadPreferenceOverride,
  } from "./lib/api";

  let server = $state(DEFAULT_SERVER);
  let email = $state("");
  let password = $state("");
  let showServer = $state(false);

  let booting = $state(true);
  let loading = $state(false);
  let error = $state<string | null>(null);

  // Automatically reconnect when the server is unreachable (Ferdium outage, network issue, etc.).
  const RECONNECT_SECS = 30;
  let reconnecting = $state(false);
  let reconnectIn = $state(RECONNECT_SECS);
  let pendingCreds = $state<{ server: string; email: string; password: string } | null>(
    null,
  );
  let reconnectAttempt: (() => Promise<boolean>) | null = null;
  let reconnectTimer: ReturnType<typeof setInterval> | null = null;

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

  type View = "service" | "svcSettings" | "add" | "appSettings";
  let view = $state<View>("service");
  let settingsSvc = $state<Service | null>(null);
  let svcDirty = $state(false); // Service settings changed but not saved yet.
  let svcReload = $state(false); // A field requiring reload (URL/team/UA) changed.
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
  let sandboxAssignmentBusy = $state(false);
  let newWorkspaceName = $state("");

  type Tab = "general" | "services" | "workspaces" | "appearance" | "keybindings" | "sandbox" | "privacy" | "backup" | "audit" | "advanced" | "updates" | "about";
  let settingsTab = $state<Tab>("general");

  let managedServiceQuery = $state("");
  let managedWorkspaceFilter = $state("all");
  let managedServicePage = $state(0);
  let managedWorkspaceQuery = $state("");
  let managedWorkspacePage = $state(0);
  let managedWorkspaceId = $state<string | null>(null);
  let managedWorkspaceServiceQuery = $state("");
  let managedWorkspaceServicePage = $state(0);
  let managedWorkspaceBusy = $state(false);
  let managedWorkspaceNameDraft = $state("");
  let managedWorkspaceIconUrlDraft = $state("");
  let downloadSettingsBusy = $state(false);
  let workspaceUsagePersist: Promise<void> = Promise.resolve();
  const MANAGED_SERVICE_PAGE_SIZE = 100;
  const MAX_SIDEBAR_WIDTH_PX = 1200;

  let customColorOpen = $state(false);
  let customColorOriginal = $state("#ffc131");
  let colorHue = $state(42);
  let colorSaturation = $state(100);
  let colorLightness = $state(60);

  let recordingAction = $state<KeybindingAction | null>(null);
  let recordingStrokes = $state<string[]>([]);
  let recordingTimer: ReturnType<typeof setTimeout> | null = null;
  let shortcutPending = $state<{ stroke: string; at: number } | null>(null);

  type QuickSwitcherMode = "service" | "workspace";
  let quickSwitcherMode = $state<QuickSwitcherMode | null>(null);
  let quickSwitcherQuery = $state("");
  let quickSwitcherIndex = $state(0);
  let lastQuickSwitcherShortcutToggle: { mode: QuickSwitcherMode | null; at: number } = { mode: null, at: 0 };

  let serviceContextMenu = $state<{ serviceId: string; x: number; y: number } | null>(null);
  let toastMessage = $state("");
  let toastTone = $state<"default" | "success">("default");
  let toastTimer: ReturnType<typeof setTimeout> | null = null;
  const pendingReloadToasts = new Map<string, string>();
  let appMetadata = $state<AppMetadata | null>(null);
  const projectRepository = $derived((appMetadata?.repository || "https://github.com/Akkitto/Tauridium").replace(/\/$/, ""));

  let newSandboxName = $state("");
  let sandboxServiceQuery = $state("");
  let sandboxServicePage = $state(0);

  // Updates (automatic updater).
  let appVer = $state("");
  let updateInfo = $state<Update | null>(null);
  let updChecking = $state(false);
  let updInstalling = $state(false);
  let updStatus = $state("");

  // Portable backup/export state.
  let backupBusy = $state(false);
  let backupStatus = $state("");
  let automaticBackupTimer: ReturnType<typeof setInterval> | null = null;
  let automaticBackupStartupHandled = false;
  let automaticBackupRunning = $state(false);
  let portableExportStatus = $state("");
  let auditEntries = $state<AuditEntry[]>([]);
  let auditQuery = $state("");
  let auditLevel = $state("all");
  let auditBusy = $state(false);
  let auditStatus = $state("");
  let sidebarResizeFrame: number | null = null;

  let appSettings = $state<AppSettings>({
    autostart: false,
    startMinimized: false,
    reuseExistingSessionOnLaunch: true,
    theme: "system",
    accentColor: "#ffc131",
    customAccentColors: [],
    closeToSystemTray: true,
    privateNotifications: false,
    showDisabledServices: true,
    showServiceName: true,
    showMessageBadgeWhenMuted: true,
    showWorkspaceInWindowTitle: true,
    showWorkspaceInTaskbarTitle: false,
    customTitleTemplatesEnabled: false,
    windowTitleTemplate: DEFAULT_WINDOW_TITLE_TEMPLATE,
    taskbarTitleTemplate: DEFAULT_TASKBAR_TITLE_TEMPLATE,
    userAgentPref: "",
    sidebarWidth: 240,
    sidebarWidthMode: "pixels",
    sidebarWidthPercent: 20,
    sidebarCollapsed: false,
    defaultSidebarCollapsed: false,
    restoreLastSidebarStateOnStartup: true,
    customSidebarWidths: [],
    collapsedServiceSpacing: 2,
    expandedServiceSpacing: 2,
    iconSize: 24,
    grayscaleServices: false,
    grayscaleDim: 50,
    sidebarServicesLocation: "top",
    hibernationTimer: 0,
    preloadServices: true,
    fetchMissingServiceIcons: true,
    reloadToasts: true,
    prettyServiceContextMenu: true,
    sidebarServiceDragReorder: true,
    captureServiceShortcuts: true,
    serviceShortcutCaptureOverrides: {},
    customUrlTemplatesEnabled: false,
    serviceCustomUrlTemplates: {},
    serviceIconInversions: {},
    serviceOrder: [],
    workspaceOrder: [],
    workspaceQuickSwitchOrder: "custom",
    defaultWorkspaceId: "",
    restoreLastWorkspaceOnStartup: false,
    lastWorkspaceId: "",
    workspaceLastUsed: {},
    workspaceIcons: {},
    downloadDirectory: "",
    askEachDownload: false,
    serviceDownloadSettings: {},
    workspaceDownloadSettings: {},
    keybindings: { ...DEFAULT_KEYBINDINGS },
    sandboxes: [],
    serviceSandboxes: {},
    automaticBackupSchedule: "off",
    automaticBackupDirectory: "",
    automaticBackupRetentionMode: "count",
    automaticBackupRetention: 10,
    automaticBackupMaxAgeDays: 90,
    lastAutomaticBackupAt: 0,
  });

  // Hibernation: suspended services have their webview closed while retaining the session.
  let hibernated = $state<Set<string>>(new Set());
  const hibTimers = new Map<string, ReturnType<typeof setTimeout>>();
  let preloadGeneration = 0; // Invalidates older delayed preload chains without races.

  // Add service / local recipe management.
  type AddMode = "catalog" | "website" | "creator";
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
  const managedWorkspaces = $derived.by(() => {
    const query = managedWorkspaceQuery.trim().toLowerCase();
    return sortedWorkspaces.filter((workspace) =>
      !query || workspace.name.toLowerCase().includes(query),
    );
  });
  const managedWorkspacePageCount = $derived(
    Math.max(1, Math.ceil(managedWorkspaces.length / MANAGED_SERVICE_PAGE_SIZE)),
  );
  const managedWorkspaceRows = $derived(
    paged(managedWorkspaces, managedWorkspacePage, MANAGED_SERVICE_PAGE_SIZE),
  );
  const managedWorkspace = $derived(
    workspaces.find((workspace) => workspace.id === managedWorkspaceId) ?? null,
  );
  const managedWorkspaceServices = $derived.by(() => {
    const query = managedWorkspaceServiceQuery.trim().toLowerCase();
    return sorted.filter((service) =>
      !query || `${serviceLabel(service)} ${service.recipeId}`.toLowerCase().includes(query),
    );
  });
  const managedWorkspaceServicePageCount = $derived(
    Math.max(1, Math.ceil(managedWorkspaceServices.length / MANAGED_SERVICE_PAGE_SIZE)),
  );
  const managedWorkspaceServiceRows = $derived(
    paged(managedWorkspaceServices, managedWorkspaceServicePage, MANAGED_SERVICE_PAGE_SIZE),
  );
  const serviceWorkspaceJoinedCount = $derived.by(() => {
    const serviceId = settingsSvc?.id;
    if (!serviceId) return 0;
    return workspaces.filter((workspace) => workspace.services.includes(serviceId)).length;
  });
  const serviceWorkspaceCandidates = $derived.by(() => {
    const serviceId = settingsSvc?.id;
    if (!serviceId) return [];
    const query = serviceWorkspaceQuery.trim().toLowerCase();
    return sortedWorkspaces.filter((workspace) => {
      const joined = workspace.services.includes(serviceId);
      if (serviceWorkspaceFilter === "joined" && !joined) return false;
      if (serviceWorkspaceFilter === "available" && joined) return false;
      return !query || workspace.name.toLowerCase().includes(query);
    });
  });
  const serviceWorkspacePageCount = $derived(
    Math.max(1, Math.ceil(serviceWorkspaceCandidates.length / MANAGED_SERVICE_PAGE_SIZE)),
  );
  const serviceWorkspaceRows = $derived(
    paged(serviceWorkspaceCandidates, serviceWorkspacePage, MANAGED_SERVICE_PAGE_SIZE),
  );
  const serviceSandboxCandidates = $derived.by(() => {
    if (!settingsSvc) return [];
    const query = serviceSandboxQuery.trim().toLowerCase();
    return [
      { id: "", name: "Isolated" },
      ...appSettings.sandboxes.map((sandbox) => ({ id: sandbox.id, name: sandbox.name })),
    ].filter((sandbox) => !query || sandbox.name.toLowerCase().includes(query));
  });
  const serviceSandboxPageCount = $derived(
    Math.max(1, Math.ceil(serviceSandboxCandidates.length / MANAGED_SERVICE_PAGE_SIZE)),
  );
  const serviceSandboxRows = $derived(
    paged(serviceSandboxCandidates, serviceSandboxPage, MANAGED_SERVICE_PAGE_SIZE),
  );
  const currentServiceSandboxName = $derived.by(() => {
    const serviceId = settingsSvc?.id;
    if (!serviceId) return "Isolated";
    const sandboxId = serviceSandboxId(serviceId);
    return appSettings.sandboxes.find((sandbox) => sandbox.id === sandboxId)?.name ?? "Isolated";
  });
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
  const filteredAuditEntries = $derived.by(() => {
    const query = auditQuery.trim().toLowerCase();
    return auditEntries.filter((entry) => {
      if (auditLevel !== "all" && entry.level !== auditLevel) return false;
      if (!query) return true;
      const details = JSON.stringify(entry.details ?? {});
      return `${entry.level} ${entry.category} ${entry.action} ${entry.outcome} ${entry.message} ${details}`
        .toLowerCase()
        .includes(query);
    });
  });

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

  onDestroy(() => {
    if (automaticBackupTimer) clearInterval(automaticBackupTimer);
    if (recordingTimer) clearTimeout(recordingTimer);
    if (toastTimer) clearTimeout(toastTimer);
    if (sidebarResizeFrame !== null) cancelAnimationFrame(sidebarResizeFrame);
    window.removeEventListener("keydown", handleGlobalKeydown, true);
    window.removeEventListener("resize", handleWindowResize);
  });

  onMount(async () => {
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
    // Restore the session. If the server is unreachable (Ferdium outage, network issue, etc.),
    // do NOT show login; a reconnect screen retries automatically every 30 seconds.
    const restored = await attemptRestore();
    booting = false;
    if (!restored) startReconnect(attemptRestore);
    await maybeRunAutomaticBackup(true);
    automaticBackupTimer = setInterval(() => {
      void maybeRunAutomaticBackup(false);
    }, 60 * 60 * 1000);
    appVersion()
      .then((v) => (appVer = v))
      .catch(() => {});
    getAppMetadata()
      .then((metadata) => (appMetadata = metadata))
      .catch(() => {});
    checkUpdates(true); // Silent startup check.
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
    if (appSettings.sidebarCollapsed || appSettings.sidebarWidthMode !== "percent" || sidebarResizeFrame !== null) return;
    sidebarResizeFrame = requestAnimationFrame(() => {
      sidebarResizeFrame = null;
      syncSidebarWidth();
    });
  }

  function serviceSandboxId(serviceId: string): string | null {
    return appSettings.serviceSandboxes?.[serviceId] || null;
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
    if (view === "svcSettings" && settingsSvc?.id === serviceId) {
      showToast("Saved", "success");
    }
  }

  function preferredWebsiteIcon(service: Service): string | null {
    if (service.useFavicon !== true) return null;
    return serviceIcons[service.id] ?? null;
  }

  function displayedServiceIcon(service: Service): string {
    return preferredWebsiteIcon(service) ?? iconSrc(service);
  }

  function serviceIconInverted(serviceId: string): boolean {
    return appSettings.serviceIconInversions?.[serviceId] === true;
  }

  async function saveServiceIconInversion(serviceId: string, inverted: boolean) {
    const previous = { ...appSettings.serviceIconInversions };
    const serviceIconInversions = { ...previous };
    if (inverted) serviceIconInversions[serviceId] = true;
    else delete serviceIconInversions[serviceId];
    if ((previous[serviceId] === true) === inverted) return;

    appSettings = { ...appSettings, serviceIconInversions };
    try {
      const persisted = await setAppSettings({ serviceIconInversions });
      if ((persisted.serviceIconInversions[serviceId] === true) !== inverted) {
        throw new Error("Tauridium could not verify the service icon inversion setting");
      }
      appSettings = persisted;
      showServiceSettingsSaved(serviceId);
    } catch (err) {
      appSettings = { ...appSettings, serviceIconInversions: previous };
      error = `Unable to save service icon inversion setting: ${err}`;
    }
  }

  function workspaceIcon(workspace: Workspace): string | null {
    return appSettings.workspaceIcons[workspace.id] ?? null;
  }

  function serviceDownloadOverride(serviceId: string): DownloadPreferenceOverride | null {
    return appSettings.serviceDownloadSettings?.[serviceId] ?? null;
  }

  function workspaceDownloadOverride(workspaceId: string): DownloadPreferenceOverride | null {
    return appSettings.workspaceDownloadSettings?.[workspaceId] ?? null;
  }

  function downloadDirectoryLabel(directory: string): string {
    return directory.trim() || "System Downloads folder";
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
    if (preference) serviceDownloadSettings[serviceId] = preference;
    else delete serviceDownloadSettings[serviceId];
    if (sameDownloadPreference(previous[serviceId], preference)) return;

    downloadSettingsBusy = true;
    appSettings = { ...appSettings, serviceDownloadSettings };
    try {
      const persisted = await setAppSettings({ serviceDownloadSettings });
      if (!sameDownloadPreference(persisted.serviceDownloadSettings[serviceId], preference)) {
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
    if (preference) workspaceDownloadSettings[workspaceId] = preference;
    else delete workspaceDownloadSettings[workspaceId];
    if (sameDownloadPreference(previous[workspaceId], preference)) return;

    downloadSettingsBusy = true;
    appSettings = { ...appSettings, workspaceDownloadSettings };
    try {
      const persisted = await setAppSettings({ workspaceDownloadSettings });
      if (!sameDownloadPreference(persisted.workspaceDownloadSettings[workspaceId], preference)) {
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
    serviceContextMenu = null;
  }

  function runServiceContextAction(service: Service, action: (selectedService: Service) => Promise<void>) {
    closeServiceContextMenu();
    void action(service);
  }

  function openContextServiceSettings(service: Service) {
    openServiceSettings(service);
    closeServiceContextMenu();
  }

  async function popupNativeServiceContextMenu(service: Service, x: number, y: number) {
    const menu = await Menu.new({
      items: [
        { id: `settings-${service.id}`, text: "Settings", action: () => openContextServiceSettings(service) },
        { id: `reload-${service.id}`, text: "Reload", enabled: service.isEnabled !== false, action: () => void reloadServiceFromUi(service) },
        { id: `duplicate-${service.id}`, text: "Duplicate", action: () => void duplicateServiceFromUi(service) },
        { id: `toggle-${service.id}`, text: service.isEnabled === false ? "Enable" : "Disable", action: () => void toggleServiceEnabled(service) },
      ],
    });
    try {
      await menu.popup(new LogicalPosition(x, y));
    } finally {
      await menu.close().catch(() => {});
    }
  }

  function openServiceContextMenu(event: MouseEvent, service: Service) {
    event.preventDefault();
    event.stopPropagation();
    if (!appSettings.prettyServiceContextMenu) {
      void popupNativeServiceContextMenu(service, event.clientX, event.clientY).catch((err) => {
        error = `Unable to open service menu: ${err}`;
      });
      return;
    }
    const width = 226;
    const height = 194;
    serviceContextMenu = {
      serviceId: service.id,
      x: Math.max(8, Math.min(event.clientX, window.innerWidth - width - 8)),
      y: Math.max(8, Math.min(event.clientY, window.innerHeight - height - 8)),
    };
    requestAnimationFrame(() => document.querySelector<HTMLButtonElement>(".service-context-menu button:not(:disabled)")?.focus());
  }

  function openServiceContextMenuFromKeyboard(event: KeyboardEvent, service: Service) {
    if (!(event.key === "ContextMenu" || (event.shiftKey && event.key === "F10"))) return;
    event.preventDefault();
    const rect = event.currentTarget instanceof HTMLElement ? event.currentTarget.getBoundingClientRect() : null;
    if (!appSettings.prettyServiceContextMenu) {
      void popupNativeServiceContextMenu(service, rect ? rect.left + 28 : 12, rect ? rect.bottom : 12).catch((err) => {
        error = `Unable to open service menu: ${err}`;
      });
      return;
    }
    serviceContextMenu = {
      serviceId: service.id,
      x: rect ? Math.min(rect.left + 28, window.innerWidth - 234) : 12,
      y: rect ? Math.min(rect.bottom, window.innerHeight - 202) : 12,
    };
    requestAnimationFrame(() => document.querySelector<HTMLButtonElement>(".service-context-menu button:not(:disabled)")?.focus());
  }

  function handleServiceContextMenuKeydown(event: KeyboardEvent) {
    const menu = event.currentTarget instanceof HTMLElement ? event.currentTarget : null;
    const items = menu ? [...menu.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')] : [];
    if (!items.length) return;
    const current = items.indexOf(document.activeElement as HTMLButtonElement);
    let next = current;
    if (event.key === "ArrowDown") next = (current + 1 + items.length) % items.length;
    else if (event.key === "ArrowUp") next = (current - 1 + items.length) % items.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = items.length - 1;
    else return;
    event.preventDefault();
    items[next]?.focus();
  }

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
    const serviceDownloadSettingsChanged = Object.keys(serviceDownloadSettings).length !== Object.keys(appSettings.serviceDownloadSettings).length;
    const workspaceDownloadSettingsChanged = Object.keys(workspaceDownloadSettings).length !== Object.keys(appSettings.workspaceDownloadSettings).length;
    if (
      sameIds(serviceOrder, appSettings.serviceOrder) &&
      sameIds(workspaceOrder, appSettings.workspaceOrder) &&
      !startupWorkspaceChanged &&
      !usageHistoryChanged &&
      !workspaceIconsChanged &&
      !serviceIconInversionsChanged &&
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

  function stopReconnect() {
    if (reconnectTimer) {
      clearInterval(reconnectTimer);
      reconnectTimer = null;
    }
    reconnectAttempt = null;
    reconnecting = false;
  }

  // Start a reconnection loop that calls attempt every RECONNECT_SECS.
  // attempt returns true when finished (success OR definitive error), so stop;
  // false means the server is still unreachable, so retry later.
  function startReconnect(attempt: () => Promise<boolean>) {
    stopReconnect();
    reconnectAttempt = attempt;
    reconnecting = true;
    reconnectIn = RECONNECT_SECS;
    reconnectTimer = setInterval(async () => {
      reconnectIn -= 1;
      if (reconnectIn <= 0) {
        reconnectIn = RECONNECT_SECS;
        if (await attempt()) stopReconnect();
      }
    }, 1000);
  }

  async function retryNow() {
    const fn = reconnectAttempt;
    if (!fn) return;
    reconnectIn = RECONNECT_SECS;
    if (await fn()) stopReconnect();
  }

  function cancelReconnect() {
    pendingCreds = null;
    stopReconnect();
  }

  // Try to restore the session. true = finished (connected OR expired session ->
  // login screen); false = server unreachable (retry later).
  async function attemptRestore(): Promise<boolean> {
    try {
      me = await restoreSession();
      await loadAfterAuth();
      return true;
    } catch (e) {
      return !String(e).startsWith("transient:");
    }
  }

  // Try login with pending credentials. false means the server is unreachable.
  async function attemptLogin(): Promise<boolean> {
    if (!pendingCreds) return true;
    try {
      me = await login(pendingCreds.server, pendingCreds.email, pendingCreds.password);
      pendingCreds = null;
      password = "";
      error = null;
      await loadAfterAuth();
      return true;
    } catch (e) {
      if (String(e).startsWith("transient:")) return false;
      error = String(e); // Rejected credentials: stop and display the error.
      pendingCreds = null;
      return true;
    }
  }

  async function handleLogin(e: Event) {
    e.preventDefault();
    loading = true;
    error = null;
    pendingCreds = { server, email, password };
    const done = await attemptLogin();
    loading = false;
    if (!done) startReconnect(attemptLogin); // Server unreachable: reconnect automatically.
  }

  async function handleLocalSession() {
    loading = true;
    error = null;
    pendingCreds = null;
    stopReconnect();
    try {
      me = await startLocalSession();
      password = "";
      await loadAfterAuth();
    } catch (e) {
      error = String(e);
      me = null;
    } finally {
      loading = false;
    }
  }

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
        statusMap[service.id]
      ) {
        scheduleHibernation(service.id);
      }
    }
  }

  function selectService(s: Service) {
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

  function openServiceSettings(s: Service, returnToSettings = false) {
    error = null;
    serviceSettingsReturnToSettings = returnToSettings;
    settingsSvc = { ...s }; // Editable copy; applied to the server on Save.
    serviceTemplateDraft = { ...(appSettings.serviceCustomUrlTemplates[s.id] ?? { enabled: false, customId1: "", customId2: "" }) };
    serviceTemplateDirty = false;
    serviceWorkspaceQuery = "";
    serviceWorkspaceNewName = "";
    serviceWorkspaceFilter = "all";
    serviceWorkspacePage = 0;
    serviceWorkspaceBusy = false;
    serviceSandboxQuery = "";
    serviceSandboxPage = 0;
    svcDirty = false;
    svcReload = false;
    view = "svcSettings";
    hideServices();
  }

  async function closeServiceSettings() {
    if (svcDirty || serviceTemplateDirty) {
      const discard = await confirmAsk("Discard unsaved service changes?");
      if (!discard) return;
    }
    error = null;
    if (serviceSettingsReturnToSettings) {
      serviceSettingsReturnToSettings = false;
      settingsSvc = null;
      serviceTemplateDirty = false;
      svcDirty = false;
      svcReload = false;
      settingsTab = "services";
      view = "appSettings";
      hideServices().catch(() => {});
      return;
    }
    backToService();
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
      const idx = services.findIndex((candidate) => candidate.id === s.id);
      const previous = idx >= 0 ? services[idx] : null;
      if (idx >= 0) services = services.map((candidate, index) => index === idx ? { ...s } : candidate);
      if (
        s.useFavicon === true &&
        appSettings.fetchMissingServiceIcons &&
        (previous?.useFavicon !== true || !preferredWebsiteIcon(s))
      ) {
        void loadServiceIcon(s);
      }
      await setServiceFlags(s);
      await refreshNativeServicesMenu();
      if (previous?.isHibernationEnabled !== s.isHibernationEnabled) {
        clearHibTimer(s.id);
        if (s.id !== activeId && s.isHibernationEnabled === true && statusMap[s.id]) {
          scheduleHibernation(s.id);
        }
      }
      if (reload) {
        await closeService(s.id);
        const { [s.id]: _, ...rest } = statusMap;
        statusMap = rest;
      }
      return true;
    } catch (err) {
      error = `Unable to save ${serviceLabel(s)}: ${err}`;
      return false;
    }
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

  function saveSetting(key: keyof Service, value: boolean) {
    if (!settingsSvc) return;
    (settingsSvc as Record<string, unknown>)[key] = value;
    svcDirty = true;
    if (RELOAD_FIELDS.has(key)) svcReload = true;
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
    if (RELOAD_FIELDS.has(key)) svcReload = true;
  }

  async function saveServiceSettings() {
    error = null;
    const needsServiceSave = svcDirty || svcReload;
    if (needsServiceSave) {
      const saved = await persistService(svcReload);
      if (!saved) return;
      svcDirty = false;
    }
    if (settingsSvc && serviceTemplateDirty) {
      try {
        appSettings = await setAppSettings({
          serviceCustomUrlTemplates: {
            ...appSettings.serviceCustomUrlTemplates,
            [settingsSvc.id]: { ...serviceTemplateDraft },
          },
        });
        serviceTemplateDirty = false;
      } catch (err) {
        error = `Unable to save custom URL placeholders: ${err}`;
        return;
      }
    }
    svcReload = false;
  }

  async function setServiceEnabled(service: Service, enabled: boolean) {
    if ((service.isEnabled !== false) === enabled) return;
    try {
      await updateService(service.id, { isEnabled: enabled });
      services = services.map((candidate) => candidate.id === service.id ? { ...candidate, isEnabled: enabled } : candidate);
      if (settingsSvc?.id === service.id) settingsSvc = { ...settingsSvc, isEnabled: enabled };
      await refreshNativeServicesMenu();
      if (!enabled) {
        clearHibTimer(service.id);
        await closeService(service.id).catch(() => {});
        const { [service.id]: _, ...rest } = statusMap;
        statusMap = rest;
        hibernated = new Set([...hibernated].filter((id) => id !== service.id));
        if (activeId === service.id) {
          activeId = null;
          const keepServiceSettingsOpen = view === "svcSettings" && settingsSvc?.id === service.id;
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
      if (view === "svcSettings" && settingsSvc?.id === service.id) showServiceSettingsSaved(service.id);
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
        if (serviceIcons[service.id]) serviceIcons = { ...serviceIcons, [newId]: serviceIcons[service.id] };
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
      if (serviceCustomUrlTemplates[service.id]) serviceCustomUrlTemplates[newId] = { ...serviceCustomUrlTemplates[service.id] };
      if (serviceSandboxes[service.id]) serviceSandboxes[newId] = serviceSandboxes[service.id];
      if (service.id in serviceShortcutCaptureOverrides) serviceShortcutCaptureOverrides[newId] = serviceShortcutCaptureOverrides[service.id];
      if (serviceDownloadSettings[service.id]) serviceDownloadSettings[newId] = { ...serviceDownloadSettings[service.id] };
      if (serviceIconInversions[service.id] === true) serviceIconInversions[newId] = true;
      if (serviceCustomUrlTemplates[newId] || serviceSandboxes[newId] || newId in serviceShortcutCaptureOverrides || serviceDownloadSettings[newId] || serviceIconInversions[newId] === true) {
        appSettings = await setAppSettings({
          serviceCustomUrlTemplates,
          serviceSandboxes,
          serviceShortcutCaptureOverrides,
          serviceDownloadSettings,
          serviceIconInversions,
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
        appSettings.serviceSandboxes[s.id] ||
        appSettings.serviceCustomUrlTemplates[s.id] ||
        s.id in appSettings.serviceShortcutCaptureOverrides ||
        appSettings.serviceDownloadSettings[s.id] ||
        appSettings.serviceIconInversions[s.id] === true
      ) {
        const serviceSandboxes = { ...appSettings.serviceSandboxes };
        const serviceCustomUrlTemplates = { ...appSettings.serviceCustomUrlTemplates };
        const serviceShortcutCaptureOverrides = { ...appSettings.serviceShortcutCaptureOverrides };
        const serviceDownloadSettings = { ...appSettings.serviceDownloadSettings };
        const serviceIconInversions = { ...appSettings.serviceIconInversions };
        delete serviceSandboxes[s.id];
        delete serviceCustomUrlTemplates[s.id];
        delete serviceShortcutCaptureOverrides[s.id];
        delete serviceDownloadSettings[s.id];
        delete serviceIconInversions[s.id];
        appSettings = await setAppSettings({
          serviceSandboxes,
          serviceCustomUrlTemplates,
          serviceShortcutCaptureOverrides,
          serviceDownloadSettings,
          serviceIconInversions,
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
    if (managedWorkspaceId && !workspaces.some((workspace) => workspace.id === managedWorkspaceId)) {
      managedWorkspaceId = null;
      managedWorkspaceNameDraft = "";
    }
    const query = managedWorkspaceQuery.trim().toLowerCase();
    const matchingCount = workspaces.filter((workspace) => !query || workspace.name.toLowerCase().includes(query)).length;
    const lastPage = Math.max(0, Math.ceil(matchingCount / MANAGED_SERVICE_PAGE_SIZE) - 1);
    managedWorkspacePage = Math.min(managedWorkspacePage, lastPage);
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
    const visibleIds = managedWorkspaces.map((workspace) => workspace.id);
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
      !(await confirmAsk("Discard unsaved workspace name changes?"))
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
      await reloadWorkspaces();
      managedWorkspaceNameDraft = name;
      showToast("Saved", "success");
    } catch (err) {
      error = `Unable to rename workspace: ${err}`;
      managedWorkspaceNameDraft = managedWorkspace.name;
    } finally {
      managedWorkspaceBusy = false;
    }
  }

  async function toggleManagedWorkspaceService(serviceId: string, member: boolean) {
    if (!managedWorkspace || managedWorkspaceBusy) return;
    managedWorkspaceBusy = true;
    try {
      if (await toggleServiceInWorkspace(managedWorkspace, serviceId, member)) {
        showToast("Saved", "success");
      }
    } finally {
      managedWorkspaceBusy = false;
    }
  }

  async function persistManagedWorkspaceIcon(iconUrl: string | null, busyAlready = false) {
    if (!managedWorkspace || (!busyAlready && managedWorkspaceBusy)) return;
    const previous = { ...appSettings.workspaceIcons };
    const workspaceIcons = { ...previous };
    if (iconUrl) workspaceIcons[managedWorkspace.id] = iconUrl;
    else delete workspaceIcons[managedWorkspace.id];
    if ((previous[managedWorkspace.id] ?? null) === (workspaceIcons[managedWorkspace.id] ?? null)) return;

    if (!busyAlready) managedWorkspaceBusy = true;
    appSettings = { ...appSettings, workspaceIcons };
    try {
      const persisted = await setAppSettings({ workspaceIcons });
      if ((persisted.workspaceIcons[managedWorkspace.id] ?? null) !== (iconUrl ?? null)) {
        throw new Error("Tauridium could not verify the saved workspace icon");
      }
      appSettings = persisted;
      const nextFailed = new Set(failedWorkspaceIcons);
      nextFailed.delete(managedWorkspace.id);
      failedWorkspaceIcons = nextFailed;
      showToast("Saved", "success");
    } catch (err) {
      appSettings = { ...appSettings, workspaceIcons: previous };
      error = `Unable to save workspace icon: ${err}`;
    } finally {
      if (!busyAlready) managedWorkspaceBusy = false;
    }
  }

  async function saveManagedWorkspaceIcon(iconUrl: string | null) {
    await persistManagedWorkspaceIcon(iconUrl);
  }

  async function assignManagedWorkspaceIconFromService(service: Service) {
    if (!managedWorkspace || managedWorkspaceBusy) return;
    if (service.useFavicon === true && !preferredWebsiteIcon(service)) {
      await loadServiceIcon(service, false, false, true);
    }
    await saveManagedWorkspaceIcon(displayedServiceIcon(service));
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
      error = `Unable to fetch workspace icon: ${err}`;
    } finally {
      managedWorkspaceBusy = false;
    }
  }

  async function resetWorkspaceUsageHistory() {
    await saveAppSetting("workspaceLastUsed", {});
  }

  async function deleteManagedWorkspace() {
    if (!managedWorkspace) return;
    await handleDeleteWorkspace(managedWorkspace);
  }

  async function handleCreateWorkspace() {
    const name = newWorkspaceName.trim();
    if (!name) return;
    try {
      const created = await createWorkspace(name);
      newWorkspaceName = "";
      await reloadWorkspaces();
      const workspace = workspaces.find((candidate) => candidate.id === created.id) ?? created;
      manageWorkspace(workspace);
    } catch (err) {
      error = String(err);
    }
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

  function serviceShortcutCaptureMode(serviceId: string): "inherit" | "tauridium" | "website" {
    if (!(serviceId in appSettings.serviceShortcutCaptureOverrides)) return "inherit";
    return appSettings.serviceShortcutCaptureOverrides[serviceId] ? "tauridium" : "website";
  }

  function effectiveServiceShortcutCapture(serviceId: string): boolean {
    return appSettings.serviceShortcutCaptureOverrides[serviceId] ?? appSettings.captureServiceShortcuts;
  }

  async function setServiceShortcutCaptureMode(
    serviceId: string,
    mode: "inherit" | "tauridium" | "website",
  ) {
    const previous = { ...appSettings.serviceShortcutCaptureOverrides };
    const serviceShortcutCaptureOverrides = { ...previous };
    if (mode === "inherit") delete serviceShortcutCaptureOverrides[serviceId];
    else serviceShortcutCaptureOverrides[serviceId] = mode === "tauridium";
    appSettings = { ...appSettings, serviceShortcutCaptureOverrides };
    try {
      appSettings = await setAppSettings({ serviceShortcutCaptureOverrides });
      await closeService(serviceId).catch(() => {});
      const { [serviceId]: _, ...rest } = statusMap;
      statusMap = rest;
      showServiceSettingsSaved(serviceId);
    } catch (err) {
      appSettings = { ...appSettings, serviceShortcutCaptureOverrides: previous };
      error = `Unable to save shortcut handling: ${err}`;
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
      const saved = await toggleServiceInWorkspace(workspace, settingsSvc.id, member);
      if (saved) {
        serviceWorkspacePage = 0;
        showToast("Saved", "success");
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
      workspaces = [...workspaces, updated];
      serviceWorkspaceNewName = "";
      serviceWorkspaceFilter = "joined";
      serviceWorkspacePage = 0;
      await reconcileSavedOrders();
      showToast("Saved", "success");
    } catch (err) {
      if (created) await deleteWorkspace(created.id).catch(() => {});
      error = `Unable to create workspace and add ${serviceLabel(settingsSvc)}: ${err}`;
      await reloadWorkspaces().catch(() => {});
    } finally {
      serviceWorkspaceBusy = false;
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
      if (managedWorkspaceId === ws.id) {
        managedWorkspaceId = null;
        managedWorkspaceNameDraft = "";
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
      const imported = await importCustomRecipe(path);
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
    error = null;
    view = "appSettings";
    hideServices();
  }

  function openAddWorkspace() {
    error = null;
    managedWorkspaceId = null;
    managedWorkspaceNameDraft = "";
    settingsTab = "workspaces";
    openAppSettings();
    setTimeout(() => document.querySelector<HTMLInputElement>(".workspace-create-row input")?.focus(), 0);
  }

  function openAbout() {
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

  function backupFileName(): string {
    return `tauridium-backup-${backupTimestamp()}.json`;
  }

  function automaticBackupFileName(): string {
    return `tauridium-auto-backup-${backupTimestamp()}.json`;
  }

  async function maybeRunAutomaticBackup(startup: boolean) {
    if (automaticBackupRunning) return;
    const schedule = appSettings.automaticBackupSchedule ?? "off";
    const now = Date.now();
    const due = automaticBackupDue(
      schedule,
      appSettings.lastAutomaticBackupAt ?? 0,
      now,
      startup,
      automaticBackupStartupHandled,
    );
    if (schedule === "startup" && startup) automaticBackupStartupHandled = true;
    if (!due) return;
    automaticBackupRunning = true;
    try {
      const summary = await createAutomaticBackup(automaticBackupFileName());
      appSettings = await setAppSettings({ lastAutomaticBackupAt: now });
      backupStatus = backupSummaryText("Automatic backup created", summary);
    } catch (err) {
      backupStatus = `Automatic backup failed: ${err}`;
    } finally {
      automaticBackupRunning = false;
    }
  }

  function backupSummaryText(action: string, summary: BackupSummary): string {
    const integrity = summary.integrityVerified
      ? "integrity verified"
      : summary.sourceSchema < summary.schema
        ? `migrated from legacy schema ${summary.sourceSchema}`
        : "legacy integrity metadata unavailable";
    const recovery = summary.recoveryBackupPath ? ` Recovery snapshot: ${summary.recoveryBackupPath}` : "";
    const warnings = summary.warnings?.length ? ` Warning: ${summary.warnings.join(" ")}` : "";
    return `${action}: schema ${summary.schema}, ${integrity}; ${summary.customRecipeCount} custom recipes, ${summary.serviceCount} local services, ${summary.workspaceCount} local workspaces.${recovery}${warnings}`;
  }

  async function chooseAutomaticBackupDirectory() {
    try {
      const selected = await open({
        directory: true,
        multiple: false,
        title: "Choose automatic backup folder",
        defaultPath: appSettings.automaticBackupDirectory || undefined,
      });
      const path = Array.isArray(selected) ? selected[0] : selected;
      if (path) await saveAppSetting("automaticBackupDirectory", path);
    } catch (err) {
      error = `Unable to choose automatic backup folder: ${err}`;
    }
  }

  async function useDefaultAutomaticBackupDirectory() {
    await saveAppSetting("automaticBackupDirectory", "");
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

  async function refreshAuditLog() {
    auditBusy = true;
    auditStatus = "";
    try {
      auditEntries = await getAuditLog(5000);
      auditStatus = `${auditEntries.length} most recent audit event(s) loaded.`;
    } catch (err) {
      auditStatus = `Unable to load audit log: ${err}`;
    } finally {
      auditBusy = false;
    }
  }

  async function doExportAuditLog() {
    try {
      const path = await saveDialog({
        title: "Export Tauridium audit log",
        defaultPath: `tauridium-audit-${backupTimestamp()}.jsonl`,
        filters: [{ name: "JSON Lines", extensions: ["jsonl"] }],
      });
      if (!path) return;
      const count = await exportAuditLog(path);
      auditStatus = `Exported ${count} audit event(s).`;
      await refreshAuditLog();
    } catch (err) {
      auditStatus = `Audit export failed: ${err}`;
    }
  }

  async function doClearAuditLog() {
    const confirmed = await confirmAsk(
      "Clear the local Tauridium audit history? A new audit event recording this clear action will remain.",
    );
    if (!confirmed) return;
    try {
      await clearAuditLog();
      await refreshAuditLog();
    } catch (err) {
      auditStatus = `Unable to clear audit log: ${err}`;
    }
  }

  function selectSettingsTab(id: string) {
    if (id === "about") {
      openAbout();
      return;
    }
    settingsTab = id as Tab;
    if (settingsTab === "audit") void refreshAuditLog();
  }

  async function doExportBackup() {
    backupBusy = true;
    backupStatus = "";
    error = null;
    try {
      const path = await saveDialog({
        title: "Export Tauridium backup",
        defaultPath: backupFileName(),
        filters: [{ name: "Tauridium backup", extensions: ["json"] }],
      });
      if (!path) return;
      const summary = await exportBackup(path);
      backupStatus = backupSummaryText("Backup exported", summary);
    } catch (err) {
      error = `Backup export failed: ${err}`;
    } finally {
      backupBusy = false;
    }
  }

  async function runAutomaticBackupNow() {
    if (automaticBackupRunning || backupBusy) return;
    automaticBackupRunning = true;
    backupBusy = true;
    backupStatus = "";
    try {
      const now = Date.now();
      const summary = await createAutomaticBackup(automaticBackupFileName());
      appSettings = await setAppSettings({ lastAutomaticBackupAt: now });
      backupStatus = backupSummaryText("Automatic backup created", summary);
    } catch (err) {
      backupStatus = `Automatic backup failed: ${err}`;
    } finally {
      automaticBackupRunning = false;
      backupBusy = false;
    }
  }

  async function doRestoreBackup() {
    backupStatus = "";
    error = null;
    try {
      const selected = await open({
        directory: false,
        multiple: false,
        title: "Restore Tauridium backup",
        filters: [{ name: "Tauridium backup", extensions: ["json"] }],
      });
      const path = Array.isArray(selected) ? selected[0] : selected;
      if (!path) return;
      const confirmed = await confirmAsk(
        "Restore this Tauridium backup? Local app settings and local services/workspaces will be replaced. Custom recipes with matching ids will be overwritten; other custom recipes are retained. Backups can contain sensitive local service configuration such as proxy credentials.",
      );
      if (!confirmed) return;
      backupBusy = true;
      await closeServices();
      const summary = await restoreBackup(path);
      backupStatus = backupSummaryText("Backup restored", summary);
      window.setTimeout(() => window.location.reload(), 150);
    } catch (err) {
      error = `Backup restore failed: ${err}`;
    } finally {
      backupBusy = false;
    }
  }

  async function checkUpdates(silent = false) {
    updChecking = true;
    if (!silent) updStatus = "";
    try {
      updateInfo = await checkForUpdate();
      if (!silent && !updateInfo) updStatus = "You're on the latest version.";
    } catch (e) {
      if (!silent) updStatus = `Update check failed: ${e}`;
    } finally {
      updChecking = false;
    }
  }

  async function doInstall() {
    if (!updateInfo) return;
    updInstalling = true;
    updStatus = "Downloading…";
    try {
      await installUpdate(updateInfo); // Download, install, and restart.
    } catch (e) {
      updStatus = `Update failed: ${e}`;
      updInstalling = false;
    }
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
        void maybeRunAutomaticBackup(false);
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

  function openCustomColorPicker() {
    customColorOriginal = appSettings.accentColor;
    const hsl = hexToHsl(appSettings.accentColor);
    colorHue = hsl.hue;
    colorSaturation = hsl.saturation;
    colorLightness = hsl.lightness;
    customColorOpen = true;
  }

  function cancelCustomColorPicker() {
    appSettings.accentColor = customColorOriginal;
    customColorOpen = false;
    applyTheme();
  }

  function previewCustomColor() {
    appSettings.accentColor = hslToHex(colorHue, colorSaturation, colorLightness);
    applyTheme();
  }

  function setCustomColorFromNative(value: string) {
    const normalized = normalizeHexColor(value);
    if (!normalized) return;
    const hsl = hexToHsl(normalized);
    colorHue = hsl.hue;
    colorSaturation = hsl.saturation;
    colorLightness = hsl.lightness;
    appSettings.accentColor = normalized;
    applyTheme();
  }

  async function applyCustomColor(savePreset: boolean) {
    const color = hslToHex(colorHue, colorSaturation, colorLightness);
    const customAccentColors = savePreset
      ? [...new Set([...(appSettings.customAccentColors ?? []), color])].slice(-32)
      : appSettings.customAccentColors;
    try {
      appSettings = await setAppSettings({ accentColor: color, customAccentColors });
      customColorOpen = false;
      applyTheme();
      showToast("Saved", "success");
    } catch (err) {
      error = String(err);
    }
  }

  async function removeCustomAccent(color: string) {
    await saveAppSetting(
      "customAccentColors",
      appSettings.customAccentColors.filter((candidate) => candidate !== color),
    );
  }

  function previewSidebarWidth(value: number) {
    const width = Math.max(160, Math.min(420, Math.round(value)));
    appSettings.sidebarWidth = width;
    applyLayout();
    void setSidebarWidth(width);
  }

  async function saveCurrentSidebarPreset() {
    const width = Math.round(appSettings.sidebarWidth);
    if ([180, 240, 320].includes(width)) return;
    const customSidebarWidths = [...new Set([...(appSettings.customSidebarWidths ?? []), width])]
      .slice(-16)
      .sort((left, right) => left - right);
    await saveAppSetting("customSidebarWidths", customSidebarWidths);
  }

  async function removeSidebarPreset(width: number) {
    await saveAppSetting(
      "customSidebarWidths",
      appSettings.customSidebarWidths.filter((candidate) => candidate !== width),
    );
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
      case "toggleDevtools": void toggleDeveloperTools(); break;
    }
  }

  function handleGlobalKeydown(event: KeyboardEvent) {
    if (event.key === "Escape" && serviceContextMenu) {
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
    if (sandboxAssignmentBusy) return;
    const previous = { ...appSettings.serviceSandboxes };
    const serviceSandboxes = { ...previous };
    if (sandboxId) serviceSandboxes[serviceId] = sandboxId;
    else delete serviceSandboxes[serviceId];
    if ((previous[serviceId] ?? "") === (serviceSandboxes[serviceId] ?? "")) return;

    sandboxAssignmentBusy = true;
    appSettings = { ...appSettings, serviceSandboxes };
    try {
      const persisted = await setAppSettings({ serviceSandboxes });
      const actual = persisted.serviceSandboxes[serviceId] ?? "";
      if (actual !== (sandboxId || "")) throw new Error("Tauridium could not verify the saved sandbox assignment");
      appSettings = persisted;
      if (view === "svcSettings" && settingsSvc?.id === serviceId) showServiceSettingsSaved(serviceId);
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
    // Cleanup prevents hibernation timers, preloading, or reconnection from the
    // previous session from continuing and recreating webviews afterward.
    cancelPreloading();
    for (const id of [...hibTimers.keys()]) clearHibTimer(id);
    hibernated = new Set();
    stopReconnect();
    await closeServices();
    await logout();
    me = null;
    services = [];
    workspaces = [];
    await refreshNativeServicesMenu();
    allRecipes = [];
    activeId = null;
    view = "service";
    error = null;
  }
</script>

{#if booting}
  <main class="login">
    <div class="card"><p class="sub">Restoring session…</p></div>
  </main>
{:else if reconnecting}
  <main class="login">
    <div class="card">
      <h1>Tauridium</h1>
      <p class="notice">⚠️ Can't reach the server — it may be temporarily down.</p>
      <p class="sub">Retrying automatically in {reconnectIn}s…</p>
      <button class="primary" onclick={retryNow}>Retry now</button>
      <button class="link" onclick={cancelReconnect}>
        {pendingCreds ? "Cancel" : "Sign in with a different account"}
      </button>
    </div>
  </main>
{:else if !me}
  <main class="login">
    <form class="card" onsubmit={handleLogin}>
      <h1>Tauridium</h1>
      <p class="sub">Lightweight Ferdium client — use a server or keep everything local</p>
      <label>
        Email
        <input type="email" bind:value={email} autocomplete="username" required />
      </label>
      <label>
        Password
        <input
          type="password"
          bind:value={password}
          autocomplete="current-password"
          required
        />
      </label>
      <button type="button" class="gear" onclick={() => (showServer = !showServer)}>
        ⚙︎ Server {showServer ? "▲" : "▼"}
      </button>
      {#if showServer}
        <label>
          Server URL
          <input type="url" bind:value={server} placeholder={DEFAULT_SERVER} />
        </label>
      {/if}
      {#if error}<p class="error">{error}</p>{/if}
      <button class="primary" type="submit" disabled={loading}>
        {loading ? "Signing in…" : "Sign in"}
      </button>
      <div class="local-separator"><span>or</span></div>
      <button class="local-mode" type="button" disabled={loading} onclick={handleLocalSession}>
        Use Tauridium without an account
      </button>
      <p class="local-note">Services and workspaces stay on this device. No Ferdium server is used.</p>
    </form>
  </main>
{:else}
  <div class="shell">
    <aside class="sidebar" class:collapsed={appSettings.sidebarCollapsed}>
      <div class="account">
        <div class="account-copy">
          <strong title={me.local ? "Local" : me.firstname || me.email}>{me.local ? "Local" : me.firstname || me.email}</strong>
          <span class="workspace-scope" title={activeWorkspaceName} aria-label={`Workspace: ${activeWorkspaceName}`}>{activeWorkspaceName}</span>
        </div>
        <button
          class="sidebar-collapse-button"
          type="button"
          aria-label={appSettings.sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-pressed={appSettings.sidebarCollapsed}
          title={`${appSettings.sidebarCollapsed ? "Expand" : "Collapse"} sidebar (${appSettings.keybindings.toggleSidebar || "unassigned"})`}
          onclick={toggleSidebarCollapsed}
        >
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <rect x="2.5" y="3.5" width="15" height="13" rx="2"></rect>
            <path d="M7 4v12"></path>
            {#if appSettings.sidebarCollapsed}
              <path d="m10.5 7 3 3-3 3"></path>
            {:else}
              <path d="m13.5 7-3 3 3 3"></path>
            {/if}
          </svg>
        </button>
      </div>

      <div class="svcarea" role="region" aria-label="Service list drop area" ondragover={onServiceAreaDragOver} ondrop={onServiceAreaDrop}>
        <div class="svclist">
          {#each visibleServices as s (s.id)}{@render row(s)}{/each}
        </div>
      </div>

      <div class="count">
        {services.length} services · {workspaces.length} workspaces{#if appVer} · <span class="ver">v{appVer}</span>{/if}
      </div>
    </aside>

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
          {:else if statusMap[activeService.id] !== "ready"}
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
      {:else if view === "svcSettings" && settingsSvc}
        {@const settingsServiceId = settingsSvc.id}
        {@const settingsServiceDownload = serviceDownloadOverride(settingsServiceId)}
        <div class="panel">
          <div class="panel-head">
            <h2>Settings — {serviceLabel(settingsSvc)}</h2>
            <span class="head-actions">
              <button class="primary sm" disabled={!svcDirty && !serviceTemplateDirty} onclick={saveServiceSettings}>
                {svcDirty || serviceTemplateDirty ? "Save changes" : "Saved"}
              </button>
              <button class="link" onclick={closeServiceSettings}>✕ close</button>
            </span>
          </div>
          <code class="recipe">recipe: {settingsSvc.recipeId}</code>

          <div class="set-title">General</div>
          <label class="block">
            Name
            <input value={settingsSvc.name} oninput={(e) => saveText("name", e.currentTarget.value)} />
          </label>
          <div class="setrow">
            <label class="block">
              Custom URL
              <input value={settingsSvc.customUrl ?? ""} placeholder="https://… (for services that support it)" onchange={(e) => saveText("customUrl", e.currentTarget.value, true)} />
            </label>
            <p class="desc">Override the recipe URL. Supports <code>{"{teamId}"}</code> for recipes with website workspace IDs and, when enabled below, <code>{"{{custom_id_1}}"}</code> / <code>{"{{custom_id_2}}"}</code>. Reloads the service.</p>
          </div>
          <div class="setrow">
            <label class="block">
              Team / workspace ID
              <input value={settingsSvc.team ?? ""} placeholder="wrk_01ABC123EXAMPLE" onchange={(e) => saveText("team", e.currentTarget.value, true)} />
            </label>
            <p class="desc">Website-specific team/workspace slug or ID, not a Tauridium Workspace. Example: <code>wrk_01ABC123EXAMPLE</code> becomes <code>https://opencode.ai/workspace/wrk_01ABC123EXAMPLE/go</code> for OpenCode. Reloads the service.</p>
          </div>
          <div class="set-title">Custom URL placeholders</div>
          <div class="setrow">
            <label class="row-toggle">
              <input type="checkbox" checked={appSettings.customUrlTemplatesEnabled || serviceTemplateDraft.enabled} disabled={appSettings.customUrlTemplatesEnabled} onchange={(e) => saveServiceTemplateField("enabled", e.currentTarget.checked)} />
              <span>{appSettings.customUrlTemplatesEnabled ? "Custom URL placeholders enabled globally" : "Enable custom URL placeholders for this service"}</span>
            </label>
            <p class="desc">Allow exact <code>{"{{custom_id_1}}"}</code> and <code>{"{{custom_id_2}}"}</code> tokens in this service's Custom URL. Global enablement is available in Advanced settings.</p>
          </div>
          {#if appSettings.customUrlTemplatesEnabled || serviceTemplateDraft.enabled}
            <div class="setrow">
              <div class="proxy-grid">
                <label>Custom ID 1<input value={serviceTemplateDraft.customId1} placeholder="first replacement value" onchange={(e) => saveServiceTemplateField("customId1", e.currentTarget.value)} /></label>
                <label>Custom ID 2 (optional)<input value={serviceTemplateDraft.customId2} placeholder="second replacement value" onchange={(e) => saveServiceTemplateField("customId2", e.currentTarget.value)} /></label>
              </div>
            </div>
          {/if}
          {@render toggle("Notifications", "Show system notifications for new messages in this service.", "isNotificationEnabled", settingsSvc.isNotificationEnabled !== false)}
          {@render toggle("Muted", "Silence this service — no notifications at all.", "isMuted", settingsSvc.isMuted === true)}
          {@render toggle("Unread badge", `Count this service's unread messages in the ${dockWord} badge.`, "isBadgeEnabled", settingsSvc.isBadgeEnabled !== false)}
          {@render toggle("Indirect message badge", "Also count indirect (group / channel) messages in the badge.", "isIndirectMessageBadgeEnabled", settingsSvc.isIndirectMessageBadgeEnabled === true)}
          {@render toggle("Only favorites in unread count", "Count unread messages only from favorite chats in this service.", "onlyShowFavoritesInUnreadCount", settingsSvc.onlyShowFavoritesInUnreadCount === true)}
          {@render toggle("Media badge", "Count calls / media activity in the badge.", "isMediaBadgeEnabled", settingsSvc.isMediaBadgeEnabled === true)}
          {@render toggle("Allow hibernation", "Let this service sleep when inactive to save memory.", "isHibernationEnabled", settingsSvc.isHibernationEnabled === true)}
          {@render toggle("Open links externally", "Open clicked links in your default browser instead of inside the service.", "trapLinkClicks", settingsSvc.trapLinkClicks === true)}
          {@render toggle("Allow wake up", "Wake this service from hibernation on new activity.", "isWakeUpEnabled", settingsSvc.isWakeUpEnabled === true)}

          <div class="set-title">Keyboard shortcuts</div>
          <div class="setrow service-shortcut-policy">
            <div class="service-shortcut-copy">
              <strong>Shortcut priority</strong>
              <p class="desc">Choose who receives configured Tauridium shortcuts while this website has keyboard focus. Normal typing remains untouched unless a key or key sequence is explicitly assigned as a Tauridium shortcut.</p>
            </div>
            <select
              class="select"
              aria-label={`Shortcut priority for ${serviceLabel(settingsSvc)}`}
              value={serviceShortcutCaptureMode(settingsServiceId)}
              onchange={(event) => setServiceShortcutCaptureMode(settingsServiceId, event.currentTarget.value as "inherit" | "tauridium" | "website")}
            >
              <option value="inherit">Use global setting ({appSettings.captureServiceShortcuts ? "Tauridium" : "Website"})</option>
              <option value="tauridium">Tauridium shortcuts first</option>
              <option value="website">Website shortcuts first</option>
            </select>
            <p class="desc service-shortcut-effective">Effective behavior: <strong>{effectiveServiceShortcutCapture(settingsServiceId) ? "Tauridium shortcuts work while the website is focused" : "the website receives matching shortcuts while focused"}</strong>. Applied when this service webview is next opened.</p>
          </div>

          <div class="set-title">Workspaces</div>
          <div class="service-workspace-manager">
            <div class="service-workspace-overview">
              <div class="setting-copy">
                <strong>Workspace membership</strong>
                <p class="desc">Select the workspaces that include this service. Click anywhere in a row to change membership; changes are saved immediately.</p>
              </div>
              <span class="status-badge">{serviceWorkspaceJoinedCount} of {workspaces.length} included</span>
            </div>
            <div class="service-workspace-toolbar">
              <input
                class="service-workspace-search"
                type="search"
                bind:value={serviceWorkspaceQuery}
                oninput={() => (serviceWorkspacePage = 0)}
                placeholder="Search workspaces…"
                aria-label="Search workspaces for this service"
              />
              <div class="service-workspace-filters" role="group" aria-label="Filter workspace membership">
                <button
                  type="button"
                  class:active={serviceWorkspaceFilter === "all"}
                  aria-pressed={serviceWorkspaceFilter === "all"}
                  onclick={() => setServiceWorkspaceFilter("all")}
                >All</button>
                <button
                  type="button"
                  class:active={serviceWorkspaceFilter === "joined"}
                  aria-pressed={serviceWorkspaceFilter === "joined"}
                  onclick={() => setServiceWorkspaceFilter("joined")}
                >Included</button>
                <button
                  type="button"
                  class:active={serviceWorkspaceFilter === "available"}
                  aria-pressed={serviceWorkspaceFilter === "available"}
                  onclick={() => setServiceWorkspaceFilter("available")}
                >Not included</button>
              </div>
            </div>
            <ul class="service-workspace-list" aria-label={`Workspace membership for ${serviceLabel(settingsSvc)}`}>
              {#each serviceWorkspaceRows as workspace (workspace.id)}
                {@const joined = workspace.services.includes(settingsServiceId)}
                <li class="service-workspace-item">
                  <label class="service-workspace-option" class:joined class:busy={serviceWorkspaceBusy}>
                    <input
                      class="service-workspace-checkbox"
                      type="checkbox"
                      checked={joined}
                      disabled={serviceWorkspaceBusy}
                      onchange={(event) => toggleCurrentServiceWorkspace(workspace, event.currentTarget.checked)}
                      aria-label={`Include ${serviceLabel(settingsSvc)} in ${workspace.name}`}
                    />
                    {#if workspaceIcon(workspace) && !failedWorkspaceIcons.has(workspace.id)}
                      <img class="workspace-avatar service-workspace-avatar workspace-avatar-image" src={workspaceIcon(workspace) ?? ""} alt="" onerror={() => markWorkspaceIconFailed(workspace.id)} />
                    {:else}
                      <span class="workspace-avatar service-workspace-avatar" aria-hidden="true">{workspace.name.slice(0, 1).toUpperCase()}</span>
                    {/if}
                    <span class="service-workspace-copy">
                      <strong>{workspace.name}</strong>
                      <small>{workspace.services.length} service{workspace.services.length === 1 ? "" : "s"}</small>
                    </span>
                    <span class="service-workspace-state" aria-hidden="true">{joined ? "Included" : "Not included"}</span>
                  </label>
                </li>
              {:else}
                <li class="managed-empty">
                  <strong>No workspaces match</strong>
                  <span>{workspaces.length ? "Change the search or membership filter." : "Create a workspace below to organize this service."}</span>
                </li>
              {/each}
            </ul>
            {#if serviceWorkspaceCandidates.length > MANAGED_SERVICE_PAGE_SIZE}
              <div class="pagination" aria-label="Service workspace pages">
                <button class="secondary sm" disabled={serviceWorkspacePage === 0} onclick={() => (serviceWorkspacePage = Math.max(0, serviceWorkspacePage - 1))}>Previous</button>
                <span>Page {serviceWorkspacePage + 1} of {serviceWorkspacePageCount} · {serviceWorkspaceCandidates.length} workspaces</span>
                <button class="secondary sm" disabled={serviceWorkspacePage >= serviceWorkspacePageCount - 1} onclick={() => (serviceWorkspacePage = Math.min(serviceWorkspacePageCount - 1, serviceWorkspacePage + 1))}>Next</button>
              </div>
            {/if}
            <div class="service-workspace-create-card">
              <div class="setting-copy">
                <strong>Create a workspace</strong>
                <p class="desc">Create a new workspace and include this service immediately.</p>
              </div>
              <div class="service-workspace-create">
                <input bind:value={serviceWorkspaceNewName} maxlength="80" placeholder="Workspace name" aria-label="New workspace name for this service" />
                <button class="secondary sm" disabled={serviceWorkspaceBusy || !serviceWorkspaceNewName.trim()} onclick={createWorkspaceForCurrentService}>Create and include</button>
              </div>
            </div>
          </div>

          <div class="set-title">Sandbox</div>
          <div class="service-workspace-manager service-sandbox-manager">
            <div class="service-workspace-overview">
              <div class="setting-copy">
                <strong>Sandbox assignment</strong>
                <p class="desc">Choose the persistent webview data store for this service. Services in the same shared sandbox can share compatible login sessions and caches. Changes are saved immediately.</p>
              </div>
              <span class="status-badge">{currentServiceSandboxName}</span>
            </div>
            <input
              class="service-workspace-search service-sandbox-search"
              type="search"
              bind:value={serviceSandboxQuery}
              oninput={() => (serviceSandboxPage = 0)}
              placeholder="Search sandboxes…"
              aria-label={`Search sandboxes for ${serviceLabel(settingsSvc)}`}
            />
            <ul class="service-workspace-list service-sandbox-list" aria-label={`Sandbox assignment for ${serviceLabel(settingsSvc)}`}>
              {#each serviceSandboxRows as sandbox (sandbox.id)}
                {@const assigned = (serviceSandboxId(settingsServiceId) ?? "") === sandbox.id}
                <li class="service-workspace-item">
                  <label class="service-workspace-option service-sandbox-option" class:joined={assigned} class:busy={sandboxAssignmentBusy}>
                    <input
                      class="service-workspace-checkbox"
                      type="radio"
                      name={`service-sandbox-${settingsServiceId}`}
                      value={sandbox.id}
                      checked={assigned}
                      disabled={sandboxAssignmentBusy}
                      onchange={() => assignServiceSandbox(settingsServiceId, sandbox.id)}
                      aria-label={`Use ${sandbox.name} for ${serviceLabel(settingsSvc)}`}
                    />
                    <span class="workspace-avatar service-workspace-avatar" aria-hidden="true">{sandbox.id ? sandbox.name.slice(0, 1).toUpperCase() : "I"}</span>
                    <span class="service-workspace-copy">
                      <strong>{sandbox.name}</strong>
                      <small>{sandbox.id ? `${Object.values(appSettings.serviceSandboxes).filter((value) => value === sandbox.id).length} assigned service(s)` : "Private storage for this service"}</small>
                    </span>
                    <span class="service-workspace-state" aria-hidden="true">{assigned ? "Selected" : "Available"}</span>
                  </label>
                </li>
              {:else}
                <li class="managed-empty"><strong>No sandboxes match</strong><span>Change the search text, or create a shared sandbox in Settings → Sandbox.</span></li>
              {/each}
            </ul>
            {#if serviceSandboxCandidates.length > MANAGED_SERVICE_PAGE_SIZE}
              <div class="pagination" aria-label="Service sandbox pages">
                <button class="secondary sm" disabled={serviceSandboxPage === 0} onclick={() => (serviceSandboxPage = Math.max(0, serviceSandboxPage - 1))}>Previous</button>
                <span>Page {serviceSandboxPage + 1} of {serviceSandboxPageCount} · {serviceSandboxCandidates.length} options</span>
                <button class="secondary sm" disabled={serviceSandboxPage >= serviceSandboxPageCount - 1} onclick={() => (serviceSandboxPage = Math.min(serviceSandboxPageCount - 1, serviceSandboxPage + 1))}>Next</button>
              </div>
            {/if}
            <p class="desc service-sandbox-help">Shared sandboxes are created and managed globally in Settings → Sandbox.</p>
          </div>

          <div class="set-title">Downloads</div>
          <div class="service-workspace-manager service-download-manager">
            <div class="service-workspace-overview">
              <div class="setting-copy">
                <strong>Service download settings</strong>
                <p class="desc">Optionally override download behavior for this service. A service override has highest priority. Without one, an active workspace override is used when present, then the global Advanced defaults.</p>
              </div>
              <span class="status-badge">{settingsServiceDownload ? "Override" : "Inherited"}</span>
            </div>
            <label class="row-toggle download-override-toggle">
              <input
                type="checkbox"
                checked={settingsServiceDownload !== null}
                disabled={downloadSettingsBusy}
                onchange={(event) => saveServiceDownloadOverride(
                  settingsServiceId,
                  event.currentTarget.checked ? inheritedDownloadPreference() : null,
                )}
              />
              <span>Override download settings for this service</span>
            </label>
            {#if settingsServiceDownload}
              <div class="download-setting-row">
                <div class="setting-copy">
                  <strong>Download directory</strong>
                  <p class="desc" title={downloadDirectoryLabel(settingsServiceDownload.directory)}>{downloadDirectoryLabel(settingsServiceDownload.directory)}</p>
                </div>
                <div class="setting-actions">
                  <button class="secondary sm" disabled={downloadSettingsBusy} onclick={() => chooseServiceDownloadDirectory(settingsServiceId)}>Choose folder…</button>
                  <button class="secondary sm" disabled={downloadSettingsBusy || !settingsServiceDownload.directory} onclick={() => saveServiceDownloadOverride(settingsServiceId, { ...settingsServiceDownload, directory: "" })}>Use system Downloads</button>
                </div>
              </div>
              <label class="download-setting-row setting-card-toggle">
                <span class="setting-copy"><strong>Ask where to save each download</strong><span class="desc">Show a native Save dialog for every download, initialized with the website's suggested filename and this directory.</span></span>
                <span class="switch-control">
                  <input class="switch-input" type="checkbox" checked={settingsServiceDownload.askEachDownload} disabled={downloadSettingsBusy} aria-label={`Ask where to save downloads for ${serviceLabel(settingsSvc)}`} onchange={(event) => saveServiceDownloadOverride(settingsServiceId, { ...settingsServiceDownload, askEachDownload: event.currentTarget.checked })} />
                  <span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>
                </span>
              </label>
            {:else}
              <p class="desc download-inherited-copy">Inherited global directory: <strong>{downloadDirectoryLabel(appSettings.downloadDirectory)}</strong> · Ask each time: <strong>{appSettings.askEachDownload ? "On" : "Off"}</strong>. Workspace settings can override these values when this service is opened through that workspace.</p>
            {/if}
          </div>

          <div class="set-title">Appearance</div>
          <div class="setrow">
            <label class="row-toggle">
              <input
                type="checkbox"
                checked={serviceIconInverted(settingsServiceId)}
                onchange={(event) => saveServiceIconInversion(settingsServiceId, event.currentTarget.checked)}
              />
              <span>Invert service icon colors</span>
            </label>
            <p class="desc">Invert this service icon in Tauridium's UI so black or very dark artwork stays visible on Black OLED backgrounds. This affects only the icon, not the website.</p>
          </div>
          {@render toggle("Dark mode", "Force a dark theme on this service (via Dark Reader). Reloads the service when changed.", "isDarkModeEnabled", settingsSvc.isDarkModeEnabled === true)}
          {#if settingsSvc.isDarkModeEnabled}
            <div class="setrow">
              <div class="num-row">
                <label>Brightness<input class="num" type="number" value={settingsSvc.darkReaderBrightness ?? 100} onchange={(e) => saveNum("darkReaderBrightness", e.currentTarget.value)} /></label>
                <label>Contrast<input class="num" type="number" value={settingsSvc.darkReaderContrast ?? 90} onchange={(e) => saveNum("darkReaderContrast", e.currentTarget.value)} /></label>
                <label>Sepia<input class="num" type="number" value={settingsSvc.darkReaderSepia ?? 10} onchange={(e) => saveNum("darkReaderSepia", e.currentTarget.value)} /></label>
              </div>
              <p class="desc">Dark Reader fine-tuning (applies to this service's dark mode).</p>
            </div>
          {/if}
          {@render toggle("Use website icon", "Prefer this service's cached website icon over its recipe icon. Tauridium fetches it once and reuses the persistent local cache.", "useFavicon", settingsSvc.useFavicon === true)}
          <div class="setrow">
            <div><strong>Website icon cache</strong><p class="desc">Discard the cached result and fetch this service's current website icon again.</p></div>
            <button class="secondary sm" onclick={() => settingsSvc && loadServiceIcon(settingsSvc, true, true, true)}>Refetch icon</button>
          </div>
          {@render toggle("Progress bar", "Service preference. Tauridium already shows a loading spinner per service.", "isProgressbarEnabled", settingsSvc.isProgressbarEnabled === true)}
          <div class="setrow">
            <label class="block">
              Custom user agent
              <input value={settingsSvc.userAgentPref ?? ""} placeholder="empty = app default" onchange={(e) => saveText("userAgentPref", e.currentTarget.value, true)} />
            </label>
            <p class="desc">Per-service browser identity, overrides the global one. Reloads the service.</p>
          </div>

          <div class="set-title">Proxy</div>
          {@render toggle("Use a proxy", "Route this service through an HTTP/HTTPS proxy.", "isProxyFeatureEnabled", settingsSvc.isProxyFeatureEnabled === true)}
          {#if settingsSvc.isProxyFeatureEnabled}
            <div class="setrow">
              <div class="proxy-grid">
                <input placeholder="Host" value={settingsSvc.proxyHost ?? ""} onchange={(e) => saveText("proxyHost", e.currentTarget.value)} />
                <input placeholder="Port" value={String(settingsSvc.proxyPort ?? "")} onchange={(e) => saveText("proxyPort", e.currentTarget.value)} />
                <input placeholder="Username (optional)" value={settingsSvc.proxyUser ?? ""} onchange={(e) => saveText("proxyUser", e.currentTarget.value)} />
                <input placeholder="Password (optional)" type="password" value={settingsSvc.proxyPassword ?? ""} onchange={(e) => saveText("proxyPassword", e.currentTarget.value)} />
              </div>
            </div>
          {/if}

          {#if error}<p class="error">{error}</p>{/if}
          <div class="danger-zone">
            <div class="dz-row">
              <div>
                <strong>Clear cache & session</strong>
                <p class="dz-hint">Sign out of this service and wipe its cookies/storage from disk. The service stays in your list.</p>
              </div>
              <button class="danger sm" onclick={() => settingsSvc && handleClearCache(settingsSvc)}>
                Clear cache
              </button>
            </div>
            <div class="dz-row">
              <div>
                <strong>{settingsSvc.isEnabled === false ? "Enable service" : "Disable service"}</strong>
                <p class="dz-hint">{settingsSvc.isEnabled === false ? "Allow this web app to load again." : "Keep it in the list, but close it and prevent the web app from loading until re-enabled."}</p>
              </div>
              <button class:danger={settingsSvc.isEnabled !== false} class:secondary={settingsSvc.isEnabled === false} class="sm" onclick={() => settingsSvc && toggleServiceEnabled(settingsSvc)}>
                {settingsSvc.isEnabled === false ? "Enable" : "Disable"}
              </button>
            </div>
            <div class="dz-row">
              <div>
                <strong>Delete service</strong>
                <p class="dz-hint">Remove this service from your account and wipe its data.</p>
              </div>
              <button class="danger sm" onclick={() => settingsSvc && handleDelete(settingsSvc)}>
                Delete
              </button>
            </div>
          </div>
        </div>
      {:else if view === "add"}
        <div class="panel">
          <div class="panel-head">
            <h2>Add a service</h2>
            <button class="link" onclick={backToService}>✕ close</button>
          </div>
          <p class="notice">⚠️ Passkey / biometric sign-in (Touch ID, security keys) isn't supported in the embedded webview. On a service's login screen, choose "try another way" and use a password + authenticator code (TOTP) or a phone prompt instead.</p>

          <div class="add-tabs" role="tablist" aria-label="Add service method">
            <button class:active={addMode === "catalog"} onclick={() => (addMode = "catalog")}>Recipes</button>
            <button class:active={addMode === "website"} onclick={() => openCustomWebsite()}>Custom website</button>
            <button class:active={addMode === "creator"} onclick={openRecipeCreator}>Recipe creator</button>
          </div>

          {#if error}<p class="error">{error}</p>{/if}

          {#if addMode === "catalog"}
            <label class="block">
              Name (optional)
              <input bind:value={newServiceName} placeholder="leave empty = recipe name" />
            </label>
            <input class="filter" bind:value={recipeQuery} placeholder="Filter among {allRecipes.length} services…" />
            <div class="recipe-tools">
              <button class="secondary sm" onclick={refreshRecipes} disabled={recipesLoading}>Refresh</button>
              <button class="secondary sm" onclick={() => importRecipe(true)}>Import folder…</button>
              <button class="secondary sm" onclick={() => importRecipe(false)}>Import package.json…</button>
            </div>
            {#if recipeStorage}
              <p class="recipe-path">Local recipes: <code>{recipeStorage.recipesDir}</code></p>
            {/if}
            {#if recipesLoading}
              <p class="sub">Loading catalog…</p>
            {:else}
              <div class="results">
                {#each filteredRecipes as r (r.id)}
                  <button class="result" onclick={() => pickRecipe(r)}>
                    {#if r.icons?.svg}<img class="result-icon" src={r.icons.svg} alt="" />{/if}
                    <span class="result-main">
                      <span class="result-name">{r.name}</span>
                      {#if r.description}<span class="result-desc">{r.description}</span>{/if}
                    </span>
                    <span class="result-meta">
                      {#if r.source && r.source !== "remote"}<span class="source-badge">{r.source}</span>{/if}
                      <span class="result-id">{r.id}</span>
                    </span>
                  </button>
                {:else}
                  <div class="empty-recipe">
                    <strong>No preset recipe matches.</strong>
                    <p class="sub">You can still add the site directly or create a reusable local recipe.</p>
                    <div class="recipe-tools">
                      <button class="primary sm" onclick={() => openCustomWebsite(recipeQuery)}>Add a custom website</button>
                      <button class="secondary sm" onclick={openRecipeCreator}>Create a recipe</button>
                    </div>
                  </div>
                {/each}
              </div>
            {/if}
          {:else if addMode === "website"}
            <div class="creator-card">
              <h3>Custom Website</h3>
              <p class="sub">A local service backed by Tauridium's built-in Custom Website recipe. It stays on this device and does not require a Ferdium server recipe.</p>
              <label class="block">Website URL<input bind:value={customWebsiteUrl} placeholder="https://example.com" /></label>
              <label class="block">Name (optional)<input bind:value={newServiceName} placeholder="derived from the hostname" /></label>
              <div class="recipe-actions">
                <button class="primary" onclick={createWebsite}>Add website</button>
                <button class="secondary" onclick={() => (addMode = "catalog")}>Back to recipes</button>
              </div>
            </div>
          {:else}
            <div class="creator-card">
              <h3>Local recipe creator</h3>
              <p class="sub">Creates a reusable recipe under Tauridium's configuration folder. Name, id, and URL are enough for a basic recipe.</p>
              <div class="creator-grid">
                <label class="block">Recipe name<input value={recipeDraft.name} oninput={(e) => setRecipeName(e.currentTarget.value)} placeholder="My AI Service" /></label>
                <label class="block">Recipe id<input value={recipeDraft.id} oninput={(e) => { recipeIdEdited = true; recipeDraft.id = e.currentTarget.value.toLowerCase(); }} placeholder="my-ai-service" /></label>
              </div>
              <label class="block">Service URL<input bind:value={recipeDraft.serviceUrl} placeholder="https://example.com" /></label>
              <label class="block">Description (optional)<input bind:value={recipeDraft.description} placeholder="What this recipe opens" /></label>
              <div class="creator-options">
                <label class="row-toggle compact"><span>Allow a per-service custom URL</span><input type="checkbox" bind:checked={recipeDraft.hasCustomUrl} /></label>
                <label class="row-toggle compact"><span>Use a teamId placeholder in the URL</span><input type="checkbox" bind:checked={recipeDraft.hasTeamId} /></label>
              </div>
              <button class="link" onclick={() => (recipeAdvanced = !recipeAdvanced)}>{recipeAdvanced ? "Hide advanced files" : "Advanced: icon.svg / webview.js"}</button>
              {#if recipeAdvanced}
                <label class="block">icon.svg (optional)<textarea class="code-input" bind:value={recipeDraft.iconSvg} rows="5" placeholder="<svg …>…</svg>"></textarea></label>
                <label class="block">webview.js (optional)<textarea class="code-input" bind:value={recipeDraft.webviewJs} rows="8" placeholder="Optional Ferdium-compatible recipe integration script"></textarea></label>
                <p class="notice security-note">A recipe webview.js runs inside the loaded website and can access that page's DOM. Only import or write scripts you trust.</p>
              {/if}
              <label class="block">Service name after “Save & add” (optional)<input bind:value={newServiceName} placeholder="leave empty = recipe name" /></label>
              <div class="recipe-actions">
                <button class="primary" disabled={recipeSaving} onclick={() => saveRecipe(true)}>{recipeSaving ? "Saving…" : "Save & add"}</button>
                <button class="secondary" disabled={recipeSaving} onclick={() => saveRecipe(false)}>Save recipe</button>
                <button class="secondary" onclick={() => importRecipe(true)}>Import folder…</button>
              </div>
              {#if recipeStorage}
                <p class="recipe-path">Saved under <code>{recipeStorage.recipesDir}</code> as <code>&lt;recipe-id&gt;/package.json</code>. You can also place compatible recipe folders there manually and press Refresh.</p>
              {/if}
              {#if customRecipes.length > 0}<p class="sub">{customRecipes.length} custom recipe{customRecipes.length === 1 ? "" : "s"} currently loaded.</p>{/if}
            </div>
          {/if}
        </div>
      {:else if view === "appSettings"}
        <div class="panel settings-panel">
          <div class="panel-head settings-head">
            <div>
              <h2>Settings</h2>
              <p class="panel-subtitle">Configure Tauridium's application-wide behavior.</p>
            </div>
            <button class="icon-button" title="Close settings" aria-label="Close settings" onclick={backToService}>✕</button>
          </div>

          <nav class="settings-tabs" aria-label="Settings sections">
            {#each [["general", "General"], ["services", "Services"], ["workspaces", "Workspaces"], ["appearance", "Appearance"], ["keybindings", "Keybinds"], ["sandbox", "Sandbox"], ["privacy", "Privacy"], ["backup", "Backup"], ["audit", "Audit log"], ["advanced", "Advanced"], ["updates", "Updates"], ["about", "About"]] as [id, label] (id)}
              <button
                class="setting-tab"
                class:on={settingsTab === id}
                aria-current={settingsTab === id ? "page" : undefined}
                onclick={() => selectSettingsTab(id)}>{label}</button>
            {/each}
          </nav>

          <div class="settings-content">
            {#if settingsTab === "general"}
              <section class="settings-section" aria-labelledby="settings-general-startup">
                <div class="section-heading">
                  <h3 id="settings-general-startup">Startup</h3>
                  <p>Choose how Tauridium behaves when the desktop session starts and when its window closes.</p>
                </div>
                <div class="settings-list">
                  {@render appToggle("Launch at login", `Start Tauridium automatically ${loginText}.`, "autostart", appSettings.autostart)}
                  {@render appToggle("Start in background", `Launch with the main window hidden while Tauridium remains available in the ${trayWord}.`, "startMinimized", appSettings.startMinimized)}
                  {@render appToggle("Close to tray", `Hide Tauridium to the ${trayWord} when the window close button is used instead of quitting the app.`, "closeToSystemTray", appSettings.closeToSystemTray)}
                </div>
              </section>
            {:else if settingsTab === "services"}
              <section class="settings-section" aria-labelledby="settings-services-configured">
                <div class="section-heading">
                  <h3 id="settings-services-configured">Configured services <span class="section-count">{services.length}</span></h3>
                  <p>Search or separate the list by workspace. Reordering a filtered workspace changes only those visible service slots while preserving the canonical global order.</p>
                </div>
                <div class="managed-toolbar service-managed-toolbar">
                  <input
                    class="setting-text-input"
                    type="search"
                    placeholder="Search configured services…"
                    bind:value={managedServiceQuery}
                    oninput={() => (managedServicePage = 0)}
                    aria-label="Search configured services"
                  />
                  <select
                    class="select"
                    bind:value={managedWorkspaceFilter}
                    onchange={() => (managedServicePage = 0)}
                    aria-label="Filter configured services by workspace"
                  >
                    <option value="all">All workspaces</option>
                    {#each sortedWorkspaces as workspace (workspace.id)}
                      <option value={workspace.id}>{workspace.name}</option>
                    {/each}
                  </select>
                  <button class="primary" onclick={openAdd}>Create service</button>
                </div>
                <div class="managed-list" role="list" aria-label="Configured services">
                  {#each managedServiceRows as service, index (service.id)}
                    <div class="managed-row" role="listitem">
                      <div class="managed-identity">
                        {#if serviceIconFailed(service)}
                          <span class="managed-icon fallback">{serviceLabel(service).slice(0, 1).toUpperCase()}</span>
                        {:else}
                          <img class="managed-icon" class:service-icon-inverted={serviceIconInverted(service.id)} src={displayedServiceIcon(service)} alt="" onerror={() => markIconFailed(service)} />
                        {/if}
                        <div class="managed-copy">
                          <strong>{serviceLabel(service)}</strong>
                          <span>{service.isEnabled ? "Enabled" : "Disabled"} · {service.recipeId || "Unknown recipe"}{service.isLocalRecipe ? " · Local recipe" : ""}</span>
                        </div>
                      </div>
                      <div class="managed-actions">
                        <button class="icon-button compact" disabled={serviceOrderBusy || managedServicePage * MANAGED_SERVICE_PAGE_SIZE + index === 0} aria-label={`Move ${serviceLabel(service)} up`} title="Move up" onclick={() => moveManagedService(service.id, -1)}>↑</button>
                        <button class="icon-button compact" disabled={serviceOrderBusy || managedServicePage * MANAGED_SERVICE_PAGE_SIZE + index === managedServices.length - 1} aria-label={`Move ${serviceLabel(service)} down`} title="Move down" onclick={() => moveManagedService(service.id, 1)}>↓</button>
                        <button class="secondary sm" onclick={() => openServiceSettings(service, true)}>Service settings</button>
                      </div>
                    </div>
                  {:else}
                    <div class="managed-empty">
                      <strong>{services.length ? "No services match this view" : "No services configured"}</strong>
                      <span>{services.length ? "Change the search or workspace filter." : "Create a service above or use the Tauridium application menu."}</span>
                    </div>
                  {/each}
                </div>
                {#if managedServices.length > MANAGED_SERVICE_PAGE_SIZE}
                  <div class="pagination" aria-label="Configured services pages">
                    <button class="secondary sm" disabled={managedServicePage === 0} onclick={() => (managedServicePage = Math.max(0, managedServicePage - 1))}>Previous</button>
                    <span>Page {managedServicePage + 1} of {managedServicePageCount} · {managedServices.length} services</span>
                    <button class="secondary sm" disabled={managedServicePage >= managedServicePageCount - 1} onclick={() => (managedServicePage = Math.min(managedServicePageCount - 1, managedServicePage + 1))}>Next</button>
                  </div>
                {/if}
              </section>
              <section class="settings-section" aria-labelledby="settings-services-list">
                <div class="section-heading">
                  <h3 id="settings-services-list">Service list</h3>
                  <p>Control what appears in the sidebar and how unread activity is represented.</p>
                </div>
                <div class="settings-list">
                  {@render appToggle("Show disabled services", "Keep disabled services visible in the sidebar with reduced emphasis.", "showDisabledServices", appSettings.showDisabledServices)}
                  {@render appToggle("Show service names", "Display each service name beside its icon in the sidebar.", "showServiceName", appSettings.showServiceName)}
                  {@render appToggle("Unread badges for muted services", "Continue displaying unread counts for services whose notifications are muted.", "showMessageBadgeWhenMuted", appSettings.showMessageBadgeWhenMuted)}
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-services-performance">
                <div class="section-heading">
                  <h3 id="settings-services-performance">Performance</h3>
                  <p>Balance faster switching against memory use.</p>
                </div>
                <div class="settings-list">
                  <div class="setting-card">
                    <div class="setting-copy">
                      <span class="setting-label">Hibernate inactive services</span>
                      <span class="setting-description">Unload inactive services to save memory. Per-service “Allow hibernation” must also be enabled.</span>
                    </div>
                    <select class="select setting-control" aria-label="Hibernate inactive services" bind:value={appSettings.hibernationTimer} onchange={() => saveAppSetting("hibernationTimer", appSettings.hibernationTimer)}>
                      <option value={0}>Off</option>
                      <option value={30}>After 30 seconds</option>
                      <option value={60}>After 1 minute</option>
                      <option value={300}>After 5 minutes</option>
                    </select>
                  </div>
                  {@render appToggle("Preload services", "Load services in the background after startup for faster switching. This uses more memory.", "preloadServices", appSettings.preloadServices)}
                </div>
              </section>
            {:else if settingsTab === "workspaces"}
              {#if managedWorkspace}
                {@const selectedWorkspaceId = managedWorkspace.id}
                {@const selectedWorkspaceName = managedWorkspace.name}
                {@const selectedWorkspaceServices = managedWorkspace.services}
                {@const selectedWorkspaceDownload = workspaceDownloadOverride(selectedWorkspaceId)}
                <section class="settings-section workspace-detail-section" aria-labelledby="settings-workspace-detail">
                  <div class="section-heading workspace-detail-heading">
                    <div>
                      <h3 id="settings-workspace-detail">Workspace settings · {selectedWorkspaceName}</h3>
                      <p>Rename this workspace, assign its icon, and manage exactly which services belong to it.</p>
                    </div>
                    <button class="secondary sm" onclick={closeManagedWorkspace}>← Workspaces</button>
                  </div>
                  <div class="settings-list">
                    <div class="setting-card">
                      <div class="setting-copy">
                        <span class="setting-label">Name</span>
                        <span class="setting-description">Used in the quick switcher and Navigate menu.</span>
                      </div>
                      <div class="workspace-name-control">
                        <input class="setting-text-input" bind:value={managedWorkspaceNameDraft} maxlength="80" aria-label="Workspace name" />
                        <button class="primary" disabled={managedWorkspaceBusy || !managedWorkspaceNameDraft.trim() || managedWorkspaceNameDraft.trim() === selectedWorkspaceName} onclick={saveManagedWorkspaceName}>Save</button>
                      </div>
                    </div>
                    <div class="setting-card setting-card-stack workspace-icon-card">
                      <div class="setting-copy">
                        <span class="setting-label">Icon</span>
                        <span class="setting-description">Choose from the same resolved service icons Tauridium already uses. The selected icon is stored with application settings and embedded in workspace exports and backups.</span>
                      </div>
                      <div class="workspace-icon-current">
                        {#if workspaceIcon(managedWorkspace) && !failedWorkspaceIcons.has(selectedWorkspaceId)}
                          <img class="workspace-avatar workspace-icon-preview" src={workspaceIcon(managedWorkspace) ?? ""} alt="" onerror={() => markWorkspaceIconFailed(selectedWorkspaceId)} />
                        {:else}
                          <span class="workspace-avatar workspace-icon-preview" aria-hidden="true">{selectedWorkspaceName.slice(0, 1).toUpperCase()}</span>
                        {/if}
                        <div class="setting-copy">
                          <strong>{workspaceIcon(managedWorkspace) ? "Custom workspace icon" : "Automatic initial"}</strong>
                          <span class="setting-description">Select a configured service below to copy its currently resolved icon into this workspace.</span>
                        </div>
                        <button class="secondary sm" disabled={managedWorkspaceBusy || !workspaceIcon(managedWorkspace)} onclick={() => saveManagedWorkspaceIcon(null)}>Use initial</button>
                      </div>
                      <div class="workspace-icon-url-row">
                        <input
                          class="setting-text-input"
                          type="url"
                          bind:value={managedWorkspaceIconUrlDraft}
                          placeholder="https://example.com/icon.png or https://example.com/"
                          aria-label={`Icon URL for ${selectedWorkspaceName}`}
                          onkeydown={(event) => { if (event.key === "Enter") { event.preventDefault(); void assignManagedWorkspaceIconFromUrl(); } }}
                        />
                        <button class="secondary sm" disabled={managedWorkspaceBusy || !managedWorkspaceIconUrlDraft.trim()} onclick={assignManagedWorkspaceIconFromUrl}>Fetch and use</button>
                      </div>
                      <p class="settings-note">Enter a direct image URL or a website URL. Tauridium downloads the icon once, validates its size/type, and stores it with the workspace so later backups and portable workspace exports do not depend on the remote site.</p>
                      <div class="workspace-icon-choices">
                        {#each sorted as service (service.id)}
                          {@const candidateIcon = displayedServiceIcon(service)}
                          <button
                            type="button"
                            class="workspace-icon-choice"
                            class:selected={workspaceIcon(managedWorkspace) === candidateIcon}
                            disabled={managedWorkspaceBusy}
                            onclick={() => assignManagedWorkspaceIconFromService(service)}
                            aria-label={`Use ${serviceLabel(service)} icon for ${selectedWorkspaceName}`}
                          >
                            {#if !serviceIconFailed(service)}
                              <img class:service-icon-inverted={serviceIconInverted(service.id)} src={candidateIcon} alt="" onerror={() => markIconFailed(service)} />
                            {:else}
                              <span aria-hidden="true">{serviceLabel(service).slice(0, 1).toUpperCase()}</span>
                            {/if}
                            <small>{serviceLabel(service)}</small>
                          </button>
                        {:else}
                          <div class="managed-empty"><strong>No service icons available</strong><span>Add a service before assigning a workspace icon.</span></div>
                        {/each}
                      </div>
                    </div>
                    <div class="setting-card setting-card-stack workspace-download-card">
                      <div class="setting-copy">
                        <span class="setting-label">Downloads</span>
                        <span class="setting-description">Optionally override the global Advanced download defaults whenever a service is opened in this workspace. A per-service override still takes priority.</span>
                      </div>
                      <label class="row-toggle download-override-toggle">
                        <input
                          type="checkbox"
                          checked={selectedWorkspaceDownload !== null}
                          disabled={downloadSettingsBusy}
                          onchange={(event) => saveWorkspaceDownloadOverride(
                            selectedWorkspaceId,
                            event.currentTarget.checked ? inheritedDownloadPreference() : null,
                          )}
                        />
                        <span>Override download settings for this workspace</span>
                      </label>
                      {#if selectedWorkspaceDownload}
                        <div class="download-setting-row">
                          <div class="setting-copy">
                            <strong>Download directory</strong>
                            <span class="setting-description" title={downloadDirectoryLabel(selectedWorkspaceDownload.directory)}>{downloadDirectoryLabel(selectedWorkspaceDownload.directory)}</span>
                          </div>
                          <div class="setting-actions">
                            <button class="secondary sm" disabled={downloadSettingsBusy} onclick={() => chooseWorkspaceDownloadDirectory(selectedWorkspaceId)}>Choose folder…</button>
                            <button class="secondary sm" disabled={downloadSettingsBusy || !selectedWorkspaceDownload.directory} onclick={() => saveWorkspaceDownloadOverride(selectedWorkspaceId, { ...selectedWorkspaceDownload, directory: "" })}>Use system Downloads</button>
                          </div>
                        </div>
                        <label class="download-setting-row setting-card-toggle">
                          <span class="setting-copy"><strong>Ask where to save each download</strong><span class="setting-description">Show a native Save dialog for each download while this workspace is active.</span></span>
                          <span class="switch-control">
                            <input class="switch-input" type="checkbox" checked={selectedWorkspaceDownload.askEachDownload} disabled={downloadSettingsBusy} aria-label={`Ask where to save downloads in ${selectedWorkspaceName}`} onchange={(event) => saveWorkspaceDownloadOverride(selectedWorkspaceId, { ...selectedWorkspaceDownload, askEachDownload: event.currentTarget.checked })} />
                            <span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>
                          </span>
                        </label>
                      {:else}
                        <p class="settings-note">Inherited global directory: <strong>{downloadDirectoryLabel(appSettings.downloadDirectory)}</strong> · Ask each time: <strong>{appSettings.askEachDownload ? "On" : "Off"}</strong>.</p>
                      {/if}
                    </div>
                    <div class="setting-card setting-card-stack workspace-membership-card">
                      <div class="setting-copy">
                        <span class="setting-label">Services</span>
                        <span class="setting-description">Membership changes are saved immediately. Search and pagination keep this usable with large service collections.</span>
                      </div>
                      <input
                        class="setting-text-input"
                        type="search"
                        placeholder="Search services…"
                        bind:value={managedWorkspaceServiceQuery}
                        oninput={() => (managedWorkspaceServicePage = 0)}
                        aria-label={`Search services in ${selectedWorkspaceName}`}
                      />
                      <div class="workspace-service-list" role="list" aria-label={`Services in ${selectedWorkspaceName}`}>
                        {#each managedWorkspaceServiceRows as service (service.id)}
                          <label class="workspace-service-row" role="listitem">
                            <span>
                              <strong>{serviceLabel(service)}</strong>
                              <small>{service.recipeId || "Unknown recipe"}{service.isEnabled === false ? " · Disabled" : ""}</small>
                            </span>
                            <input
                              type="checkbox"
                              checked={selectedWorkspaceServices.includes(service.id)}
                              disabled={managedWorkspaceBusy}
                              onchange={(event) => toggleManagedWorkspaceService(service.id, event.currentTarget.checked)}
                              aria-label={`${selectedWorkspaceServices.includes(service.id) ? "Remove" : "Add"} ${serviceLabel(service)} ${selectedWorkspaceServices.includes(service.id) ? "from" : "to"} ${selectedWorkspaceName}`}
                            />
                          </label>
                        {:else}
                          <div class="managed-empty"><strong>No services match this search</strong><span>Change the search to manage other services.</span></div>
                        {/each}
                      </div>
                      {#if managedWorkspaceServices.length > MANAGED_SERVICE_PAGE_SIZE}
                        <div class="pagination" aria-label="Workspace service pages">
                          <button class="secondary sm" disabled={managedWorkspaceServicePage === 0} onclick={() => (managedWorkspaceServicePage = Math.max(0, managedWorkspaceServicePage - 1))}>Previous</button>
                          <span>Page {managedWorkspaceServicePage + 1} of {managedWorkspaceServicePageCount} · {managedWorkspaceServices.length} services</span>
                          <button class="secondary sm" disabled={managedWorkspaceServicePage >= managedWorkspaceServicePageCount - 1} onclick={() => (managedWorkspaceServicePage = Math.min(managedWorkspaceServicePageCount - 1, managedWorkspaceServicePage + 1))}>Next</button>
                        </div>
                      {/if}
                      <div class="workspace-detail-actions">
                        <button class="secondary" onclick={() => doPortableExport("workspace", `workspace ${selectedWorkspaceName}`, workspacePortablePayload(selectedWorkspaceId))}>Export workspace…</button>
                        <button class="secondary danger-button" onclick={deleteManagedWorkspace}>Delete workspace</button>
                      </div>
                    </div>
                  </div>
                </section>
              {:else}
                <section class="settings-section" aria-labelledby="settings-workspaces-startup">
                  <div class="section-heading">
                    <h3 id="settings-workspaces-startup">Startup workspace</h3>
                    <p>Choose which workspace Tauridium opens after restoring a session. Last-workspace restore takes precedence; the default remains the fallback if that workspace no longer exists.</p>
                  </div>
                  <div class="settings-list">
                    <div class="setting-card">
                      <div class="setting-copy">
                        <span class="setting-label">Default workspace</span>
                        <span class="setting-description">Used at startup when restoring the last workspace is disabled, or when the remembered workspace is unavailable.</span>
                      </div>
                      <select
                        class="select setting-control workspace-startup-select"
                        aria-label="Default workspace"
                        bind:value={appSettings.defaultWorkspaceId}
                        onchange={() => saveAppSetting("defaultWorkspaceId", appSettings.defaultWorkspaceId)}
                      >
                        <option value="">All services</option>
                        {#each sortedWorkspaces as workspace (workspace.id)}
                          <option value={workspace.id}>{workspace.name}</option>
                        {/each}
                      </select>
                    </div>
                    <label class="setting-card setting-card-toggle">
                      <span class="setting-copy">
                        <span class="setting-label">Restore last workspace on startup</span>
                        <span class="setting-description">Start with the workspace that was active most recently. Enabling this remembers the workspace active right now.</span>
                      </span>
                      <span class="switch-control">
                        <input
                          class="switch-input"
                          type="checkbox"
                          checked={appSettings.restoreLastWorkspaceOnStartup}
                          aria-label="Restore last workspace on startup"
                          onchange={(event) => saveRestoreLastWorkspaceOnStartup(event.currentTarget.checked)}
                        />
                        <span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>
                      </span>
                    </label>
                  </div>
                </section>

                <section class="settings-section" aria-labelledby="settings-workspaces-switcher">
                  <div class="section-heading">
                    <h3 id="settings-workspaces-switcher">Quick workspace switcher</h3>
                    <p>Choose how Ctrl+D orders workspaces. “All services” always remains first so you can leave a workspace filter quickly.</p>
                  </div>
                  <div class="settings-list">
                    <div class="setting-card">
                      <div class="setting-copy">
                        <span class="setting-label">Workspace switch order</span>
                        <span class="setting-description">Custom order is managed below. Recent modes use the last time each workspace was selected.</span>
                      </div>
                      <select
                        class="select setting-control workspace-order-select"
                        aria-label="Workspace switch order"
                        bind:value={appSettings.workspaceQuickSwitchOrder}
                        onchange={() => saveAppSetting("workspaceQuickSwitchOrder", appSettings.workspaceQuickSwitchOrder)}
                      >
                        <option value="custom">Custom</option>
                        <option value="customReverse">Custom — reverse</option>
                        <option value="alphabetical">Alphabetical — A to Z</option>
                        <option value="alphabeticalReverse">Alphabetical — Z to A</option>
                        <option value="recent">Most recently used</option>
                        <option value="recentReverse">Least recently used</option>
                      </select>
                    </div>
                    <div class="setting-card">
                      <div class="setting-copy">
                        <span class="setting-label">Workspace usage history</span>
                        <span class="setting-description">Clear remembered workspace-use times without changing custom ordering or membership.</span>
                      </div>
                      <button class="secondary" disabled={Object.keys(appSettings.workspaceLastUsed).length === 0} onclick={resetWorkspaceUsageHistory}>Reset history</button>
                    </div>
                  </div>
                </section>

                <section class="settings-section" aria-labelledby="settings-workspaces-configured">
                  <div class="section-heading">
                    <h3 id="settings-workspaces-configured">Configured workspaces <span class="section-count">{workspaces.length}</span></h3>
                    <p>Create, search, reorder, export, and manage workspace membership. Reordering a filtered result moves only the matching workspace slots in the canonical custom order.</p>
                  </div>
                  <div class="managed-toolbar workspace-managed-toolbar">
                    <input
                      class="setting-text-input"
                      type="search"
                      placeholder="Search configured workspaces…"
                      bind:value={managedWorkspaceQuery}
                      oninput={() => (managedWorkspacePage = 0)}
                      aria-label="Search configured workspaces"
                    />
                    <button class="secondary" disabled={!sortedWorkspaces.length} onclick={() => doPortableExport("workspaces", "all workspaces", workspacePortablePayload())}>Export all…</button>
                  </div>
                  <div class="workspace-create-row">
                    <input class="setting-text-input" bind:value={newWorkspaceName} maxlength="80" placeholder="New workspace name" aria-label="New workspace name" />
                    <button class="primary" disabled={!newWorkspaceName.trim()} onclick={handleCreateWorkspace}>Create workspace</button>
                  </div>
                  {#if portableExportStatus}<p class="settings-status">{portableExportStatus}</p>{/if}
                  <div class="managed-list" role="list" aria-label="Configured workspaces">
                    {#each managedWorkspaceRows as workspace, index (workspace.id)}
                      <div class="managed-row" class:selected={managedWorkspaceId === workspace.id} role="listitem">
                        <div class="managed-identity workspace-managed-identity">
                          {#if workspaceIcon(workspace) && !failedWorkspaceIcons.has(workspace.id)}
                            <img class="workspace-avatar workspace-avatar-image" src={workspaceIcon(workspace) ?? ""} alt="" onerror={() => markWorkspaceIconFailed(workspace.id)} />
                          {:else}
                            <span class="workspace-avatar" aria-hidden="true">{workspace.name.slice(0, 1).toUpperCase()}</span>
                          {/if}
                          <div class="managed-copy">
                            <strong>{workspace.name}</strong>
                            <span>{workspace.services.length} service{workspace.services.length === 1 ? "" : "s"}</span>
                          </div>
                        </div>
                        <div class="managed-actions">
                          <button class="icon-button compact" disabled={managedWorkspacePage * MANAGED_SERVICE_PAGE_SIZE + index === 0} aria-label={`Move ${workspace.name} up`} title="Move up" onclick={() => moveManagedWorkspace(workspace.id, -1)}>↑</button>
                          <button class="icon-button compact" disabled={managedWorkspacePage * MANAGED_SERVICE_PAGE_SIZE + index === managedWorkspaces.length - 1} aria-label={`Move ${workspace.name} down`} title="Move down" onclick={() => moveManagedWorkspace(workspace.id, 1)}>↓</button>
                          <button class="secondary sm" onclick={() => manageWorkspace(workspace)}>Workspace settings</button>
                        </div>
                      </div>
                    {:else}
                      <div class="managed-empty">
                        <strong>{workspaces.length ? "No workspaces match this search" : "No workspaces configured"}</strong>
                        <span>{workspaces.length ? "Change the search to see more workspaces." : "Create a workspace above, then add services to it."}</span>
                      </div>
                    {/each}
                  </div>
                  {#if managedWorkspaces.length > MANAGED_SERVICE_PAGE_SIZE}
                    <div class="pagination" aria-label="Configured workspace pages">
                      <button class="secondary sm" disabled={managedWorkspacePage === 0} onclick={() => (managedWorkspacePage = Math.max(0, managedWorkspacePage - 1))}>Previous</button>
                      <span>Page {managedWorkspacePage + 1} of {managedWorkspacePageCount} · {managedWorkspaces.length} workspaces</span>
                      <button class="secondary sm" disabled={managedWorkspacePage >= managedWorkspacePageCount - 1} onclick={() => (managedWorkspacePage = Math.min(managedWorkspacePageCount - 1, managedWorkspacePage + 1))}>Next</button>
                    </div>
                  {/if}
                </section>
              {/if}
            {:else if settingsTab === "appearance"}
              <section class="settings-section" aria-labelledby="settings-appearance-app">
                <div class="section-heading">
                  <h3 id="settings-appearance-app">App appearance</h3>
                  <p>Choose the color scheme and accent used by Tauridium's own interface.</p>
                </div>
                <div class="settings-list">
                  <div class="setting-card">
                    <div class="setting-copy">
                      <span class="setting-label">Theme</span>
                      <span class="setting-description">Follow the operating system appearance or force Light, Dark, or true-black Black OLED mode.</span>
                    </div>
                    <select class="select setting-control" aria-label="Theme" bind:value={appSettings.theme} onchange={() => saveAppSetting("theme", appSettings.theme)}>
                      <option value="system">Use system setting</option>
                      <option value="dark">Dark</option>
                      <option value="oled">Black OLED</option>
                      <option value="light">Light</option>
                    </select>
                  </div>
                  <div class="setting-card setting-card-stack accent-setting-card">
                    <div class="setting-copy">
                      <span class="setting-label">Accent color</span>
                      <span class="setting-description">Used for selected navigation, primary actions, and active-service emphasis.</span>
                    </div>
                    <div class="accent-picker-control">
                      <div class="swatches" role="group" aria-label="Accent color presets">
                        {#each ["#ffc131", "#4f46e5", "#2563eb", "#0891b2", "#16a34a", "#d97706", "#dc2626", "#db2777", "#7c3aed"] as c (c)}
                          <button class="swatch" class:on={appSettings.accentColor === c} style="background:{c}" aria-label={`Use accent color ${c}`} aria-pressed={appSettings.accentColor === c} onclick={() => saveAppSetting("accentColor", c)}></button>
                        {/each}
                        {#each appSettings.customAccentColors as c (c)}
                          <span class="custom-swatch-wrap">
                            <button class="swatch" class:on={appSettings.accentColor === c} style="background:{c}" aria-label={`Use custom accent color ${c}`} aria-pressed={appSettings.accentColor === c} onclick={() => saveAppSetting("accentColor", c)}></button>
                            <button class="swatch-remove" aria-label={`Remove custom accent ${c}`} title="Remove preset" onclick={() => removeCustomAccent(c)}>×</button>
                          </span>
                        {/each}
                      </div>
                      <button class="secondary sm accent-custom-button" onclick={openCustomColorPicker}>Custom…</button>
                    </div>
                  </div>
                  {#if customColorOpen}
                    <div class="setting-card setting-card-stack color-picker-card">
                      <div class="setting-copy"><span class="setting-label">Custom accent</span><span class="setting-description">Use the platform color picker or adjust hue, saturation, and lightness with keyboard-accessible sliders.</span></div>
                      <div class="color-picker-preview-row">
                        <input type="color" value={appSettings.accentColor} aria-label="Custom accent native color picker" oninput={(event) => setCustomColorFromNative(event.currentTarget.value)} />
                        <code>{appSettings.accentColor}</code>
                        <span class="color-preview" style={`background:${appSettings.accentColor}`} aria-hidden="true"></span>
                      </div>
                      <label class="slider-field"><span>Hue <strong>{Math.round(colorHue)}°</strong></span><input type="range" min="0" max="359" value={colorHue} oninput={(event) => { colorHue = Number(event.currentTarget.value); previewCustomColor(); }} /></label>
                      <label class="slider-field"><span>Saturation <strong>{Math.round(colorSaturation)}%</strong></span><input type="range" min="0" max="100" value={colorSaturation} oninput={(event) => { colorSaturation = Number(event.currentTarget.value); previewCustomColor(); }} /></label>
                      <label class="slider-field"><span>Lightness <strong>{Math.round(colorLightness)}%</strong></span><input type="range" min="10" max="90" value={colorLightness} oninput={(event) => { colorLightness = Number(event.currentTarget.value); previewCustomColor(); }} /></label>
                      <div class="setting-actions"><button class="secondary sm" onclick={cancelCustomColorPicker}>Cancel</button><button class="secondary sm" onclick={() => applyCustomColor(false)}>Use color</button><button class="primary sm" onclick={() => applyCustomColor(true)}>Use & save preset</button></div>
                    </div>
                  {/if}
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-appearance-titles">
                <div class="section-heading">
                  <h3 id="settings-appearance-titles">Native titles</h3>
                  <p>Show workspace context in operating-system window and app-icon labels.</p>
                </div>
                <div class="settings-list">
                  {@render appToggle("Workspace in window title", "Show the selected workspace in the native title bar, for example Tauridium ~ Engineering.", "showWorkspaceInWindowTitle", appSettings.showWorkspaceInWindowTitle)}
                  {@render appToggle("Workspace in taskbar title", `Use workspace context for a separately addressable ${dockWord} or app-icon label when the operating system exposes one. Windows taskbar buttons always mirror the native window title; independent taskbar titles are unsupported on Windows.`, "showWorkspaceInTaskbarTitle", appSettings.showWorkspaceInTaskbarTitle)}
                  {@render appToggle("Custom title templates", "Enable variable-based title formats for the window title and taskbar/app-icon title. The two workspace-title toggles still decide which destinations use the custom format.", "customTitleTemplatesEnabled", appSettings.customTitleTemplatesEnabled)}
                  {#if appSettings.customTitleTemplatesEnabled}
                    <div class="setting-card setting-card-stack">
                      <div class="setting-copy">
                        <span class="setting-label">Window title template</span>
                        <span class="setting-description">Available variables: {"{app}"}, {"{workspace}"}, {"{service}"}. Unknown text is preserved literally.</span>
                      </div>
                      <input
                        class="input setting-text-input"
                        aria-label="Window title template"
                        maxlength="240"
                        bind:value={appSettings.windowTitleTemplate}
                        onchange={() => saveAppSetting("windowTitleTemplate", appSettings.windowTitleTemplate)}
                      />
                      <span class="settings-note">Preview: {renderTitleTemplate(appSettings.windowTitleTemplate, { app: "Tauridium", workspace: activeWorkspaceName, service: activeService ? serviceLabel(activeService) : "No service" })}</span>
                    </div>
                    <div class="setting-card setting-card-stack">
                      <div class="setting-copy">
                        <span class="setting-label">Taskbar title template</span>
                        <span class="setting-description">Used where the OS exposes a separate taskbar/app-icon label. Windows taskbar buttons always mirror the native window title.</span>
                      </div>
                      <input
                        class="input setting-text-input"
                        aria-label="Taskbar title template"
                        maxlength="240"
                        bind:value={appSettings.taskbarTitleTemplate}
                        onchange={() => saveAppSetting("taskbarTitleTemplate", appSettings.taskbarTitleTemplate)}
                      />
                      <span class="settings-note">Preview: {renderTitleTemplate(appSettings.taskbarTitleTemplate, { app: "Tauridium", workspace: activeWorkspaceName, service: activeService ? serviceLabel(activeService) : "No service" })}</span>
                    </div>
                    <p class="settings-note">Variables: <code>{"{app}"}</code> application name, <code>{"{workspace}"}</code> selected workspace (or All services), <code>{"{service}"}</code> active service (or No service).</p>
                  {/if}
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-appearance-sidebar">
                <div class="section-heading">
                  <h3 id="settings-appearance-sidebar">Sidebar</h3>
                  <p>Adjust service density and placement without changing individual service configuration.</p>
                </div>
                <div class="settings-list">
                  {@render appToggle("Collapse sidebar", "Use the compact icon-only rail now. The expanded width is preserved and restored when reopened. Default shortcut: Ctrl+Shift+B.", "sidebarCollapsed", appSettings.sidebarCollapsed)}
                  <div class="setting-card">
                    <div class="setting-copy">
                      <span class="setting-label">Default sidebar state</span>
                      <span class="setting-description">Used at startup when restoring the last sidebar state is disabled.</span>
                    </div>
                    <select
                      class="select setting-control"
                      aria-label="Default sidebar state"
                      value={appSettings.defaultSidebarCollapsed ? "collapsed" : "expanded"}
                      onchange={(event) => saveAppSetting("defaultSidebarCollapsed", event.currentTarget.value === "collapsed")}
                    >
                      <option value="expanded">Expanded</option>
                      <option value="collapsed">Collapsed</option>
                    </select>
                  </div>
                  <label class="setting-card setting-card-toggle">
                    <span class="setting-copy">
                      <span class="setting-label">Restore last sidebar state on startup</span>
                      <span class="setting-description">Start with the sidebar state used most recently. When enabled, this takes precedence over the default sidebar state.</span>
                    </span>
                    <span class="switch-control">
                      <input
                        class="switch-input"
                        type="checkbox"
                        checked={appSettings.restoreLastSidebarStateOnStartup}
                        aria-label="Restore last sidebar state on startup"
                        onchange={(event) => saveRestoreLastSidebarStateOnStartup(event.currentTarget.checked)}
                      />
                      <span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>
                    </span>
                  </label>
                  <div class="setting-card setting-card-stack">
                    <div class="setting-copy"><span class="setting-label">Expanded sidebar width</span><span class="setting-description">Use a fixed pixel width or keep the expanded sidebar proportional to the Tauridium window. Collapsed mode uses a fixed 52 px rail for consistent icon alignment.</span></div>
                    <select class="select setting-control" aria-label="Sidebar width mode" value={appSettings.sidebarWidthMode} onchange={(event) => saveAppSetting("sidebarWidthMode", event.currentTarget.value)}>
                      <option value="pixels">Fixed pixels</option>
                      <option value="percent">Relative to window</option>
                    </select>
                    {#if appSettings.sidebarWidthMode === "pixels"}
                      <div class="sidebar-width-control">
                        <input class="range" type="range" min="160" max="420" step="2" value={appSettings.sidebarWidth} aria-label="Sidebar width in pixels" oninput={(event) => previewSidebarWidth(Number(event.currentTarget.value))} onchange={() => saveAppSetting("sidebarWidth", appSettings.sidebarWidth)} />
                        <output>{Math.round(appSettings.sidebarWidth)} px</output>
                      </div>
                      <div class="preset-row" role="group" aria-label="Sidebar width presets">
                        <button class="secondary sm" class:on={appSettings.sidebarWidth === 180} onclick={() => saveAppSetting("sidebarWidth", 180)}>Slim · 180</button>
                        <button class="secondary sm" class:on={appSettings.sidebarWidth === 240} onclick={() => saveAppSetting("sidebarWidth", 240)}>Normal · 240</button>
                        <button class="secondary sm" class:on={appSettings.sidebarWidth === 320} onclick={() => saveAppSetting("sidebarWidth", 320)}>Wide · 320</button>
                        {#each appSettings.customSidebarWidths as width (width)}
                          <span class="preset-chip"><button class="secondary sm" class:on={appSettings.sidebarWidth === width} onclick={() => saveAppSetting("sidebarWidth", width)}>{width} px</button><button class="preset-remove" aria-label={`Remove ${width} pixel sidebar preset`} onclick={() => removeSidebarPreset(width)}>×</button></span>
                        {/each}
                        <button class="secondary sm" disabled={[180, 240, 320, ...appSettings.customSidebarWidths].includes(Math.round(appSettings.sidebarWidth))} onclick={saveCurrentSidebarPreset}>Save current preset</button>
                      </div>
                    {:else}
                      <div class="sidebar-width-control">
                        <input class="range" type="range" min="10" max="40" step="1" value={appSettings.sidebarWidthPercent} aria-label="Sidebar width as percentage of window" oninput={(event) => { appSettings.sidebarWidthPercent = Number(event.currentTarget.value); syncSidebarWidth(); }} onchange={() => saveAppSetting("sidebarWidthPercent", appSettings.sidebarWidthPercent)} />
                        <output>{Math.round(appSettings.sidebarWidthPercent)}%</output>
                      </div>
                      <p class="settings-note">Relative mode recalculates the service viewport while the window is resized. Updates are animation-frame throttled to avoid unnecessary layout work.</p>
                    {/if}
                  </div>
                  <div class="setting-card setting-card-stack">
                    <div class="setting-copy"><span class="setting-label">Collapsed icon spacing</span><span class="setting-description">Increase the vertical space between icon-only service targets. The current compact 2 px spacing is the minimum.</span></div>
                    <div class="sidebar-width-control">
                      <input class="range" type="range" min="2" max="24" step="1" value={appSettings.collapsedServiceSpacing} aria-label="Collapsed service icon spacing" oninput={(event) => previewServiceSpacing("collapsedServiceSpacing", Number(event.currentTarget.value), true)} onchange={() => saveServiceSpacing("collapsedServiceSpacing", true)} />
                      <output>{Math.round(appSettings.collapsedServiceSpacing)} px</output>
                    </div>
                  </div>
                  <div class="setting-card setting-card-stack">
                    <div class="setting-copy"><span class="setting-label">Expanded service spacing</span><span class="setting-description">Increase the vertical space between service rows in the expanded sidebar. The current compact 2 px spacing is the minimum.</span></div>
                    <div class="sidebar-width-control">
                      <input class="range" type="range" min="2" max="24" step="1" value={appSettings.expandedServiceSpacing} aria-label="Expanded service item spacing" oninput={(event) => previewServiceSpacing("expandedServiceSpacing", Number(event.currentTarget.value), false)} onchange={() => saveServiceSpacing("expandedServiceSpacing", false)} />
                      <output>{Math.round(appSettings.expandedServiceSpacing)} px</output>
                    </div>
                  </div>
                  <div class="setting-card">
                    <div class="setting-copy"><span class="setting-label">Service icon size</span><span class="setting-description">Change icon size while preserving consistent sidebar spacing.</span></div>
                    <select class="select setting-control" aria-label="Service icon size" bind:value={appSettings.iconSize} onchange={() => saveAppSetting("iconSize", appSettings.iconSize)}>
                      <option value={18}>Very small</option><option value={21}>Small</option><option value={24}>Normal</option><option value={28}>Large</option><option value={34}>Very large</option>
                    </select>
                  </div>
                  <div class="setting-card">
                    <div class="setting-copy"><span class="setting-label">Service list alignment</span><span class="setting-description">Align the service list to the top, center, or bottom of the sidebar.</span></div>
                    <select class="select setting-control" aria-label="Service list alignment" bind:value={appSettings.sidebarServicesLocation} onchange={() => saveAppSetting("sidebarServicesLocation", appSettings.sidebarServicesLocation)}>
                      <option value="top">Top</option><option value="center">Center</option><option value="bottom">Bottom</option>
                    </select>
                  </div>
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-appearance-icons">
                <div class="section-heading"><h3 id="settings-appearance-icons">Service icons</h3><p>Reduce visual noise while keeping the active service easy to identify.</p></div>
                <div class="settings-list">
                  {@render appToggle("Grayscale inactive icons", "Show service icons in grayscale until they are hovered or active.", "grayscaleServices", appSettings.grayscaleServices)}
                  {#if appSettings.grayscaleServices}
                    <div class="setting-card">
                      <div class="setting-copy"><span class="setting-label">Inactive icon dimming</span><span class="setting-description">Control how strongly inactive grayscale icons are dimmed.</span></div>
                      <div class="range-control"><input class="range" type="range" min="0" max="100" value={appSettings.grayscaleDim} aria-label="Inactive icon dimming" onchange={(e) => saveAppSetting("grayscaleDim", Number(e.currentTarget.value))} /><span>{appSettings.grayscaleDim}%</span></div>
                    </div>
                  {/if}
                </div>
              </section>
            {:else if settingsTab === "keybindings"}
              <section class="settings-section" aria-labelledby="settings-keybindings-main">
                <div class="section-heading"><h3 id="settings-keybindings-main">Keybindings</h3><p>Customize application navigation. Bindings may be a single shortcut or a two-stroke chord such as Ctrl+K Ctrl+S. Letter keys are shown as uppercase key labels; Shift is required only when <strong>Shift</strong> is explicitly present. Press Delete while recording to clear a binding.</p></div>
                <div class="settings-list keybinding-list">
                  {#each [
                    ["quickWorkspaceSwitch", "Quick workspace switcher", "Search and switch workspaces."],
                    ["quickServiceSwitch", "Quick service search", "Search and switch services in the active workspace."],
                    ["openSettings", "Open Settings", "Open Tauridium application settings."],
                    ["addService", "Add service", "Open the add-service screen."],
                    ["addWorkspace", "Add workspace", "Create a new workspace."],
                    ["toggleSidebar", "Toggle sidebar", "Collapse to the icon-only rail or restore the expanded sidebar."],
                    ["nextService", "Next service", "Move to the next enabled service."],
                    ["previousService", "Previous service", "Move to the previous enabled service."],
                    ["nextWorkspace", "Next workspace", "Move to the next workspace."],
                    ["previousWorkspace", "Previous workspace", "Move to the previous workspace."],
                    ["reloadService", "Reload service", "Reload the active service webview."],
                    ["reloadApp", "Reload Tauridium", "Reload the Tauridium shell."],
                    ["toggleDevtools", "Toggle Developer Tools", "Open or close developer tools for the active service."]
                  ] as [action, label, description] (action)}
                    {@const binding = appSettings.keybindings[action] ?? ""}
                    {@const conflict = keybindingConflicts.get(bindingStrokes(binding).join(" "))}
                    <div class="setting-card keybinding-card">
                      <div class="setting-copy"><span class="setting-label">{label}</span><span class="setting-description">{description}{#if conflict}<span class="keybinding-conflict"> Conflicts with another action.</span>{/if}</span></div>
                      <div class="keybinding-control">
                        <kbd>{recordingAction === action ? (recordingStrokes.length ? `${recordingStrokes.join(" ")} …` : "Press shortcut…") : (binding || "Unassigned")}</kbd>
                        <button class="secondary sm" aria-pressed={recordingAction === action} onclick={() => beginRecording(action as KeybindingAction)}>{recordingAction === action ? "Recording" : "Record"}</button>
                        <button class="link" disabled={!binding} onclick={() => saveKeybinding(action as KeybindingAction, "")}>Clear</button>
                      </div>
                    </div>
                  {/each}
                </div>
                <div class="setting-actions"><button class="secondary" onclick={() => saveAppSetting("keybindings", { ...DEFAULT_KEYBINDINGS })}>Restore defaults</button></div>
              </section>
            {:else if settingsTab === "sandbox"}
              <section class="settings-section" aria-labelledby="settings-sandbox-groups">
                <div class="section-heading"><h3 id="settings-sandbox-groups">Shared sandboxes</h3><p>Services assigned to the same sandbox use the same persistent webview data store, allowing compatible services to share login sessions and caches. Unassigned services remain isolated.</p></div>
                <div class="sandbox-create-row"><input class="setting-text-input" bind:value={newSandboxName} maxlength="80" placeholder="New sandbox name, e.g. Proton" aria-label="New sandbox name" /><button class="primary" disabled={!newSandboxName.trim()} onclick={createSandboxGroup}>Create sandbox</button></div>
                <div class="setting-actions sandbox-export-actions"><button class="secondary sm" disabled={!appSettings.sandboxes.length} onclick={() => doPortableExport("sandboxes", "all sandboxes", sandboxPortablePayload())}>Export all sandboxes…</button></div>
                {#if portableExportStatus}<p class="settings-status">{portableExportStatus}</p>{/if}
                <div class="settings-list">
                  {#each appSettings.sandboxes as sandbox (sandbox.id)}
                    <div class="setting-card sandbox-card">
                      <div class="setting-copy">
                        <input class="setting-text-input sandbox-name" value={sandbox.name} maxlength="80" aria-label={`Sandbox name ${sandbox.name}`} onchange={(event) => renameSandboxGroup(sandbox.id, event.currentTarget.value)} />
                        <span class="setting-description">{Object.values(appSettings.serviceSandboxes).filter((value) => value === sandbox.id).length} assigned service(s)</span>
                      </div>
                      <div class="setting-actions"><button class="secondary sm" onclick={() => doPortableExport("sandbox", `sandbox ${sandbox.name}`, sandboxPortablePayload(sandbox.id))}>Export…</button><button class="secondary sm" onclick={() => clearSandboxGroup(sandbox)}>Clear session</button><button class="link danger-link" onclick={() => deleteSandboxGroup(sandbox)}>Delete</button></div>
                    </div>
                  {:else}
                    <div class="managed-empty"><strong>No shared sandboxes</strong><span>Create one, then assign two or more compatible services below.</span></div>
                  {/each}
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-sandbox-services">
                <div class="section-heading"><h3 id="settings-sandbox-services">Service assignments <span class="section-count">{services.length}</span></h3><p>Changing an assignment closes only that service webview and recreates it using the selected data store.</p></div>
                <input class="setting-text-input" type="search" bind:value={sandboxServiceQuery} oninput={() => (sandboxServicePage = 0)} placeholder="Search services…" aria-label="Search sandbox service assignments" />
                <div class="managed-list" role="list" aria-label="Sandbox service assignments">
                  {#each sandboxServiceRows as service (service.id)}
                    <div class="managed-row" role="listitem">
                      <div class="managed-copy"><strong>{serviceLabel(service)}</strong><span>{service.recipeId}</span></div>
                      <select class="select sandbox-select" value={serviceSandboxId(service.id) ?? ""} disabled={sandboxAssignmentBusy} aria-label={`Sandbox for ${serviceLabel(service)}`} onchange={(event) => assignServiceSandbox(service.id, event.currentTarget.value)}>
                        <option value="">Isolated</option>
                        {#each appSettings.sandboxes as sandbox (sandbox.id)}<option value={sandbox.id}>{sandbox.name}</option>{/each}
                      </select>
                    </div>
                  {:else}<div class="managed-empty"><strong>No services match</strong><span>Change the search text.</span></div>{/each}
                </div>
                {#if sandboxServices.length > MANAGED_SERVICE_PAGE_SIZE}
                  <div class="pagination"><button class="secondary sm" disabled={sandboxServicePage === 0} onclick={() => (sandboxServicePage = Math.max(0, sandboxServicePage - 1))}>Previous</button><span>Page {sandboxServicePage + 1} of {sandboxServicePageCount}</span><button class="secondary sm" disabled={sandboxServicePage >= sandboxServicePageCount - 1} onclick={() => (sandboxServicePage = Math.min(sandboxServicePageCount - 1, sandboxServicePage + 1))}>Next</button></div>
                {/if}
              </section>
            {:else if settingsTab === "privacy"}
              <section class="settings-section" aria-labelledby="settings-privacy-notifications">
                <div class="section-heading"><h3 id="settings-privacy-notifications">Notifications</h3><p>Limit message information exposed through operating-system notifications.</p></div>
                <div class="settings-list">{@render appToggle("Private notifications", "Hide sender and message content and show only a generic new-message notification.", "privateNotifications", appSettings.privateNotifications)}</div>
              </section>
            {:else if settingsTab === "backup"}
              <section class="settings-section" aria-labelledby="settings-backup-manual">
                <div class="section-heading"><h3 id="settings-backup-manual">Manual backup</h3><p>Export or restore Tauridium-owned configuration using a versioned, integrity-verified backup file.</p></div>
                <div class="settings-list">
                  <div class="setting-card">
                    <div class="setting-copy"><span class="setting-label">Tauridium data</span><span class="setting-description">Exports app settings, canonical service/workspace order, local services and workspaces, and complete custom recipes. Restore validates every component before committing. Ferdium login tokens, website cookies/storage, remote caches, and machine-specific monitor geometry are excluded.</span></div>
                    <div class="setting-actions"><button class="secondary sm" disabled={backupBusy} onclick={doRestoreBackup}>Restore backup…</button><button class="primary sm" disabled={backupBusy} onclick={doExportBackup}>Export backup…</button></div>
                  </div>
                  <p class="settings-note">Backups can contain sensitive local service configuration such as proxy credentials. Store them accordingly.</p>
                  {#if backupStatus}<p class="settings-status">{backupStatus}</p>{/if}
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-backup-automatic">
                <div class="section-heading"><h3 id="settings-backup-automatic">Automatic backup</h3><p>Create integrity-verified recovery copies on a schedule or on demand, then prune only after the new backup has been reread and verified.</p></div>
                <div class="settings-list">
                  <div class="setting-card">
                    <div class="setting-copy"><span class="setting-label">Schedule</span><span class="setting-description">Choose when Tauridium creates automatic backups while it is running.</span></div>
                    <select class="setting-control" aria-label="Automatic backup schedule" value={appSettings.automaticBackupSchedule} onchange={(e) => saveAppSetting("automaticBackupSchedule", e.currentTarget.value)}><option value="off">Off</option><option value="startup">On program startup</option><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select>
                  </div>
                  <div class="setting-card setting-card-stack">
                    <div class="setting-copy"><span class="setting-label">Output folder</span><span class="setting-description">Choose the folder used for scheduled and on-demand automatic backups. Leave unset to use Tauridium's managed configuration folder.</span></div>
                    <div class="backup-location-row">
                      <code title={appSettings.automaticBackupDirectory || "Tauridium configuration/backups/automatic (default)"}>{appSettings.automaticBackupDirectory || "Tauridium configuration/backups/automatic (default)"}</code>
                      <div class="setting-actions"><button class="secondary sm" onclick={chooseAutomaticBackupDirectory}>Choose folder…</button><button class="secondary sm" disabled={!appSettings.automaticBackupDirectory} onclick={useDefaultAutomaticBackupDirectory}>Use default</button></div>
                    </div>
                  </div>
                  <div class="setting-card">
                    <div class="setting-copy"><span class="setting-label">Retention strategy</span><span class="setting-description">Choose a simple count, age limit, both limits together, or tiered GFS-style history.</span></div>
                    <select class="setting-control" aria-label="Automatic backup retention strategy" value={appSettings.automaticBackupRetentionMode} onchange={(e) => saveAppSetting("automaticBackupRetentionMode", e.currentTarget.value)}>
                      <option value="count">Newest backup count</option>
                      <option value="age">Maximum age</option>
                      <option value="countAndAge">Count and maximum age</option>
                      <option value="tiered">Tiered history (GFS-style)</option>
                    </select>
                  </div>
                  {#if appSettings.automaticBackupRetentionMode === "count" || appSettings.automaticBackupRetentionMode === "countAndAge"}
                    <div class="setting-card">
                      <div class="setting-copy"><span class="setting-label">Newest backups to keep</span><span class="setting-description">Always keep at least the newest verified automatic backup.</span></div>
                      <input class="setting-number" type="number" min="1" max="365" value={appSettings.automaticBackupRetention} aria-label="Automatic backup count retention" onchange={(e) => saveAppSetting("automaticBackupRetention", Math.max(1, Math.min(365, Number(e.currentTarget.value) || 1)))} />
                    </div>
                  {/if}
                  {#if appSettings.automaticBackupRetentionMode === "age" || appSettings.automaticBackupRetentionMode === "countAndAge"}
                    <div class="setting-card">
                      <div class="setting-copy"><span class="setting-label">Maximum backup age</span><span class="setting-description">Delete automatic backups older than this many days after a new verified backup exists. The newest verified backup is never removed solely because of age.</span></div>
                      <div class="number-with-unit"><input class="setting-number" type="number" min="1" max="3650" value={appSettings.automaticBackupMaxAgeDays} aria-label="Automatic backup maximum age in days" onchange={(e) => saveAppSetting("automaticBackupMaxAgeDays", Math.max(1, Math.min(3650, Number(e.currentTarget.value) || 1)))} /><span>days</span></div>
                    </div>
                  {/if}
                  {#if appSettings.automaticBackupRetentionMode === "tiered"}
                    <div class="setting-card info-card">
                      <div class="setting-copy"><span class="setting-label">Tiered history</span><span class="setting-description">Keeps one representative per recent day, then progressively one per week, calendar month, and calendar year for up to about five years. This is a GFS-style retention pattern; using one folder does not by itself satisfy a 3-2-1 backup strategy.</span></div>
                      <span class="status-badge">Daily → weekly → monthly → yearly</span>
                    </div>
                  {/if}
                  <div class="setting-actions"><button class="primary sm" disabled={backupBusy || automaticBackupRunning} onclick={runAutomaticBackupNow}>Back up now</button></div>
                  <p class="settings-note">Retention cleanup runs only after the newly written backup has been staged, flushed, reread, parsed, and integrity-verified.</p>
                </div>
              </section>
            {:else if settingsTab === "audit"}
              <section class="settings-section" aria-labelledby="settings-audit-log">
                <div class="section-heading"><h3 id="settings-audit-log">Audit log</h3><p>Review application-setting changes, backup exports/restores, scheduled backups, portable exports, warnings, and failures. Secret-like fields are redacted before persistence.</p></div>
                <div class="audit-toolbar">
                  <input class="setting-text-input" type="search" bind:value={auditQuery} placeholder="Search audit events…" aria-label="Search audit events" />
                  <select class="select" bind:value={auditLevel} aria-label="Filter audit events by level"><option value="all">All levels</option><option value="info">Info</option><option value="warning">Warnings</option><option value="error">Errors</option></select>
                  <button class="secondary sm" disabled={auditBusy} onclick={refreshAuditLog}>Refresh</button>
                  <button class="secondary sm" disabled={auditBusy || !auditEntries.length} onclick={doExportAuditLog}>Export…</button>
                  <button class="secondary sm" disabled={auditBusy || !auditEntries.length} onclick={doClearAuditLog}>Clear…</button>
                </div>
                {#if auditStatus}<p class="settings-status">{auditStatus}</p>{/if}
                <div class="audit-list" role="list" aria-label="Tauridium audit events">
                  {#each filteredAuditEntries as entry}
                    <article class="audit-entry" class:audit-warning={entry.level === "warning"} class:audit-error={entry.level === "error"} role="listitem">
                      <div class="audit-entry-head"><time datetime={new Date(entry.timestampUnixMs).toISOString()}>{new Date(entry.timestampUnixMs).toLocaleString()}</time><span class="audit-level">{entry.level}</span><span>{entry.category} · {entry.action} · {entry.outcome}</span></div>
                      <strong>{entry.message}</strong>
                      {#if entry.details && JSON.stringify(entry.details) !== "{}"}<pre>{JSON.stringify(entry.details, null, 2)}</pre>{/if}
                    </article>
                  {:else}
                    <div class="managed-empty"><strong>No matching audit events</strong><span>Change the filter or refresh the log.</span></div>
                  {/each}
                </div>
                <p class="settings-note">Audit files rotate locally when they grow large. The UI loads the latest 5,000 events; exported JSONL preserves chronological order.</p>
              </section>

            {:else if settingsTab === "advanced"}
              <section class="settings-section" aria-labelledby="settings-advanced-instances">
                <div class="section-heading"><h3 id="settings-advanced-instances">Application instances</h3><p>Control what happens when Tauridium is launched again while it is already running.</p></div>
                <div class="settings-list">
                  {@render appToggle("Reuse existing session on launch", "Enabled by default on Windows. Starting Tauridium.exe again reopens and focuses the existing session, including when it is hidden in the tray, instead of creating another Tauridium process and tray icon. Disable this to allow multiple independent Tauridium instances.", "reuseExistingSessionOnLaunch", appSettings.reuseExistingSessionOnLaunch)}
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-advanced-context-menu">
                <div class="section-heading"><h3 id="settings-advanced-context-menu">Service context menu</h3><p>Choose between Tauridium's original styled menu and the native fallback that always stays above service webviews.</p></div>
                <div class="settings-list">
                  {@render appToggle("Use original service context menu", "Enabled by default. Uses Tauridium's original styled right-click menu. Embedded service webviews can cover the part of this shell menu that extends over them. Disable this to use the native system menu, which always stays in front.", "prettyServiceContextMenu", appSettings.prettyServiceContextMenu)}
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-advanced-sidebar-order">
                <div class="section-heading"><h3 id="settings-advanced-sidebar-order">Sidebar service ordering</h3><p>Control whether services can be rearranged directly from the sidebar.</p></div>
                <div class="settings-list">
                  {@render appToggle("Drag to reorder services", "Enabled by default. Drag a service to another position in the sidebar to update Tauridium's canonical service order. Workspace filtering and hidden disabled services keep their underlying slots stable. Disable this to make sidebar service rows non-draggable; the accessible move controls in Settings → Services remain available.", "sidebarServiceDragReorder", appSettings.sidebarServiceDragReorder)}
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-advanced-shortcuts">
                <div class="section-heading"><h3 id="settings-advanced-shortcuts">Keyboard shortcut priority</h3><p>Control whether Tauridium shortcuts continue to work while a service website has keyboard focus.</p></div>
                <div class="settings-list">
                  {@render appToggle("Capture Tauridium shortcuts inside services", "Enabled by default. Matching configured Tauridium shortcuts are intercepted before the focused website. Normal typing remains untouched unless explicitly assigned as a Tauridium shortcut. Disable this if websites should receive matching shortcuts by default. Individual services can override this in Service Settings.", "captureServiceShortcuts", appSettings.captureServiceShortcuts)}
                  <p class="settings-note">Changing this setting recreates open service webviews so the keyboard policy applies immediately while preserving their persistent sessions.</p>
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-advanced-downloads">
                <div class="section-heading"><h3 id="settings-advanced-downloads">Downloads</h3><p>Choose where websites save downloads. Tauridium preserves the filename suggested by the website or server, including attachment names and extensions.</p></div>
                <div class="settings-list">
                  <div class="setting-card">
                    <div class="setting-copy">
                      <span class="setting-label">Default download directory</span>
                      <span class="setting-description" title={downloadDirectoryLabel(appSettings.downloadDirectory)}>{downloadDirectoryLabel(appSettings.downloadDirectory)}</span>
                    </div>
                    <div class="setting-actions">
                      <button class="secondary sm" onclick={chooseGlobalDownloadDirectory}>Choose folder…</button>
                      <button class="secondary sm" disabled={!appSettings.downloadDirectory} onclick={() => saveAppSetting("downloadDirectory", "")}>Use system Downloads</button>
                    </div>
                  </div>
                  {@render appToggle("Ask where to save each download", "Show a native Save dialog for every download. The dialog starts with the website/server-suggested filename and the effective download directory.", "askEachDownload", appSettings.askEachDownload)}
                  <p class="settings-note">Priority: service override → active workspace override → these global defaults. Directory overrides are device-specific settings and full backups preserve them; portable workspace exports intentionally omit filesystem paths.</p>
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-advanced-browser">
                <div class="section-heading"><h3 id="settings-advanced-browser">Browser identity</h3><p>Advanced compatibility controls for services that depend on browser identification.</p></div>
                <div class="settings-list">
                  <div class="setting-card setting-card-stack">
                    <div class="setting-copy"><span class="setting-label">Custom user agent</span><span class="setting-description">Override the browser identity sent to newly opened services. Restart Tauridium to apply it everywhere.</span></div>
                    <input class="setting-text-input" value={appSettings.userAgentPref} aria-label="Custom user agent" placeholder="Leave empty to use the app default" onchange={(e) => saveAppSetting("userAgentPref", e.currentTarget.value)} />
                  </div>
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-advanced-service-icons">
                <div class="section-heading"><h3 id="settings-advanced-service-icons">Service icons</h3><p>Control durable website-icon discovery and refresh.</p></div>
                <div class="settings-list">
                  {@render appToggle("Fetch preferred website icons automatically", "For services with Use website icon enabled, fetch the website icon once and keep it in Tauridium's persistent cache. Services that do not prefer website icons are never fetched automatically.", "fetchMissingServiceIcons", appSettings.fetchMissingServiceIcons)}
                  <div class="setting-card">
                    <div class="setting-copy"><span class="setting-label">Refetch preferred website icons</span><span class="setting-description">Refresh only services whose Use website icon preference is enabled. Recipe-icon services are left untouched.</span></div>
                    <button class="secondary sm" onclick={refetchAllServiceIcons}>Refetch all…</button>
                  </div>
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-advanced-url-templates">
                <div class="section-heading"><h3 id="settings-advanced-url-templates">Custom URL placeholders</h3><p>Opt in to reusable values inside service Custom URLs.</p></div>
                <div class="settings-list">
                  {@render appToggle("Enable custom URL placeholders for all services", "Allow {{custom_id_1}} and {{custom_id_2}} replacement in every service Custom URL. Disabled by default; individual services can opt in instead.", "customUrlTemplatesEnabled", appSettings.customUrlTemplatesEnabled)}
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-advanced-feedback">
                <div class="section-heading"><h3 id="settings-advanced-feedback">Feedback</h3></div>
                <div class="settings-list">
                  {@render appToggle("Show reload notifications", "Show a brief toast after a service is reloaded from a keybinding or the service context menu.", "reloadToasts", appSettings.reloadToasts)}
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-advanced-account">
                <div class="section-heading"><h3 id="settings-advanced-account">{me.local ? "Account" : "Server"}</h3></div>
                <div class="settings-list">
                  <div class="setting-card info-card">
                    <div class="setting-copy"><span class="setting-label">{me.local ? "Local mode" : me.email}</span><span class="setting-description">{me.local ? "Services and workspaces are stored on this device without a Ferdium account." : `Connected to ${server}. Sign out to change the server.`}</span></div>
                    <span class="status-badge">{me.local ? "Local" : "Connected"}</span>
                  </div>
                </div>
              </section>
            {:else if settingsTab === "updates"}
              <section class="settings-section" aria-labelledby="settings-updates-version">
                <div class="section-heading"><h3 id="settings-updates-version">Updates</h3><p>Keep Tauridium current using signed releases published through the project repository.</p></div>
                <div class="settings-list">
                  <div class="setting-card">
                    <div class="setting-copy"><span class="setting-label">Current version</span><span class="setting-description">Tauridium {appVer ? `v${appVer}` : "version information is loading"}.</span></div>
                    {#if updateInfo}
                      <button class="primary" disabled={updInstalling} onclick={doInstall}>{updInstalling ? "Installing…" : `Update to v${updateInfo.version}`}</button>
                    {:else}
                      <button class="secondary" disabled={updChecking} onclick={() => checkUpdates(false)}>{updChecking ? "Checking…" : "Check for updates"}</button>
                    {/if}
                  </div>
                  {#if updateInfo}<p class="settings-status">Version {updateInfo.version} is available. Tauridium will restart after installation.</p>{/if}
                  {#if updStatus}<p class="settings-status">{updStatus}</p>{/if}
                </div>
              </section>
            {:else if settingsTab === "about"}
              <section class="about-page" aria-labelledby="about-tauridium-title">
                <div class="about-hero">
                  <img class="about-logo" src={tauridiumLogo} alt="Tauridium application icon" />
                  <div class="about-identity"><h3 id="about-tauridium-title">{appMetadata?.name ?? "Tauridium"}</h3><p class="about-version">Version {appVer ? `v${appVer}` : "loading…"}</p><p class="about-summary">{appMetadata?.description ?? "Tauridium desktop client"}</p></div>
                </div>
                <div class="about-actions" role="group" aria-label="Tauridium project links">
                  <button class="primary" onclick={() => openProjectLink(projectRepository)}>Source code ↗</button>
                  <button class="secondary" onclick={() => openProjectLink(`${projectRepository}/releases`)}>Releases ↗</button>
                  <button class="secondary" onclick={() => openProjectLink(`${projectRepository}/issues/new`)}>Report an issue ↗</button>
                </div>
                <section class="settings-section" aria-labelledby="about-project-heading">
                  <div class="section-heading"><h3 id="about-project-heading">Project</h3><p>Open-source project information and useful destinations.</p></div>
                  <div class="settings-list">
                    <button class="setting-card about-link-card" onclick={() => openProjectLink(projectRepository)}><span class="setting-copy"><span class="setting-label">Repository</span><span class="setting-description">{projectRepository}</span></span><span class="external-indicator" aria-hidden="true">Open ↗</span></button>
                    <button class="setting-card about-link-card" onclick={() => openProjectLink(`${projectRepository}/issues`)}><span class="setting-copy"><span class="setting-label">Issues and feature requests</span><span class="setting-description">Report a problem, follow known issues, or propose an improvement.</span></span><span class="external-indicator" aria-hidden="true">Open ↗</span></button>
                  </div>
                </section>
                <section class="settings-section" aria-labelledby="about-legal-heading">
                  <div class="section-heading"><h3 id="about-legal-heading">Legal</h3></div>
                  <div class="settings-list"><button class="setting-card about-link-card" onclick={() => openProjectLink(`${projectRepository}/blob/master/LICENSE`)}><span class="setting-copy"><span class="setting-label">{appMetadata?.license ?? "License"}</span><span class="setting-description">Copyright © 2026 {appMetadata?.author ?? "Daniel Braniewski"}. View the complete license text.</span></span><span class="external-indicator" aria-hidden="true">View ↗</span></button></div>
                </section>
                <section class="settings-section" aria-labelledby="about-author-heading">
                  <div class="section-heading"><h3 id="about-author-heading">Author</h3></div>
                  <div class="settings-list"><button class="setting-card about-link-card" onclick={() => openProjectLink("https://brani.dev")}><span class="setting-copy"><span class="setting-label">{appMetadata?.author ?? "Daniel Braniewski"}</span><span class="setting-description">brani.dev</span></span><span class="external-indicator" aria-hidden="true">Homepage ↗</span></button></div>
                </section>
                <section class="settings-section" aria-labelledby="about-technology-heading">
                  <div class="section-heading"><h3 id="about-technology-heading">Technology</h3><p>Key projects Tauridium builds on or interoperates with.</p></div>
                  <div class="about-reference-grid">
                    <button class="reference-card" onclick={() => openProjectLink("https://v2.tauri.app/") }><strong>Tauri v2</strong><span>Native desktop application framework ↗</span></button>
                    <button class="reference-card" onclick={() => openProjectLink("https://ferdium.org/") }><strong>Ferdium</strong><span>Service and recipe ecosystem ↗</span></button>
                  </div>
                </section>
              </section>
            {/if}
          </div>
          {#if error}<p class="error">{error}</p>{/if}
        </div>
      {/if}
    </section>
  </div>
{/if}

{#if serviceContextMenu}
  {@const contextService = services.find((service) => service.id === serviceContextMenu?.serviceId) ?? null}
  <div class="service-context-backdrop" role="presentation" onclick={(event) => event.currentTarget === event.target && closeServiceContextMenu()} oncontextmenu={(event) => { event.preventDefault(); if (event.currentTarget === event.target) closeServiceContextMenu(); }}>
    {#if contextService}
      <div class="service-context-menu" role="menu" tabindex="-1" aria-label={`${serviceLabel(contextService)} actions`} style={`left:${serviceContextMenu.x}px;top:${serviceContextMenu.y}px`} onkeydown={handleServiceContextMenuKeydown}>
        <button role="menuitem" onclick={() => openContextServiceSettings(contextService)}>Settings</button>
        <button role="menuitem" disabled={contextService.isEnabled === false} onclick={() => runServiceContextAction(contextService, reloadServiceFromUi)}>Reload</button>
        <button role="menuitem" onclick={() => runServiceContextAction(contextService, duplicateServiceFromUi)}>Duplicate</button>
        <div class="service-context-separator" aria-hidden="true"></div>
        <button role="menuitem" class:context-danger={contextService.isEnabled !== false} onclick={() => runServiceContextAction(contextService, toggleServiceEnabled)}>{contextService.isEnabled === false ? "Enable" : "Disable"}</button>
      </div>
    {/if}
  </div>
{/if}

{#if toastMessage}
  <div class="toast" class:success={toastTone === "success"} role="status" aria-live="polite">{toastMessage}</div>
{/if}

{#if quickSwitcherMode}
  <div class="quick-switcher-backdrop" role="presentation" onclick={(event) => event.currentTarget === event.target && closeQuickSwitcher()}>
    <div class="quick-switcher" role="dialog" aria-modal="true" aria-label={quickSwitcherMode === "service" ? "Quick service search" : "Quick workspace switcher"}>
      <div class="quick-switcher-head">
        <input
          type="search"
          value={quickSwitcherQuery}
          placeholder={quickSwitcherMode === "service" ? "Search services…" : "Search workspaces…"}
          aria-label={quickSwitcherMode === "service" ? "Search services" : "Search workspaces"}
          oninput={(event) => { quickSwitcherQuery = event.currentTarget.value; quickSwitcherIndex = 0; }}
        />
        <button class="icon-button" aria-label="Close quick switcher" title="Close" onclick={() => closeQuickSwitcher()}>×</button>
      </div>
      <div class="quick-switcher-results" role="listbox" aria-label="Quick switcher results">
        {#each quickSwitcherItems.slice(0, 100) as item, index (item.id)}
          <button
            class="quick-switcher-item"
            class:active={index === quickSwitcherIndex}
            class:current={(quickSwitcherMode === "workspace" && item.id === (activeWorkspace ?? "__all__")) || (quickSwitcherMode === "service" && item.id === activeId)}
            role="option"
            aria-selected={index === quickSwitcherIndex}
            aria-current={(quickSwitcherMode === "workspace" && item.id === (activeWorkspace ?? "__all__")) || (quickSwitcherMode === "service" && item.id === activeId) ? "true" : undefined}
            onmouseenter={() => (quickSwitcherIndex = index)}
            onclick={() => chooseQuickSwitcherItem(item)}
          >
            <span>{item.label}</span><small>{item.kind === "service" ? "Service" : "Workspace"}</small>
          </button>
        {:else}
          <div class="quick-switcher-empty">No matches</div>
        {/each}
      </div>
      {#if quickSwitcherItems.length > 100}<p class="quick-switcher-hint">Showing the first 100 matches. Refine your search to narrow the list.</p>{/if}
    </div>
  </div>
{/if}

{#snippet row(s: Service)}
  <div
    class="srow-wrap"
    class:drag-before={appSettings.sidebarServiceDragReorder && !serviceOrderBusy && dragOverId === s.id && dragPlacement === "before"}
    class:drag-after={appSettings.sidebarServiceDragReorder && !serviceOrderBusy && dragOverId === s.id && dragPlacement === "after"}
    class:dragging={appSettings.sidebarServiceDragReorder && !serviceOrderBusy && dragIds.includes(s.id)}
    class:drag-selected={appSettings.sidebarServiceDragReorder && serviceDragSelection.includes(s.id)}
    class:draggable={appSettings.sidebarServiceDragReorder && !serviceOrderBusy}
    draggable={appSettings.sidebarServiceDragReorder && !serviceOrderBusy}
    role="listitem"
    ondragstart={(e) => onDragStart(e, s)}
    ondragover={(e) => onDragOver(e, s)}
    ondragleave={(e) => onDragLeave(e, s)}
    ondrop={(e) => onDrop(e, s)}
    ondragend={onDragEnd}
  >
    <button
      class="srow"
      class:active={s.id === activeId && view === "service"}
      class:disabled={s.isEnabled === false}
      class:asleep={hibernated.has(s.id)}
      aria-disabled={s.isEnabled === false}
      oncontextmenu={(e) => openServiceContextMenu(e, s)}
      onclick={(e) => onServiceRowClick(e, s)}
      onkeydown={(e) => openServiceContextMenuFromKeyboard(e, s)}
      title={`${serviceLabel(s)}${hibernated.has(s.id) ? " · Hibernated" : ""}${(unreadMap[s.id] ?? 0) > 0 ? ` · ${unreadMap[s.id]} unread` : ""}`}
      aria-label={`${serviceLabel(s)}${hibernated.has(s.id) ? ", hibernated" : ""}${(unreadMap[s.id] ?? 0) > 0 ? `, ${unreadMap[s.id]} unread` : ""}`}
    >
      {#if serviceIconFailed(s)}
        <span class="dot">{serviceLabel(s).slice(0, 1).toUpperCase()}</span>
      {:else}
        <img class="svc-icon" class:service-icon-inverted={serviceIconInverted(s.id)} src={displayedServiceIcon(s)} alt="" onerror={() => markIconFailed(s)} />
      {/if}
      {#if appSettings.showServiceName && !appSettings.sidebarCollapsed}
        <span class="srow-name">{serviceLabel(s)}</span>
      {/if}
      {#if hibernated.has(s.id) && !appSettings.sidebarCollapsed}<span class="zzz" title="Hibernated">💤</span>{/if}
      {#if s.isBadgeEnabled !== false && (unreadMap[s.id] ?? 0) > 0 && (s.isMuted !== true || appSettings.showMessageBadgeWhenMuted)}
        <span class="ubadge" class:muted={s.isMuted === true}>
          {unreadMap[s.id] > 99 ? "99+" : unreadMap[s.id]}
        </span>
      {/if}
    </button>
  </div>
{/snippet}

{#snippet toggle(label: string, desc: string, key: keyof Service, checked: boolean)}
  <div class="setrow">
    <label class="row-toggle">
      <input
        type="checkbox"
        {checked}
        onchange={(e) => saveSetting(key, e.currentTarget.checked)}
      />
      <span>{label}</span>
    </label>
    <p class="desc">{desc}</p>
  </div>
{/snippet}

{#snippet appToggle(label: string, desc: string, key: keyof AppSettings, checked: boolean)}
  <label class="setting-card setting-card-toggle">
    <span class="setting-copy"><span class="setting-label">{label}</span><span class="setting-description">{desc}</span></span>
    <span class="switch-control">
      <input class="switch-input" type="checkbox" {checked} aria-label={label} onchange={(e) => saveAppSetting(key, e.currentTarget.checked)} />
      <span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>
    </span>
  </label>
{/snippet}

<style>
  :global(:root) {
    --bg: #1f2230; --sidebar: #1b1d28; --card: #282b3a; --panel: #232633;
    --input: #1f2230; --border: #2f3445; --border2: #3a3f55;
    --text: #e8e8ef; --text2: #d6d9e6; --muted: #9aa0b5; --muted2: #6b7193;
    --hover: #262a3a; --accent: #ffc131; --accent-fg: #1f2230; --accent-soft: #b9b2ff; --link: #7a82a8;
  }
  :global(body.light) {
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
  button, input, select, textarea { font-family: inherit; }
  .login { display: grid; place-items: center; height: 100vh; }
  .card {
    background: var(--card); padding: 28px; border-radius: 14px; width: 320px;
    display: flex; flex-direction: column; gap: 12px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
  }
  .card h1 { margin: 0; font-size: 24px; }
  .sub { margin: 0 0 6px; color: var(--muted); font-size: 13px; }
  label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); }
  input {
    padding: 9px 11px; border-radius: 8px; border: 1px solid var(--border2);
    background: var(--input); color: var(--text); font-size: 14px;
  }
  .primary {
    padding: 10px 14px; border: none; border-radius: 8px; background: var(--accent);
    color: var(--accent-fg); font-weight: 700; cursor: pointer;
  }
  .primary:disabled { opacity: 0.6; cursor: default; }
  .local-separator {
    display: flex; align-items: center; gap: 10px; color: var(--muted2); font-size: 11px;
  }
  .local-separator::before, .local-separator::after {
    content: ""; flex: 1; height: 1px; background: var(--border);
  }
  .local-mode {
    padding: 10px 14px; border: 1px solid var(--border2); border-radius: 8px;
    background: var(--input); color: var(--text); font-weight: 700; cursor: pointer;
  }
  .local-mode:hover { background: var(--hover); }
  .local-mode:disabled { opacity: 0.6; cursor: default; }
  .local-note { margin: -3px 0 0; color: var(--muted2); font-size: 11px; line-height: 1.4; }
  .gear { align-self: flex-start; background: none; border: none; color: var(--muted); cursor: pointer; font-size: 12px; padding: 0; }
  .error { color: #ff8a8a; font-size: 13px; margin: 4px 0; }

  .shell { display: grid; grid-template-columns: var(--sidebar-w, 240px) 1fr; height: 100vh; }
  .sidebar {
    background: var(--sidebar); padding: 10px 10px 8px; overflow: hidden;
    display: flex; flex-direction: column; gap: 8px;
  }
  .svcarea {
    flex: 1; min-height: 0; display: flex; flex-direction: column; overflow-y: auto;
    overscroll-behavior: contain; scrollbar-gutter: stable;
  }
  :global(body[data-svcloc="center"]) .svclist { margin-block: auto; }
  :global(body[data-svcloc="bottom"]) .svclist { margin-top: auto; }
  .account { display: flex; align-items: center; min-width: 0; min-height: 32px; font-size: 13px; }
  .account-copy { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; }
  .account strong { flex: 0 1 auto; min-width: 0; max-width: 45%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .workspace-scope { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted2); }
  .sidebar-collapse-button {
    width: 30px; height: 30px; margin-left: 6px; flex: none; display: grid; place-items: center;
    padding: 0; border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--muted); cursor: pointer;
  }
  .sidebar-collapse-button:hover { border-color: var(--border); background: var(--hover); color: var(--text2); }
  .sidebar-collapse-button:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  .sidebar-collapse-button svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
  .sidebar.collapsed { padding-inline: 5px; }
  .sidebar.collapsed .account { width: 42px; justify-content: center; }
  .sidebar.collapsed .account-copy, .sidebar.collapsed .count { display: none; }
  .sidebar.collapsed .sidebar-collapse-button { margin-left: 0; }
  .sidebar.collapsed .svcarea { width: 42px; scrollbar-gutter: auto; scrollbar-width: none; }
  .sidebar.collapsed .svcarea::-webkit-scrollbar { width: 0; height: 0; }
  .sidebar.collapsed .svclist { gap: var(--collapsed-service-gap, 2px); }
  .sidebar.collapsed .svclist, .sidebar.collapsed .srow-wrap { width: 42px; }
  .sidebar.collapsed .srow {
    position: relative; width: 42px; height: 42px; min-height: 42px; flex: none;
    justify-content: center; gap: 0; padding: 4px; box-sizing: border-box; border-radius: 8px;
  }
  .sidebar.collapsed .srow-wrap.drag-before::before, .sidebar.collapsed .srow-wrap.drag-after::after { left: 4px; right: 4px; }
  .sidebar.collapsed .ubadge { position: absolute; top: 2px; right: 2px; min-width: 14px; height: 14px; padding: 0 3px; border-radius: 8px; font-size: 9px; line-height: 14px; }
  .link { background: none; border: none; color: var(--link); cursor: pointer; font-size: 12px; text-decoration: underline; }
  .svclist { display: flex; flex: none; flex-direction: column; gap: var(--expanded-service-gap, 2px); padding-right: 0; }

  .srow-wrap { display: flex; align-items: center; position: relative; width: 100%; }
  .srow-wrap.draggable .srow { cursor: grab; }
  .srow-wrap.draggable:active .srow { cursor: grabbing; }
  .srow-wrap.dragging { opacity: 0.42; }
  .srow-wrap.drag-selected .srow:not(.active) { background: color-mix(in srgb, var(--accent) 18%, var(--hover)); outline: 1px solid color-mix(in srgb, var(--accent) 58%, var(--border2)); outline-offset: -1px; }
  .srow-wrap.drag-before::before, .srow-wrap.drag-after::after {
    content: ""; position: absolute; z-index: 2; left: 6px; right: 6px;
    height: 2px; background: var(--accent); border-radius: 2px; pointer-events: none;
  }
  .srow-wrap.drag-before::before { top: -1px; }
  .srow-wrap.drag-after::after { bottom: -1px; }
  .srow { width: 100%;
    display: flex; align-items: center; gap: 9px; flex: 1; min-width: 0;
    padding: 7px 8px; border: none; border-radius: 8px; background: none;
    color: var(--text2); cursor: pointer; text-align: left; font-size: 14px; user-select: none;
  }
  .srow:hover { background: var(--hover); }
  .srow.active { background: var(--accent); color: var(--accent-fg); }
  .srow.disabled { opacity: 0.45; }
  .srow.asleep .svc-icon, .srow.asleep .dot { opacity: 0.5; }
  .zzz { margin-left: auto; font-size: 12px; opacity: 0.8; }
  .svc-icon, .srow .dot { width: var(--icon-size, 22px); height: var(--icon-size, 22px); border-radius: 5px; object-fit: cover; flex: none; }
  .service-icon-inverted { filter: invert(1); }
  .srow.asleep .svc-icon:not(.service-icon-inverted) { filter: grayscale(1); }
  .srow.asleep .svc-icon.service-icon-inverted { filter: invert(1) grayscale(1); }
  .srow .dot { display: grid; place-items: center; background: var(--border2); font-size: 12px; font-weight: 700; }
  :global(body.grayscale) .svc-icon { filter: grayscale(1); opacity: var(--gray-op, 0.6); transition: filter 0.15s, opacity 0.15s; }
  :global(body.grayscale) .svc-icon.service-icon-inverted { filter: invert(1) grayscale(1); }
  :global(body.grayscale) .srow:hover .svc-icon,
  :global(body.grayscale) .srow.active .svc-icon { filter: none; opacity: 1; }
  :global(body.grayscale) .srow:hover .svc-icon.service-icon-inverted,
  :global(body.grayscale) .srow.active .svc-icon.service-icon-inverted { filter: invert(1); }
  .srow-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ubadge {
    margin-left: auto; background: #e23b3b; color: #fff; font-size: 11px; font-weight: 700;
    min-width: 18px; height: 18px; padding: 0 5px; border-radius: 9px; flex: none;
    display: inline-flex; align-items: center; justify-content: center;
  }
  .ubadge.muted { background: var(--muted2); }
  .count { font-size: 11px; color: var(--muted2); }
  .ver { font-weight: 700; color: var(--muted); }

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
  .head-actions { display: inline-flex; align-items: center; gap: 12px; }
  .primary.sm { padding: 6px 12px; font-size: 13px; }
  .panel-head h2 { margin: 0; font-size: 18px; }
  .recipe { color: var(--accent-soft); font-size: 12px; }
  .set-title { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted2); }
  .row-toggle { flex-direction: row; align-items: center; gap: 10px; color: var(--text2); font-size: 14px; cursor: pointer; }
  .row-toggle input { width: auto; }
  .setrow { display: flex; flex-direction: column; gap: 3px; }
  .desc { margin: 0 0 0 26px; color: var(--muted); font-size: 12px; line-height: 1.35; }
  .notice {
    margin: 0; padding: 9px 11px; border-radius: 8px; font-size: 12px; line-height: 1.4;
    background: rgba(217, 119, 6, 0.12); border: 1px solid rgba(217, 119, 6, 0.35); color: var(--text2);
  }
  .select {
    margin-left: auto; padding: 6px 9px; border-radius: 8px;
    border: 1px solid var(--border2); background: var(--input); color: var(--text); font-size: 13px;
  }
  .range { margin-left: auto; width: 130px; accent-color: var(--accent); }
  .swatches { margin-left: auto; display: inline-flex; gap: 7px; }
  .swatch {
    width: 22px; height: 22px; border-radius: 999px; border: none; padding: 0; cursor: pointer;
  }
  .swatch.on { outline: 2px solid var(--text); outline-offset: 2px; }
  .block { gap: 6px; }
  .num-row { display: flex; gap: 12px; }
  .num-row label { flex: 1; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
  .num { padding: 6px 8px; border-radius: 8px; border: 1px solid var(--border2); background: var(--input); color: var(--text); font-size: 13px; }
  .proxy-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .danger { margin-top: 6px; background: #3a2330; border: 1px solid #6e2b3e; color: #ff9aa8; border-radius: 8px; padding: 9px; cursor: pointer; }
  .danger:hover { filter: brightness(1.15); }
  .danger.sm { margin-top: 0; padding: 6px 12px; font-size: 13px; white-space: nowrap; align-self: center; }
  .danger-zone { margin-top: 16px; border: 1px solid #6e2b3e; border-radius: 10px; overflow: hidden; }
  .dz-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 14px; }
  .dz-row + .dz-row { border-top: 1px solid #6e2b3e; }
  .dz-row strong { font-size: 14px; }
  .dz-hint { margin: 3px 0 0; font-size: 12px; color: var(--muted); max-width: 380px; }
  .results { display: flex; flex-direction: column; gap: 6px; max-height: 55vh; overflow-y: auto; }
  .result {
    display: flex; justify-content: space-between; align-items: center;
    background: var(--input); border: 1px solid var(--border); border-radius: 8px;
    padding: 9px 11px; cursor: pointer; color: var(--text); text-align: left;
  }
  .result:hover { background: var(--hover); border-color: var(--accent); }
  .result-icon { width: 22px; height: 22px; border-radius: 5px; flex: none; }
  .result-name { flex: 1; }
  .result-id { color: var(--muted2); font-size: 12px; }
  .secondary { padding: 9px 12px; border: 1px solid var(--border2); border-radius: 8px; background: var(--input); color: var(--text2); font-weight: 600; cursor: pointer; }
  .secondary:hover { background: var(--hover); border-color: var(--accent); }
  .secondary:disabled { opacity: 0.55; cursor: default; }
  .secondary.sm { padding: 6px 10px; font-size: 12px; }
  .add-tabs { display: flex; gap: 6px; flex-wrap: wrap; }
  .add-tabs button { padding: 7px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--input); color: var(--muted); cursor: pointer; }
  .add-tabs button.active { border-color: var(--accent); color: var(--text); background: var(--hover); }
  .recipe-tools, .recipe-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .recipe-path { margin: -4px 0 2px; color: var(--muted2); font-size: 11px; line-height: 1.45; word-break: break-all; }
  .result { gap: 10px; }
  .result-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .result-name { font-weight: 600; }
  .result-desc { color: var(--muted); font-size: 11px; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .result-meta { flex: none; display: flex; flex-direction: column; align-items: flex-end; gap: 3px; }
  .source-badge { padding: 2px 6px; border-radius: 999px; background: var(--hover); color: var(--accent-soft); font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; }
  .empty-recipe { padding: 14px; border: 1px dashed var(--border2); border-radius: 10px; display: flex; flex-direction: column; gap: 8px; }
  .empty-recipe .sub { margin: 0; }
  .creator-card { display: flex; flex-direction: column; gap: 12px; }
  .creator-card h3 { margin: 0; font-size: 16px; }
  .creator-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .creator-options { display: flex; flex-direction: column; gap: 6px; }
  .row-toggle.compact { flex-direction: row; justify-content: space-between; padding: 7px 9px; border: 1px solid var(--border); border-radius: 8px; background: var(--input); }
  textarea { width: 100%; box-sizing: border-box; resize: vertical; padding: 9px 11px; border-radius: 8px; border: 1px solid var(--border2); background: var(--input); color: var(--text); font-size: 13px; }
  .code-input { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; line-height: 1.4; }
  .security-note { margin-top: -4px; }

  .danger-link { color: #e77d8e; }
  .icon-button.compact { width: 30px; height: 30px; border-color: var(--border); background: var(--input); }
  .icon-button.compact:disabled { opacity: 0.35; cursor: default; }
  .managed-list { display: flex; flex-direction: column; gap: 7px; }
  .managed-row {
    min-height: 62px; display: flex; align-items: center; justify-content: space-between; gap: 16px;
    padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--input);
  }
  .managed-identity { min-width: 0; display: flex; align-items: center; gap: 10px; }
  .managed-icon { width: 34px; height: 34px; border-radius: 8px; object-fit: cover; flex: none; }
  .managed-icon.fallback { display: grid; place-items: center; background: var(--hover); color: var(--text2); font-weight: 750; }
  .managed-copy { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .managed-copy strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text2); font-size: 14px; }
  .managed-copy span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); font-size: 11.5px; }
  .managed-actions { display: inline-flex; align-items: center; gap: 5px; flex: none; }
  .managed-empty {
    display: flex; flex-direction: column; gap: 4px; padding: 18px; border: 1px dashed var(--border2);
    border-radius: 10px; color: var(--muted); text-align: center;
  }
  .managed-empty strong { color: var(--text2); font-size: 14px; }
  .managed-empty span { font-size: 12px; }
  .section-count {
    display: inline-flex; min-width: 22px; height: 20px; align-items: center; justify-content: center;
    margin-left: 4px; padding: 0 6px; border-radius: 999px; background: var(--hover); color: var(--muted);
    font-size: 11px; font-weight: 700; vertical-align: middle;
  }

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
  .icon-button:focus-visible, .setting-tab:focus-visible, .setting-card:focus-visible,
  .reference-card:focus-visible, .primary:focus-visible, .secondary:focus-visible,
  .select:focus-visible, .setting-text-input:focus-visible, .swatch:focus-visible {
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
  .settings-section { display: flex; flex-direction: column; gap: 10px; }
  .section-heading { display: flex; flex-direction: column; gap: 4px; padding: 0 2px; }
  .section-heading h3 { margin: 0; font-size: 13px; line-height: 1.3; font-weight: 700; color: var(--text); }
  .section-heading p { margin: 0; max-width: 840px; color: var(--muted); font-size: 12.5px; line-height: 1.45; }
  .settings-list { display: flex; flex-direction: column; gap: 8px; }
  .setting-card {
    width: 100%; box-sizing: border-box; display: grid; grid-template-columns: minmax(0, 1fr) auto;
    align-items: center; gap: 18px; min-height: 68px; padding: 13px 14px;
    border: 1px solid var(--border); border-radius: 10px; background: var(--input);
    color: var(--text); text-align: left; font: inherit;
  }
  button.setting-card { cursor: pointer; }
  button.setting-card:hover { background: var(--hover); border-color: var(--border2); }
  .setting-card-stack { grid-template-columns: 1fr; align-items: stretch; gap: 10px; }
  .setting-copy { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .setting-label { color: var(--text2); font-size: 14px; line-height: 1.35; font-weight: 650; }
  .setting-description { max-width: 760px; color: var(--muted); font-size: 12.5px; line-height: 1.45; font-weight: 400; }
  .setting-control { min-width: 176px; max-width: 230px; margin-left: 0; }
  .setting-text-input { width: 100%; box-sizing: border-box; }
  .setting-number { width: 96px; box-sizing: border-box; text-align: right; }
  .setting-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
  .settings-note, .settings-status { margin: 0 2px; color: var(--muted); font-size: 12px; line-height: 1.45; }
  .settings-status { color: var(--text2); }
  .info-card { min-height: 72px; }
  .status-badge {
    display: inline-flex; align-items: center; min-height: 24px; padding: 0 9px;
    border: 1px solid var(--border2); border-radius: 999px; background: var(--hover);
    color: var(--text2); font-size: 11px; font-weight: 700;
  }
  .switch-control { position: relative; width: 38px; height: 22px; flex: none; }
  .switch-input { position: absolute; inset: 0; width: 38px; height: 22px; margin: 0; opacity: 0; cursor: pointer; z-index: 1; }
  .switch-track { position: absolute; inset: 0; border: 1px solid var(--border2); border-radius: 999px; background: var(--bg); transition: background 0.15s ease, border-color 0.15s ease; }
  .switch-thumb { position: absolute; width: 16px; height: 16px; left: 2px; top: 2px; border-radius: 50%; background: var(--muted); transition: transform 0.15s ease, background 0.15s ease; }
  .switch-input:checked + .switch-track { background: var(--accent); border-color: var(--accent); }
  .switch-input:checked + .switch-track .switch-thumb { transform: translateX(16px); background: var(--accent-fg); }
  .switch-input:focus-visible + .switch-track { outline: 2px solid var(--accent); outline-offset: 2px; }
  .setting-card-toggle { cursor: pointer; }
  .setting-card-toggle:hover { background: var(--hover); border-color: var(--border2); }
  .settings-panel .select { padding: 8px 10px; font-size: 13px; }
  .settings-panel .primary, .settings-panel .secondary { min-height: 34px; display: inline-flex; align-items: center; justify-content: center; }
  .settings-panel .primary.sm, .settings-panel .secondary.sm { min-height: 30px; }
  .settings-panel .swatches { margin-left: 0; justify-content: flex-end; flex-wrap: wrap; max-width: 250px; }
  .accent-setting-card { align-items: stretch; }
  .accent-picker-control { display: flex; align-items: center; justify-content: space-between; gap: 14px; width: 100%; }
  .accent-picker-control .swatches { flex: 1 1 auto; justify-content: flex-start; max-width: none; }
  .accent-custom-button { flex: 0 0 auto; min-width: 92px; }
  .settings-panel .swatch { width: 24px; height: 24px; border: 1px solid rgba(255,255,255,0.18); }
  .range-control { display: flex; align-items: center; gap: 10px; color: var(--muted); font-size: 12px; min-width: 180px; }
  .settings-panel .range { width: 140px; margin-left: 0; }
  .managed-toolbar { display: grid; grid-template-columns: minmax(0, 1fr) minmax(160px, 220px); gap: 8px; }
  .service-managed-toolbar { grid-template-columns: minmax(0, 1fr) minmax(160px, 220px) auto; }
  .workspace-managed-toolbar { grid-template-columns: minmax(0, 1fr) auto; }
  .workspace-create-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: center; }
  .workspace-order-select { min-width: 210px; max-width: 280px; }
  .workspace-managed-identity { min-width: 0; flex: 1 1 auto; }
  .workspace-avatar { width: 34px; height: 34px; display: grid; place-items: center; flex: none; border-radius: 8px; background: var(--hover); color: var(--text2); font-size: 13px; font-weight: 750; }
  .workspace-avatar-image { object-fit: contain; padding: 3px; box-sizing: border-box; }
  .workspace-icon-card { gap: 10px; }
  .workspace-icon-current { display: grid; grid-template-columns: 44px minmax(0, 1fr) auto; align-items: center; gap: 12px; width: 100%; }
  .workspace-icon-url-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 8px; width: 100%; }
  .workspace-icon-preview { width: 44px; height: 44px; border-radius: 10px; object-fit: contain; padding: 5px; box-sizing: border-box; }
  .workspace-icon-choices { width: 100%; display: grid; grid-template-columns: repeat(auto-fill, minmax(112px, 1fr)); gap: 7px; max-height: 250px; overflow-y: auto; overscroll-behavior: contain; padding: 3px; border: 1px solid var(--border); border-radius: 9px; background: var(--bg); }
  .workspace-icon-choice { min-width: 0; min-height: 72px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 5px; padding: 8px; border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--text2); cursor: pointer; font: inherit; }
  .workspace-icon-choice:hover:not(:disabled) { background: var(--hover); border-color: var(--border); }
  .workspace-icon-choice.selected { border-color: color-mix(in srgb, var(--accent) 58%, var(--border)); background: color-mix(in srgb, var(--accent) 8%, var(--input)); }
  .workspace-icon-choice:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  .workspace-icon-choice:disabled { cursor: wait; opacity: 0.68; }
  .workspace-icon-choice img, .workspace-icon-choice > span { width: 32px; height: 32px; display: grid; place-items: center; object-fit: contain; padding: 3px; box-sizing: border-box; border-radius: 7px; background: var(--hover); font-size: 12px; font-weight: 750; }
  .workspace-icon-choice small { width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); text-align: center; }
  .managed-row.selected { border-color: color-mix(in srgb, var(--accent) 62%, var(--border)); background: color-mix(in srgb, var(--accent) 8%, var(--input)); }
  .workspace-detail-section { padding-top: 4px; border-top: 1px solid var(--border); }
  .workspace-detail-heading { flex-direction: row; align-items: flex-start; justify-content: space-between; gap: 12px; }
  .workspace-detail-heading > div { min-width: 0; }
  .workspace-name-control { min-width: min(430px, 48vw); display: grid; grid-template-columns: minmax(160px, 1fr) auto; gap: 8px; align-items: center; }
  .workspace-membership-card { gap: 9px; }
  .workspace-service-list { display: flex; flex-direction: column; gap: 5px; max-height: min(46vh, 520px); overflow-y: auto; overscroll-behavior: contain; padding: 3px; border: 1px solid var(--border); border-radius: 9px; background: var(--bg); }
  .workspace-service-row { min-height: 46px; display: flex; flex-direction: row; align-items: center; justify-content: space-between; gap: 12px; padding: 7px 9px; border-radius: 7px; cursor: pointer; }
  .workspace-service-row:hover { background: var(--hover); }
  .workspace-service-row > span { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .workspace-service-row strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text2); font-size: 13px; }
  .workspace-service-row small { color: var(--muted); font-size: 11px; }
  .workspace-service-row input { width: 18px; height: 18px; flex: none; accent-color: var(--accent); }
  .workspace-detail-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
  .danger-button { color: #ff9b9b; border-color: color-mix(in srgb, #ff7373 45%, var(--border2)); }
  .pagination { display: flex; align-items: center; justify-content: center; gap: 10px; color: var(--muted); font-size: 12px; }
  .custom-swatch-wrap { position: relative; display: inline-flex; align-items: center; }
  .swatch-remove { position: absolute; top: -8px; right: -8px; width: 18px; height: 18px; display: grid; place-items: center; padding: 0; border: 1px solid var(--border2); border-radius: 999px; background: var(--panel); color: var(--muted); cursor: pointer; font-size: 12px; line-height: 1; }
  .swatch-remove:hover, .preset-remove:hover { color: var(--text); background: var(--hover); }
  .color-picker-card { gap: 12px; }
  .color-picker-preview-row { display: grid; grid-template-columns: 48px minmax(100px, 1fr) 38px; align-items: center; gap: 10px; }
  .color-picker-preview-row input[type="color"] { width: 48px; height: 38px; padding: 2px; border-radius: 8px; cursor: pointer; }
  .color-picker-preview-row code { color: var(--text2); font: 12px ui-monospace, SFMono-Regular, Consolas, monospace; }
  .color-preview { width: 34px; height: 34px; border: 1px solid var(--border2); border-radius: 8px; }
  .slider-field { display: grid; grid-template-columns: 112px minmax(140px, 1fr); align-items: center; gap: 10px; color: var(--muted); }
  .slider-field > span { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; }
  .slider-field strong { color: var(--text2); font-variant-numeric: tabular-nums; }
  .slider-field input[type="range"] { width: 100%; margin: 0; accent-color: var(--accent); }
  .sidebar-width-control { display: grid; grid-template-columns: minmax(160px, 1fr) 72px; align-items: center; gap: 12px; }
  .sidebar-width-control .range { width: 100%; margin: 0; }
  .sidebar-width-control output { color: var(--text2); font-size: 12px; font-variant-numeric: tabular-nums; text-align: right; }
  .preset-row { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }
  .preset-chip { min-height: 30px; display: inline-flex; align-items: center; gap: 6px; padding: 4px 8px; border: 1px solid var(--border2); border-radius: 999px; background: var(--input); color: var(--text2); }
  .preset-chip button { min-height: 24px; }
  .preset-chip .secondary { border: none; background: transparent; padding: 2px 4px; color: var(--text2); }
  .preset-remove { min-width: 24px; padding: 0; border: none; background: transparent; color: var(--muted); cursor: pointer; }
  .keybinding-list { gap: 7px; }
  .keybinding-card { min-height: 72px; }
  .keybinding-control { display: flex; align-items: center; justify-content: flex-end; gap: 7px; flex-wrap: wrap; }
  .keybinding-control kbd { min-width: 120px; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 6px 8px; border: 1px solid var(--border2); border-bottom-width: 2px; border-radius: 6px; background: var(--bg); color: var(--text2); font: 12px ui-monospace, SFMono-Regular, Consolas, monospace; text-align: center; }
  .keybinding-conflict { color: #ff9b9b; font-weight: 650; }
  .backup-location-row { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 8px; align-items: center; width: 100%; }
  .backup-location-row code { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .number-with-unit { display: inline-flex; align-items: center; gap: 8px; color: var(--muted); font-size: 12px; }
  .audit-toolbar { display: grid; grid-template-columns: minmax(220px, 1fr) minmax(120px, 160px) auto auto auto; gap: 8px; align-items: center; }
  .audit-list { display: flex; flex-direction: column; gap: 8px; max-height: min(56vh, 620px); overflow-y: auto; overscroll-behavior: contain; padding-right: 2px; }
  .audit-entry { display: flex; flex-direction: column; gap: 6px; padding: 11px 12px; border: 1px solid var(--border); border-radius: 9px; background: var(--input); }
  .audit-entry.audit-warning { border-color: color-mix(in srgb, #ffbf69 55%, var(--border)); }
  .audit-entry.audit-error { border-color: color-mix(in srgb, #ff7373 62%, var(--border)); }
  .audit-entry-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; color: var(--muted); font-size: 11px; }
  .audit-entry-head time { font-variant-numeric: tabular-nums; }
  .audit-level { min-height: 20px; display: inline-flex; align-items: center; padding: 0 6px; border: 1px solid var(--border2); border-radius: 999px; color: var(--text2); font-weight: 700; text-transform: uppercase; font-size: 10px; }
  .audit-entry strong { color: var(--text2); font-size: 13px; line-height: 1.35; }
  .audit-entry pre { max-height: 190px; margin: 0; padding: 9px; overflow: auto; border-radius: 7px; background: var(--bg); color: var(--muted); font: 11px/1.45 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
  .sandbox-create-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }
  .sandbox-card { align-items: start; }
  .sandbox-name { max-width: 320px; }
  .sandbox-select { min-width: 180px; }
  .service-shortcut-policy { display: grid; grid-template-columns: minmax(0, 1fr) minmax(230px, 320px); align-items: start; gap: 8px 18px; }
  .service-shortcut-copy { min-width: 0; }
  .service-shortcut-policy .desc { margin-left: 0; }
  .service-shortcut-policy .select { width: 100%; min-width: 0; max-width: none; margin-left: 0; }
  .service-shortcut-effective { grid-column: 1 / -1; margin-top: 0; }
  .service-workspace-manager { display: flex; flex-direction: column; gap: 12px; padding: 14px; border: 1px solid var(--border); border-radius: 10px; background: color-mix(in srgb, var(--panel) 88%, var(--bg)); }
  .service-sandbox-manager { gap: 8px; }
  .service-sandbox-manager .service-workspace-overview { align-items: center; }
  .service-sandbox-help { margin: 0; }
  .service-download-manager { gap: 10px; }
  .download-override-toggle { width: fit-content; max-width: 100%; }
  .download-setting-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 12px; width: 100%; box-sizing: border-box; padding: 10px 0 0; border-top: 1px solid var(--border); }
  label.download-setting-row { cursor: pointer; }
  .download-setting-row .desc { margin-left: 0; }
  .download-inherited-copy { margin: 0; padding-top: 4px; }
  .workspace-download-card .download-setting-row { padding: 10px 0 0; }
  .service-workspace-overview { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
  .service-workspace-overview .setting-copy { min-width: 0; }
  .service-workspace-toolbar { display: flex; align-items: stretch; gap: 8px; }
  .service-workspace-search { min-width: 0; min-height: 40px; flex: 1 1 280px; box-sizing: border-box; }
  .service-workspace-search.service-sandbox-search { width: min(100%, 240px); max-width: 240px; min-height: 36px; flex: none; align-self: flex-start; margin: 0; }
  .service-workspace-filters { display: inline-grid; grid-template-columns: repeat(3, auto); align-items: stretch; flex: none; padding: 3px; border: 1px solid var(--border); border-radius: 9px; background: var(--input); }
  .service-workspace-filters button { min-height: 32px; padding: 5px 10px; border: 1px solid transparent; border-radius: 6px; background: transparent; color: var(--muted); cursor: pointer; font: inherit; font-size: 12px; font-weight: 650; white-space: nowrap; }
  .service-workspace-filters button:hover { background: var(--hover); color: var(--text2); }
  .service-workspace-filters button.active { border-color: var(--border2); background: var(--panel); color: var(--text); box-shadow: 0 1px 3px rgba(0, 0, 0, 0.14); }
  .service-workspace-filters button:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  .service-workspace-list { display: flex; flex-direction: column; gap: 4px; max-height: min(42vh, 460px); overflow-y: auto; overscroll-behavior: contain; margin: 0; padding: 4px; border: 1px solid var(--border); border-radius: 9px; background: var(--input); }
  .service-workspace-item { margin: 0; padding: 0; list-style: none; }
  .service-workspace-option { width: 100%; min-height: 54px; box-sizing: border-box; display: grid; grid-template-columns: 20px 34px minmax(0, 1fr) auto; align-items: center; gap: 10px; padding: 8px 10px; border: 1px solid transparent; border-radius: 7px; cursor: pointer; user-select: none; transition: background 0.12s ease, border-color 0.12s ease; }
  .service-workspace-option:hover { background: var(--hover); border-color: var(--border); }
  .service-workspace-option:focus-within { border-color: var(--accent); box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 62%, transparent); }
  .service-workspace-option.joined { border-color: color-mix(in srgb, var(--accent) 32%, var(--border)); background: color-mix(in srgb, var(--accent) 8%, var(--input)); }
  .service-workspace-option.busy { cursor: wait; opacity: 0.68; }
  .service-workspace-checkbox { width: 18px; height: 18px; margin: 0; accent-color: var(--accent); cursor: pointer; }
  .service-workspace-checkbox:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .service-workspace-checkbox:disabled { cursor: wait; }
  .service-workspace-avatar { width: 34px; height: 34px; border-radius: 8px; }
  .service-workspace-copy { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .service-workspace-copy strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text2); font-size: 13px; }
  .service-workspace-copy small { color: var(--muted); font-size: 11px; }
  .service-workspace-state { min-width: 74px; color: var(--muted); font-size: 11px; font-weight: 650; text-align: right; white-space: nowrap; }
  .service-workspace-option.joined .service-workspace-state { color: var(--text2); }
  .service-workspace-create-card { display: grid; grid-template-columns: minmax(0, 1fr) minmax(290px, 48%); align-items: center; gap: 14px; padding-top: 3px; border-top: 1px solid var(--border); }
  .service-workspace-create-card .setting-copy { padding-top: 9px; }
  .service-workspace-create { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: center; padding-top: 9px; }
  .danger-link { color: #ff9b9b; }
  .service-context-backdrop { position: fixed; inset: 0; z-index: 1200; }
  .service-context-menu { position: fixed; width: 226px; padding: 5px; border: 1px solid var(--border2); border-radius: 9px; background: var(--panel); box-shadow: 0 14px 42px rgba(0, 0, 0, 0.45); }
  .service-context-menu button { width: 100%; min-height: 34px; padding: 7px 9px; border: 0; border-radius: 6px; background: transparent; color: var(--text2); text-align: left; cursor: pointer; font: inherit; }
  .service-context-menu button:hover:not(:disabled), .service-context-menu button:focus-visible { background: var(--hover); }
  .service-context-menu button:disabled { color: var(--muted2); cursor: default; }
  .service-context-menu button.context-danger { color: #ff9b9b; }
  .service-context-separator { height: 1px; margin: 4px 3px; background: var(--border); }
  .toast { position: fixed; z-index: 1400; left: 50%; bottom: 24px; transform: translateX(-50%); max-width: min(520px, calc(100vw - 32px)); padding: 10px 14px; border: 1px solid var(--border2); border-radius: 9px; background: var(--panel); color: var(--text); box-shadow: 0 10px 34px rgba(0, 0, 0, 0.42); font-size: 13px; }
  .toast.success { background: #187a45; border-color: #2ca866; color: #fff; }
  .quick-switcher-backdrop { position: fixed; inset: 0; z-index: 1000; display: flex; justify-content: center; align-items: flex-start; padding-top: min(14vh, 120px); background: rgba(0, 0, 0, 0.46); }
  .quick-switcher { width: min(620px, calc(100vw - 32px)); max-height: min(68vh, 680px); overflow: hidden; display: flex; flex-direction: column; border: 1px solid var(--border2); border-radius: 12px; background: var(--panel); box-shadow: 0 18px 60px rgba(0, 0, 0, 0.48); }
  .quick-switcher-head { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; padding: 10px; border-bottom: 1px solid var(--border); }
  .quick-switcher-head input { width: 100%; box-sizing: border-box; min-height: 38px; }
  .quick-switcher-results { min-height: 48px; overflow-y: auto; overscroll-behavior: contain; padding: 6px; }
  .quick-switcher-item { width: 100%; min-height: 40px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 10px; border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--text2); cursor: pointer; text-align: left; font: inherit; }
  .quick-switcher-item:hover, .quick-switcher-item.active { background: var(--hover); border-color: var(--border); }
  .quick-switcher-item small { color: var(--muted); font-size: 11px; }
  .quick-switcher-item.current { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }
  .quick-switcher-item.current small { color: var(--accent-fg); opacity: 0.78; }
  .quick-switcher-empty, .quick-switcher-hint { padding: 16px; color: var(--muted); font-size: 12px; text-align: center; }
  .quick-switcher-hint { margin: 0; padding: 8px 12px; border-top: 1px solid var(--border); }

  .about-page { display: flex; flex-direction: column; gap: 26px; }
  .about-hero { display: grid; grid-template-columns: 88px minmax(0, 1fr); align-items: center; gap: 20px; padding: 4px 2px 2px; }
  .about-logo { width: 88px; height: 88px; display: block; border-radius: 20px; }
  .about-identity { min-width: 0; }
  .about-identity h3 { margin: 0; color: var(--text); font-size: 26px; line-height: 1.15; letter-spacing: -0.01em; }
  .about-version { margin: 5px 0 0; color: var(--text2); font-size: 13px; font-weight: 650; }
  .about-summary { margin: 8px 0 0; max-width: 560px; color: var(--muted); font-size: 13px; line-height: 1.5; }
  .about-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .about-link-card { appearance: none; }
  .external-indicator { color: var(--muted); font-size: 12px; font-weight: 650; white-space: nowrap; }
  .about-reference-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .reference-card { display: flex; flex-direction: column; gap: 4px; padding: 13px 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--input); color: var(--text); text-align: left; cursor: pointer; font: inherit; }
  .reference-card:hover { background: var(--hover); border-color: var(--border2); }
  .reference-card strong { font-size: 14px; }
  .reference-card span { color: var(--muted); font-size: 12px; line-height: 1.4; }
  @media (max-width: 760px) {
    .creator-grid { grid-template-columns: 1fr; }
    .settings-panel { width: calc(100% - 24px); margin: 12px auto 24px; }
    .settings-head { padding: 18px 18px 14px; }
    .settings-tabs { margin: 0 12px 9px; padding: 4px; }
    .settings-content { padding: 18px; gap: 22px; }
    .setting-card { grid-template-columns: 1fr; gap: 10px; align-items: stretch; }
    .setting-card-toggle { grid-template-columns: minmax(0, 1fr) auto; align-items: center; }
    .setting-control { width: 100%; max-width: none; }
    .setting-number { width: 100%; text-align: left; }
    .setting-actions { justify-content: flex-start; }
    .managed-row { align-items: flex-start; flex-direction: column; }
    .managed-actions { width: 100%; justify-content: flex-end; flex-wrap: wrap; }
    .workspace-detail-heading { align-items: center; }
    .workspace-name-control { min-width: 0; }
    .settings-panel .swatches { justify-content: flex-start; max-width: none; }
    .range-control { min-width: 0; }
    .settings-panel .range { flex: 1; width: auto; }
    .managed-toolbar, .workspace-create-row, .workspace-name-control, .sandbox-create-row, .backup-location-row, .audit-toolbar, .service-workspace-create, .service-workspace-create-card, .workspace-icon-current, .workspace-icon-url-row, .download-setting-row { grid-template-columns: 1fr; }
    .service-workspace-overview { flex-direction: column; }
    .service-workspace-toolbar { flex-direction: column; }
    .service-workspace-filters { width: 100%; grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .service-workspace-filters button { padding-inline: 6px; }
    .service-workspace-option { grid-template-columns: 20px 34px minmax(0, 1fr); }
    .service-workspace-state { display: none; }
    .service-shortcut-policy { grid-template-columns: 1fr; }
    .service-shortcut-effective { grid-column: auto; }
    .color-picker-preview-row { grid-template-columns: 48px minmax(0, 1fr); }
    .color-preview { display: none; }
    .slider-field { grid-template-columns: 1fr; gap: 5px; }
    .sidebar-width-control { grid-template-columns: 1fr auto; }
    .keybinding-control { justify-content: flex-start; }
    .keybinding-control kbd { flex: 1; max-width: none; }
    .sandbox-select { width: 100%; margin-left: 0; }
    .about-hero { grid-template-columns: 64px minmax(0, 1fr); gap: 14px; }
    .about-logo { width: 64px; height: 64px; border-radius: 15px; }
    .about-identity h3 { font-size: 22px; }
    .about-reference-grid { grid-template-columns: 1fr; }
  }

</style>
