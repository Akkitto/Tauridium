import type { KeybindingAction } from "./ui";

export const SETTINGS_TABS = [
  ["general", "General"], ["services", "Services"], ["workspaces", "Workspaces"],
  ["appearance", "Appearance"], ["keybindings", "Keybinds"], ["sandbox", "Sandbox"],
  ["privacy", "Privacy"], ["backup", "Backup"], ["audit", "Audit log"],
  ["advanced", "Advanced"], ["updates", "Updates"], ["about", "About"],
] as const;
export type SettingsTab = typeof SETTINGS_TABS[number][0];

export const KEYBINDING_SETTINGS = [
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
  ["zoomIn", "Zoom in", "Increase page zoom for the active service."],
  ["zoomOut", "Zoom out", "Decrease page zoom for the active service."],
  ["resetZoom", "Reset zoom", "Restore the active service to 100% page zoom."],
  ["toggleDevtools", "Toggle Developer Tools", "Open or close developer tools for the active service."],
] as const satisfies readonly (readonly [KeybindingAction, string, string])[];

export interface SettingsSearchContext {
  windows: boolean;
  flatpak: boolean;
  portalDownloads: boolean;
}
export interface SettingsSearchEntry {
  readonly id: string;
  readonly tab: SettingsTab;
  readonly label: string;
  readonly description: string;
  readonly target: string;
  readonly keywords?: string;
  readonly only?: "windows" | "flatpak" | "desktop-tray" | "direct-downloads" | "portal-downloads";
  readonly fallback?: { readonly target: string; readonly message: string };
  readonly workspaceList?: boolean;
  readonly focusContainer?: boolean;
}
function setting(id: string, tab: SettingsTab, label: string, description: string,
  options: Partial<Omit<SettingsSearchEntry, "id" | "tab" | "label" | "description">> = {}): SettingsSearchEntry {
  return { id, tab, label, description, target: `settings-option-${id}`, ...options };
}
export function settingsTabLabel(tab: SettingsTab): string {
  return SETTINGS_TABS.find(([id]) => id === tab)?.[1] ?? tab;
}

