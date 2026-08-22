import { describe, expect, it } from "vitest";
import {
  DEFAULT_TASKBAR_TITLE_TEMPLATE,
  DEFAULT_WINDOW_TITLE_TEMPLATE,
  renderTitleTemplate,
} from "./title-template";

const context = {
  app: "Tauridium",
  workspace: "Engineering",
  service: "GitHub",
};

describe("title templates", () => {
  it("renders the default workspace title", () => {
    expect(renderTitleTemplate(DEFAULT_WINDOW_TITLE_TEMPLATE, context)).toBe(
      "Tauridium ~ Engineering",
    );
    expect(renderTitleTemplate(DEFAULT_TASKBAR_TITLE_TEMPLATE, context)).toBe(
      "Tauridium ~ Engineering",
    );
  });

  it("supports arbitrary ordering and service names", () => {
    expect(renderTitleTemplate("{workspace} | {service} | {app}", context)).toBe(
      "Engineering | GitHub | Tauridium",
    );
  });

  it("falls back to the app name for an empty template", () => {
    expect(renderTitleTemplate("   ", context)).toBe("Tauridium");
  });
});
