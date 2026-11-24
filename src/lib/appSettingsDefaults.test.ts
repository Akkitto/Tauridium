import { describe, expect, it } from "vitest";
import { createAppSettingsDefaults } from "./appSettingsDefaults";
import { DEFAULT_KEYBINDINGS } from "./ui";

describe("Application-owned preference defaults", () => {
  it("creates independent nested settings records for every application instance", () => {
    const first = createAppSettingsDefaults();
    const second = createAppSettingsDefaults();
    first.serviceZoomLevels.fixture = 135;
    first.customAccentColors.push("#123456");
    first.serviceDownloadSettings.fixture = { directory: "/synthetic", askEachDownload: true };
    expect(second.serviceZoomLevels).toEqual({});
    expect(second.customAccentColors).toEqual([]);
    expect(second.serviceDownloadSettings).toEqual({});
  });

  it("does not mutate the shared keybinding definitions through a preference draft", () => {
    const first = createAppSettingsDefaults();
    const second = createAppSettingsDefaults();
    const original = DEFAULT_KEYBINDINGS.openSettings;
    first.keybindings.openSettings = "Ctrl+Alt+Z";
    expect(second.keybindings.openSettings).toBe(original);
    expect(DEFAULT_KEYBINDINGS.openSettings).toBe(original);
  });
});
