import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { downloadToastPreview, ToastCountdown } from "./downloadToast";

describe("download notification examples", () => {
  it("does not reveal a path in filename-only mode", () => {
    expect(downloadToastPreview("none", 2, false)).toBeNull();
    expect(downloadToastPreview("none", 2, true)).toBeNull();
  });

  it("shows just the destination folder name", () => {
    expect(downloadToastPreview("directory", 2, true)).toBe("Reports");
  });

  it("shows complete Unix and Windows examples", () => {
    expect(downloadToastPreview("full", 2, false)).toBe("/home/you/Downloads/Reports/example.pdf");
    expect(downloadToastPreview("full", 2, true)).toBe("C:\\Users\\You\\Downloads\\Reports\\example.pdf");
  });

  it("shows precisely the requested nearest parent folders", () => {
    expect(downloadToastPreview("partial", 2, false)).toBe("…/Downloads/Reports/example.pdf");
    expect(downloadToastPreview("partial", 1, true)).toBe("…\\Reports\\example.pdf");
    expect(downloadToastPreview("partial", 3, false)).toBe("…/you/Downloads/Reports/example.pdf");
    expect(downloadToastPreview("partial", 10, false)).toBe("/home/you/Downloads/Reports/example.pdf");
  });
});

describe("download toast countdown", () => {
  beforeEach(() => { vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "performance"] }); });
  afterEach(() => { vi.useRealTimers(); });

  it("expires once after the chosen display time", () => {
    const expired = vi.fn();
    const timer = new ToastCountdown(8, expired);
    timer.resume();
    vi.advanceTimersByTime(7999);
    expect(expired).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(expired).toHaveBeenCalledTimes(1);
    timer.resume();
    vi.advanceTimersByTime(30000);
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it("never auto-dismisses a persistent notification", () => {
    const expired = vi.fn();
    const timer = new ToastCountdown(0, expired);
    timer.resume();
    vi.advanceTimersByTime(24 * 60 * 60 * 1000);
    timer.pause();
    timer.resume();
    expect(expired).not.toHaveBeenCalled();
    timer.dispose();
  });

  it("pauses for hovering, focus and background time without losing remaining time", () => {
    const expired = vi.fn();
    const timer = new ToastCountdown(8, expired);
    timer.resume();
    vi.advanceTimersByTime(3000);
    timer.pause();
    timer.pause();
    vi.advanceTimersByTime(60000);
    expect(expired).not.toHaveBeenCalled();
    timer.resume();
    vi.advanceTimersByTime(4999);
    expect(expired).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it("does not restart a running timer when queue counts update", () => {
    const expired = vi.fn();
    const timer = new ToastCountdown(8, expired);
    timer.resume();
    vi.advanceTimersByTime(6000);
    timer.resume();
    vi.advanceTimersByTime(2000);
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it("cleans up old timers when notifications change or the renderer closes", () => {
    const expired = vi.fn();
    const timer = new ToastCountdown(8, expired);
    timer.resume();
    vi.advanceTimersByTime(6000);
    timer.dispose();
    timer.resume();
    vi.advanceTimersByTime(10000);
    expect(expired).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});
