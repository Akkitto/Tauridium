// Pure UI helpers kept here for isolated Vitest coverage.

// Choose black or white according to WCAG relative-luminance contrast.
export function accentFg(hex: string): string {
  const normalized = normalizeHexColor(hex);
  if (!normalized) return "#ffffff";
  const channels = [1, 3, 5].map((index) => parseInt(normalized.slice(index, index + 2), 16) / 255);
  const linear = channels.map((channel) =>
    channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4,
  );
  const luminance = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
  const blackContrast = (luminance + 0.05) / 0.05;
  const whiteContrast = 1.05 / (luminance + 0.05);
  return blackContrast >= whiteContrast ? "#000000" : "#ffffff";
}

export function normalizeHexColor(value: string): string | null {
  const trimmed = value.trim().toLowerCase();
  if (/^#[0-9a-f]{6}$/.test(trimmed)) return trimmed;
  if (/^[0-9a-f]{6}$/.test(trimmed)) return `#${trimmed}`;
  return null;
}

export function hslToHex(hue: number, saturation: number, lightness: number): string {
  const h = ((hue % 360) + 360) % 360;
  const s = Math.max(0, Math.min(100, saturation)) / 100;
  const l = Math.max(0, Math.min(100, lightness)) / 100;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  const [r1, g1, b1] =
    h < 60
      ? [c, x, 0]
      : h < 120
        ? [x, c, 0]
        : h < 180
          ? [0, c, x]
          : h < 240
            ? [0, x, c]
            : h < 300
              ? [x, 0, c]
              : [c, 0, x];
  const channel = (value: number) => Math.round((value + m) * 255).toString(16).padStart(2, "0");
  return `#${channel(r1)}${channel(g1)}${channel(b1)}`;
}

export function hexToHsl(hex: string): { hue: number; saturation: number; lightness: number } {
  const normalized = normalizeHexColor(hex) ?? "#ffc131";
  const r = parseInt(normalized.slice(1, 3), 16) / 255;
  const g = parseInt(normalized.slice(3, 5), 16) / 255;
  const b = parseInt(normalized.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const delta = max - min;
  const lightness = (max + min) / 2;
  let hue = 0;
  if (delta !== 0) {
    if (max === r) hue = 60 * (((g - b) / delta) % 6);
    else if (max === g) hue = 60 * ((b - r) / delta + 2);
    else hue = 60 * ((r - g) / delta + 4);
  }
  if (hue < 0) hue += 360;
  const saturation = delta === 0 ? 0 : delta / (1 - Math.abs(2 * lightness - 1));
  return {
    hue,
    saturation: saturation * 100,
    lightness: lightness * 100,
  };
}

export const DEFAULT_KEYBINDINGS = {
  quickWorkspaceSwitch: "Ctrl+D",
  quickServiceSwitch: "Ctrl+S",
  openSettings: "Ctrl+,",
  addService: "Ctrl+N",
  addWorkspace: "Ctrl+Shift+N",
  nextService: "Ctrl+Tab",
  previousService: "Ctrl+Shift+Tab",
  nextWorkspace: "Ctrl+Alt+ArrowDown",
  previousWorkspace: "Ctrl+Alt+ArrowUp",
  reloadService: "Ctrl+R",
  reloadApp: "Ctrl+Shift+R",
  toggleDevtools: "Ctrl+Alt+I",
} as const;

export type KeybindingAction = keyof typeof DEFAULT_KEYBINDINGS;

function canonicalShortcutKey(event: Pick<KeyboardEvent, "key" | "code">): string | null {
  const modifierKeys = new Set(["Control", "Shift", "Alt", "Meta"]);
  if (modifierKeys.has(event.key)) return null;

  // Use physical codes for the keys used by Tauridium's defaults. This keeps native-menu,
  // shell, and service-webview matching consistent across keyboard layouts and avoids
  // browser-specific transformations of punctuation while Ctrl/Alt are held.
  if (/^Key[A-Z]$/.test(event.code)) return event.code.slice(3);
  if (/^Digit[0-9]$/.test(event.code)) return event.code.slice(5);
  const codeKeys: Record<string, string> = {
    Comma: ",",
    Period: ".",
    Minus: "-",
    Equal: "=",
    Semicolon: ";",
    Quote: "'",
    BracketLeft: "[",
    BracketRight: "]",
    Backslash: "\\",
    Backquote: "`",
    Space: "Space",
    Tab: "Tab",
    ArrowDown: "ArrowDown",
    ArrowUp: "ArrowUp",
    ArrowLeft: "ArrowLeft",
    ArrowRight: "ArrowRight",
  };
  if (codeKeys[event.code]) return codeKeys[event.code];

  let key = event.key;
  if (key === " ") key = "Space";
  else if (key.length === 1) key = key.toUpperCase();
  return key || null;
}

export function keyStrokeFromEvent(event: KeyboardEvent): string | null {
  const key = canonicalShortcutKey(event);
  if (!key) return null;
  const parts: string[] = [];
  if (event.ctrlKey) parts.push("Ctrl");
  if (event.altKey) parts.push("Alt");
  if (event.shiftKey) parts.push("Shift");
  if (event.metaKey) parts.push("Meta");
  parts.push(key);
  return parts.join("+");
}

export function bindingStrokes(binding: string): string[] {
  return binding
    .trim()
    .split(/\s+/)
    .map((stroke) => stroke.trim())
    .filter(Boolean)
    .slice(0, 2);
}

export function duplicateServiceName(name: string, existingNames: string[]): string {
  const normalizedName = name.trim() || "Service";
  const base = `${normalizedName} Copy`;
  const used = new Set(existingNames.map((candidate) => candidate.trim().toLocaleLowerCase()));
  if (!used.has(base.toLocaleLowerCase())) return base;
  for (let index = 2; index < 10_000; index += 1) {
    const candidate = `${base} ${index}`;
    if (!used.has(candidate.toLocaleLowerCase())) return candidate;
  }
  return `${base} 10000`;
}

export function shortcutConflicts(bindings: Record<string, string>): Map<string, string[]> {
  const grouped = new Map<string, string[]>();
  for (const [action, binding] of Object.entries(bindings)) {
    const normalized = bindingStrokes(binding).join(" ");
    if (!normalized) continue;
    grouped.set(normalized, [...(grouped.get(normalized) ?? []), action]);
  }
  return new Map([...grouped].filter(([, actions]) => actions.length > 1));
}

export function paged<T>(items: T[], page: number, pageSize: number): T[] {
  const safeSize = Math.max(1, Math.floor(pageSize));
  const safePage = Math.max(0, Math.floor(page));
  return items.slice(safePage * safeSize, safePage * safeSize + safeSize);
}

export function resolveStartupWorkspaceId(
  workspaceIds: Iterable<string>,
  defaultWorkspaceId: string,
  restoreLastWorkspaceOnStartup: boolean,
  lastWorkspaceId: string,
): string | null {
  const configured = new Set(workspaceIds);
  const resolve = (workspaceId: string): string | null | undefined => {
    if (!workspaceId) return null;
    return configured.has(workspaceId) ? workspaceId : undefined;
  };
  if (restoreLastWorkspaceOnStartup) {
    const last = resolve(lastWorkspaceId);
    if (last !== undefined) return last;
  }
  const fallback = resolve(defaultWorkspaceId);
  return fallback === undefined ? null : fallback;
}

// Recipe icon URL from the ferdium-recipes repository.
export function recipeIcon(recipeId: string): string {
  return `https://raw.githubusercontent.com/ferdium/ferdium-recipes/main/recipes/${recipeId}/icon.svg`;
}

// Service icon: use the server-provided custom icon, otherwise the recipe icon.
export function iconSrc(s: { iconUrl?: string | null; recipeId: string }): string {
  return s.iconUrl || recipeIcon(s.recipeId);
}

// Filter and sort the recipe catalog used by the add-service screen.
export function filterRecipes<T extends { id: string; name: string }>(
  recipes: T[],
  query: string,
): T[] {
  const q = query.trim().toLowerCase();
  const list = q
    ? recipes.filter(
        (r) =>
          r.name.toLowerCase().includes(q) || r.id.toLowerCase().includes(q),
      )
    : recipes;
  return [...list].sort((a, b) => a.name.localeCompare(b.name));
}

// Clamp an icon size to the nearest valid Ferdium size level.
export function snapIconSize(size: number): number {
  const sizes = [18, 21, 24, 28, 34];
  if (sizes.includes(size)) return size;
  return sizes.reduce((a, b) => (Math.abs(b - size) < Math.abs(a - size) ? b : a));
}


// Produce a stable, safe local recipe ID from a human-readable name.
export function recipeIdFromName(name: string): string {
  const id = name
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-");
  return id || "custom-recipe";
}

export function normalizeWebsiteUrl(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
}

export function websiteName(value: string): string {
  try {
    return new URL(normalizeWebsiteUrl(value)).hostname.replace(/^www\./, "") || "Custom Website";
  } catch {
    return "Custom Website";
  }
}

export function looksLikeWebsite(value: string): boolean {
  const candidate = value.trim();
  return /^https?:\/\//i.test(candidate) || /^[^\s]+\.[^\s]+/.test(candidate);
}

// Apply a persisted id order while preserving a deterministic fallback for newly discovered items.
export function orderedBySavedIds<T extends { id: string; order?: number }>(
  items: T[],
  savedIds: string[] | undefined,
): T[] {
  const rank = new Map((savedIds ?? []).map((id, index) => [id, index]));
  const fallbackBase = rank.size + 1;
  return [...items].sort((a, b) => {
    const aRank = rank.get(a.id);
    const bRank = rank.get(b.id);
    if (aRank !== undefined || bRank !== undefined) {
      if (aRank === undefined) return 1;
      if (bRank === undefined) return -1;
      return aRank - bRank;
    }
    const byOrder = (a.order ?? fallbackBase) - (b.order ?? fallbackBase);
    return byOrder || a.id.localeCompare(b.id);
  });
}

export type ReorderPlacement = "before" | "after";

// Reorder only the currently visible subset while leaving hidden/filter-excluded slots stable.
// Invalid/duplicate input is treated as a no-op so a stale drag event can never corrupt canonical order.
export function reorderVisibleSubsetAt(
  fullIds: string[],
  visibleIds: string[],
  fromId: string,
  toId: string,
  placement: ReorderPlacement,
): string[] {
  const fullSet = new Set(fullIds);
  if (fullSet.size !== fullIds.length) return [...fullIds];

  const seenVisible = new Set<string>();
  const subset = visibleIds.filter((id) => {
    if (!fullSet.has(id) || seenVisible.has(id)) return false;
    seenVisible.add(id);
    return true;
  });
  if (subset.length < 2 || fromId === toId) return [...fullIds];
  const fromIndex = subset.indexOf(fromId);
  if (fromIndex < 0 || !subset.includes(toId)) return [...fullIds];

  const [moved] = subset.splice(fromIndex, 1);
  const targetIndex = subset.indexOf(toId);
  if (targetIndex < 0) return [...fullIds];
  const insertIndex = placement === "after" ? targetIndex + 1 : targetIndex;
  subset.splice(insertIndex, 0, moved);

  const visibleSet = new Set(subset);
  let nextVisible = 0;
  return fullIds.map((id) => (visibleSet.has(id) ? subset[nextVisible++] : id));
}

export function contiguousIdRange(ids: string[], anchorId: string, targetId: string): string[] {
  const unique = new Set(ids);
  if (unique.size !== ids.length) return [];
  const anchorIndex = ids.indexOf(anchorId);
  const targetIndex = ids.indexOf(targetId);
  if (anchorIndex < 0 || targetIndex < 0) return [];
  const start = Math.min(anchorIndex, targetIndex);
  const end = Math.max(anchorIndex, targetIndex);
  return ids.slice(start, end + 1);
}

// Move a selected visible block as one unit while leaving filtered/hidden canonical slots stable.
// Selection order always follows the visible canonical order, never click order.
export function reorderVisibleGroupAt(
  fullIds: string[],
  visibleIds: string[],
  movedIds: string[],
  toId: string,
  placement: ReorderPlacement,
): string[] {
  const fullSet = new Set(fullIds);
  if (fullSet.size !== fullIds.length) return [...fullIds];

  const seenVisible = new Set<string>();
  const subset = visibleIds.filter((id) => {
    if (!fullSet.has(id) || seenVisible.has(id)) return false;
    seenVisible.add(id);
    return true;
  });
  if (!subset.includes(toId)) return [...fullIds];

  const requested = new Set(movedIds);
  const selected = subset.filter((id) => requested.has(id));
  if (!selected.length || selected.includes(toId)) return [...fullIds];

  const selectedSet = new Set(selected);
  const remaining = subset.filter((id) => !selectedSet.has(id));
  const targetIndex = remaining.indexOf(toId);
  if (targetIndex < 0) return [...fullIds];
  const insertIndex = placement === "after" ? targetIndex + 1 : targetIndex;
  remaining.splice(insertIndex, 0, ...selected);

  const visibleSet = new Set(subset);
  let nextVisible = 0;
  return fullIds.map((id) => (visibleSet.has(id) ? remaining[nextVisible++] : id));
}

export function reorderVisibleSubset(
  fullIds: string[],
  visibleIds: string[],
  fromId: string,
  toId: string,
): string[] {
  const subset = visibleIds.filter((id) => fullIds.includes(id));
  const fromIndex = subset.indexOf(fromId);
  const toIndex = subset.indexOf(toId);
  if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) return [...fullIds];
  return reorderVisibleSubsetAt(
    fullIds,
    visibleIds,
    fromId,
    toId,
    fromIndex < toIndex ? "after" : "before",
  );
}


export type WorkspaceQuickSwitchOrder =
  | "custom"
  | "customReverse"
  | "alphabetical"
  | "alphabeticalReverse"
  | "recent"
  | "recentReverse";

export function orderWorkspacesForQuickSwitch<T extends { id: string; name: string }>(
  workspaces: T[],
  mode: WorkspaceQuickSwitchOrder,
  lastUsed: Record<string, number>,
): T[] {
  const custom = [...workspaces];
  const customRank = new Map(custom.map((workspace, index) => [workspace.id, index]));
  const alphabetical = (a: T, b: T) =>
    a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }) ||
    a.id.localeCompare(b.id);
  const recent = (a: T, b: T) =>
    (lastUsed[b.id] ?? 0) - (lastUsed[a.id] ?? 0) ||
    (customRank.get(a.id) ?? Number.MAX_SAFE_INTEGER) -
      (customRank.get(b.id) ?? Number.MAX_SAFE_INTEGER);

  switch (mode) {
    case "customReverse":
      return custom.reverse();
    case "alphabetical":
      return custom.sort(alphabetical);
    case "alphabeticalReverse":
      return custom.sort((a, b) => alphabetical(b, a));
    case "recent":
      return custom.sort(recent);
    case "recentReverse":
      return custom.sort((a, b) => recent(b, a));
    case "custom":
    default:
      return custom;
  }
}

