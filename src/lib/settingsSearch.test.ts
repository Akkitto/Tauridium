import { describe, expect, it } from "vitest";
import { parse, type AST } from "svelte/compiler";
import app from "../App.svelte?raw";
import { DEFAULT_KEYBINDINGS } from "./ui";
import { KEYBINDING_SETTINGS, SETTINGS_SEARCH_ENTRIES, SETTINGS_TABS, normalizeSettingsQuery, searchSettings, type SettingsSearchContext, type SettingsTab } from "./settingsSearch";

const linux: SettingsSearchContext = { windows: false, flatpak: false, portalDownloads: false };
const windows: SettingsSearchContext = { ...linux, windows: true };
const flatpak: SettingsSearchContext = { windows: false, flatpak: true, portalDownloads: true };
const ids = (query: string, context = linux) => searchSettings(query, context).map((item) => item.id);

describe("Settings search", () => {
  it("prioritizes exact control names and tab names", () => {
    expect(ids("theme")[0]).toBe("theme");
    expect(ids("Appearance")[0]).toBe("tab-appearance");
    expect(ids("Show service names")[0]).toBe("showServiceName");
    expect(ids("Advanced")[0]).toBe("tab-advanced");
  });
  it("matches synonyms, CamelCase, punctuation and diacritics", () => {
    expect(ids("  TH\u00C8ME! ")[0]).toBe("theme");
    expect(ids("boot startup")).toContain("autostart");
    expect(ids("favicon")).toEqual(["fetchMissingServiceIcons", "refetchIcons"]);
    expect(ids("downloadToastParentLevels")).toContain("downloadToastParentLevels");
    expect(ids("keybindings zoom")).toContain("keybinding-zoomIn");
    expect(ids("download notifications")).toContain("downloadToasts");
    expect(ids("download directory")).toContain("downloadDirectory");
  });
  it("requires every search term instead of flooding results with unrelated options", () => {
    expect(ids("backup tray")).toEqual([]);
    expect(ids("sidebar spacing")).toEqual(expect.arrayContaining(["collapsedIconSpacing", "expandedServiceSpacing"]));
    expect(ids("download directory")).not.toContain("automaticBackupDirectory");
  });
  it("filters unavailable Windows, tray and download controls", () => {
    expect(ids("unified title bar")).toEqual([]);
    expect(ids("unified title bar", windows)[0]).toBe("unifiedTitleBar");
    expect(ids("tray", flatpak)).toContain("portalStartup");
    expect(ids("tray", flatpak)).not.toContain("closeToSystemTray");
    expect(ids("background", flatpak)).not.toContain("startMinimized");
    expect(ids("download directory", flatpak)).not.toContain("downloadDirectory");
    expect(ids("download destination", flatpak)).toContain("portalDownloads");
    expect(ids("ask where save", flatpak)).not.toContain("askEachDownload");
  });
  it("does not interpret regex, markup or object-property names as code", () => {
    expect(ids("__proto__")).toEqual([]);
    expect(ids('<img src=x onerror="throw 1">')).toEqual([]);
    expect(ids(".*[]()$")).toEqual([]);
    expect(Object.prototype).not.toHaveProperty("settingsSearch");
  });
  it("returns no suggestions for empty input and bounds pasted input", () => {
    expect(ids("   ")).toEqual([]);
    expect(ids("")).toEqual([]);
    expect(ids("x".repeat(100_000))).toEqual([]);
    expect(normalizeSettingsQuery("a".repeat(500))).toHaveLength(200);
  });
  it("keeps ordering stable and never mutates the catalog", () => {
    const before = SETTINGS_SEARCH_ENTRIES.map((item) => item.id);
    expect(ids("icons")).toEqual(ids("icons"));
    expect(SETTINGS_SEARCH_ENTRIES.map((item) => item.id)).toEqual(before);
  });
  it("uses static descriptions and covers all keyboard actions exactly once", () => {
    expect(KEYBINDING_SETTINGS.map(([key]) => key).sort()).toEqual(Object.keys(DEFAULT_KEYBINDINGS).sort());
    expect(new Set(SETTINGS_SEARCH_ENTRIES.map((entry) => entry.id)).size).toBe(SETTINGS_SEARCH_ENTRIES.length);
    for (const entry of SETTINGS_SEARCH_ENTRIES) {
      expect(entry.id).toMatch(/^[a-zA-Z0-9-]+$/);
      expect(entry.description).not.toBe("");
      expect(SETTINGS_TABS.some(([tab]) => tab === entry.tab)).toBe(true);
    }
  });
});

