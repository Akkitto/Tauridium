export type ServiceMenuAction = "settings" | "reload" | "zoom-in" | "zoom-out" | "zoom-reset" | "duplicate" | "toggle";

export interface ServiceMenuRequest {
  serviceId: string;
  label: string;
  enabled: boolean;
  zoomPercent: number;
  x: number;
  y: number;
  pixelRatio: number;
  theme: "light" | "dark" | "oled";
}

export interface ServiceMenuSnapshot {
  revision: number;
  menu: ServiceMenuRequest | null;
}

interface Port {
  prepare(request: ServiceMenuRequest): Promise<number>;
  present(id: number): Promise<boolean>;
  close(id: number, restoreFocus: boolean): Promise<void>;
  fallback(request: ServiceMenuRequest, isCurrent: () => boolean): Promise<void>;
  error(error: unknown): void;
}

// Only one preparation runs at a time. An intent is invalidated immediately,
// including while native creation, pointer release or presentation is pending.
export class ServiceMenuController {
  private intent = 0;
  private queue: Promise<void> = Promise.resolve();
  private current: { intent: number; id?: number; presenting?: boolean; request: ServiceMenuRequest; release?: (released: boolean) => void } | null = null;

  constructor(private readonly port: Port) {}

  get isOpen(): boolean { return this.current !== null; }

  open(request: ServiceMenuRequest, pointerHeld = false): Promise<void> {
    this.cancel();
    const entry: NonNullable<ServiceMenuController["current"]> = { intent: ++this.intent, request };
    this.current = entry;
    const released = pointerHeld ? new Promise<boolean>((resolve) => { entry.release = resolve; }) : Promise.resolve(true);
    const task = this.queue.then(async () => {
      if (this.current !== entry) return;
      try {
        const id = await this.port.prepare(request);
        entry.id = id;
        if (this.current !== entry) { await this.port.close(id, false); return; }
        let timer: ReturnType<typeof setTimeout> | undefined;
        const finished = await Promise.race([
          released,
          new Promise<boolean>((resolve) => { timer = setTimeout(() => resolve(false), 5000); }),
        ]).finally(() => clearTimeout(timer));
        if (!finished || this.current !== entry) {
          if (this.current === entry) this.current = null;
          await this.port.close(id, false);
          return;
        }
        entry.presenting = true;
        const shown = await this.port.present(id);
        if (this.current !== entry) await this.port.close(id, false);
        else if (!shown) { this.current = null; await this.port.close(id, false); }
      } catch (error) {
        if (entry.id !== undefined) {
          try { await this.port.close(entry.id, false); }
          catch (cleanupError) { this.port.error(cleanupError); return; }
        }
        if (this.current !== entry) return;
        // Native fallback is offered only for the still-current intent, after
        // the failed surface has been removed from the input path.
        this.current = null;
        this.port.error(error);
        await this.port.fallback(request, () => this.intent === entry.intent);
      }
    });
    this.queue = task.catch((error) => this.port.error(error));
    return this.queue;
  }

  ownerBlur(): void {
    // Moving focus into a ready popup is intentional. Losing the owner before
    // presentation (including while native creation is pending) cancels it.
    if (!this.current?.presenting) this.cancel();
  }

  releasePointer(buttons = 0): void {
    // Mouseup also fires for chorded and synthetic button releases. Keep the
    // owner in control until the pointer has no buttons held.
    if (buttons !== 0) return;
    this.current?.release?.(true);
    if (this.current) this.current.release = undefined;
  }

  cancel(restoreFocus = false): void {
    const previous = this.current;
    this.current = null;
    this.intent++;
    previous?.release?.(false);
    if (previous?.id !== undefined) void this.port.close(previous.id, restoreFocus).catch((error) => this.port.error(error));
  }

  closed(id: number): boolean {
    if (this.current?.id !== id) return false;
    this.current.release?.(false);
    this.current = null;
    this.intent++;
    return true;
  }

  takeAction(id: number, serviceId: string): boolean {
    if (this.current?.id !== id || this.current.request.serviceId !== serviceId) return false;
    return this.closed(id);
  }
}

export function menuFocusIndex(key: string, current: number, count: number): number | null {
  if (count <= 0) return null;
  if (key === "ArrowDown") return (current + 1 + count) % count;
  if (key === "ArrowUp") return current < 0 ? count - 1 : (current - 1 + count) % count;
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  return null;
}

export function captureMenuPointer(button: number, ctrlKey: boolean, platform: string): boolean {
  return button === 2 || (button === 0 && ctrlKey && platform.startsWith("Mac"));
}
