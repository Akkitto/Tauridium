// Pure helpers for spelling settings. The native engines do the checking;
// the shell only resolves which settings apply to a service.

export interface ServiceSpellcheckOverride {
  enabled?: boolean;
  languages?: string[];
}

export interface SpellcheckSettings {
  spellcheckEnabled: boolean;
  spellcheckLanguages: string[];
  serviceSpellcheck: Record<string, ServiceSpellcheckOverride>;
}

export interface EffectiveSpellcheck {
  enabled: boolean;
  /** Empty means "use the system language". */
  languages: string[];
}

/** A field set to `null` is cleared (inherits the global value again). */
export interface ServiceSpellcheckPatch {
  enabled?: boolean | null;
  languages?: string[] | null;
}

const hasOwn = (value: object, key: string): boolean => Object.hasOwn(value, key);

export function resolveEffectiveSpellcheck(settings: SpellcheckSettings, serviceId: string): EffectiveSpellcheck {
  const override = hasOwn(settings.serviceSpellcheck, serviceId) ? settings.serviceSpellcheck[serviceId] : undefined;
  return {
    enabled: override?.enabled ?? settings.spellcheckEnabled,
    languages: [...(override?.languages ?? settings.spellcheckLanguages)],
  };
}

/** Adds or removes one language, keeping order and never duplicating. */
export function toggleLanguage(languages: readonly string[], tag: string, selected: boolean): string[] {
  const without = languages.filter((existing) => existing !== tag);
  return selected ? [...without, tag] : without;
}

/**
 * Returns a copy of the per-service map with the patch applied. `null` clears a
 * field and an override with no fields left is dropped, matching what the
 * backend accepts (it rejects empty override objects).
 */
export function withServiceSpellcheckPatch(
  current: Readonly<Record<string, ServiceSpellcheckOverride>>,
  serviceId: string,
  patch: ServiceSpellcheckPatch,
): Record<string, ServiceSpellcheckOverride> {
  const next: Record<string, ServiceSpellcheckOverride> = {};
  for (const [id, value] of Object.entries(current)) {
    Object.defineProperty(next, id, { value, enumerable: true, configurable: true, writable: true });
  }
  const entry: ServiceSpellcheckOverride = hasOwn(current, serviceId) ? { ...current[serviceId] } : {};
  if (patch.enabled === null) delete entry.enabled;
  else if (patch.enabled !== undefined) entry.enabled = patch.enabled;
  if (patch.languages === null) delete entry.languages;
  else if (patch.languages !== undefined) entry.languages = [...patch.languages];
  if (Object.keys(entry).length === 0) delete next[serviceId];
  else Object.defineProperty(next, serviceId, { value: entry, enumerable: true, configurable: true, writable: true });
  return next;
}
