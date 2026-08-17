// Helpers d'UI purs — isolés ici pour être testables unitairement (vitest).

// Couleur de texte lisible sur une couleur d'accent : noir si l'accent est clair
// (jaune…), blanc sinon. Basé sur la luminance perçue.
export function accentFg(hex: string): string {
  const h = hex.replace("#", "");
  if (h.length < 6) return "#ffffff";
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return lum > 0.6 ? "#1f2230" : "#ffffff";
}

// URL de l'icône d'une recette (repo ferdium-recipes).
export function recipeIcon(recipeId: string): string {
  return `https://raw.githubusercontent.com/ferdium/ferdium-recipes/main/recipes/${recipeId}/icon.svg`;
}

// Icône d'un service : icône custom du serveur sinon celle de la recette.
export function iconSrc(s: { iconUrl?: string | null; recipeId: string }): string {
  return s.iconUrl || recipeIcon(s.recipeId);
}

// Filtre + tri du catalogue de recettes (écran d'ajout de service).
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

// Ramène une taille d'icône sur le niveau Ferdium valide le plus proche.
export function snapIconSize(size: number): number {
  const sizes = [18, 21, 24, 28, 34];
  if (sizes.includes(size)) return size;
  return sizes.reduce((a, b) => (Math.abs(b - size) < Math.abs(a - size) ? b : a));
}


// Produit un identifiant de recipe local stable et sûr à partir d'un nom lisible.
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