// Resolve destinations from the real Svelte tree, including tab ownership. A
// nearby card in another tab is not a valid destination even when its ID exists.
const ast = parse(app, { modern: true });
const targets = new Map<string, SettingsTab | undefined>();
const toggles: { key: string; label: string; tab: SettingsTab | undefined }[] = [];
const templates: { prefix: string; variable: string; tab: SettingsTab | undefined }[] = [];
const controls: { key: string; target: string | undefined; tab: SettingsTab }[] = [];
function element(value: unknown): value is AST.RegularElement {
  return value !== null && typeof value === "object" && "type" in value && value.type === "RegularElement";
}
function conditional(value: unknown): value is AST.IfBlock {
  return value !== null && typeof value === "object" && "type" in value && value.type === "IfBlock";
}
function rendered(value: unknown): value is AST.RenderTag {
  return value !== null && typeof value === "object" && "type" in value && value.type === "RenderTag";
}
function isTab(value: unknown): value is SettingsTab { return SETTINGS_TABS.some(([tab]) => tab === value); }
function attributePart(attribute: AST.Attribute) {
  if (attribute.value === true) return undefined;
  return Array.isArray(attribute.value) ? attribute.value[0] : attribute.value;
}
function visit(value: unknown, tab?: SettingsTab, card?: string): void {
  if (!value || typeof value !== "object") return;
  if (conditional(value) && value.test.type === "BinaryExpression" && value.test.operator === "==="
    && value.test.left.type === "Identifier" && value.test.left.name === "settingsTab"
    && value.test.right.type === "Literal" && isTab(value.test.right.value)) tab = value.test.right.value;
  if (element(value)) {
    let identifier: string | undefined;
    for (const attr of value.attributes) {
      if (attr.type !== "Attribute" || attr.name !== "id") continue;
      const part = attributePart(attr);
      if (part?.type === "Text") { identifier = part.data; targets.set(part.data, tab); }
      if (part?.type === "ExpressionTag" && part.expression.type === "TemplateLiteral") {
        const expression = part.expression;
        if (expression.expressions.length === 1 && expression.expressions[0].type === "Identifier"
          && expression.quasis[1]?.value.cooked === "") {
          templates.push({ prefix: expression.quasis[0].value.cooked ?? "", variable: expression.expressions[0].name, tab });
        }
      }
    }
    const classAttr = value.attributes.find((attr) => attr.type === "Attribute" && attr.name === "class");
    if (classAttr?.type === "Attribute" && Array.isArray(classAttr.value)
      && classAttr.value.some((part) => part.type === "Text" && part.data.split(/\s+/).includes("setting-card"))) card = identifier;
    if (tab && ["input", "select", "textarea"].includes(value.name)) {
      for (const attr of value.attributes) {
        const part = attr.type === "Attribute" ? attributePart(attr) : null;
        const expression = attr.type === "BindDirective" ? attr.expression : part?.type === "ExpressionTag" ? part.expression : null;
        if (expression?.type === "MemberExpression" && expression.object.type === "Identifier" && expression.object.name === "appSettings"
          && expression.property.type === "Identifier") controls.push({ key: expression.property.name, target: card, tab });
      }
    }
  }
  if (rendered(value) && value.expression.type === "CallExpression" && value.expression.callee.type === "Identifier" && value.expression.callee.name === "appToggle") {
    const [label, , key] = value.expression.arguments;
    if (key?.type === "Literal" && typeof key.value === "string" && label?.type === "Literal" && typeof label.value === "string") toggles.push({ key: key.value, label: label.value, tab });
  }
  for (const child of Object.values(value)) {
    if (Array.isArray(child)) child.forEach((item) => visit(item, tab, card)); else visit(child, tab, card);
  }
}
visit(ast.fragment);
for (const template of templates) {
  if (template.variable === "key") for (const toggle of toggles) targets.set(`${template.prefix}${toggle.key}`, toggle.tab);
  if (template.variable === "action") for (const [action] of KEYBINDING_SETTINGS) targets.set(`${template.prefix}${action}`, template.tab);
  if (template.variable === "settingsTab") for (const [tab] of SETTINGS_TABS) targets.set(`${template.prefix}${tab}`, tab);
}

describe("Settings search destination coverage", () => {
  it("provides real primary and fallback destinations in the correct tab", () => {
    for (const entry of SETTINGS_SEARCH_ENTRIES) {
      expect(targets.get(entry.target), `${entry.id}: ${entry.target}`).toBe(entry.tab);
      if (entry.fallback) expect(targets.get(entry.fallback.target), `${entry.id}: fallback`).toBe(entry.tab);
    }
  });
  it("indexes every shared application toggle under its real UI name", () => {
    expect(toggles.length).toBeGreaterThan(15);
    for (const { key, label, tab } of toggles) {
      const entry = SETTINGS_SEARCH_ENTRIES.find((item) => item.id === key);
      expect(entry, key).toBeDefined();
      expect(entry?.label, key).toBe(label);
      expect(entry?.tab, key).toBe(tab);
    }
  });
  it("makes the cards containing global form controls searchable", () => {
    expect(controls.length).toBeGreaterThan(20);
    for (const control of controls) {
      expect(SETTINGS_SEARCH_ENTRIES.some((entry) => entry.target === control.target && entry.tab === control.tab), `${control.tab}: ${control.key}`).toBe(true);
    }
  });
  it("navigates to action groups without auto-activating backup or keybinding buttons", () => {
    for (const entry of SETTINGS_SEARCH_ENTRIES.filter((entry) => entry.id === "manualBackup" || entry.id === "serviceExport" || entry.id === "keybindingDefaults" || entry.id === "automaticBackupNow" || entry.id.startsWith("keybinding-"))) expect(entry.focusContainer).toBe(true);
  });
});
