// Pure UI helpers kept here for isolated Vitest coverage.

// Use a dark foreground for bright colors and white otherwise, based on perceived luminance.
export function accentFg(hex: string): string {
  const h = hex.replace("#", "");
  if (h.length < 6) return "#ffffff";
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return lum > 0.6 ? "#1f2230" : "#ffffff";
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
