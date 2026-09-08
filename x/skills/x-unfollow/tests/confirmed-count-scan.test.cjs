#!/usr/bin/env node
'use strict';

// Exercise the actual scanner with synthetic browser responses, real staging files,
// and immediate timers. No Chrome, X requests, or production data are touched.
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const vm = require('vm');
const { createRequire } = require('module');
const { EventEmitter } = require('events');
const { buildFollowersResponse, userEntry } = require('./fixtures/followers-response.cjs');
const SCRIPT = path.join(__dirname, '../scripts/list-snapshot.cjs');
const localRequire = createRequire(SCRIPT);
const Anomaly = localRequire('./lib/anomaly.cjs');

async function runScan({ count = 1285, expected = '1285', baseline = 1168, atBottom = true,
  broken = false, exhausted = false, late429 = false, hold = false, changingTail = false } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'xu-confirmed-scan-'));
  fs.mkdirSync(path.join(dir, 'current'));
  const oldMeta = JSON.stringify({ count: baseline, complete: true, observedDate: '2026-08-30' });
  fs.writeFileSync(path.join(dir, 'current/following.meta.json'), oldMeta);
  const page = new EventEmitter();
  let emitted = 0; let idleWheels = 0; let closed = false; let keptAlive = false;
  let url = 'https://x.com/fixture/following';
  let output = ''; let sent429 = false;
  const pageCount = Math.ceil(count / 50);
  const emitPage = () => {
    if (emitted >= pageCount) { idleWheels++; return; }
    const index = emitted++;
    const users = Array.from({ length: Math.min(50, count - index * 50) }, (_, n) =>
      userEntry(index * 50 + n, { handle: `u${index * 50 + n}`, followedBy: true }));
    const cursor = index === 0 ? null : broken ? 'wrong' : `c${index}`;
    const payload = buildFollowersResponse({ users, bottom: exhausted && emitted === pageCount ? null : `c${index + 1}` });
    const responseUrl = `https://x.com/i/api/graphql/fixture/Following?variables=${encodeURIComponent(JSON.stringify({ cursor }))}`;
    page.emit('response', { status: () => 200, url: () => responseUrl,
      finished: async () => null, json: async () => payload });
  };
  page.url = () => url;
  page.mainFrame = () => page;
  page.close = async () => { closed = true; };
  page.waitForTimeout = async () => {};
  page.mouse = { move: async () => {}, wheel: async () => emitPage() };
  page.evaluate = async (fn) => {
    if (fn.name !== 'collectCells') return 0;
    if (late429 && idleWheels >= 8 && !sent429) {
      sent429 = true;
      page.emit('response', { status: () => 429, url: () => 'https://x.com/i/api/graphql/fixture/Following' });
    }
    return { cells: [], atBottom, tailTestId: changingTail ? `moving-${idleWheels}` : 'tail' };
  };
  const proc = { pid: process.pid, env: { MY_HANDLE: 'fixture', MODE: 'report', XU_DATA_DIR: dir,
    XU_RUN_TOKEN: 'test-run', XU_HEADLESS: hold ? '0' : '1', XU_DEBUG_HOLD_ON_ERROR: hold ? '1' : '0',
    ...(expected === undefined ? {} : { EXPECTED_COUNT: expected }) }, argv: ['node', SCRIPT],
    stderr: { write: (s) => { output += s; } }, stdout: { write: (s) => { output += s; } }, exitCode: 0 };
  class BrowserConfigError extends Error {}
  class XAuthenticationError extends Error {}
  const sandbox = { process: proc, console: { error: (s) => { output += s; } },
    setTimeout: (fn) => setTimeout(fn, 0), clearTimeout,
    setInterval: () => { keptAlive = true; return 1; },
    require: (id) => {
      if (id === './lib/rate-gate.cjs') return { assertRunToken() {} };
      if (id === './lib/cdp-browser.cjs') return { BrowserConfigError, XAuthenticationError,
        withAuthenticatedContext: async (_, operation) => {
          try { return await operation({ context: { pages: () => [page] }, confirmAuthenticated: async () => {} }); }
          finally { closed = true; }
        } };
      if (id === './lib/nav-helper.cjs') return { gotoRobust: async () => { emitPage(); return { ok: true }; } };
      if (id === './lib/anomaly.cjs') return { ...Anomaly, detectAnomaly: async () => null };
      return localRequire(id);
    } };
  try {
    const source = fs.readFileSync(SCRIPT, 'utf8').replace('main().catch(', 'globalThis.finished = main().catch(');
    vm.runInNewContext(source, sandbox, { filename: SCRIPT });
    if (hold) {
      for (let i = 0; i < 300 && !keptAlive; i++) await new Promise((resolve) => setTimeout(resolve, 1));
      assert.strictEqual(keptAlive, true, output);
      // A user can navigate in a held scene without the frame listener closing it.
      url = 'https://x.com/fixture'; page.emit('framenavigated', page);
      assert.strictEqual(closed, false);
      assert.strictEqual(page.listenerCount('response'), 0);
      assert.match(fs.readFileSync(path.join(dir, 'ALERT.txt'), 'utf8'), /browser remains OPEN/);
    } else await sandbox.finished;
    const stage = path.join(dir, '.staging/test-run');
    const metaFile = path.join(stage, 'following.meta.json');
    const meta = fs.existsSync(metaFile) ? JSON.parse(fs.readFileSync(metaFile)) : null;
    const rows = meta ? fs.readFileSync(path.join(stage, 'following.jsonl'), 'utf8').trim().split('\n').map(JSON.parse) : [];
    assert.strictEqual(fs.readFileSync(path.join(dir, 'current/following.meta.json'), 'utf8'), oldMeta);
    if (!meta) assert.strictEqual(fs.existsSync(stage), false, 'failed staging must be removed');
    return { meta, rows, output, exitCode: proc.exitCode, closed };
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
}

