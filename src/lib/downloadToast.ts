import type { AppSettings } from "./api";

export interface DownloadCompletion {
  id: number;
  filename: string;
  location: string | null;
  locationLabel: string;
  count: number;
}

export interface DownloadToastSnapshot {
  completion: DownloadCompletion | null;
  waiting: number;
  duration: number;
  theme: string;
  active: boolean;
}

/** Example data only; never fetch a user's real filesystem path for previews. */
export function downloadToastPreview(
  mode: AppSettings["downloadToastLocation"],
  parentLevels: number,
  windows: boolean,
): string | null {
  if (mode === "none") return null;
  if (mode === "directory") return "Reports";
  const parts = windows
    ? ["C:", "Users", "You", "Downloads", "Reports", "example.pdf"]
    : ["", "home", "you", "Downloads", "Reports", "example.pdf"];
  const separator = windows ? "\\" : "/";
  const levels = Math.max(1, Math.min(10, Math.trunc(parentLevels) || 2));
  return mode === "partial" && levels < parts.length - 2
    ? ["…", ...parts.slice(-(levels + 1))].join(separator)
    : parts.join(separator);
}

/** Pauseable countdown: notification updates/burst counts do not reset time. */
export class ToastCountdown {
  private timer: ReturnType<typeof setTimeout> | null = null;
  private remaining: number;
  private startedAt = 0;
  private finished = false;

  constructor(seconds: number, private readonly expire: () => void) {
    this.remaining = Math.max(0, seconds) * 1000;
  }

  resume() {
    if (this.timer !== null || this.finished || this.remaining === 0) return;
    this.startedAt = performance.now();
    this.timer = setTimeout(() => {
      this.timer = null;
      this.remaining = 0;
      this.finished = true;
      this.expire();
    }, this.remaining);
  }

  pause() {
    if (this.timer === null) return;
    clearTimeout(this.timer);
    this.timer = null;
    this.remaining = Math.max(1, this.remaining - (performance.now() - this.startedAt));
  }

  dispose() {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.finished = true;
  }
}
