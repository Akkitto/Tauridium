// Validate the explicit local security backport, its actual Svelte resolution,
// and the returned-object prototype boundary without lifecycle scripts.
import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const marker = "tauridiumPrototypePoison";
const forbidden = ["__proto__", "constructor", "prototype"];
const payload = () => JSON.parse('{"__proto__":{"tauridiumPrototypePoison":true},"constructor":{"prototype":{"tauridiumPrototypePoison":true}},"prototype":{"tauridiumPrototypePoison":true},"valid":{"kept":true}}');

function assertClean(value, label) {
  assert.equal(Object.getPrototypeOf(value), Object.prototype, `${label}: returned prototype changed`);
  assert.equal(value[marker], undefined, `${label}: inherited attacker property`);
  for (const key of forbidden) {
    assert.equal(Object.hasOwn(value, key), false, `${label}: reserved key ${key} copied`);
  }
}

export function checkPrototypeSafety(merge) {
  for (const [label, target] of [
    ["null target", null], ["undefined target", undefined],
    ["null-prototype target", Object.create(null)],
    ["own reserved target keys", payload()], ["ordinary target", {}],
  ]) {
    const result = merge(target, payload());
    assertClean(result, label);
    assert.deepEqual(result.valid, { kept: true });
  }
  assertClean(merge(payload(), {}), "target copy loop");
  const nested = merge({ settings: null }, { settings: payload() });
  assertClean(nested.settings, "nested null target");
  const copied = merge({ settings: payload() }, { settings: {} });
  assertClean(copied.settings, "nested target copy");
  const array = merge([payload()], [payload()]);
  for (const item of array) assertClean(item, "default array clone");
  for (const key of forbidden) {
    for (const side of ["target", "source"]) {
      const dangerous = Object.defineProperty({}, key, {
        enumerable: true,
        get() { throw new Error(`Forbidden ${side} getter was evaluated: ${key}`); },
      });
      assertClean(side === "target" ? merge(dangerous, {}) : merge({}, dangerous), `${side} getter`);
    }
  }
  assert.equal(({})[marker], undefined, "global Object.prototype was modified");
}

export function checkCompatibility(merge) {
  const left = { nested: { first: 1 }, list: [{ a: 1 }], unchanged: 0 };
  const right = { nested: { second: 2 }, list: [{ b: 2 }], unchanged: false };
  const before = JSON.stringify([left, right]);
  const result = merge(left, right);
  assert.deepEqual(result, { nested: { first: 1, second: 2 }, list: [{ a: 1 }, { b: 2 }], unchanged: false });
  assert.equal(JSON.stringify([left, right]), before, "merge mutated its inputs");
  assert.notEqual(result.nested, left.nested);
  assert.notEqual(result.list[0], left.list[0]);
  const replacement = [{ replacement: true }];
  const replaced = merge({ list: [1] }, { list: replacement }, {
    arrayMerge: (target, source) => source ?? target,
  });
  assert.equal(replaced.list, replacement, "Svelte's array replacement semantics changed");
  const symbol = Symbol("__proto__");
  const symbolic = merge({ [symbol]: { first: 1 } }, { [symbol]: { second: 2 } });
  assert.deepEqual(symbolic[symbol], { first: 1, second: 2 });
  assertClean(symbolic, "symbol key");
  const date = new Date(0);
  const regexp = /tauridium/;
  const fn = () => true;
  const special = merge({}, { date, regexp, fn, nil: null, unset: undefined });
  assert.equal(special.date, date);
  assert.equal(special.regexp, regexp);
  assert.equal(special.fn, fn);
  assert.equal(special.nil, null);
  assert.equal(Object.hasOwn(special, "unset"), true);
  const inherited = Object.create({ untrusted: true });
  inherited.kept = 1;
  assert.deepEqual(merge({}, inherited), { kept: 1 });
  assert.deepEqual(merge.all([{ a: 1 }, { b: 2 }]), { a: 1, b: 2 });
  assert.deepEqual(merge({ nested: { a: 1 } }, { nested: { b: 2 } }, {
    customMerge: (key) => key === "nested" ? () => ({ custom: true }) : undefined,
  }), { nested: { custom: true } });
  const reference = { value: true };
  assert.equal(merge({}, { reference }, { clone: false }).reference, reference);
}

export async function checkInstallation() {
  const vendor = path.join(root, "vendor", "deepmerge");
  const provenance = JSON.parse(fs.readFileSync(path.join(vendor, "TAURIDIUM-PATCH.json"), "utf8"));
  assert.equal(provenance.version, "4.3.1+tauridium.1");
  assert.equal(provenance.upstream.name, "deepmerge");
  assert.equal(provenance.upstream.version, "4.3.1");
  assert.equal(provenance.upstream.url, "https://registry.npmjs.org/deepmerge/-/deepmerge-4.3.1.tgz");
  assert.equal(provenance.upstream.sha512, "sha512-3sUqbMEc77XqpdNO7FRyRog+eW3ph+GYCbj+rK+uYyRMuwsVy0rMiVtPn+QJlKFvWP/1PYpapqYn0Me2knFn+A==");
  assert.deepEqual(Object.keys(provenance.files).sort(), ["LICENSE", "dist/cjs.js", "index.d.ts", "package.json"]);
  for (const [relative, expected] of Object.entries(provenance.files)) {
    const actual = crypto.createHash("sha256").update(fs.readFileSync(path.join(vendor, relative))).digest("hex");
    assert.equal(actual, expected, `Backport content changed: ${relative}`);
  }
  const metadata = JSON.parse(fs.readFileSync(path.join(vendor, "package.json"), "utf8"));
  assert.equal(metadata.version, provenance.version);
  assert.equal(metadata.main, "dist/cjs.js");
  const require = createRequire(path.join(root, "package.json"));
  const pluginEntry = require.resolve("@sveltejs/vite-plugin-svelte");
  const pluginRequire = createRequire(pluginEntry);
  assert.equal(fs.realpathSync(pluginRequire.resolve("deepmerge")), fs.realpathSync(path.join(vendor, "dist", "cjs.js")),
    "Svelte must resolve the explicit patched dependency, not a nested registry copy");
  const merge = pluginRequire("deepmerge");
  checkPrototypeSafety(merge);
  checkCompatibility(merge);
  const optionsUrl = new URL("./utils/options.js", pathToFileURL(pluginEntry));
  const { preResolveOptions } = await import(optionsUrl.href);
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "tauridium-merge-probe-"));
  try {
    const ordinary = await preResolveOptions({ configFile: false, extensions: [".svelte"], compilerOptions: { dev: false } },
      { root: directory }, { command: "build", mode: "production" });
    assert.deepEqual(ordinary.extensions, [".svelte"]);
    assert.equal(ordinary.compilerOptions.dev, false);
    // Exercise the real plugin's null-placeholder merge, not only the library API.
    const configFile = path.join(directory, "svelte.config.mjs");
    fs.writeFileSync(configFile, "export default { compilerOptions: null };\n");
    const merged = await preResolveOptions({ configFile, compilerOptions: payload() },
      { root: directory }, { command: "build", mode: "production" });
    assertClean(merged.compilerOptions, "actual Svelte options merge");
    assert.deepEqual(merged.compilerOptions.valid, { kept: true });
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
  console.log("Patched deepmerge: provenance, actual Svelte resolution, prototype controls and configuration compatibility validated.");
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await checkInstallation();
}
