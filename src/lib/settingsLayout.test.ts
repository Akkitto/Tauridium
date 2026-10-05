import source from "../App.svelte?raw";
import { parse, type AST } from "svelte/compiler";
import { describe, expect, it } from "vitest";

const ast = parse(source, { modern: true });

function element(value: unknown): value is AST.RegularElement {
  return value !== null && typeof value === "object" && "type" in value && value.type === "RegularElement";
}

function classes(node: AST.RegularElement): string[] {
  const attribute = node.attributes.find((item) => item.type === "Attribute" && item.name === "class");
  if (attribute?.type !== "Attribute" || !Array.isArray(attribute.value)) return [];
  return attribute.value.filter((item) => item.type === "Text").map((item) => item.data).join(" ").split(/\s+/);
}

const switches: { input: AST.RegularElement; parent: AST.RegularElement | undefined }[] = [];
function visit(value: unknown, parent?: AST.RegularElement): void {
  if (value === null || typeof value !== "object") return;
  if (element(value)) {
    if (value.name === "input" && classes(value).includes("switch-input")) switches.push({ input: value, parent });
    parent = value;
  }
  for (const child of Object.values(value)) {
    if (Array.isArray(child)) child.forEach((item) => visit(item, parent));
    else visit(child, parent);
  }
}
visit(ast.fragment);

describe("Settings switch layout contract", () => {
  it("anchors every absolute switch input and track to the positioned wrapper", () => {
    expect(switches.length).toBeGreaterThan(0);
    for (const { input, parent } of switches) {
      expect(parent, `switch at source offset ${input.start}`).toBeDefined();
      expect(parent && classes(parent), `switch at source offset ${input.start}`).toContain("switch-control");
    }
    const wrapper = source.match(/\.switch-control\s*\{([^}]+)\}/)?.[1];
    expect(wrapper).toMatch(/position:\s*relative\s*;/);
    expect(wrapper).toMatch(/width:\s*38px\s*;/);
    expect(wrapper).toMatch(/height:\s*22px\s*;/);
  });

  it("keeps the decorative track and thumb inside the checkbox control", () => {
    for (const { parent } of switches) {
      const track = parent?.fragment.nodes.find((node) => element(node) && classes(node).includes("switch-track"));
      expect(track).toBeDefined();
      expect(track && element(track) && track.fragment.nodes.some((node) => element(node) && classes(node).includes("switch-thumb"))).toBe(true);
    }
  });
});
