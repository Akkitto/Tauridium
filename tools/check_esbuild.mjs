// Probe the locked local API, not an npm shim that may not exist on Windows
// when lifecycle scripts are disabled. This performs a real native transform
// without running postinstall or allowing npm to download a fallback package.
import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const lock = JSON.parse(fs.readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"));
const esbuild = require(fileURLToPath(new URL("../node_modules/esbuild", import.meta.url)));
assert.equal(esbuild.version, lock.packages["node_modules/esbuild"].version);
const input = "let tauridiumCheck = 1 + 2;\n";
assert.equal(esbuild.transformSync(input, { loader: "js" }).code, input);
console.log(`Local esbuild ${esbuild.version}: native transform validated without installation scripts.`);
