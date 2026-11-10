// Execute the real injected scripts and pinned public recipes without accounts.
const assert = require('node:assert/strict');
const { readFileSync, existsSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');
const native = readFileSync(path.join(root, 'src-tauri/src/main.rs'), 'utf8');
const raw = name => native.match(new RegExp(`const ${name}: &str = r#"([\\s\\S]*?)"#;`))[1];
const bridgePath = path.join(root, 'src-tauri/src/service_badges.js');
const bridge = existsSync(bridgePath) ? readFileSync(bridgePath, 'utf8') : '';

function environment({ loading = false, counts = {}, title = '', meta = null, nativeMarker = false } = {}) {
  const intervals = [];
  const listeners = new Map();
  const document = {
    readyState: loading ? 'loading' : 'complete', title,
    querySelector(selector) {
      if (selector === 'meta[property="og:url"]') {
        return meta ? { getAttribute: () => meta } : null;
      }
      return counts[selector] ?? null;
    },
    querySelectorAll: selector => counts[selector] ?? [],
    addEventListener: (name, cb) => listeners.set(name, cb),
  };
  const window = { navigator: {}, onload() {}, isTauri: nativeMarker };
  const context = vm.createContext({ window, navigator: window.navigator, document,
    setInterval: cb => { intervals.push(cb); return intervals.length; },
    clearInterval() {}, console: { warn() {} }, location: { origin: 'https://example.test' } });
  const run = script => vm.runInContext(script, context, { timeout: 2000 });
  run(bridge);
  run(raw('IPC_SHIM_JS'));
  return { window, document, counts, intervals, run,
    recipe(name) { run(raw('RECIPE_PREAMBLE') + readFileSync(path.join(__dirname, 'fixtures/badges', `${name}.js`), 'utf8') + raw('RECIPE_SUFFIX')); },
    ready(value = meta) { meta = value; document.readyState = 'interactive'; listeners.get('DOMContentLoaded')?.(); },
    tick() { intervals.slice().forEach(cb => cb()); },
    badge() { return JSON.parse(JSON.stringify(window.__pakeBadge)); },
  };
}

test('standard badge APIs report increases, decreases and explicit zero without DOM guesses', async () => {
  const e = environment();
  assert.equal(typeof e.window.navigator.setAppBadge, 'function');
  assert.equal(await e.window.navigator.setAppBadge(12), undefined);
  assert.equal(e.window.__pakeAppBadge, 12);
  await e.window.navigator.setAppBadge(3);
  assert.equal(e.window.__pakeAppBadge, 3);
  await e.window.navigator.setAppBadge(0);
  assert.equal(e.window.__pakeAppBadge, 0);
  await e.window.navigator.setAppBadge();
  assert.equal(e.window.__pakeAppBadge, 1);
  await e.window.navigator.clearAppBadge();
  assert.equal(e.window.__pakeAppBadge, 0);
});

test('invalid standard counts reject without replacing the last valid count', async () => {
  const e = environment();
  await e.window.navigator.setAppBadge(4);
  for (const invalid of [-1, Infinity, NaN, 2 ** 64, Symbol('invalid'), 1n]) {
    await assert.rejects(e.window.navigator.setAppBadge(invalid));
    assert.equal(e.window.__pakeAppBadge, 4);
  }
  await e.window.navigator.setAppBadge('6');
  assert.equal(e.window.__pakeAppBadge, 6);
  await e.window.navigator.setAppBadge(1.9);
  assert.equal(e.window.__pakeAppBadge, 1);
  await e.window.navigator.setAppBadge(2 ** 53);
  assert.equal(e.window.__pakeAppBadge, 1_000_000);
});

test('a page that does not call the standard API keeps the recipe fallback', () => {
  const e = environment();
  assert.equal(e.window.__pakeAppBadge, undefined);
  e.recipe('discord');
  assert.deepEqual(e.badge(), { direct: 0, indirect: 0 });
});

test('recipe counts retain direct/indirect components and clear both on read', () => {
  const e = environment();
  e.run(raw('RECIPE_PREAMBLE') + 'module.exports = F => F.setBadge(4, 7);' + raw('RECIPE_SUFFIX'));
  assert.deepEqual(e.badge(), { direct: 4, indirect: 7 });
  assert.equal(e.window.__pakeUnread, 11);
  e.window.Ferdium.setBadge(0, 0);
  assert.deepEqual(e.badge(), { direct: 0, indirect: 0 });
  assert.equal(e.window.__pakeUnread, 0);
});

test('malformed recipe counts stay finite and independently bounded', () => {
  const e = environment();
  e.run(raw('RECIPE_PREAMBLE') + 'module.exports = F => F.setBadge(-9, "20000000000000000000000000000");' + raw('RECIPE_SUFFIX'));
  assert.deepEqual(e.badge(), { direct: 0, indirect: 1_000_000 });
  e.window.Ferdium.setBadge(Infinity, 'garbage');
  assert.deepEqual(e.badge(), { direct: 0, indirect: 0 });
});

test('Electron message-counts objects preserve explicit clears and both components', () => {
  const e = environment();
  e.window.ipc = {};
  e.window.ipc.sendToHost('message-counts', { direct: 5, indirect: 2 });
  assert.deepEqual(e.badge(), { direct: 5, indirect: 2 });
  e.window.ipc.sendToHost('message-counts', { direct: 0, indirect: 0 });
  assert.deepEqual(e.badge(), { direct: 0, indirect: 0 });
  e.window.ipc.sendToHost('updateUnread', { count: 8 });
  assert.deepEqual(e.badge(), { direct: 8, indirect: 0 });
  e.window.ipc.sendToHost('updateBadge', 0);
  assert.deepEqual(e.badge(), { direct: 0, indirect: 0 });
  e.window.ipc.sendToHost('unrelated', 99);
  assert.equal(e.window.__pakeUnread, 0);
});

test('Discord can clear read mentions while retaining a separate unread-channel signal', () => {
  const e = environment({ title: '• Discord' });
  const selector = '[class*="lowerBadge_"] [class*="numberBadge_"]';
  e.counts[selector] = [{ textContent: '3' }];
  e.recipe('discord');
  assert.deepEqual(e.badge(), { direct: 3, indirect: 1 });
  e.counts[selector] = [];
  e.tick();
  assert.deepEqual(e.badge(), { direct: 0, indirect: 1 });
  e.document.title = 'Discord';
  e.tick();
  assert.deepEqual(e.badge(), { direct: 0, indirect: 0 });
});

test('GitHub unread/read transitions still use its pinned recipe', () => {
  const e = environment();
  const count = 'li[data-item-id="inbox"] .Counter';
  const indicator = '#AppHeader-notifications-button.AppHeader-button--hasIndicator, [data-target="notification-indicator.badge"]:not([hidden])';
  e.counts[count] = { textContent: '6' };
  e.counts[indicator] = [{}];
  e.recipe('github');
  assert.deepEqual(e.badge(), { direct: 6, indirect: 1 });
  e.counts[count] = null;
  e.counts[indicator] = [];
  e.tick();
  assert.deepEqual(e.badge(), { direct: 0, indirect: 0 });
});

test('Telegram Web K is detected after document parsing, then clears read messages', () => {
  const e = environment({ loading: true });
  e.recipe('telegram');
  assert.equal(e.intervals.length, 0, 'recipe must not initialize before metadata exists');
  const selector = '.rp:not(.is-muted)';
  e.counts[selector] = [{ dataset: { peerId: '42' }, querySelector: () => ({ textContent: '5' }) }];
  e.ready('https://web.telegram.org/k/');
  assert.equal(e.window.__pakeUnread, 5);
  e.counts[selector] = [];
  e.tick();
  assert.equal(e.window.__pakeUnread, 0);
});

test('Telegram Web A receives browser counts instead of invoking its unrelated desktop host', async () => {
  const e = environment({ nativeMarker: true });
  const workaround = readFileSync(path.join(root, 'src-tauri/src/proton_compat.rs'), 'utf8').match(/TAURI_MARKER_WORKAROUND_JS: &str = r#"([\s\S]*?)"#;/)[1];
  e.run(workaround);
  const update = count => e.window.isTauri
    ? assert.fail('Telegram must not call its own privileged desktop commands')
    : e.window.navigator.setAppBadge(count);
  await update(7);
  assert.equal(e.window.__pakeAppBadge, 7);
  await update(0);
  assert.equal(e.window.__pakeAppBadge, 0);
  assert.equal(e.window.tauri, undefined, 'no substitute privileged Telegram bridge');
});

test('fresh documents do not inherit a previous page standard badge', () => {
  const first = environment();
  first.window.navigator.setAppBadge(9);
  const second = environment();
  assert.equal(second.window.__pakeAppBadge, undefined);
  assert.equal(second.window.__pakeUnread, 0);
});
