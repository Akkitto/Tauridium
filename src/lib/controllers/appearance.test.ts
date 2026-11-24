import { beforeEach, describe, expect, it, vi } from "vitest";
import { createAppearanceController, type AppearanceHost } from "./appearance.svelte";
import { createAppSettingsDefaults } from "../appSettingsDefaults";
import { setAppSettings } from "../api";
import { hslToHex } from "../ui";

vi.mock("../api", () => ({ setAppSettings: vi.fn(), setSidebarWidth: vi.fn() }));

function host(): AppearanceHost {
  return {
    appSettings: createAppSettingsDefaults(), error: null,
    applyLayout: vi.fn(), applyTheme: vi.fn(), showToast: vi.fn(),
    saveAppSetting: vi.fn(async () => undefined),
  };
}
describe("Appearance draft ownership", () => {
  beforeEach(() => vi.resetAllMocks());

  it("reads the latest host settings when starting and cancelling a color preview", () => {
    const owner = host(), controller = createAppearanceController(owner);
    owner.appSettings = { ...createAppSettingsDefaults(), accentColor: "#123456" };
    controller.openCustomColorPicker();
    controller.colorHue = 120;
    controller.previewCustomColor();
    expect(owner.appSettings.accentColor).not.toBe("#123456");
    controller.cancelCustomColorPicker();
    expect(owner.appSettings.accentColor).toBe("#123456");
    expect(controller.customColorOpen).toBe(false);
    expect(setAppSettings).not.toHaveBeenCalled();
  });

  it("keeps independent color drafts and preserves an editable draft after a failed save", async () => {
    const firstHost = host(), secondHost = host();
    const first = createAppearanceController(firstHost), second = createAppearanceController(secondHost);
    first.openCustomColorPicker();
    first.colorHue = 200;
    vi.mocked(setAppSettings).mockRejectedValue(new Error("synthetic write failure"));
    await first.applyCustomColor(true);
    expect(first.customColorOpen).toBe(true);
    expect(firstHost.error).toContain("synthetic write failure");
    expect(second.customColorOpen).toBe(false);
    expect(secondHost.appSettings).toEqual(createAppSettingsDefaults());
  });

  it("commits the acknowledged settings and reports Saved after successful persistence", async () => {
    const owner = host(), controller = createAppearanceController(owner);
    controller.openCustomColorPicker();
    controller.colorHue = 180;
    const color = hslToHex(controller.colorHue, controller.colorSaturation, controller.colorLightness);
    const saved = { ...owner.appSettings, accentColor: color, customAccentColors: [color] };
    vi.mocked(setAppSettings).mockResolvedValue(saved);
    await controller.applyCustomColor(true);
    expect(owner.appSettings).toEqual(saved);
    expect(controller.customColorOpen).toBe(false);
    expect(owner.showToast).toHaveBeenCalledWith("Saved", "success");
  });
});