async function main() {
  let passed = 0;
  async function test(name, fn) { await fn(); passed++; console.log(`  ✅ ${name}`); }
  await test('1285 with stale 1168 baseline promotes truthful pending-cursor staging', async () => {
    const r = await runScan();
    assert.strictEqual(r.exitCode, 0, r.output);
    assert.strictEqual(r.rows.length, 1285);
    assert.strictEqual(r.meta.completionEvidence, 'confirmed_count_stable_bottom');
    assert.strictEqual(r.meta.cursorChainComplete, false);
    assert.strictEqual(r.meta.expectedCountSource, 'user_confirmed');
    assert.strictEqual(r.meta.expectedCountTolerancePct, 1);
    assert.strictEqual(r.meta.previousBaselineDate, '2026-08-30');
    assert.strictEqual(r.meta.bottomStableRounds >= 8, true);
  });
  await test('inclusive lower/upper 1% bounds preserve actual row counts', async () => {
    for (const count of [1273, 1297]) {
      const r = await runScan({ count });
      assert.strictEqual(r.exitCode, 0, r.output);
      assert.strictEqual(r.rows.length, count);
      assert.strictEqual(r.meta.expectedCountDelta, count - 1285);
    }
  });
  await test('outside tolerance cannot fall back to old baseline even with exhausted cursor', async () => {
    for (const count of [1272, 1298]) for (const exhausted of [false, true]) {
      const r = await runScan({ count, baseline: count, exhausted });
      assert.strictEqual(r.exitCode, 17, r.output); assert.strictEqual(r.meta, null);
    }
  });
  await test('matching count above page bottom is rejected', async () => {
    const r = await runScan({ atBottom: false });
    assert.strictEqual(r.exitCode, 17, r.output); assert.strictEqual(r.meta, null);
    assert.match(r.output, /bottom_not_stable/);
  });
  await test('broken cursor chain is rejected despite matching total', async () => {
    const r = await runScan({ broken: true });
    assert.strictEqual(r.exitCode, 17, r.output); assert.match(r.output, /CURSOR_CHAIN_BROKEN/);
  });
  await test('late 429 at stable bottom wins over count-based completion', async () => {
    const r = await runScan({ late429: true });
    assert.strictEqual(r.exitCode, 11, r.output); assert.strictEqual(r.meta, null);
  });
  await test('without expected count the existing historical baseline behavior remains', async () => {
    const ok = await runScan({ count: 1168, expected: '' });
    assert.strictEqual(ok.exitCode, 0, ok.output);
    assert.strictEqual(ok.meta.completionEvidence, 'baseline_coverage_stable');
    const rejected = await runScan({ expected: '' });
    assert.strictEqual(rejected.exitCode, 17, rejected.output);
    assert.match(rejected.output, /previousBaselineCeiling/);
    assert.match(rejected.output, /2026-08-30/);
  });
  await test('headed debug hold retains context, disables capture and allows manual navigation', async () => {
    const r = await runScan({ count: 1272, hold: true });
    assert.strictEqual(r.closed, false); assert.match(r.output, /DEBUG_HOLD/);
  });
  console.log(`\n${passed} confirmed-count scanner tests passed`);
}
main().catch((e) => { console.error(e); process.exitCode = 1; });