// Curated UI metadata only. Never index persisted values, paths, service names, audit events or credentials.
export const SETTINGS_SEARCH_ENTRIES: readonly SettingsSearchEntry[] = [
  ...SETTINGS_TABS.map(([tab, label]) => setting(`tab-${tab}`, tab, label, `Open ${label} settings.`, {
    target: `settings-tab-${tab}`, focusContainer: true,
  })),
  setting("autostart", "general", "Launch at login", "Start Tauridium with your desktop session.", { keywords: "autostart startup boot automatic" }),
  setting("startMinimized", "general", "Start in background", "Start with the main window hidden.", { only: "desktop-tray", keywords: "minimized startup launch tray" }),
  setting("closeToSystemTray", "general", "Close to tray", "Keep Tauridium running when its window closes.", { only: "desktop-tray", keywords: "background minimize quit exit notification area" }),
  setting("portalStartup", "general", "Background/tray startup", "Flatpak keeps the main window recoverable; background and tray startup options are disabled.", { only: "flatpak", target: "settings-general-startup", focusContainer: true }),
  setting("manageServices", "services", "Configured services", "Manage individual services, notifications, zoom, icons and service preferences.", { target: "settings-services-configured", keywords: "mute unread badge rename edit proxy" }),
  setting("serviceExport", "services", "Portable service export", "Export selected services and personal recipes.", { keywords: "share sharing bundle include all personal recipes custom websites executable scripts", focusContainer: true }),
  setting("showDisabledServices", "services", "Show disabled services", "Keep disabled services visible in the sidebar."),
  setting("showServiceName", "services", "Show service names", "Display service names beside sidebar icons."),
  setting("showMessageBadgeWhenMuted", "services", "Unread badges for muted services", "Keep unread counts visible when notifications are muted.", { keywords: "bubbles message counter" }),
  setting("hibernationTimer", "services", "Hibernate inactive services", "Unload inactive service views while retaining their sessions.", { keywords: "memory performance suspend sleep timer" }),
  setting("preloadServices", "services", "Preload services", "Load services in the background for faster switching.", { keywords: "memory performance startup" }),
  setting("manageWorkspaces", "workspaces", "Configured workspaces", "Choose a workspace to edit its name, icon, services or download folder.", { target: "settings-workspaces-configured", workspaceList: true, keywords: "workspace preferences downloads directory membership rename" }),
  setting("defaultWorkspaceId", "workspaces", "Default workspace", "Choose the workspace selected at startup.", { workspaceList: true }),
  setting("restoreLastWorkspace", "workspaces", "Restore last workspace on startup", "Reopen the last selected workspace.", { workspaceList: true }),
  setting("workspaceQuickSwitchOrder", "workspaces", "Workspace switch order", "Order workspaces alphabetically, manually or by recent use.", { workspaceList: true, keywords: "quick switcher sorting" }),
  setting("workspaceHistory", "workspaces", "Workspace usage history", "Reset remembered workspace-use times.", { workspaceList: true, keywords: "recent recency clear history" }),
  setting("theme", "appearance", "Theme", "Use system, light, dark or black OLED appearance.", { keywords: "colors colour mode" }),
  setting("accentColor", "appearance", "Accent color", "Choose the interface accent and preset palette.", { keywords: "colour swatches" }),
  setting("customAccent", "appearance", "Custom accent", "Add your own accent color.", { keywords: "colour palette hex" }),
  setting("showWorkspaceInWindowTitle", "appearance", "Workspace in window title", "Show workspace context in the native title bar."),
  setting("showWorkspaceInTaskbarTitle", "appearance", "Workspace in taskbar title", "Show workspace context in the taskbar or app-icon label.", { keywords: "dock" }),
  setting("customTitleTemplatesEnabled", "appearance", "Custom title templates", "Enable variable-based window and taskbar titles."),
  setting("windowTitleTemplate", "appearance", "Window title template", "Customize the window title format.", { fallback: { target: "settings-option-customTitleTemplatesEnabled", message: "Enable Custom title templates to edit the window title format." } }),
  setting("taskbarTitleTemplate", "appearance", "Taskbar title template", "Customize the taskbar or app-icon title format.", { fallback: { target: "settings-option-customTitleTemplatesEnabled", message: "Enable Custom title templates to edit the taskbar title format." } }),
  setting("sidebarCollapsed", "appearance", "Collapse sidebar", "Switch between an icon rail and the expanded sidebar."),
  setting("sidebarStartupCollapsed", "appearance", "Default sidebar state", "Choose whether the sidebar starts collapsed or expanded."),
  setting("restoreLastSidebarState", "appearance", "Restore last sidebar state on startup", "Remember whether the sidebar was collapsed."),
  setting("sidebarWidth", "appearance", "Expanded sidebar width", "Adjust sidebar width in pixels or percent."),
  setting("collapsedIconSpacing", "appearance", "Collapsed icon spacing", "Adjust spacing in the icon-only sidebar."),
  setting("expandedServiceSpacing", "appearance", "Expanded service spacing", "Adjust spacing between expanded sidebar entries."),
  setting("iconSize", "appearance", "Service icon size", "Resize service icons in the sidebar."),
  setting("serviceListAlignment", "appearance", "Service list alignment", "Align the service list within the sidebar."),
  setting("grayscaleServices", "appearance", "Grayscale inactive icons", "Desaturate inactive service icons."),
  setting("inactiveIconDimming", "appearance", "Inactive icon dimming", "Adjust the opacity of inactive icons."),
  ...KEYBINDING_SETTINGS.map(([action, label, description]) => setting(`keybinding-${action}`, "keybindings", `${label} shortcut`, description, { keywords: "keyboard hotkey keybind chord", focusContainer: true })),
  setting("sandboxes", "sandbox", "Shared sandboxes", "Create groups that deliberately share browser sessions.", { target: "settings-sandbox-groups", keywords: "cookies login isolation profiles" }),
  setting("sandboxAssignments", "sandbox", "Service assignments", "Assign services to shared sandboxes.", { target: "settings-sandbox-services", keywords: "cookies session isolation" }),
  setting("privateNotifications", "privacy", "Private notifications", "Hide sender and message content in desktop notifications."),
  setting("manualBackup", "backup", "Manual backup", "Export or restore Tauridium settings, workspaces and recipes.", { target: "settings-backup-manual", keywords: "recovery restore import export data", focusContainer: true }),
  setting("automaticBackupSchedule", "backup", "Automatic backup schedule", "Choose startup, daily, weekly or monthly backups."),
  setting("automaticBackupDirectory", "backup", "Automatic backup output folder", "Choose where recovery copies are stored; Flatpak uses private application storage.", { keywords: "directory location destination" }),
  setting("automaticBackupRetentionMode", "backup", "Backup retention strategy", "Keep backups by count, age or tiered history.", { keywords: "cleanup pruning GFS daily weekly monthly yearly" }),
  setting("automaticBackupRetention", "backup", "Newest backups to keep", "Choose how many recent verified backups to retain.", { fallback: { target: "settings-option-automaticBackupRetentionMode", message: "Choose a retention strategy that includes a backup count to show this control." } }),
  setting("automaticBackupMaxAgeDays", "backup", "Maximum backup age", "Choose the maximum age of automatic backups in days.", { fallback: { target: "settings-option-automaticBackupRetentionMode", message: "Choose a retention strategy that includes maximum age to show this control." } }),
  setting("auditLog", "audit", "Audit log", "Review, filter, export or clear recorded application events.", { target: "settings-audit-log", keywords: "diagnostics history warnings errors" }),
  setting("unifiedTitleBar", "advanced", "Unified title bar", "Choose unified or classic Windows window chrome.", { only: "windows", keywords: "menu bar decorations caption" }),
  setting("prettyServiceContextMenu", "advanced", "Use original service context menu", "Choose Tauridium's styled right-click menu or the native system menu."),
  setting("sidebarServiceDragReorder", "advanced", "Drag to reorder services", "Rearrange services directly in the sidebar.", { keywords: "drag drop ordering" }),
  setting("captureServiceShortcuts", "advanced", "Capture Tauridium shortcuts inside services", "Choose keyboard shortcut priority while a website has focus."),
  setting("downloadDirectory", "advanced", "Default download directory", "Choose where websites save downloaded files.", { only: "direct-downloads", keywords: "folder destination location attachments" }),
  setting("askEachDownload", "advanced", "Ask where to save each download", "Use a Save dialog for each downloaded file.", { only: "direct-downloads", keywords: "destination prompt attachments" }),
  setting("portalDownloads", "advanced", "Portal-selected download destination", "Choose each download's file and folder through the desktop portal.", { only: "portal-downloads", target: "settings-advanced-downloads", keywords: "save directory attachments" }),
  setting("downloadToasts", "advanced", "Show download completion toasts", "Show a bottom-of-window notification after a successful download.", { keywords: "automatic downloaded files popup" }),
  setting("downloadToastLocation", "advanced", "Download notification saved location", "Choose filename, folder name, full file path or partial path.", { keywords: "directory toast privacy" }),
  setting("downloadToastParentLevels", "advanced", "Parent folders to show", "Choose how many parent directories appear in download notifications.", { fallback: { target: "settings-option-downloadToastLocation", message: "Choose Partial file path under Saved location to show this control." }, keywords: "partial path levels toast" }),
  setting("downloadToastDuration", "advanced", "Download notification display time", "Set toast duration or keep it visible until dismissed.", { keywords: "seconds timeout" }),
  setting("userAgentPref", "advanced", "Custom user agent", "Override browser identification for service compatibility.", { keywords: "browser identity ua" }),
  setting("fetchMissingServiceIcons", "advanced", "Fetch preferred website icons automatically", "Cache website icons for services that prefer them.", { keywords: "favicon" }),
  setting("refetchIcons", "advanced", "Refetch preferred website icons", "Refresh the cached icons of services that prefer website icons.", { keywords: "favicon cache" }),
  setting("customUrlTemplatesEnabled", "advanced", "Enable custom URL placeholders for all services", "Allow reusable custom ID values in service URLs.", { keywords: "templates custom_id_1 custom_id_2" }),
  setting("reloadToasts", "advanced", "Show reload notifications", "Show confirmation after a service reloads.", { keywords: "toast feedback" }),
  setting("account", "advanced", "Account and server", "Review local mode or the connected Ferdium server.", { target: "settings-advanced-account", keywords: "login connection profile" }),
  setting("keybindingDefaults", "keybindings", "Restore default keybindings", "Reset all keyboard shortcuts to their defaults.", { keywords: "hotkeys reset", focusContainer: true }),
  setting("automaticBackupNow", "backup", "Back up now", "Create a verified automatic backup immediately.", { keywords: "run backup now", focusContainer: true }),
  setting("currentVersion", "updates", "Current version and updates", "Review the installed version and check for signed updates.", { target: "settings-updates-version", focusContainer: true }),
  setting("projectSource", "about", "Repository", "Open the project's source code and repository.", { target: "about-project-heading", keywords: "github source code", focusContainer: true }),
  setting("projectIssues", "about", "Issues and feature requests", "Find where to report bugs or suggest improvements.", { target: "about-project-heading", keywords: "github feedback bug report", focusContainer: true }),
  setting("license", "about", "License", "Review Tauridium's licensing information.", { target: "about-legal-heading", focusContainer: true }),
  setting("author", "about", "Project author", "Review the application's author information.", { target: "about-author-heading", focusContainer: true }),
  setting("technology", "about", "Technology", "Review the components used to build Tauridium.", { target: "about-technology-heading", keywords: "Tauri Rust Svelte WebView2 WebKit GStreamer", focusContainer: true }),

];

