<script lang="ts">
  import { onMount } from "svelte";
  import tauridiumLogo from "./assets/tauridium.svg";
  import { listen } from "@tauri-apps/api/event";
  import {
    accentFg,
    iconSrc,
    filterRecipes,
    snapIconSize,
    recipeIdFromName,
    normalizeWebsiteUrl,
    websiteName,
    looksLikeWebsite,
  } from "./lib/ui";
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
    listRecipes,
    getRecipeStorageInfo,
    saveCustomRecipe,
    importCustomRecipe,
    createWorkspace,
    updateWorkspace,
    deleteWorkspace,
    getAppSettings,
    setAppSettings,
    setSidebarWidth,
    exportBackup,
    restoreBackup,
    openExternalUrl,
    DEFAULT_SERVER,
    type MeUser,
    type Service,
    type Workspace,
    type RecipePreview,
    type RecipeDraft,
    type RecipeStorageInfo,
    type AppSettings,
    type BackupSummary,
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
  // Per-service loading state emitted by the backend through on_page_load.
  let statusMap = $state<Record<string, "loading" | "ready">>({});
  // Error opening the active service (showService rejected it: broken recipe, invalid URL, etc.).
  let serviceLoadError = $state<string | null>(null);
  // Reorder services with drag and drop.
  let dragId = $state<string | null>(null);
  let dragOverId = $state<string | null>(null);
  let activeWorkspace = $state<string | null>(null);

  type View = "service" | "svcSettings" | "add" | "appSettings" | "workspaces";
  let view = $state<View>("service");
  let settingsSvc = $state<Service | null>(null);
  let svcDirty = $state(false); // Service settings changed but not saved yet.
  let svcReload = $state(false); // A field requiring reload (URL/team/UA) changed.
  let newWorkspaceName = $state("");

  type Tab = "general" | "services" | "appearance" | "privacy" | "advanced" | "updates" | "about";
  let settingsTab = $state<Tab>("general");

  // Updates (automatic updater).
  let appVer = $state("");
  let updateInfo = $state<Update | null>(null);
  let updChecking = $state(false);
  let updInstalling = $state(false);
  let updStatus = $state("");

  // Portable backup/export state.
  let backupBusy = $state(false);
  let backupStatus = $state("");

  let appSettings = $state<AppSettings>({
    autostart: false,
    startMinimized: false,
    theme: "system",
    accentColor: "#ffc131",
    closeToSystemTray: true,
    privateNotifications: false,
    showDisabledServices: true,
    showServiceName: true,
    showMessageBadgeWhenMuted: true,
    userAgentPref: "",
    sidebarWidth: 240,
    iconSize: 24,
    grayscaleServices: false,
    grayscaleDim: 50,
    sidebarServicesLocation: "top",
    hibernationTimer: 0,
    preloadServices: true,
  });

  // Hibernation: suspended services have their webview closed while retaining the session.
  let hibernated = $state<Set<string>>(new Set());
  const hibTimers = new Map<string, ReturnType<typeof setTimeout>>();
  let preloadCancelled = false; // Cancels the preload chain on logout or session change.

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
  const sorted = $derived(
    [...services].sort((a, b) => (a.order ?? 0) - (b.order ?? 0)),
  );
  const visibleServices = $derived.by(() => {
    let list = sorted;
    if (activeWorkspace) {
      const ws = workspaces.find((w) => w.id === activeWorkspace);
      const ids = new Set(ws?.services ?? []);
      list = list.filter((s) => ids.has(s.id));
    }
    if (!appSettings.showDisabledServices) {
      list = list.filter((s) => s.isEnabled);
    }
    return list;
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

  onMount(async () => {
    darkMq?.addEventListener("change", () => {
      if (appSettings.theme === "system") applyTheme();
    });
    listen<Record<string, number>>("unread", (e) => {
      unreadMap = e.payload;
    });
    listen<{ id: string; status: "loading" | "ready" }>("svc-status", (e) => {
      statusMap = { ...statusMap, [e.payload.id]: e.payload.status };
      // The requested service loaded, so clear any previous opening error.
      if (e.payload.status === "ready" && e.payload.id === activeId) {
        serviceLoadError = null;
      }
    });
    // Command+1..9 from the native menu switches to the Nth visible service.
    listen<number>("select-index", (e) => {
      const s = visibleServices[e.payload - 1];
      if (s) selectService(s);
    });
    // The native About menu opens the same deterministic in-app About section on every OS.
    listen("open-about", openAbout);
    try {
      appSettings = await getAppSettings();
      // Snap iconSize to a valid level for compatibility with older arbitrary values.
      const snapped = snapIconSize(appSettings.iconSize);
      if (snapped !== appSettings.iconSize) {
        appSettings.iconSize = snapped;
        setAppSettings({ iconSize: snapped }).catch(() => {});
      }
      applyTheme();
      applyLayout();
    } catch {
      /* defaults */
    }
    // Restore the session. If the server is unreachable (Ferdium outage, network issue, etc.),
    // do NOT show login; a reconnect screen retries automatically every 30 seconds.
    const restored = await attemptRestore();
    booting = false;
    if (!restored) startReconnect(attemptRestore);
    appVersion()
      .then((v) => (appVer = v))
      .catch(() => {});
    checkUpdates(true); // Silent startup check.
  });

  function applyTheme() {
    const dark =
      appSettings.theme === "dark" ||
      (appSettings.theme === "system" && (darkMq?.matches ?? true));
    document.body.classList.toggle("light", !dark);
    document.body.style.setProperty("--accent", appSettings.accentColor);
    document.body.style.setProperty("--accent-fg", accentFg(appSettings.accentColor));
  }

  // Sidebar customization: width, icon size, grayscale/dimming, and position.
  function applyLayout() {
    const b = document.body;
    b.style.setProperty("--sidebar-w", `${appSettings.sidebarWidth}px`);
    b.style.setProperty("--icon-size", `${appSettings.iconSize}px`);
    b.classList.toggle("grayscale", !!appSettings.grayscaleServices);
    // dim 0..100 controls grayscale icon opacity (100 = heavily faded).
    const op = Math.max(0.2, 1 - (appSettings.grayscaleDim ?? 50) / 130);
    b.style.setProperty("--gray-op", String(op));
    b.dataset.svcloc = appSettings.sidebarServicesLocation ?? "top";
  }

  function markIconFailed(id: string) {
    failedIcons = new Set(failedIcons).add(id);
  }

  async function loadAfterAuth() {
    [services, workspaces] = await Promise.all([getServices(), getWorkspaces()]);
    await Promise.all(services.map((s) => setServiceFlags(s).catch(() => {})));
    const first = sorted.find((s) => s.isEnabled) ?? sorted[0] ?? null;
    if (first) selectService(first);
    preloadRest(first?.id);
  }

  // Gradually preload other active services in off-screen webviews,
  // making later switches nearly instantaneous. Skip services destined for
  // hibernation because they would be unloaded, and respect the setting.
  function preloadRest(firstId: string | undefined) {
    if (!appSettings.preloadServices) return;
    preloadCancelled = false;
    const list = sorted.filter(
      (s) =>
        s.isEnabled &&
        s.id !== firstId &&
        !(appSettings.hibernationTimer > 0 && s.isHibernationEnabled === true),
    );
    let i = 0;
    const step = () => {
      if (preloadCancelled) return; // Stop after logout or session change.
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

  function selectService(s: Service) {
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
    showService(s).catch((err) => {
      // Display the error only if this service is still on screen.
      if (activeId === s.id) serviceLoadError = `${err}`;
    });
  }

  function retryActiveService() {
    const s = activeService;
    if (s) {
      statusMap = { ...statusMap, [s.id]: "loading" };
      selectService(s);
    }
  }

  // --- Service reordering (drag and drop) --------------------------------------
  function onDragStart(e: DragEvent, s: Service) {
    dragId = s.id;
    if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
  }
  function onDragOver(e: DragEvent, s: Service) {
    if (!dragId || dragId === s.id) return;
    e.preventDefault(); // autorise le drop
    dragOverId = s.id;
  }
  function onDragLeave(s: Service) {
    if (dragOverId === s.id) dragOverId = null;
  }
  function onDragEnd() {
    dragId = null;
    dragOverId = null;
  }
  async function onDrop(e: DragEvent, target: Service) {
    e.preventDefault();
    const from = dragId;
    dragId = null;
    dragOverId = null;
    if (!from || from === target.id) return;
    const list = [...sorted];
    const fromIdx = list.findIndex((s) => s.id === from);
    const toIdx = list.findIndex((s) => s.id === target.id);
    if (fromIdx < 0 || toIdx < 0) return;
    const [moved] = list.splice(fromIdx, 1);
    list.splice(toIdx, 0, moved);
    const orderById = new Map(list.map((s, i) => [s.id, i]));
    // Persist each service whose order changed (best effort).
    const updates: Promise<unknown>[] = [];
    for (const s of services) {
      const ord = orderById.get(s.id);
      if (ord !== undefined && s.order !== ord) {
        updates.push(updateService(s.id, { order: ord }).catch(() => {}));
      }
    }
    services = services.map((s) => ({
      ...s,
      order: orderById.get(s.id) ?? s.order,
    }));
    await Promise.all(updates);
  }

  function openServiceSettings(s: Service) {
    error = null;
    settingsSvc = { ...s }; // Editable copy; applied to the server on Save.
    svcDirty = false;
    svcReload = false;
    view = "svcSettings";
    hideServices();
  }

  async function persistService(reload = false) {
    if (!settingsSvc) return;
    const s = settingsSvc;
    const idx = services.findIndex((x) => x.id === s.id);
    if (idx >= 0) services[idx] = { ...s };
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
      await setServiceFlags(s);
      if (reload) {
        await closeService(s.id); // recreated on next open with new params
        const { [s.id]: _, ...rest } = statusMap;
        statusMap = rest;
      }
    } catch (err) {
      error = String(err);
    }
  }

  // Handlers modify ONLY local state; Save persists everything at once.
  // Fields whose changes require recreating the webview (script injected at creation).
  const RELOAD_FIELDS = new Set<keyof Service>([
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

  function saveNum(key: keyof Service, value: string) {
    if (!settingsSvc) return;
    const n = Number.parseInt(value, 10);
    (settingsSvc as Record<string, unknown>)[key] = Number.isNaN(n) ? undefined : n;
    svcDirty = true;
    if (RELOAD_FIELDS.has(key)) svcReload = true;
  }

  async function saveServiceSettings() {
    await persistService(svcReload);
    svcDirty = false;
    svcReload = false;
  }

  async function handleDelete(s: Service) {
    if (!(await confirmAsk(`Delete service "${s.name}"?`))) return;
    try {
      await deleteService(s.id);
      clearHibTimer(s.id); // Prevent a hibernation timer from re-adding a deleted service.
      const { [s.id]: _, ...rest } = statusMap;
      statusMap = rest;
      services = services.filter((x) => x.id !== s.id);
      backToService();
    } catch (err) {
      error = String(err);
    }
  }

  async function handleClearCache(s: Service) {
    if (
      !(await confirmAsk(
        `Clear cache & session for "${s.name}"? You'll be signed out of this service.`,
      ))
    )
      return;
    try {
      await clearServiceCache(s.id);
      clearHibTimer(s.id);
      const { [s.id]: _, ...rest } = statusMap;
      statusMap = rest;
      hibernated = new Set([...hibernated].filter((id) => id !== s.id));
      backToService(); // Reopens cleanly in a signed-out state.
    } catch (err) {
      error = String(err);
    }
  }

  function openWorkspaces() {
    error = null;
    view = "workspaces";
    newWorkspaceName = "";
    hideServices();
  }

  async function reloadWorkspaces() {
    workspaces = await getWorkspaces();
  }

  async function handleCreateWorkspace() {
    const name = newWorkspaceName.trim();
    if (!name) return;
    try {
      await createWorkspace(name);
      newWorkspaceName = "";
      await reloadWorkspaces();
    } catch (err) {
      error = String(err);
    }
  }

  async function toggleServiceInWorkspace(
    ws: Workspace,
    serviceId: string,
    member: boolean,
  ) {
    const set = new Set(ws.services);
    if (member) set.add(serviceId);
    else set.delete(serviceId);
    const list = [...set];
    const idx = workspaces.findIndex((w) => w.id === ws.id);
    if (idx >= 0) workspaces[idx].services = list;
    try {
      await updateWorkspace(ws.id, ws.name, list);
    } catch (err) {
      error = String(err);
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

  async function activateCreated(result: unknown, recipeId: string) {
    const res = result as { id?: string; data?: { id?: string }; service?: { id?: string } };
    const newId = res?.id ?? res?.data?.id ?? res?.service?.id;
    [services, workspaces] = await Promise.all([getServices(), getWorkspaces()]);
    await Promise.all(services.map((service) => setServiceFlags(service).catch(() => {})));
    const created =
      (newId && services.find((service) => service.id === newId)) ??
      [...services].reverse().find((service) => service.recipeId === recipeId) ??
      null;
    if (created) selectService(created);
    else view = "service";
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
      await activateCreated(result, "custom-website");
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
        await activateCreated(result, draft.id);
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
      await activateCreated(result, r.id);
    } catch (err) {
      error = String(err);
    }
  }

  function openAppSettings() {
    error = null;
    view = "appSettings";
    hideServices();
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
    return `tauridium-backup-${new Date().toISOString().slice(0, 10)}.json`;
  }

  function backupSummaryText(action: string, summary: BackupSummary): string {
    return `${action}: ${summary.customRecipeCount} custom recipes, ${summary.serviceCount} local services, ${summary.workspaceCount} local workspaces.`;
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

  async function saveAppSetting(key: keyof AppSettings, value: unknown) {
    (appSettings as Record<string, unknown>)[key] = value;
    if (key === "theme" || key === "accentColor") applyTheme();
    applyLayout();
    if (key === "sidebarWidth") setSidebarWidth(value as number).catch(() => {});
    try {
      appSettings = await setAppSettings({
        [key]: value,
      } as Partial<AppSettings>);
      applyTheme();
      applyLayout();
    } catch (err) {
      error = String(err);
    }
  }

  function backToService() {
    error = null;
    const target = activeService ?? sorted.find((s) => s.isEnabled) ?? sorted[0];
    if (target) selectService(target);
    else view = "service";
  }

  async function handleLogout() {
    // Cleanup prevents hibernation timers, preloading, or reconnection from the
    // previous session from continuing and recreating webviews afterward.
    preloadCancelled = true;
    for (const id of [...hibTimers.keys()]) clearHibTimer(id);
    hibernated = new Set();
    stopReconnect();
    await closeServices();
    await logout();
    me = null;
    services = [];
    workspaces = [];
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
    <aside class="sidebar">
      <div class="account">
        <strong>{me.local ? "Local only" : me.firstname || me.email}</strong>
        <button class="link" onclick={handleLogout}>sign out</button>
      </div>

      <button class="add" onclick={openAdd}>＋ Add a service</button>

      <div class="wspills">
        <button
          class="pill"
          class:on={activeWorkspace === null}
          onclick={() => (activeWorkspace = null)}>All</button>
        {#each workspaces as w (w.id)}
          <button
            class="pill"
            class:on={activeWorkspace === w.id}
            onclick={() => (activeWorkspace = w.id)}>{w.name}</button>
        {/each}
        <button class="pill mng" onclick={openWorkspaces} title="Manage workspaces">⚙</button>
      </div>

      <div class="svcarea">
        <div class="svclist">
          {#each visibleServices as s (s.id)}{@render row(s)}{/each}
        </div>
      </div>

      <button class="appcog" onclick={openAppSettings}>
        <span class="ic">⚙</span> Settings{#if updateInfo}<span class="upddot" title="Update available"></span>{/if}
      </button>
      <div class="count">
        {services.length} services · {workspaces.length} workspaces{#if appVer} · <span class="ver">v{appVer}</span>{/if}
      </div>
    </aside>

    <section class="stage">
      {#if view === "service"}
        {#if activeService}
          {#if serviceLoadError}
            <div class="placeholder">
              <h2>{activeService.name}</h2>
              <p class="load-err">Couldn't load this service.</p>
              <p class="load-err-detail">{serviceLoadError}</p>
              <button class="primary" onclick={retryActiveService}>Reload</button>
            </div>
          {:else if statusMap[activeService.id] !== "ready"}
            <div class="placeholder">
              <div class="spinner" aria-hidden="true"></div>
              <p>Loading {activeService.name}…</p>
            </div>
          {:else}
            <div class="placeholder"><h2>{activeService.name}</h2></div>
          {/if}
        {:else}
          <div class="placeholder"><p>No service selected.</p></div>
        {/if}
      {:else if view === "svcSettings" && settingsSvc}
        <div class="panel">
          <div class="panel-head">
            <h2>Settings — {settingsSvc.name}</h2>
            <span class="head-actions">
              <button class="primary sm" disabled={!svcDirty} onclick={saveServiceSettings}>
                {svcDirty ? "Save changes" : "Saved"}
              </button>
              <button class="link" onclick={backToService}>✕ close</button>
            </span>
          </div>
          <code class="recipe">recipe: {settingsSvc.recipeId}</code>

          <div class="set-title">General</div>
          <label class="block">
            Name
            <input value={settingsSvc.name} onchange={(e) => saveText("name", e.currentTarget.value)} />
          </label>
          <div class="setrow">
            <label class="block">
              Custom URL
              <input value={settingsSvc.customUrl ?? ""} placeholder="https://… (for services that support it)" onchange={(e) => saveText("customUrl", e.currentTarget.value, true)} />
            </label>
            <p class="desc">Override the service URL (self-hosted instances, custom domains). Reloads the service.</p>
          </div>
          <div class="setrow">
            <label class="block">
              Team / workspace ID
              <input value={settingsSvc.team ?? ""} placeholder="e.g. Slack team" onchange={(e) => saveText("team", e.currentTarget.value, true)} />
            </label>
            <p class="desc">For services whose URL includes a team ID (Slack, etc.). Reloads the service.</p>
          </div>

          {@render toggle("Enabled", "Load this service. Disabled services stay listed but aren't loaded.", "isEnabled", settingsSvc.isEnabled !== false)}
          {@render toggle("Notifications", "Show system notifications for new messages in this service.", "isNotificationEnabled", settingsSvc.isNotificationEnabled !== false)}
          {@render toggle("Muted", "Silence this service — no notifications at all.", "isMuted", settingsSvc.isMuted === true)}
          {@render toggle("Unread badge", `Count this service's unread messages in the ${dockWord} badge.`, "isBadgeEnabled", settingsSvc.isBadgeEnabled !== false)}
          {@render toggle("Indirect message badge", "Also count indirect (group / channel) messages in the badge.", "isIndirectMessageBadgeEnabled", settingsSvc.isIndirectMessageBadgeEnabled === true)}
          {@render toggle("Media badge", "Count calls / media activity in the badge.", "isMediaBadgeEnabled", settingsSvc.isMediaBadgeEnabled === true)}
          {@render toggle("Allow hibernation", "Let this service sleep when inactive to save memory.", "isHibernationEnabled", settingsSvc.isHibernationEnabled === true)}
          {@render toggle("Open links externally", "Open clicked links in your default browser instead of inside the service.", "trapLinkClicks", settingsSvc.trapLinkClicks === true)}
          {@render toggle("Allow wake up", "Wake this service from hibernation on new activity.", "isWakeUpEnabled", settingsSvc.isWakeUpEnabled === true)}
          {@render toggle("Only favorites in unread count", "Count unread messages only from favorite chats in this service.", "onlyShowFavoritesInUnreadCount", settingsSvc.onlyShowFavoritesInUnreadCount === true)}

          <div class="set-title">Appearance</div>
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
          {@render toggle("Use favicon as icon", "Use the site's favicon instead of the recipe icon (not rendered locally yet).", "useFavicon", settingsSvc.useFavicon === true)}
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
      {:else if view === "workspaces"}
        <div class="panel">
          <div class="panel-head">
            <h2>Workspaces</h2>
            <button class="link" onclick={backToService}>✕ close</button>
          </div>

          <div class="searchrow">
            <input bind:value={newWorkspaceName} placeholder="New workspace name" />
            <button class="primary" onclick={handleCreateWorkspace}>Create</button>
          </div>
          {#if error}<p class="error">{error}</p>{/if}

          {#each workspaces as ws (ws.id)}
            <div class="wsedit">
              <div class="wsedit-head">
                <input
                  class="wsname"
                  value={ws.name}
                  onblur={(e) => renameWorkspace(ws, e.currentTarget.value)}
                />
                <button class="link" onclick={() => handleDeleteWorkspace(ws)}>delete</button>
              </div>
              <div class="set-title">Services in this workspace</div>
              <div class="wsservices">
                {#each sorted as s (s.id)}
                  <label class="row-toggle">
                    <input
                      type="checkbox"
                      checked={ws.services.includes(s.id)}
                      onchange={(e) =>
                        toggleServiceInWorkspace(ws, s.id, e.currentTarget.checked)}
                    />
                    <span>{s.name}</span>
                  </label>
                {/each}
              </div>
            </div>
          {:else}
            <p class="sub">No workspace yet. Create one above.</p>
          {/each}
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
            {#each [["general", "General"], ["services", "Services"], ["appearance", "Appearance"], ["privacy", "Privacy"], ["advanced", "Advanced"], ["updates", "Updates"], ["about", "About"]] as [id, label] (id)}
              <button
                class="setting-tab"
                class:on={settingsTab === id}
                aria-current={settingsTab === id ? "page" : undefined}
                onclick={() => (id === "about" ? openAbout() : (settingsTab = id as Tab))}>{label}</button>
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
                      <span class="setting-description">Follow the operating system appearance or force a light or dark theme.</span>
                    </div>
                    <select class="select setting-control" aria-label="Theme" bind:value={appSettings.theme} onchange={() => saveAppSetting("theme", appSettings.theme)}>
                      <option value="system">Use system setting</option>
                      <option value="dark">Dark</option>
                      <option value="light">Light</option>
                    </select>
                  </div>
                  <div class="setting-card">
                    <div class="setting-copy">
                      <span class="setting-label">Accent color</span>
                      <span class="setting-description">Used for selected navigation, primary actions, and active-service emphasis.</span>
                    </div>
                    <div class="swatches" role="group" aria-label="Accent color">
                      {#each ["#ffc131", "#4f46e5", "#2563eb", "#0891b2", "#16a34a", "#d97706", "#dc2626", "#db2777", "#7c3aed"] as c (c)}
                        <button class="swatch" class:on={appSettings.accentColor === c} style="background:{c}" aria-label={`Use accent color ${c}`} aria-pressed={appSettings.accentColor === c} onclick={() => saveAppSetting("accentColor", c)}></button>
                      {/each}
                    </div>
                  </div>
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-appearance-sidebar">
                <div class="section-heading">
                  <h3 id="settings-appearance-sidebar">Sidebar</h3>
                  <p>Adjust service density and placement without changing individual service configuration.</p>
                </div>
                <div class="settings-list">
                  <div class="setting-card">
                    <div class="setting-copy"><span class="setting-label">Sidebar width</span><span class="setting-description">Choose the horizontal space reserved for services and workspaces.</span></div>
                    <select class="select setting-control" aria-label="Sidebar width" bind:value={appSettings.sidebarWidth} onchange={() => saveAppSetting("sidebarWidth", appSettings.sidebarWidth)}>
                      <option value={200}>Compact</option><option value={240}>Normal</option><option value={300}>Wide</option>
                    </select>
                  </div>
                  <div class="setting-card">
                    <div class="setting-copy"><span class="setting-label">Service icon size</span><span class="setting-description">Change icon size while preserving consistent sidebar spacing.</span></div>
                    <select class="select setting-control" aria-label="Service icon size" bind:value={appSettings.iconSize} onchange={() => saveAppSetting("iconSize", appSettings.iconSize)}>
                      <option value={18}>Very small</option><option value={21}>Small</option><option value={24}>Normal</option><option value={28}>Large</option><option value={34}>Very large</option>
                    </select>
                  </div>
                  <div class="setting-card">
                    <div class="setting-copy"><span class="setting-label">Service position</span><span class="setting-description">Place the service list at the top, center, or bottom of the sidebar.</span></div>
                    <select class="select setting-control" aria-label="Service position" bind:value={appSettings.sidebarServicesLocation} onchange={() => saveAppSetting("sidebarServicesLocation", appSettings.sidebarServicesLocation)}>
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
            {:else if settingsTab === "privacy"}
              <section class="settings-section" aria-labelledby="settings-privacy-notifications">
                <div class="section-heading"><h3 id="settings-privacy-notifications">Notifications</h3><p>Limit message information exposed through operating-system notifications.</p></div>
                <div class="settings-list">{@render appToggle("Private notifications", "Hide sender and message content and show only a generic new-message notification.", "privateNotifications", appSettings.privateNotifications)}</div>
              </section>
            {:else if settingsTab === "advanced"}
              <section class="settings-section" aria-labelledby="settings-advanced-browser">
                <div class="section-heading"><h3 id="settings-advanced-browser">Browser identity</h3><p>Advanced compatibility controls for services that depend on browser identification.</p></div>
                <div class="settings-list">
                  <div class="setting-card setting-card-stack">
                    <div class="setting-copy"><span class="setting-label">Custom user agent</span><span class="setting-description">Override the browser identity sent to newly opened services. Restart Tauridium to apply it everywhere.</span></div>
                    <input class="setting-text-input" value={appSettings.userAgentPref} aria-label="Custom user agent" placeholder="Leave empty to use the app default" onchange={(e) => saveAppSetting("userAgentPref", e.currentTarget.value)} />
                  </div>
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-advanced-backup">
                <div class="section-heading"><h3 id="settings-advanced-backup">Backup</h3><p>Move Tauridium-owned local configuration between installations or keep a manual recovery copy.</p></div>
                <div class="settings-list">
                  <div class="setting-card">
                    <div class="setting-copy"><span class="setting-label">Local Tauridium data</span><span class="setting-description">Exports app settings, local services and workspaces, and complete custom recipes. Ferdium login tokens, website cookies/storage, and remote caches are excluded.</span></div>
                    <div class="setting-actions"><button class="secondary sm" disabled={backupBusy} onclick={doRestoreBackup}>Restore backup…</button><button class="primary sm" disabled={backupBusy} onclick={doExportBackup}>Export backup…</button></div>
                  </div>
                  <p class="settings-note">Backups can contain sensitive local service configuration such as proxy credentials. Store them accordingly.</p>
                  {#if backupStatus}<p class="settings-status">{backupStatus}</p>{/if}
                </div>
              </section>
              <section class="settings-section" aria-labelledby="settings-advanced-account">
                <div class="section-heading"><h3 id="settings-advanced-account">{me.local ? "Account" : "Server"}</h3></div>
                <div class="settings-list">
                  <div class="setting-card info-card">
                    <div class="setting-copy"><span class="setting-label">{me.local ? "Local-only mode" : me.email}</span><span class="setting-description">{me.local ? "Services and workspaces are stored on this device without a Ferdium account." : `Connected to ${server}. Sign out to change the server.`}</span></div>
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
                  <div class="about-identity"><h3 id="about-tauridium-title">Tauridium</h3><p class="about-version">Version {appVer ? `v${appVer}` : "loading…"}</p><p class="about-summary">A lightweight Tauri desktop client for Ferdium with accountless local mode and locally managed recipes.</p></div>
                </div>
                <div class="about-actions" role="group" aria-label="Tauridium project links">
                  <button class="primary" onclick={() => openProjectLink("https://github.com/Gizmo091/Tauridium")}>Source code ↗</button>
                  <button class="secondary" onclick={() => openProjectLink("https://github.com/Gizmo091/Tauridium/releases")}>Releases ↗</button>
                  <button class="secondary" onclick={() => openProjectLink("https://github.com/Gizmo091/Tauridium/issues/new")}>Report an issue ↗</button>
                </div>
                <section class="settings-section" aria-labelledby="about-project-heading">
                  <div class="section-heading"><h3 id="about-project-heading">Project</h3><p>Open-source project information and useful destinations.</p></div>
                  <div class="settings-list">
                    <button class="setting-card about-link-card" onclick={() => openProjectLink("https://github.com/Gizmo091/Tauridium")}><span class="setting-copy"><span class="setting-label">Repository</span><span class="setting-description">github.com/Gizmo091/Tauridium</span></span><span class="external-indicator" aria-hidden="true">Open ↗</span></button>
                    <button class="setting-card about-link-card" onclick={() => openProjectLink("https://github.com/Gizmo091/Tauridium/issues")}><span class="setting-copy"><span class="setting-label">Issues and feature requests</span><span class="setting-description">Report a problem, follow known issues, or propose an improvement.</span></span><span class="external-indicator" aria-hidden="true">Open ↗</span></button>
                  </div>
                </section>
                <section class="settings-section" aria-labelledby="about-legal-heading">
                  <div class="section-heading"><h3 id="about-legal-heading">Legal</h3></div>
                  <div class="settings-list"><button class="setting-card about-link-card" onclick={() => openProjectLink("https://github.com/Gizmo091/Tauridium/blob/master/LICENSE")"><span class="setting-copy"><span class="setting-label">MIT License</span><span class="setting-description">Copyright © 2026 Mathieu Vedie. View the complete license text.</span></span><span class="external-indicator" aria-hidden="true">View ↗</span></button></div>
                </section>
                <section class="settings-section" aria-labelledby="about-credits-heading">
                  <div class="section-heading"><h3 id="about-credits-heading">Credits</h3></div>
                  <div class="settings-list"><div class="setting-card info-card"><span class="setting-copy"><span class="setting-label">Maintainer</span><span class="setting-description">Mathieu Vedie</span></span><button class="secondary sm" onclick={() => openProjectLink("https://github.com/Gizmo091/Tauridium/graphs/contributors")}>Contributors ↗</button></div></div>
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

{#snippet row(s: Service)}
  <div
    class="srow-wrap"
    class:drag-over={dragOverId === s.id}
    class:dragging={dragId === s.id}
    draggable="true"
    role="listitem"
    ondragstart={(e) => onDragStart(e, s)}
    ondragover={(e) => onDragOver(e, s)}
    ondragleave={() => onDragLeave(s)}
    ondrop={(e) => onDrop(e, s)}
    ondragend={onDragEnd}
  >
    <button
      class="srow"
      class:active={s.id === activeId && view === "service"}
      class:disabled={!s.isEnabled}
      class:asleep={hibernated.has(s.id)}
      onclick={() => selectService(s)}
    >
      {#if failedIcons.has(s.id)}
        <span class="dot">{s.name.slice(0, 1)}</span>
      {:else}
        <img class="svc-icon" src={iconSrc(s)} alt="" onerror={() => markIconFailed(s.id)} />
      {/if}
      {#if appSettings.showServiceName}
        <span class="srow-name">{s.name}</span>
      {/if}
      {#if hibernated.has(s.id)}<span class="zzz" title="Hibernated">💤</span>{/if}
      {#if (unreadMap[s.id] ?? 0) > 0 && (s.isMuted !== true || appSettings.showMessageBadgeWhenMuted)}
        <span class="ubadge" class:muted={s.isMuted === true}>
          {unreadMap[s.id] > 99 ? "99+" : unreadMap[s.id]}
        </span>
      {/if}
    </button>
    <button class="cog" title="Settings" onclick={() => openServiceSettings(s)}>⚙</button>
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
    background: var(--sidebar); padding: 12px; overflow: hidden;
    display: flex; flex-direction: column; gap: 12px;
  }
  .svcarea { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow-y: auto; }
  :global(body[data-svcloc="center"]) .svcarea { justify-content: center; }
  :global(body[data-svcloc="bottom"]) .svcarea { justify-content: flex-end; }
  .account { display: flex; justify-content: space-between; align-items: center; font-size: 13px; }
  .link { background: none; border: none; color: var(--link); cursor: pointer; font-size: 12px; text-decoration: underline; }
  .add {
    background: var(--hover); border: 1px dashed var(--border2); color: var(--accent-soft);
    border-radius: 8px; padding: 8px; cursor: pointer; font-size: 13px;
  }
  .add:hover { filter: brightness(1.1); }
  .wspills { display: flex; flex-wrap: wrap; gap: 5px; }
  .pill {
    background: var(--hover); border: none; color: var(--muted);
    border-radius: 999px; padding: 3px 10px; cursor: pointer; font-size: 12px;
  }
  .pill.on { background: var(--accent); color: var(--accent-fg); }
  .pill.mng { background: transparent; border: 1px dashed var(--border2); color: var(--muted); font-size: 15px; line-height: 1; padding: 2px 9px; }
  .svclist { display: flex; flex-direction: column; gap: 2px; }

  .srow-wrap { display: flex; align-items: center; position: relative; }
  .srow-wrap.dragging { opacity: 0.4; }
  .srow-wrap.drag-over::before {
    content: ""; position: absolute; left: 6px; right: 6px; top: -1px;
    height: 2px; background: var(--accent); border-radius: 2px;
  }
  .srow {
    display: flex; align-items: center; gap: 9px; flex: 1; min-width: 0;
    padding: 7px 8px; border: none; border-radius: 8px; background: none;
    color: var(--text2); cursor: pointer; text-align: left; font-size: 14px;
  }
  .srow:hover { background: var(--hover); }
  .srow.active { background: var(--accent); color: var(--accent-fg); }
  .srow.disabled { opacity: 0.45; }
  .srow.asleep .svc-icon, .srow.asleep .dot { filter: grayscale(1); opacity: 0.5; }
  .zzz { margin-left: auto; font-size: 12px; opacity: 0.8; }
  .svc-icon, .srow .dot { width: var(--icon-size, 22px); height: var(--icon-size, 22px); border-radius: 5px; object-fit: cover; flex: none; }
  .srow .dot { display: grid; place-items: center; background: var(--border2); font-size: 12px; font-weight: 700; }
  :global(body.grayscale) .svc-icon { filter: grayscale(1); opacity: var(--gray-op, 0.6); transition: filter 0.15s, opacity 0.15s; }
  :global(body.grayscale) .srow:hover .svc-icon,
  :global(body.grayscale) .srow.active .svc-icon { filter: none; opacity: 1; }
  .srow-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ubadge {
    margin-left: auto; background: #e23b3b; color: #fff; font-size: 11px; font-weight: 700;
    min-width: 18px; height: 18px; padding: 0 5px; border-radius: 9px; flex: none;
    display: inline-flex; align-items: center; justify-content: center;
  }
  .ubadge.muted { background: var(--muted2); }
  .cog { background: none; border: none; color: var(--muted2); cursor: pointer; font-size: 21px; line-height: 1; opacity: 0; padding: 2px 4px; }
  .srow-wrap:hover .cog { opacity: 1; }
  .cog:hover { color: var(--accent-soft); }
  .appcog {
    background: var(--hover); border: 1px solid var(--border);
    color: var(--text2); border-radius: 8px; padding: 9px; cursor: pointer; font-size: 13px;
    display: inline-flex; align-items: center; justify-content: center; gap: 7px;
  }
  .appcog .ic { font-size: 19px; line-height: 1; }
  .upddot { width: 8px; height: 8px; border-radius: 999px; background: #22c55e; display: inline-block; margin-left: 2px; }
  .appcog:hover { filter: brightness(1.1); }
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
  .tabs { display: flex; gap: 4px; flex-wrap: wrap; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
  .tab { background: none; border: none; color: var(--muted); cursor: pointer; font-size: 13px; padding: 5px 10px; border-radius: 8px; }
  .tab.on { background: var(--hover); color: var(--text); }
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
  .searchrow { display: flex; gap: 8px; }
  .searchrow input { flex: 1; }
  .wsedit {
    display: flex; flex-direction: column; gap: 8px; padding: 12px;
    border: 1px solid var(--border); border-radius: 10px; background: var(--input);
  }
  .wsedit-head { display: flex; gap: 10px; align-items: center; }
  .wsname { flex: 1; }
  .wsservices { display: flex; flex-direction: column; gap: 4px; max-height: 30vh; overflow-y: auto; }
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

  .settings-panel {
    width: min(820px, calc(100% - 48px)); margin: 24px auto 40px; padding: 0; gap: 0; overflow: hidden;
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
    display: flex; gap: 4px; overflow-x: auto; padding: 0 18px 10px;
    border-bottom: 1px solid var(--border); scrollbar-width: thin;
  }
  .setting-tab {
    flex: none; padding: 8px 11px; border: 1px solid transparent; border-radius: 8px;
    background: transparent; color: var(--muted); cursor: pointer; font: inherit;
    font-size: 13px; font-weight: 600; line-height: 1.2;
  }
  .setting-tab:hover { background: var(--hover); color: var(--text2); }
  .setting-tab.on { background: var(--hover); border-color: var(--border); color: var(--text); }
  .settings-content { display: flex; flex-direction: column; gap: 26px; padding: 24px; min-height: 260px; }
  .settings-section { display: flex; flex-direction: column; gap: 10px; }
  .section-heading { display: flex; flex-direction: column; gap: 4px; padding: 0 2px; }
  .section-heading h3 { margin: 0; font-size: 13px; line-height: 1.3; font-weight: 700; color: var(--text); }
  .section-heading p { margin: 0; max-width: 620px; color: var(--muted); font-size: 12.5px; line-height: 1.45; }
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
  .setting-description { max-width: 560px; color: var(--muted); font-size: 12.5px; line-height: 1.45; font-weight: 400; }
  .setting-control { min-width: 176px; max-width: 230px; margin-left: 0; }
  .setting-text-input { width: 100%; box-sizing: border-box; }
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
  .settings-panel .swatch { width: 24px; height: 24px; border: 1px solid rgba(255,255,255,0.18); }
  .range-control { display: flex; align-items: center; gap: 10px; color: var(--muted); font-size: 12px; min-width: 180px; }
  .settings-panel .range { width: 140px; margin-left: 0; }
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
    .settings-tabs { padding: 0 12px 9px; }
    .settings-content { padding: 18px; gap: 22px; }
    .setting-card { grid-template-columns: 1fr; gap: 10px; align-items: stretch; }
    .setting-card-toggle { grid-template-columns: minmax(0, 1fr) auto; align-items: center; }
    .setting-control { width: 100%; max-width: none; }
    .setting-actions { justify-content: flex-start; }
    .settings-panel .swatches { justify-content: flex-start; max-width: none; }
    .range-control { min-width: 0; }
    .settings-panel .range { flex: 1; width: auto; }
    .about-hero { grid-template-columns: 64px minmax(0, 1fr); gap: 14px; }
    .about-logo { width: 64px; height: 64px; border-radius: 15px; }
    .about-identity h3 { font-size: 22px; }
    .about-reference-grid { grid-template-columns: 1fr; }
  }

</style>
