// Pure helpers for ad blocking settings. Rust owns list handling and
// enforcement; the shell only resolves which settings apply to a service.

export interface ServiceAdblockOverride {
  enabled?: boolean;
  allowlist?: string[];
}

/** A field set to `null` is cleared (inherits the global value again). */
export interface ServiceAdblockPatch {
  enabled?: boolean | null;
  allowlist?: string[] | null;
}

export interface AdblockSettings {
  adblockEnabled: boolean;
  adblockLists: string[];
  adblockCustomLists: string[];
  adblockAllowlist: string[];
  serviceAdblock: Record<string, ServiceAdblockOverride>;
}

const hasOwn = (value: object, key: string): boolean => Object.hasOwn(value, key);

/** Whether blocking is on for a service once the override is applied. */
export function resolveEffectiveAdblock(settings: Pick<AdblockSettings, "adblockEnabled" | "serviceAdblock">, serviceId: string): boolean {
  const override = hasOwn(settings.serviceAdblock, serviceId) ? settings.serviceAdblock[serviceId] : undefined;
  return override?.enabled ?? settings.adblockEnabled;
}

/**
 * Applies a patch to one service's override and drops the entry when nothing
 * is left, which the backend requires (it rejects empty override objects).
 */
export function withServiceAdblockPatch(
  current: Readonly<Record<string, ServiceAdblockOverride>>,
  serviceId: string,
  patch: ServiceAdblockPatch,
): Record<string, ServiceAdblockOverride> {
  const next: Record<string, ServiceAdblockOverride> = {};
  for (const [id, value] of Object.entries(current)) {
    Object.defineProperty(next, id, { value, enumerable: true, configurable: true, writable: true });
  }
  const entry: ServiceAdblockOverride = hasOwn(current, serviceId) ? { ...current[serviceId] } : {};
  if (patch.enabled === null) delete entry.enabled;
  else if (patch.enabled !== undefined) entry.enabled = patch.enabled;
  if (patch.allowlist === null) delete entry.allowlist;
  else if (patch.allowlist !== undefined) entry.allowlist = [...patch.allowlist];
  if (entry.allowlist !== undefined && entry.allowlist.length === 0) delete entry.allowlist;
  if (Object.keys(entry).length === 0) delete next[serviceId];
  else Object.defineProperty(next, serviceId, { value: entry, enumerable: true, configurable: true, writable: true });
  return next;
}

/** Adds or removes one id, keeping order and uniqueness. */
export function toggleListId(current: readonly string[], id: string, selected: boolean): string[] {
  const without = current.filter((candidate) => candidate !== id);
  return selected ? [...without, id] : without;
}

/** Splits free text (commas, spaces or lines) into site entries. */
export function splitSiteInput(text: string): string[] {
  return text
    .split(/[\s,;]+/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

/** Short status line for a filter list row. */
export function describeListStatus(list: { status: string; lastUpdated: number | null; ruleCount: number; lastError: string | null }, now = Date.now()): string {
  if (list.status === "waiting") return "Waiting to download";
  if (list.status === "error") return list.lastError ?? "Unavailable";
  const rules = `${list.ruleCount.toLocaleString("en-US")} rules`;
  if (list.lastUpdated === null) return rules;
  const days = Math.floor((now - list.lastUpdated * 1000) / 86_400_000);
  const age = days <= 0 ? "updated today" : days === 1 ? "updated yesterday" : `updated ${days} days ago`;
  return list.lastError ? `${rules}, ${age} (latest update failed)` : `${rules}, ${age}`;
}
