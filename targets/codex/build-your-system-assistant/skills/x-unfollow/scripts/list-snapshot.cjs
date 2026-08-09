#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { chromium } = require('playwright');
const { gotoRobust } = require('./lib/nav-helper.cjs');
const { detectAnomaly, writeAlert, EXIT_CODES } = require('./lib/anomaly.cjs');
const { parseCount } = require('./lib/filters.cjs');
const { parseCell, parseMembershipCell, mergeObservation } = require('./lib/cell-parse.cjs');
const { normalizeHandle, todayInShanghai } = require('./lib/hygiene.cjs');
const { assertRunToken } = require('./lib/rate-gate.cjs');
const Scan = require('./lib/list-scan-state.cjs');
const {
  SNAPSHOT_MAX_ROUNDS, SNAPSHOT_WAIT_MIN_MS, SNAPSHOT_WAIT_MAX_MS,
  SNAPSHOT_LONG_BREAK_EVERY, SNAPSHOT_LONG_BREAK_MS, boundedInt, jitterMs,
} = require('./lib/rate-policy.cjs');

const arg = (name) => (process.argv.find((item) => item.startsWith(`${name}=`)) || '').slice(name.length + 1);
const HANDLE = String(process.env.MY_HANDLE || '').replace(/^@/, '').trim();
const LIST_TYPE = arg('--list') || 'following';
const RUN_ID = arg('--run-id') || process.env.XU_RUN_TOKEN || '';
const DATA_DIR = process.env.XU_DATA_DIR || path.join(os.homedir(), '.config/x-unfollow-data');
const PROFILE_DIR = process.env.PROFILE_DIR || path.join(os.homedir(), '.config/playwright-chrome-profile-campaign');
const ALERT_PATH = process.env.ALERT_PATH || path.join(DATA_DIR, 'ALERT.txt');
const STAGING_DIR = path.join(DATA_DIR, '.staging', RUN_ID);
const MAX_ROUNDS = boundedInt(process.env.MAX_SCROLL_ROUNDS, SNAPSHOT_MAX_ROUNDS, { min: 1, max: SNAPSHOT_MAX_ROUNDS });
const WAIT_MIN = boundedInt(process.env.SCROLL_WAIT_MS, SNAPSHOT_WAIT_MIN_MS, { min: SNAPSHOT_WAIT_MIN_MS });
const WAIT_MAX = boundedInt(process.env.SCROLL_WAIT_MAX_MS, SNAPSHOT_WAIT_MAX_MS, { min: WAIT_MIN });
const STABLE_LIMIT = boundedInt(process.env.SCROLL_IDLE_LIMIT, 8, { min: 8 });
const MIN_COVERAGE = boundedInt(process.env.MIN_COVERAGE_PCT, 95, { min: 95, max: 100 });
const EXPECTED_OVERRIDE = Number.parseInt(process.env.EXPECTED_LIST_COUNT || '0', 10);
const say = (message) => process.stderr.write(`[list-snapshot] ${message}\n`);
let detectedDriftUrl = null;

if (!HANDLE || !/^[A-Za-z0-9_]{1,15}$/.test(HANDLE)) throw new Error('MY_HANDLE required');
if (!['following', 'followers'].includes(LIST_TYPE)) throw new Error('--list must be following or followers');
if (!RUN_ID) throw new Error('--run-id required');

const collectCells = () => ({
  cells: [...document.querySelectorAll('[data-testid="UserCell"]')].map((cell) => {
    const avatar = cell.querySelector('[data-testid^="UserAvatar-Container-"]');
    const name = cell.querySelector('div[dir="ltr"]');
    return {
      avatarTestId: avatar && avatar.getAttribute('data-testid'),
      hrefs: [...cell.querySelectorAll('a[href^="/"]')].map((a) => a.getAttribute('href')),
      hasFollowIndicator: !!cell.querySelector('[data-testid="userFollowIndicator"]'),
      hasActionButton: !!cell.querySelector('[data-testid$="-follow"], [data-testid$="-unfollow"]'),
      nameText: ((name && name.innerText) || '').split('\n')[0].trim(),
      innerText: cell.innerText || '',
    };
  }),
  scrollHeight: document.documentElement.scrollHeight,
});

