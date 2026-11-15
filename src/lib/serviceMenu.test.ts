import { describe, expect, it, vi } from "vitest";
import { ServiceMenuController, menuFocusIndex, captureMenuPointer, type ServiceMenuRequest } from "./serviceMenu";

const request: ServiceMenuRequest = { serviceId: "mail", label: "Mail", enabled: true, zoomPercent: 100, x: 200, y: 100, pixelRatio: 1, theme: "dark" };
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function harness() {
  let id = 0;
  const port = {
    prepare: vi.fn(async (_request: ServiceMenuRequest) => ++id),
    present: vi.fn(async (_id: number) => true),
    close: vi.fn(async (_id: number, _restore: boolean) => {}),
    fallback: vi.fn(async (_request: ServiceMenuRequest, _current: () => boolean) => {}),
    error: vi.fn(),
  };
  return { port, menu: new ServiceMenuController(port) };
}
async function flush() { for (let count = 0; count < 12; count++) await Promise.resolve(); }

describe("native service menu lifecycle", () => {
  it("never presents an opening cancelled before native preparation completes", async () => {
    const { port, menu } = harness(); const pending = deferred<number>();
    port.prepare.mockReturnValueOnce(pending.promise);
    const opening = menu.open(request); await flush(); menu.cancel(); pending.resolve(7); await opening;
    expect(port.present).not.toHaveBeenCalled();
    expect(port.close).toHaveBeenCalledWith(7, false);
    expect(menu.isOpen).toBe(false);
  });

  it("cancels preparation when focus moves straight to a native service", async () => {
    const { port, menu } = harness(); const pending = deferred<number>();
    port.prepare.mockReturnValueOnce(pending.promise);
    const opening = menu.open(request); await flush(); menu.ownerBlur(); pending.resolve(7); await opening;
    expect(port.present).not.toHaveBeenCalled();
    expect(port.close).toHaveBeenCalledWith(7, false);
    expect(menu.isOpen).toBe(false);
  });

  it("allows the deliberate focus transition into an already prepared popup", async () => {
    const { port, menu } = harness(); const pending = deferred<boolean>();
    port.present.mockReturnValueOnce(pending.promise);
    const opening = menu.open(request); await flush(); menu.ownerBlur(); pending.resolve(true); await opening;
    expect(menu.isOpen).toBe(true);
    expect(port.close).not.toHaveBeenCalled();
  });

  it("suppresses a late error fallback after a click away", async () => {
    const { port, menu } = harness(); const pending = deferred<number>();
    port.prepare.mockReturnValueOnce(pending.promise);
    const opening = menu.open(request); await flush(); menu.cancel(); pending.reject(new Error("create failed")); await opening;
    expect(port.fallback).not.toHaveBeenCalled();
    expect(port.present).not.toHaveBeenCalled();
  });

  it("serializes preparations and keeps only the newest target", async () => {
    const { port, menu } = harness(); const pending = deferred<number>();
    port.prepare.mockReturnValueOnce(pending.promise);
    const first = menu.open(request); await flush();
    const second = menu.open({ ...request, serviceId: "chat" }); await flush();
    expect(port.prepare).toHaveBeenCalledTimes(1);
    pending.resolve(8); await first; await second;
    expect(port.close).toHaveBeenCalledWith(8, false);
    expect(port.present).toHaveBeenCalledTimes(1);
    expect(menu.takeAction(8, "mail")).toBe(false);
    expect(menu.takeAction(1, "chat")).toBe(true);
    expect(menu.takeAction(1, "chat")).toBe(false);
  });

  it("waits for pointer release without suppressing later focus loss", async () => {
    const { port, menu } = harness(); const opening = menu.open(request, true);
    await flush(); expect(port.present).not.toHaveBeenCalled();
    menu.releasePointer(); await opening;
    expect(port.present).toHaveBeenCalledWith(1);
    menu.cancel(); await flush(); expect(port.close).toHaveBeenCalledWith(1, false);
  });

  it("cancels a held opening without ever showing it", async () => {
    const { port, menu } = harness(); const opening = menu.open(request, true);
    await flush(); menu.cancel(); await opening;
    expect(port.present).not.toHaveBeenCalled();
  });

  it("closes a presentation that finishes after cancellation", async () => {
    const { port, menu } = harness(); const pending = deferred<boolean>(); port.present.mockReturnValueOnce(pending.promise);
    const opening = menu.open(request); await flush(); menu.cancel(); pending.resolve(true); await opening;
    expect(port.close).toHaveBeenCalledWith(1, false);
    expect(port.fallback).not.toHaveBeenCalled();
  });

  it("cleans up a readiness failure before offering the system menu", async () => {
    const { port, menu } = harness(); port.present.mockRejectedValueOnce(new Error("not ready"));
    await menu.open(request);
    expect(port.close).toHaveBeenCalledWith(1, false);
    expect(port.close.mock.invocationCallOrder[0]).toBeLessThan(port.fallback.mock.invocationCallOrder[0]);
    expect(port.fallback).toHaveBeenCalledTimes(1);
    const isCurrent = port.fallback.mock.calls[0][1]; expect(isCurrent()).toBe(true);
    menu.cancel(); expect(isCurrent()).toBe(false);
  });

  it("ignores stale close notifications and mismatched or repeated action targets", async () => {
    const { menu } = harness(); await menu.open(request);
    expect(menu.closed(99)).toBe(false);
    expect(menu.takeAction(1, "other-service")).toBe(false);
    expect(menu.isOpen).toBe(true);
    expect(menu.takeAction(1, "mail")).toBe(true);
    expect(menu.takeAction(1, "mail")).toBe(false);
    expect(menu.isOpen).toBe(false);
  });

  it("does not fall back when native presentation was cancelled by deactivation", async () => {
    const { port, menu } = harness(); port.present.mockResolvedValueOnce(false); await menu.open(request);
    expect(port.fallback).not.toHaveBeenCalled(); expect(menu.isOpen).toBe(false);
  });
});

describe("service menu keyboard navigation", () => {
  it("wraps among enabled items and supports Home/End without trapping unrelated keys", () => {
    expect(menuFocusIndex("ArrowDown", -1, 5)).toBe(0);
    expect(menuFocusIndex("ArrowDown", 4, 5)).toBe(0);
    expect(menuFocusIndex("ArrowUp", 0, 5)).toBe(4);
    expect(menuFocusIndex("ArrowUp", -1, 5)).toBe(4);
    expect(menuFocusIndex("Home", 3, 5)).toBe(0);
    expect(menuFocusIndex("End", 1, 5)).toBe(4);
    expect(menuFocusIndex("x", 1, 5)).toBeNull();
    expect(menuFocusIndex("ArrowDown", 0, 0)).toBeNull();
  });
});

it("leaves primary clicks and Windows/Linux Ctrl-click selection and dragging alone", () => {
  for (const platform of ["Win32", "Linux x86_64", "MacIntel"]) {
    expect(captureMenuPointer(2, false, platform)).toBe(true);
    expect(captureMenuPointer(0, false, platform)).toBe(false);
  }
  expect(captureMenuPointer(0, true, "Win32")).toBe(false);
  expect(captureMenuPointer(0, true, "Linux x86_64")).toBe(false);
  expect(captureMenuPointer(0, true, "MacIntel")).toBe(true);
});