export function serviceLabel(service: { name?: string | null; recipeId?: string | null }): string {
  const name = service.name?.trim();
  if (name) return name;
  const recipeId = service.recipeId?.trim();
  return recipeId || "Unnamed service";
}

export function sameDownloadPreference(
  left: { directory: string; askEachDownload: boolean } | null | undefined,
  right: { directory: string; askEachDownload: boolean } | null | undefined,
): boolean {
  if (!left || !right) return left == null && right == null;
  return left.directory === right.directory && left.askEachDownload === right.askEachDownload;
}


export type AutomaticBackupSchedule = "off" | "startup" | "daily" | "weekly" | "monthly";

export function backupTimestamp(date = new Date()): string {
  const pad = (value: number, width = 2) => String(value).padStart(width, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}-${pad(date.getMilliseconds(), 3)}`;
}

export function automaticBackupDue(
  schedule: AutomaticBackupSchedule,
  lastRun: number,
  now: number,
  startup: boolean,
  startupHandled: boolean,
): boolean {
  if (schedule === "off") return false;
  if (schedule === "startup") return startup && !startupHandled;
  if (lastRun <= 0) return true;
  if (schedule === "monthly") {
    const due = new Date(lastRun);
    const day = due.getDate();
    due.setDate(1);
    due.setMonth(due.getMonth() + 1);
    const lastDay = new Date(due.getFullYear(), due.getMonth() + 1, 0).getDate();
    due.setDate(Math.min(day, lastDay));
    return now >= due.getTime();
  }
  const elapsed = Math.max(0, now - Math.max(0, lastRun));
  const interval = schedule === "daily" ? 24 * 60 * 60 * 1000 : 7 * 24 * 60 * 60 * 1000;
  return elapsed >= interval;
}
