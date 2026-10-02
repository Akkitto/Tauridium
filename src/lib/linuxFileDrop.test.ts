import { describe, expect, it, vi } from "vitest";
import script from "../../src-tauri/src/linux_file_drop.js?raw";

function setup() {
  class ElementNode {
    id = "";
    textContent = "";
    type = "";
    style = { cssText: "" };
    children: ElementNode[] = [];
    setAttribute = vi.fn();
    addEventListener = vi.fn();
    append(...children: ElementNode[]) { this.children.push(...children); }
    attachShadow(): ElementNode { return new ElementNode(); }
    remove() { nodes.delete(this.id); }
  }
  const nodes = new Map<string, ElementNode>();
  const element = () => new ElementNode();
  const body = element();
  body.append = (...children: ElementNode[]) => { for (const child of children) nodes.set(child.id, child); };
  const doc = {
    body, documentElement: body,
    addEventListener: vi.fn(), createElement: element,
    getElementById: (id: string) => nodes.get(id),
  };
  const schedule = vi.fn();
  const cancel = vi.fn();
  new Function("document", "setTimeout", "clearTimeout", script)(doc, schedule, cancel);
  const handler = doc.addEventListener.mock.calls[0][1];
  function drop(overrides: Record<string, unknown> = {}) {
    const event = {
      isTrusted: true, preventDefault: vi.fn(),
      dataTransfer: { files: [], types: ["text/uri-list"], getData: () => "" },
      ...overrides,
    };
    handler(event);
    return event;
  }
  return { nodes, doc, schedule, cancel, drop };
}

describe("Linux file-drop fallback", () => {
  it("explains an engine-blocked native file drop and prevents file navigation", () => {
    const test = setup();
    const event = test.drop();
    expect(event.preventDefault).toHaveBeenCalledOnce();
    expect(test.nodes.size).toBe(1);
    expect(test.doc.addEventListener.mock.calls[0][2]).toBe(true);
    expect(test.schedule).toHaveBeenCalledWith(expect.any(Function), 10000);
  });

  it.each([
    { isTrusted: false },
    { dataTransfer: null },
    { dataTransfer: { files: [{}], types: ["Files", "text/uri-list"] } },
    { dataTransfer: { files: [], types: ["text/plain"] } },
    { dataTransfer: { files: [], types: ["text/uri-list"], getData: () => "https://example.com/" } },
  ])("preserves normal files, links, text, and synthetic page drags (%j)", (override) => {
    const test = setup();
    expect(test.drop(override).preventDefault).not.toHaveBeenCalled();
    expect(test.nodes.size).toBe(0);
  });

  it("replaces repeated notices and lets the timer remove the last notice", () => {
    const test = setup();
    test.drop();
    const first = test.nodes.get("__tauridium-file-drop-help");
    test.drop();
    expect(test.nodes.size).toBe(1);
    expect(test.nodes.get("__tauridium-file-drop-help")).not.toBe(first);
    test.schedule.mock.calls[1][0]();
    expect(test.nodes.size).toBe(0);
  });
});
