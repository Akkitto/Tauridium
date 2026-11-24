import { hexToHsl, hslToHex, normalizeHexColor } from "../ui";
import { setAppSettings, setSidebarWidth, type AppSettings } from "../api";

export interface AppearanceHost {
  appSettings: AppSettings;
  readonly applyLayout: () => void;
  readonly applyTheme: () => void;
  error: string | null;
  readonly saveAppSetting: (key: keyof AppSettings, value: unknown) => Promise<void>;
  readonly showToast: (message: string, tone?: "default" | "success") => void;
}

/** Feature state is created once per application instance; host accessors stay live. */
export function createAppearanceController(host: AppearanceHost) {

  let customColorOpen = $state(false);

  let customColorOriginal = $state("#ffc131");

  let colorHue = $state(42);

  let colorSaturation = $state(100);

  let colorLightness = $state(60);

  function openCustomColorPicker() {
    customColorOriginal = host.appSettings.accentColor;
    const hsl = hexToHsl(host.appSettings.accentColor);
    colorHue = hsl.hue;
    colorSaturation = hsl.saturation;
    colorLightness = hsl.lightness;
    customColorOpen = true;
  }

  function cancelCustomColorPicker() {
    host.appSettings.accentColor = customColorOriginal;
    customColorOpen = false;
    host.applyTheme();
  }

  function previewCustomColor() {
    host.appSettings.accentColor = hslToHex(colorHue, colorSaturation, colorLightness);
    host.applyTheme();
  }

  function setCustomColorFromNative(value: string) {
    const normalized = normalizeHexColor(value);
    if (!normalized) return;
    const hsl = hexToHsl(normalized);
    colorHue = hsl.hue;
    colorSaturation = hsl.saturation;
    colorLightness = hsl.lightness;
    host.appSettings.accentColor = normalized;
    host.applyTheme();
  }

  async function applyCustomColor(savePreset: boolean) {
    const color = hslToHex(colorHue, colorSaturation, colorLightness);
    const customAccentColors = savePreset
      ? [...new Set([...(host.appSettings.customAccentColors ?? []), color])].slice(-32)
      : host.appSettings.customAccentColors;
    try {
      host.appSettings = await setAppSettings({ accentColor: color, customAccentColors });
      customColorOpen = false;
      host.applyTheme();
      host.showToast("Saved", "success");
    } catch (err) {
      host.error = String(err);
    }
  }

  async function removeCustomAccent(color: string) {
    await host.saveAppSetting(
      "customAccentColors",
      host.appSettings.customAccentColors.filter((candidate) => candidate !== color),
    );
  }

  function previewSidebarWidth(value: number) {
    const width = Math.max(160, Math.min(420, Math.round(value)));
    host.appSettings.sidebarWidth = width;
    host.applyLayout();
    void setSidebarWidth(width);
  }

  async function saveCurrentSidebarPreset() {
    const width = Math.round(host.appSettings.sidebarWidth);
    if ([180, 240, 320].includes(width)) return;
    const customSidebarWidths = [...new Set([...(host.appSettings.customSidebarWidths ?? []), width])]
      .slice(-16)
      .sort((left, right) => left - right);
    await host.saveAppSetting("customSidebarWidths", customSidebarWidths);
  }

  async function removeSidebarPreset(width: number) {
    await host.saveAppSetting(
      "customSidebarWidths",
      host.appSettings.customSidebarWidths.filter((candidate) => candidate !== width),
    );
  }

  return {
    applyCustomColor,
    cancelCustomColorPicker,
    get colorHue() { return colorHue; },
    set colorHue(value: typeof colorHue) { colorHue = value; },
    get colorLightness() { return colorLightness; },
    set colorLightness(value: typeof colorLightness) { colorLightness = value; },
    get colorSaturation() { return colorSaturation; },
    set colorSaturation(value: typeof colorSaturation) { colorSaturation = value; },
    get customColorOpen() { return customColorOpen; },
    openCustomColorPicker,
    previewCustomColor,
    previewSidebarWidth,
    removeCustomAccent,
    removeSidebarPreset,
    saveCurrentSidebarPreset,
    setCustomColorFromNative,
  };
}

export type AppearanceController = ReturnType<typeof createAppearanceController>;
