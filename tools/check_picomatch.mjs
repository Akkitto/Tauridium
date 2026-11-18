// Verify the exact local backport, real tool resolution and bounded ReDoS controls.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'package.json'));
const vendor = path.join(root, 'vendor/picomatch');
const manifestBytes = fs.readFileSync(path.join(vendor, 'TAURIDIUM-PATCH.json'));
assert.equal(createHash('sha256').update(manifestBytes).digest('hex'), '0bbade1d0862d8b971e15f90a97920231b145737398e3ee6f2fd20c000668101');
const manifest = JSON.parse(manifestBytes);
assert.equal(manifest.version, '4.0.7+tauridium.1');
assert.equal(manifest.files['lib/parse.js'], '10e08261453bc5e1579afe463d2855940c89b35b821df7cc7483a1f93e42c2e1');
for (const [name, digest] of Object.entries(manifest.files)) {
  assert.equal(createHash('sha256').update(fs.readFileSync(path.join(vendor, name))).digest('hex'), digest);
}
for (const owner of [null, 'vite', 'vitest', 'tinyglobby', 'fdir']) {
  const resolver = owner ? createRequire(require.resolve(owner)) : require;
  assert.equal(fs.realpathSync(resolver.resolve('picomatch')), path.join(vendor, 'index.js'), `${owner}: unpatched matcher`);
}
const match = require('picomatch');
const cases = [
  ['src/**/*.test.ts', 'src/lib/serviceMenu.test.ts', true],
  ['**/*.{test,spec}.?(c|m)[jt]s?(x)', 'src/lib/serviceMenu.test.ts', true],
  ['**/node_modules/**', 'node_modules/vite/index.js', true],
  ['**/*.svelte', 'src/App.svelte', true],
  ['**/*.svelte', 'src/lib/serviceMenu.ts', false],
  ['+(*a)', 'aba', true], ['+(*a)', 'abb', false],
  ['*(a*)', '', false], ['+(a*)', '', false],
  ['a/+(b*)', 'a/bbb', true], ['a/+(b*)', 'a/b/c', false],
  ['+(a|b)', 'abba', true], ['+(a|b)', 'abc', false],
];
for (const [glob, value, expected] of cases) assert.equal(match(glob)(value), expected, `${glob} / ${value}`);
// Deadlines are enforced by a parent process: a regression cannot hang CI.
for (const glob of ['+(*a)', '*(*a)', '+(*)a', '*(*)a', '+(a*b)', '*(a*b)', '+(**a)', '*(**a)', '+(*[ab])', '*(*[ab])', '+(*a/b)', '*(*a/b)']) {
  const source = `const pm=require(${JSON.stringify(path.join(vendor, 'index.js'))}); const m=pm(${JSON.stringify(glob)}); m('a'.repeat(20000)+'!');`;
  const child = spawnSync(process.execPath, ['-e', source], { timeout: 2500, encoding: 'utf8', windowsHide: true });
  assert.equal(child.error, undefined, `${glob}: matcher exceeded deadline`);
  assert.equal(child.status, 0, `${glob}: ${child.stderr}`);
}
assert.equal(match('+(*a)', { capture: true })('+(*a)'), true, 'capture uses safe literal fallback');
console.log('Patched picomatch: exact provenance, real build-tool resolution, glob compatibility and bounded ReDoS controls validated.');
