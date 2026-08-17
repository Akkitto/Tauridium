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
        dark: {
          enabled: true,
          brightness: 95,
          contrast: 90,
          sepia: 5,
        },
      },
    });
  });
});
