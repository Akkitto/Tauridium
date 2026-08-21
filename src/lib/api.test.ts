import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  invoke: vi.fn(),
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: mocks.invoke }));

import {
  preloadService,
  showService,
  startLocalSession,
  type Service,
} from "./api";

describe("startLocalSession", () => {
  beforeEach(() => {
    mocks.invoke.mockReset();
  });

  it("starts accountless mode without server credentials", async () => {
    mocks.invoke.mockResolvedValue({
      email: "local@tauridium.invalid",
      firstname: "Local",
      lastname: "",
      id: "local",
      local: true,
    });

    await expect(startLocalSession()).resolves.toMatchObject({ local: true });
    expect(mocks.invoke).toHaveBeenCalledOnce();
    expect(mocks.invoke).toHaveBeenCalledWith("start_local_session");
  });
});

describe("service view commands", () => {
  beforeEach(() => {
    mocks.invoke.mockReset();
    mocks.invoke.mockResolvedValue(undefined);
  });

  const service: Service = {
    id: "00112233-4455-6677-8899-aabbccddeeff",
    name: "Example",
    recipeId: "example",
    iconUrl: null,
    isEnabled: true,
    customUrl: "https://example.test",
    team: "acme",
    userAgentPref: "custom-agent",
    isDarkModeEnabled: true,
    darkReaderBrightness: 95,
    darkReaderContrast: 90,
    darkReaderSepia: 5,
  };

  it.each([
    ["show_service", showService],
    ["preload_service", preloadService],
  ])("passes %s a single typed request payload", async (command, call) => {
    await call(service);

    expect(mocks.invoke).toHaveBeenCalledOnce();
    expect(mocks.invoke).toHaveBeenCalledWith(command, {
      request: {
        serviceId: service.id,
        recipeId: service.recipeId,
        customUrl: service.customUrl,
        team: service.team,
        userAgentPref: service.userAgentPref,
        openLinksExternally: false,
        workspaceId: null,
        dark: {
          enabled: true,
          brightness: 95,
          contrast: 90,
          sepia: 5,
        },
      },
    });
  });


  it("forwards the per-service external-link preference", async () => {
    await showService({ ...service, trapLinkClicks: true });

    expect(mocks.invoke).toHaveBeenCalledOnce();
    expect(mocks.invoke).toHaveBeenCalledWith("show_service", {
      request: expect.objectContaining({
        serviceId: service.id,
        openLinksExternally: true,
      }),
    });
  });

  it("passes an explicit workspace context to show_service", async () => {
    await showService(service, "workspace-123");

    expect(mocks.invoke).toHaveBeenCalledOnce();
    expect(mocks.invoke).toHaveBeenCalledWith("show_service", {
      request: expect.objectContaining({
        serviceId: service.id,
        workspaceId: "workspace-123",
      }),
    });
  });
});

describe("local recipe commands", () => {
  beforeEach(() => {
    mocks.invoke.mockReset();
    mocks.invoke.mockResolvedValue(undefined);
  });

  it("creates a custom website atomically in the backend", async () => {
    const { createCustomWebsiteService } = await import("./api");
    await createCustomWebsiteService("Example", "https://example.com");
    expect(mocks.invoke).toHaveBeenCalledWith("create_custom_website_service", {
      name: "Example",
      url: "https://example.com",
    });
  });

  it("reads recipe storage and persists creator drafts", async () => {
    const { getRecipeStorageInfo, saveCustomRecipe } = await import("./api");
    await getRecipeStorageInfo();
    expect(mocks.invoke).toHaveBeenCalledWith("get_recipe_storage_info");
    mocks.invoke.mockClear();
    const draft = {
      id: "my-ai",
      name: "My AI",
      serviceUrl: "https://example.com",
      description: "test",
      hasCustomUrl: false,
      hasTeamId: false,
      iconSvg: "",
      webviewJs: "",
    };
    await saveCustomRecipe(draft);
    expect(mocks.invoke).toHaveBeenCalledWith("save_custom_recipe", { draft });
  });

  it("imports an existing recipe path", async () => {
    const { importCustomRecipe } = await import("./api");
    await importCustomRecipe("C:\\Recipes\\my-ai\\package.json");
    expect(mocks.invoke).toHaveBeenCalledWith("import_custom_recipe", {
      path: "C:\\Recipes\\my-ai\\package.json",
    });
  });
});

describe("backup commands", () => {
  beforeEach(() => {
    mocks.invoke.mockReset();
    mocks.invoke.mockResolvedValue(undefined);
  });

  it("exports a backup to the selected path", async () => {
    const { exportBackup } = await import("./api");
    await exportBackup("C:\\Backups\\tauridium-backup.json");
    expect(mocks.invoke).toHaveBeenCalledWith("export_backup", {
      path: "C:\\Backups\\tauridium-backup.json",
    });
  });

  it("restores a backup from the selected path", async () => {
    const { restoreBackup } = await import("./api");
    await restoreBackup("/home/example/tauridium-backup.json");
    expect(mocks.invoke).toHaveBeenCalledWith("restore_backup", {
      path: "/home/example/tauridium-backup.json",
    });
  });

  it("creates an automatic backup in the app-managed backup directory", async () => {
    const { createAutomaticBackup } = await import("./api");
    await createAutomaticBackup("tauridium-auto-backup-2026-08-19-001122-037.json");
    expect(mocks.invoke).toHaveBeenCalledWith("create_automatic_backup", {
      filename: "tauridium-auto-backup-2026-08-19-001122-037.json",
    });
  });
});

describe("external links", () => {
  beforeEach(() => {
    mocks.invoke.mockReset();
    mocks.invoke.mockResolvedValue(undefined);
  });

  it("opens project links through the native default-browser command", async () => {
    const { openExternalUrl } = await import("./api");
    await openExternalUrl("https://github.com/Akkitto/Tauridium");
    expect(mocks.invoke).toHaveBeenCalledWith("open_external_url", {
      url: "https://github.com/Akkitto/Tauridium",
    });
  });
});

describe("service icon cache commands", () => {
  beforeEach(() => {
    mocks.invoke.mockReset();
    mocks.invoke.mockResolvedValue(undefined);
  });

  it("copies a persistent cached icon when duplicating a service", async () => {
    const { copyServiceIconCache } = await import("./api");
    await copyServiceIconCache("source-service", "duplicate-service");
    expect(mocks.invoke).toHaveBeenCalledWith("copy_service_icon_cache", {
      sourceServiceId: "source-service",
      targetServiceId: "duplicate-service",
    });
  });
});
