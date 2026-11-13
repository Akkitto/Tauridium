import { stepServiceZoomPercent } from "./ui";

/** Actions the native layer accepts from the service menu renderer. Keep in sync with `MenuAction`. */
export type ServiceMenuAction = "settings" | "reload" | "zoom-in" | "zoom-out" | "zoom-reset" | "duplicate" | "toggle";

export const SERVICE_MENU_ACTIONS: readonly ServiceMenuAction[] = [
  "settings",
  "reload",
  "zoom-in",
  "zoom-out",
  "zoom-reset",
  "duplicate",
  "toggle",
];

export interface ServiceMenuSnapshot {
  /** Identifies this opening; stale dismissals and choices are ignored by the native layer. */
  id: number;
  label: string;
  enabled: boolean;
  zoomPercent: number;
  theme: string;
  /** False where child webviews are opaque (macOS): the renderer then paints a square backdrop. */
  transparent: boolean;
  width: number;
  height: number;
}

export interface ServiceMenuActionEvent {
  serviceId: string;
  action: ServiceMenuAction;
}

export type ServiceMenuEntry =
  | { kind: "item"; action: ServiceMenuAction; label: string; disabled: boolean; danger: boolean }
  | { kind: "separator" };

// Zoom limits shared with the native layer, which rejects out-of-range requests.
const MIN_ZOOM_PERCENT = 50;
const MAX_ZOOM_PERCENT = 200;

export function serviceMenuEntries(menu: Pick<ServiceMenuSnapshot, "enabled" | "zoomPercent">): ServiceMenuEntry[] {
  const item = (action: ServiceMenuAction, label: string, disabled = false, danger = false): ServiceMenuEntry => ({
    kind: "item",
    action,
    label,
    disabled,
    danger,
  });
  const separator: ServiceMenuEntry = { kind: "separator" };
  const zoom = menu.zoomPercent;
  return [
    item("settings", "Settings"),
    item("reload", "Reload", !menu.enabled),
    separator,
    item("zoom-in", `Zoom in (${stepServiceZoomPercent(zoom, 1)}%)`, zoom >= MAX_ZOOM_PERCENT),
    item("zoom-out", `Zoom out (${stepServiceZoomPercent(zoom, -1)}%)`, zoom <= MIN_ZOOM_PERCENT),
    item("zoom-reset", "Reset zoom (100%)", zoom === 100),
    separator,
    item("duplicate", "Duplicate"),
    separator,
    item("toggle", menu.enabled ? "Disable" : "Enable", false, menu.enabled),
  ];
}

/** Index of the next enabled item for a navigation key, or null when the key is not navigation. */
export function nextMenuIndex(key: string, current: number, enabled: boolean[]): number | null {
  const count = enabled.length;
  if (!count || !enabled.some(Boolean)) return null;
  const step = (from: number, direction: 1 | -1) => {
    for (let offset = 1; offset <= count; offset += 1) {
      const index = (from + direction * offset + count * 2) % count;
      if (enabled[index]) return index;
    }
    return null;
  };
  if (key === "ArrowDown") return step(current, 1);
  if (key === "ArrowUp") return step(current < 0 ? 0 : current, -1);
  if (key === "Home") return enabled.indexOf(true);
  if (key === "End") return enabled.lastIndexOf(true);
  return null;
}
