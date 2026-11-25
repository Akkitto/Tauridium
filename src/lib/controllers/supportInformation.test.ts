import { beforeEach, describe, expect, it, vi } from "vitest";
import { copySupportInformation, getSupportInformation } from "../api";
import { createSupportInformationController } from "./supportInformation.svelte";

vi.mock("../api", () => ({ copySupportInformation: vi.fn(), getSupportInformation: vi.fn() }));
const preview = "Synthetic allowlisted support preview";
const copied = "Fresh native support report copied to clipboard";

describe("Support information ownership and copy acknowledgement", () => {
  beforeEach(() => vi.resetAllMocks());

  it("loads a preview without reading or writing the clipboard", async () => {
    vi.mocked(getSupportInformation).mockResolvedValue(preview);
    const support = createSupportInformationController();
    await support.refresh();
    expect(support.text).toBe(preview);
    expect(support.status).toBe("");
    expect(support.error).toBe("");
    expect(copySupportInformation).not.toHaveBeenCalled();
  });

  it("reports success only after native copy completes and displays the exact copied text", async () => {
    const pending = Promise.withResolvers<string>();
    vi.mocked(copySupportInformation).mockReturnValue(pending.promise);
    const support = createSupportInformationController();
    const copying = support.copy();
    expect(support.busy).toBe(true);
    expect(support.status).toBe("");
    await support.copy();
    await support.refresh();
    expect(copySupportInformation).toHaveBeenCalledExactlyOnceWith();
    expect(getSupportInformation).not.toHaveBeenCalled();
    pending.resolve(copied);
    await copying;
    expect(support.text).toBe(copied);
    expect(support.status).toBe("Support information copied.");
    expect(support.busy).toBe(false);
  });

  it("keeps the selectable preview on failure, suppresses private errors and permits retry", async () => {
    vi.mocked(getSupportInformation).mockResolvedValue(preview);
    vi.mocked(copySupportInformation).mockRejectedValueOnce(new Error("/private/PRIVATE_ERROR_CANARY"));
    const support = createSupportInformationController();
    await support.refresh();
    await support.copy();
    expect(support.text).toBe(preview);
    expect(support.error).toContain("copy it manually");
    expect(support.error).not.toContain("PRIVATE_ERROR_CANARY");
    expect(support.error).not.toContain("/private/");
    expect(support.status).toBe("");
    expect(support.busy).toBe(false);
    vi.mocked(copySupportInformation).mockResolvedValueOnce(copied);
    await support.copy();
    expect(support.error).toBe("");
    expect(support.status).toBe("Support information copied.");
  });

  it("does not discard a previous preview or expose native errors when refreshing fails", async () => {
    vi.mocked(getSupportInformation).mockResolvedValueOnce(preview).mockRejectedValueOnce("PRIVATE_ERROR_CANARY");
    const support = createSupportInformationController();
    await support.refresh();
    await support.refresh();
    expect(support.text).toBe(preview);
    expect(support.error).toContain("temporarily unavailable");
    expect(support.error).not.toContain("PRIVATE_ERROR_CANARY");
    expect(support.busy).toBe(false);
  });

  it("keeps different support panels independent", async () => {
    vi.mocked(copySupportInformation).mockResolvedValue(copied);
    const first = createSupportInformationController(), second = createSupportInformationController();
    await first.copy();
    expect(second.text).toBe("");
    expect(second.status).toBe("");
    expect(second.busy).toBe(false);
  });
});
