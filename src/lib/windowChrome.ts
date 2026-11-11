/** Roving native-menu keyboard navigation; all other keys retain their action. */
export function menuKeyIndex(key: string, selected: number, length: number): number | null {
  if (!Number.isInteger(length) || length < 1) return null;
  if (key === "ArrowRight") return (selected + 1) % length;
  if (key === "ArrowLeft") return (selected + length - 1) % length;
  if (key === "Home") return 0;
  if (key === "End") return length - 1;
  return null;
}
