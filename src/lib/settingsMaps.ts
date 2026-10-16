import type { DownloadPreferenceOverride } from "./api";

// Service/workspace IDs are data, including names inherited by ordinary objects.
export function ownValue<T>(values: Readonly<Record<string, T>> | null | undefined, key: string): T | undefined {
  return values != null && Object.hasOwn(values, key) ? values[key] : undefined;
}

export function setOwnValue<T>(values: Record<string, T>, key: string, value: T): void {
  Object.defineProperty(values, key, { value, enumerable: true, configurable: true, writable: true });
}

export function copyOwnEntry<T>(values: Record<string, T>, source: string, destination: string): void {
  const value = ownValue(values, source);
  if (value !== undefined) {
    // These settings are flat records. Spreading also unwraps a Svelte reactive
    // proxy; structuredClone would reject that proxy during service duplication.
    const copied = value !== null && typeof value === "object" ? { ...value } : value;
    setOwnValue(values, destination, copied);
  }
}

export function downloadOverride(values: Readonly<Record<string, unknown>> | null | undefined, key: string): DownloadPreferenceOverride | null {
  const value = ownValue(values, key);
  if (value === null || typeof value !== "object" || Array.isArray(value)
      || !Object.hasOwn(value, "directory") || !Object.hasOwn(value, "askEachDownload")
      || !("directory" in value) || typeof value.directory !== "string"
      || !("askEachDownload" in value) || typeof value.askEachDownload !== "boolean") return null;
  return { directory: value.directory, askEachDownload: value.askEachDownload };
}

export function downloadDirectoryLabel(directory: string): string {
  return directory.trim() || "System Downloads folder";
}
