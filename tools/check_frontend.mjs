// Validate the supported Node runtime and the locked native Vite 8 toolchain.
// All modules and platform bindings must already exist locally; no install
// script, npm shim, WebAssembly fallback or registry download is permitted.
import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const [major, minor] = process.versions.node.split(".").map(Number);
assert(
  (major === 22 && minor >= 12) || major === 24 || major >= 26,
  "Node.js 22.12+, 24 or 26+ is required by the locked frontend tools; install a supported LTS runtime.",
);
if (process.argv.includes("--runtime-only")) {
  console.log(`Node.js ${process.versions.node}: frontend runtime supported.`);
  process.exit(0);
}

assert(!process.env.NAPI_RS_NATIVE_LIBRARY_PATH, "External native binding overrides are prohibited.");
assert(!process.env.NAPI_RS_FORCE_WASI && !process.env.NAPI_RS_WASI_FLAVOR,
  "The frontend probe requires the locked native platform bindings.");
process.env.NAPI_RS_ENFORCE_VERSION_CHECK = "1";
const require = createRequire(import.meta.url);
const lock = JSON.parse(fs.readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"));
function lockedPackage(name) {
  const base = new URL(`../node_modules/${name}/`, import.meta.url);
  const metadata = JSON.parse(fs.readFileSync(new URL("package.json", base), "utf8"));
  assert.equal(metadata.version, lock.packages[`node_modules/${name}`].version);
  return { base, version: metadata.version };
}
const rolldownPackage = lockedPackage("rolldown");
const lightningcssPackage = lockedPackage("lightningcss");
const abi = process.platform === "linux"
  ? (process.report.getReport().header.glibcVersionRuntime ? "gnu" : "musl")
  : process.platform === "win32" ? "msvc" : null;
const platform = [process.platform, process.arch, abi].filter(Boolean).join("-");
for (const [name, expectedVersion] of [
  [`@rolldown/binding-${platform}`, rolldownPackage.version],
  [`lightningcss-${platform}`, lightningcssPackage.version],
]) {
  const binding = lockedPackage(name);
  assert.equal(binding.version, expectedVersion);
  require.resolve(fileURLToPath(binding.base));
}
const rolldown = await import(new URL("dist/index.mjs", rolldownPackage.base));
const { transformSync } = await import(new URL("dist/utils-index.mjs", rolldownPackage.base));
assert.equal(rolldown.VERSION, rolldownPackage.version);
const input = "const tauridiumCheck: number = 1 + 2;\n";
const javascript = transformSync("tauridium-probe.ts", input, { lang: "ts" });
assert.deepEqual(javascript.errors, []);
assert.equal(javascript.code, "const tauridiumCheck = 1 + 2;\n");
const lightningcss = require(fileURLToPath(lightningcssPackage.base));
const css = lightningcss.transform({
  filename: "tauridium-probe.css",
  code: Buffer.from(".tauridium-check { color: #ff0000; }"),
  minify: true,
});
assert.equal(css.code.toString(), ".tauridium-check{color:red}");
console.log(`Local Rolldown ${rolldownPackage.version} and Lightning CSS ${lightningcssPackage.version}: native transforms validated without installation scripts.`);
