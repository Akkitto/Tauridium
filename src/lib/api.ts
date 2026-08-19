import { invoke } from "@tauri-apps/api/core";

// Models mirror the Ferdium server API (/v1).
export interface MeUser {
  email: string;
  firstname: string;
  lastname: string;
  id: string;
  locale?: string;
  local?: boolean;
  [k: string]: unknown;
}

export interface Service {
  id: string;
  name: string;
  recipeId: string;
  iconUrl: string | null;
  isEnabled: boolean;
  isMuted?: boolean;
  isNotificationEnabled?: boolean;
  isBadgeEnabled?: boolean;
  isMediaBadgeEnabled?: boolean;
  isIndirectMessageBadgeEnabled?: boolean;
  isHibernationEnabled?: boolean;
  isWakeUpEnabled?: boolean;
  trapLinkClicks?: boolean;
  useFavicon?: boolean;
  isDarkModeEnabled?: boolean;
  isProgressbarEnabled?: boolean;
  onlyShowFavoritesInUnreadCount?: boolean;
  darkReaderBrightness?: number;
  darkReaderContrast?: number;
  darkReaderSepia?: number;
  isProxyFeatureEnabled?: boolean;
  proxyHost?: string;
  proxyPort?: string | number;
  proxyUser?: string;
  proxyPassword?: string;
  customUrl?: string;
  team?: string;
  userAgentPref?: string;
  order?: number;
  workspaces?: string[];
  isLocalRecipe?: boolean;
  [k: string]: unknown;
}

export interface RecipePreview {
  id: string;
  name: string;
  description?: string;
  source?: "bundled" | "custom" | "remote";
  icons?: { svg?: string };
  [k: string]: unknown;
}

export interface RecipeDraft {
  id: string;
  name: string;
  serviceUrl: string;
  description: string;
  hasCustomUrl: boolean;
  hasTeamId: boolean;
  iconSvg: string;
  webviewJs: string;
}

export interface RecipeStorageInfo {
  configDir: string;
  recipesDir: string;
}

export interface Workspace {
  id: string;
  name: string;
  order: number;
  services: string[];
  userId: number | string;
}

export const DEFAULT_SERVER = "https://api.ferdium.org";

// All HTTP requests originate from Rust (no CORS issue; the token stays outside JavaScript).
export function login(
  server: string,
  email: string,
  password: string,
): Promise<MeUser> {
  return invoke("login", { server, email, password });
}

export function startLocalSession(): Promise<MeUser> {
  return invoke("start_local_session");
}

export function getServices(): Promise<Service[]> {
  return invoke("get_services");
}

export function getWorkspaces(): Promise<Workspace[]> {
  return invoke("get_workspaces");
}

// Restore a saved session (rejects when missing or expired).
export function restoreSession(): Promise<MeUser> {
  return invoke("restore_session");
}

export function logout(): Promise<void> {
  return invoke("logout");
}

// Phase 2: show the active service in an isolated child webview.
// Dark-mode settings sent to the backend (null when disabled, so Dark Reader is not injected).
function darkArg(s: Service) {
  return s.isDarkModeEnabled
    ? {
        enabled: true,
        brightness: s.darkReaderBrightness ?? null,
        contrast: s.darkReaderContrast ?? null,
        sepia: s.darkReaderSepia ?? null,
      }
    : null;
}

function serviceViewRequest(s: Service) {
  return {
    serviceId: s.id,
    recipeId: s.recipeId,
    customUrl: (s.customUrl as string | undefined) ?? null,
    team: (s.team as string | undefined) ?? null,
    userAgentPref: (s.userAgentPref as string | undefined) ?? null,
    dark: darkArg(s),
  };
}

export function showService(s: Service): Promise<void> {
  return invoke("show_service", { request: serviceViewRequest(s) });
}

// Preload a service off-screen for near-instant switching.
export function preloadService(s: Service): Promise<void> {
  return invoke("preload_service", { request: serviceViewRequest(s) });
}

export function closeService(serviceId: string): Promise<void> {
  return invoke("close_service", { serviceId });
}

export function closeServices(): Promise<void> {
  return invoke("close_services");
}

export function hideServices(): Promise<void> {
  return invoke("hide_all_services");
}

export function openExternalUrl(url: string): Promise<void> {
  return invoke("open_external_url", { url });
}

export function reloadActiveService(): Promise<void> {
  return invoke("reload_active_service_command");
}

export function reloadTauridium(): Promise<void> {
  return invoke("reload_app_command");
}

export function toggleDeveloperTools(): Promise<void> {
  return invoke("toggle_devtools_command");
}

// Push service notification/mute/badge settings respected by the Rust poller.
export function setServiceFlags(s: Service): Promise<void> {
  return invoke("set_service_flags", {
    serviceId: s.id,
    notif: s.isNotificationEnabled !== false,
    muted: s.isMuted === true,
    badge: s.isBadgeEnabled !== false,
  });
}

export function updateService(
  serviceId: string,
  patch: Record<string, unknown>,
): Promise<unknown> {
  return invoke("update_service", { serviceId, patch });
}

export function createService(name: string, recipeId: string): Promise<unknown> {
  return invoke("create_service", { name, recipeId });
}

export function createCustomWebsiteService(name: string, url: string): Promise<unknown> {
  return invoke("create_custom_website_service", { name, url });
}

