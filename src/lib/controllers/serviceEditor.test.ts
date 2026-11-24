import { beforeEach, describe, expect, it, vi } from "vitest";
import { createServiceEditorController, type ServiceEditorHost } from "./serviceEditor.svelte";
import { createAppSettingsDefaults } from "../appSettingsDefaults";
import { hideServices, setAppSettings, setServiceFlags, updateService, type Service } from "../api";

vi.mock("../api", () => ({
  closeService: vi.fn(), hideServices: vi.fn(), setServiceFlags: vi.fn(), updateService: vi.fn(),
  fetchServiceIconUrl: vi.fn(), createWorkspace: vi.fn(), updateWorkspace: vi.fn(),
  deleteWorkspace: vi.fn(), setAppSettings: vi.fn(),
}));
const service: Service = { id: "synthetic-service", name: "Original", recipeId: "synthetic", iconUrl: null, isEnabled: true };
function host(): ServiceEditorHost {
  return {
    MANAGED_SERVICE_PAGE_SIZE: 100, RELOAD_FIELDS: new Set(), activeId: service.id,
    appSettings: createAppSettingsDefaults(), backToService: vi.fn(), clearHibTimer: vi.fn(),
    closeServiceContextMenu: vi.fn(), confirmAsk: vi.fn(async () => true), error: null,
    failedIcons: new Set(), iconFetchAttempted: new Set(), loadServiceIcon: vi.fn(async () => undefined),
    preferredWebsiteIcon: () => null, reconcileSavedOrders: vi.fn(async () => undefined),
    refreshNativeServicesMenu: vi.fn(async () => undefined), reloadWorkspaces: vi.fn(async () => undefined),
    scheduleHibernation: vi.fn(), serviceIcons: {}, serviceSandboxId: () => null,
    services: [{ ...service }], settingsTab: "services", showServiceSettingsSaved: vi.fn(),
    showToast: vi.fn(), sortedWorkspaces: [], statusMap: {},
    toggleServiceInWorkspace: vi.fn(async () => true), view: "appSettings", workspaces: [],
  };
}
describe("Service editor persistence boundaries", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(hideServices).mockResolvedValue(undefined);
    vi.mocked(setServiceFlags).mockResolvedValue(undefined);
  });

  it("retains the editable draft and original service when persistence fails", async () => {
    const owner = host(), editor = createServiceEditorController(owner);
    editor.openServiceSettings(owner.services[0], true);
    editor.saveText("name", "Changed");
    vi.mocked(updateService).mockRejectedValue(new Error("synthetic write failure"));
    await editor.saveServiceSettings();
    expect(owner.services[0].name).toBe("Original");
    expect(editor.settingsSvc?.name).toBe("Changed");
    expect(editor.svcDirty).toBe(true);
    expect(owner.error).toContain("synthetic write failure");
    expect(setServiceFlags).not.toHaveBeenCalled();
    expect(owner.refreshNativeServicesMenu).not.toHaveBeenCalled();
  });

  it("commits only after acknowledgement and returns to the originating settings tab", async () => {
    const owner = host(), editor = createServiceEditorController(owner);
    editor.openServiceSettings(owner.services[0], true);
    editor.saveText("name", "Changed");
    const pending = Promise.withResolvers<Awaited<ReturnType<typeof updateService>>>();
    vi.mocked(updateService).mockReturnValue(pending.promise);
    const saving = editor.saveServiceSettings();
    expect(owner.services[0].name).toBe("Original");
    pending.resolve({ ...service, name: "Changed" });
    await saving;
    expect(owner.services[0].name).toBe("Changed");
    expect(editor.svcDirty).toBe(false);
    await editor.closeServiceSettings();
    expect(owner.view).toBe("appSettings");
    expect(owner.settingsTab).toBe("services");
    expect(editor.settingsSvc).toBe(null);
  });

  it("honors declined discard confirmation and rolls back failed shortcut overrides", async () => {
    const owner = host(), editor = createServiceEditorController(owner);
    editor.openServiceSettings(owner.services[0], true);
    editor.saveText("name", "Changed");
    vi.mocked(owner.confirmAsk).mockResolvedValue(false);
    await editor.closeServiceSettings();
    expect(owner.view).toBe("svcSettings");
    expect(editor.settingsSvc?.name).toBe("Changed");
    vi.mocked(setAppSettings).mockRejectedValue(new Error("synthetic override failure"));
    await editor.setServiceShortcutCaptureMode(service.id, "website");
    expect(owner.appSettings.serviceShortcutCaptureOverrides).toEqual({});
    expect(owner.error).toContain("synthetic override failure");
    expect(owner.showServiceSettingsSaved).not.toHaveBeenCalled();
  });
});