export function normalizeSettingsQuery(value: string): string {
  return value.slice(0, 200).replace(/([a-z0-9])([A-Z])/g, "$1 $2").normalize("NFKD")
    .replace(/\p{M}/gu, "").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
}
function available(entry: SettingsSearchEntry, context: SettingsSearchContext): boolean {
  switch (entry.only) {
    case "windows": return context.windows;
    case "flatpak": return context.flatpak;
    case "desktop-tray": return !context.flatpak;
    case "direct-downloads": return !context.portalDownloads;
    case "portal-downloads": return context.portalDownloads;
    default: return true;
  }
}
export function searchSettings(query: string, context: SettingsSearchContext): SettingsSearchEntry[] {
  const normalized = normalizeSettingsQuery(query);
  if (!normalized) return [];
  const words = [...new Set(normalized.split(/\s+/).map((word) => word.length > 3 && word.endsWith("s") && !word.endsWith("ss") ? word.slice(0, -1) : word))];
  return SETTINGS_SEARCH_ENTRIES.filter((entry) => available(entry, context)).map((entry, order) => {
    const label = normalizeSettingsQuery(entry.label);
    const titleWords = label.split(" ");
    // Metadata is bounded and independent of any persisted setting value.
    const haystack = [entry.label, entry.description, entry.keywords ?? "", settingsTabLabel(entry.tab), entry.tab, entry.id]
      .map(normalizeSettingsQuery).join(" ");
    if (!words.every((word) => haystack.includes(word))) return { entry, order, score: -1 };
    const score = (label === normalized ? 1000 : label.startsWith(normalized) ? 700 : label.includes(normalized) ? 400 : 0)
      + words.reduce((total, word) => total + (label.includes(word) ? 30 : 0) + (titleWords.some((part) => part.startsWith(word)) ? 20 : 0), 0);
    return { entry, order, score };
  }).filter((match) => match.score >= 0).sort((a, b) => b.score - a.score || a.order - b.order).map(({ entry }) => entry);
}