export function deleteService(serviceId: string): Promise<void> {
  return invoke("delete_service", { serviceId });
}

// Clear a service cache/session by closing its webview and purging persistent storage.
export function clearServiceCache(serviceId: string): Promise<void> {
  return invoke("clear_service_cache", { serviceId });
}

export function clearSandbox(sandboxId: string): Promise<void> {
  return invoke("clear_sandbox", { sandboxId });
}

export function listRecipes(): Promise<RecipePreview[]> {
  return invoke("list_recipes");
}

export function getRecipeStorageInfo(): Promise<RecipeStorageInfo> {
  return invoke("get_recipe_storage_info");
}

export function saveCustomRecipe(draft: RecipeDraft): Promise<unknown> {
  return invoke("save_custom_recipe", { draft });
}

export function importCustomRecipe(path: string): Promise<RecipePreview> {
  return invoke("import_custom_recipe", { path });
}

export function createWorkspace(name: string): Promise<Workspace> {
  return invoke("create_workspace", { name });
}

export function updateWorkspace(
  workspaceId: string,
  name: string,
  services: string[],
): Promise<Workspace> {
  return invoke("update_workspace", { workspaceId, name, services });
}

export function deleteWorkspace(workspaceId: string): Promise<void> {
  return invoke("delete_workspace", { workspaceId });
}

export interface AppSettings {
  autostart: boolean;
  startMinimized: boolean;
  theme: "dark" | "light" | "oled" | "system";
  accentColor: string;
  customAccentColors: string[];
  closeToSystemTray: boolean;
  privateNotifications: boolean;
  showDisabledServices: boolean;
  showServiceName: boolean;
  showMessageBadgeWhenMuted: boolean;
  userAgentPref: string;
  sidebarWidth: number;
  sidebarWidthMode: "pixels" | "percent";
  sidebarWidthPercent: number;
  customSidebarWidths: number[];
  iconSize: number;
  grayscaleServices: boolean;
  grayscaleDim: number;
  sidebarServicesLocation: "top" | "center" | "bottom";
  hibernationTimer: number;
  preloadServices: boolean;
  serviceOrder: string[];
  workspaceOrder: string[];
  keybindings: Record<string, string>;
  sandboxes: SandboxDefinition[];
  serviceSandboxes: Record<string, string>;
  automaticBackupSchedule: "off" | "startup" | "daily" | "weekly" | "monthly";
  automaticBackupDirectory: string;
  automaticBackupRetentionMode: "count" | "age" | "countAndAge" | "tiered";
  automaticBackupRetention: number;
  automaticBackupMaxAgeDays: number;
  lastAutomaticBackupAt: number;
  [k: string]: unknown;
}

export interface SandboxDefinition {
  id: string;
  name: string;
}

export function setSidebarWidth(width: number): Promise<void> {
  return invoke("set_sidebar_width", { width });
}

export function getAppSettings(): Promise<AppSettings> {
  return invoke("get_app_settings");
}

export function setServiceOrder(serviceIds: string[]): Promise<AppSettings> {
  return invoke("set_service_order", { serviceIds });
}

export function setWorkspaceOrder(workspaceIds: string[]): Promise<AppSettings> {
  return invoke("set_workspace_order", { workspaceIds });
}

export interface NativeServiceMenuEntry {
  id: string;
  name: string;
  enabled: boolean;
}

export function syncServicesMenu(services: NativeServiceMenuEntry[]): Promise<void> {
  return invoke("sync_services_menu", { services });
}

export function setAppSettings(
  patch: Partial<AppSettings>,
): Promise<AppSettings> {
  return invoke("set_app_settings", { patch });
}

export interface BackupSummary {
  path: string;
  schema: number;
  sourceSchema: number;
  integrityVerified: boolean;
  customRecipeCount: number;
  serviceCount: number;
  workspaceCount: number;
  recoveryBackupPath?: string;
  warnings?: string[];
}

export function exportBackup(path: string): Promise<BackupSummary> {
  return invoke("export_backup", { path });
}

export function restoreBackup(path: string): Promise<BackupSummary> {
  return invoke("restore_backup", { path });
}

export function createAutomaticBackup(filename: string): Promise<BackupSummary> {
  return invoke("create_automatic_backup", { filename });
}

export interface PortablePayload {
  services: Service[];
  workspaces: Workspace[];
  sandboxes: SandboxDefinition[];
  serviceSandboxes: Record<string, string>;
}

export interface PortableSummary {
  path: string;
  kind: "sandbox" | "sandboxes" | "workspace" | "workspaces";
  serviceCount: number;
  workspaceCount: number;
  sandboxCount: number;
  customRecipeCount: number;
  integrityVerified: boolean;
}

export function exportPortableBundle(
  path: string,
  kind: PortableSummary["kind"],
  payload: PortablePayload,
): Promise<PortableSummary> {
  return invoke("export_portable_bundle", { path, kind, payload });
}

export interface AuditEntry {
  timestampUnixMs: number;
  level: "info" | "warning" | "error" | string;
  category: string;
  action: string;
  outcome: string;
  message: string;
  details: unknown;
}

export function getAuditLog(limit = 500): Promise<AuditEntry[]> {
  return invoke("get_audit_log", { limit });
}

export function exportAuditLog(path: string): Promise<number> {
  return invoke("export_audit_log", { path });
}

export function clearAuditLog(): Promise<void> {
  return invoke("clear_audit_log");
}