function removeStaging() { fs.rmSync(STAGING_DIR, { recursive: true, force: true }); }
function pageDrift(actualUrl) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  writeAlert(ALERT_PATH, {
    type: 'PAGE_DRIFT', text: `expected https://x.com${Scan.expectedListPath(HANDLE, LIST_TYPE)}; actual ${actualUrl}`,
    expectedUrl: `https://x.com${Scan.expectedListPath(HANDLE, LIST_TYPE)}`, actualUrl,
    handle: HANDLE, url: actualUrl, profileDir: PROFILE_DIR, dataDir: DATA_DIR,
  });
}

async function main() {
  assertRunToken();
  fs.mkdirSync(STAGING_DIR, { recursive: true });
  const expectedUrl = `https://x.com${Scan.expectedListPath(HANDLE, LIST_TYPE)}`;
  say(`target=${LIST_TYPE} url=${expectedUrl} hard-cap=${MAX_ROUNDS} worst-case≈37–48min cadence=${WAIT_MIN}-${WAIT_MAX}ms + ${SNAPSHOT_LONG_BREAK_MS / 1000}s/10 rounds`);
  const context = await chromium.launchPersistentContext(PROFILE_DIR, {
    channel: 'chrome', headless: false, viewport: { width: 1400, height: 1000 },
    ignoreDefaultArgs: ['--enable-automation'], args: ['--disable-blink-features=AutomationControlled'],
  });
  const page = context.pages()[0] || await context.newPage();
  let armed = false;
  let driftUrl = null;
  page.on('framenavigated', (frame) => {
    if (armed && frame === page.mainFrame() && !Scan.isExpectedListUrl(frame.url(), HANDLE, LIST_TYPE)) {
      driftUrl = frame.url(); detectedDriftUrl = driftUrl;
      pageDrift(driftUrl); removeStaging();
      void context.close().catch(() => {});
    }
  });
  const assertTarget = async (where) => {
    const actual = page.url();
    if (driftUrl || !Scan.isExpectedListUrl(actual, HANDLE, LIST_TYPE)) {
      pageDrift(driftUrl || actual); removeStaging(); await context.close();
      say(`PAGE_DRIFT at ${where}: expected=${expectedUrl} actual=${driftUrl || actual}`);
      process.exit(15);
    }
  };
  const haltAnomaly = async (where) => {
    const anomaly = await detectAnomaly(page);
    if (anomaly && !['EVAL_ERROR', 'EMPTY_PAGE'].includes(anomaly.type)) {
      writeAlert(ALERT_PATH, { ...anomaly, where, handle: HANDLE, url: page.url(), profileDir: PROFILE_DIR, dataDir: DATA_DIR });
      removeStaging(); await context.close(); process.exit(EXIT_CODES[anomaly.type] || 99);
    }
  };

  let expectedCount = EXPECTED_OVERRIDE > 0 ? EXPECTED_OVERRIDE : null;
  if (expectedCount === null) {
    const link = `a[href="/${HANDLE}/${LIST_TYPE}"]`;
    const profile = await gotoRobust(page, `https://x.com/${HANDLE}`, { needSel: link, settle: 5000, retries: 3 });
    await haltAnomaly('profile-header');
    if (profile.ok) {
      const text = await page.locator(link).first().innerText().catch(() => '');
      const parsed = parseCount(text.replace(/\n/g, ' '));
      if (parsed >= 0) expectedCount = parsed;
    }
  }

  const nav = await gotoRobust(page, expectedUrl, { needSel: '[data-testid="UserCell"], [data-testid="primaryColumn"]', settle: 5000, retries: 4 });
  await haltAnomaly(`${LIST_TYPE}-nav`);
  if (!nav.ok || !Scan.isExpectedListUrl(page.url(), HANDLE, LIST_TYPE)) {
    pageDrift(page.url()); removeStaging(); await context.close(); process.exit(15);
  }
  armed = true;
  await assertTarget('navigation-complete');

  const seen = new Map();
  let state = Scan.initialProgress({ expectedCount, stableLimit: STABLE_LIMIT, minCoveragePct: MIN_COVERAGE });
  let executed = 0;
  let stopReason = null;
  for (let round = 1; round <= MAX_ROUNDS; round++) {
    executed = round;
    await assertTarget(`round-${round}-before`);
    const batch = await page.evaluate(collectCells);
    await assertTarget(`round-${round}-after`);
    for (const raw of batch.cells) {
      const parsed = LIST_TYPE === 'following' ? parseCell(raw) : parseMembershipCell(raw);
      if (LIST_TYPE === 'following') mergeObservation(seen, parsed);
      else if (parsed) seen.set(normalizeHandle(parsed.handle), seen.get(normalizeHandle(parsed.handle)) || parsed);
    }
    try { state = Scan.advanceProgress(state, { uniqueCount: seen.size, scrollHeight: batch.scrollHeight }); }
    catch (error) {
      writeAlert(ALERT_PATH, { type: 'COUNT_ANOMALY', text: error.message, handle: HANDLE, url: page.url(), profileDir: PROFILE_DIR, dataDir: DATA_DIR });
      removeStaging(); await context.close(); process.exit(17);
    }
    if (round % 20 === 0) { say(`round=${round}/${MAX_ROUNDS} unique=${seen.size} stable=${state.stableRounds} coverage=${state.coveragePct ?? 'unknown'}%`); await haltAnomaly(`round-${round}`); }
    if (state.stopReason === 'stable') { stopReason = 'stable'; break; }
    if (state.stableRounds >= STABLE_LIMIT && state.coveragePct !== null && state.coveragePct < MIN_COVERAGE) {
      if (state.recoveries >= 2) { stopReason = 'coverage_low'; break; }
      state = { ...state, recoveries: state.recoveries + 1, stableRounds: 0 };
      await page.evaluate(() => window.scrollBy(0, -4000));
      await page.waitForTimeout(WAIT_MIN);
    }
    await page.evaluate(() => window.scrollBy(0, window.innerHeight * 0.85));
    await page.waitForTimeout(jitterMs(WAIT_MIN, WAIT_MAX));
    if (Scan.shouldPauseAfterRound({ round, maxRounds: MAX_ROUNDS, stopped: false, every: SNAPSHOT_LONG_BREAK_EVERY })) await page.waitForTimeout(SNAPSHOT_LONG_BREAK_MS);
  }
  if (!stopReason) stopReason = 'max_rounds';
  await assertTarget('final');
  const finalUrl = page.url();
  await context.close();

  const generatedAt = new Date().toISOString();
  const rows = [...seen.values()].map((row) => ({ ...row, observedAt: generatedAt }));
  const usableForNegativeDiff = stopReason === 'stable' && state.coveragePct !== null && state.coveragePct >= 99;
  const complete = stopReason === 'stable' && state.coveragePct !== null && state.coveragePct >= MIN_COVERAGE;
  const meta = {
    schemaVersion: 3, runId: RUN_ID, listType: LIST_TYPE, handle: HANDLE,
    observedDate: todayInShanghai(), generatedAt, expectedUrl, finalUrl,
    count: rows.length, headerCount: expectedCount, coveragePct: state.coveragePct,
    rounds: Scan.executedRounds(executed), stableRounds: state.stableRounds,
    recoveries: state.recoveries, stopReason, complete, usableForNegativeDiff,
  };
  if (!complete) { removeStaging(); process.exit(17); }
  fs.writeFileSync(path.join(STAGING_DIR, `${LIST_TYPE}.jsonl`), rows.map((row) => JSON.stringify(row)).join('\n') + (rows.length ? '\n' : ''));
  fs.writeFileSync(path.join(STAGING_DIR, `${LIST_TYPE}.meta.json`), `${JSON.stringify(meta, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify(meta, null, 2)}\n`);
}

main().catch((error) => {
  removeStaging();
  if (detectedDriftUrl) { console.error(`PAGE_DRIFT: ${detectedDriftUrl}`); process.exit(15); }
  console.error(error.stack || error); process.exit(99);
});
