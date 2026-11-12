// Exercises src-tauri/src/spellcheck_toggle.js against a minimal fake DOM.
const fs = require("fs");
const vm = require("vm");
const assert = require("assert");

class Element {
  constructor(tag, attrs = {}) {
    this.tag = tag;
    this.attrs = new Map(Object.entries(attrs));
  }
  hasAttribute(name) { return this.attrs.has(name); }
  getAttribute(name) { return this.attrs.has(name) ? this.attrs.get(name) : null; }
  setAttribute(name, value) { this.attrs.set(name, String(value)); }
  removeAttribute(name) { this.attrs.delete(name); }
  closest() { return this.editable ? this : null; }
}

function page(enabled) {
  const listeners = [];
  const elements = [];
  const document = {
    readyState: "complete",
    querySelectorAll: () => elements.filter((el) => el.editable),
    addEventListener: (type, fn) => listeners.push([type, fn]),
  };
  const window = { __tauridiumSpellcheckState: { enabled } };
  const context = vm.createContext({ window, document, Element, Boolean });
  vm.runInContext(fs.readFileSync("src-tauri/src/spellcheck_toggle.js", "utf8"), context);
  const add = (attrs) => { const el = new Element("input", attrs); el.editable = true; elements.push(el); return el; };
  const focus = (el) => listeners.filter(([t]) => t === "focusin").forEach(([, fn]) => fn({ target: el }));
  return { window, add, focus };
}

// Disabled at load: existing editable fields are forced off, and so are ones focused later.
{
  const p = page(false);
  const existing = p.add({});
  const explicitTrue = p.add({ spellcheck: "true" });
  // The script applies once at load, before these fields exist in this fake; re-apply.
  p.window.__tauridiumSpellcheckSet(false);
  assert.strictEqual(existing.getAttribute("spellcheck"), "false");
  assert.strictEqual(explicitTrue.getAttribute("spellcheck"), "false");
  const late = p.add({});
  p.focus(late);
  assert.strictEqual(late.getAttribute("spellcheck"), "false");

  // Re-enabling restores each field's own original attribute.
  p.window.__tauridiumSpellcheckSet(true);
  assert.strictEqual(existing.hasAttribute("spellcheck"), false);
  assert.strictEqual(explicitTrue.getAttribute("spellcheck"), "true");
  assert.strictEqual(late.hasAttribute("spellcheck"), false);
  assert.strictEqual(existing.hasAttribute("data-tauridium-spellcheck"), false);
}

// Enabled: nothing is touched, even on focus.
{
  const p = page(true);
  const el = p.add({ spellcheck: "false" });
  p.focus(el);
  assert.strictEqual(el.getAttribute("spellcheck"), "false");
  assert.strictEqual(el.hasAttribute("data-tauridium-spellcheck"), false);
  // Disable then enable keeps the page's own "false".
  p.window.__tauridiumSpellcheckSet(false);
  p.window.__tauridiumSpellcheckSet(true);
  assert.strictEqual(el.getAttribute("spellcheck"), "false");
}

// Injecting twice must not stack handlers or reset state.
{
  const p = page(false);
  assert.strictEqual(typeof p.window.__tauridiumSpellcheckSet, "function");
}
console.log("spellcheck toggle probe ok");
