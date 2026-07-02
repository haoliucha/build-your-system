#!/usr/bin/env node
// snapshot.cjs — scan the accounts MY_HANDLE follows on x.com/<me>/following and write
// ALL scanned rows (with a real isFollowingMe verdict) into a dated JSONL snapshot.
// Cross-day snapshots accumulate so classify.cjs can compute "days not following back";
// classify/hygiene only count isFollowingMe === false rows, so mutual rows are inert
// history that makes coverage auditable in-file.
//
// Detection contract (post-2026-07-02 false-positive fix):
//   - rows are ONLY [data-testid="UserCell"] elements (no generic-class selectors —
//     the old css-175oi2r selector matched ghost sub-divs and flagged 72% of mutuals)
//   - badge = [data-testid="userFollowIndicator"] presence, text regex as fallback
//   - decisions live in lib/cell-parse.cjs (pure, unit-tested): unhydrated cells yield
//     NO observation, and a seen-badge (true) can never be downgraded by a later
//     badge-less read (everTrue merge)
//   - the scroll loop runs in Node (one thin page-evaluate per round) and stops on
//     scanned-set + scrollHeight stagnation, with bottom-error retry and coverage
//     recovery ported from the proven followers ground-truth scraper
//   - coverage is measured against the profile header's following count and reported
//     in stdout JSON; low coverage warns by default (COVERAGE_STRICT=1 -> exit 17)
//
// Usage:
//   MY_HANDLE=you NODE_PATH=~/.config/playwright-mcp-server/node_modules node snapshot.cjs [--limit=N]
// Env: MY_HANDLE (required), PROFILE_DIR, XU_DATA_DIR, ALERT_PATH, SNAPSHOT_DATE (YYYY-MM-DD),
//      MAX_SCROLL_ROUNDS=300, SCROLL_WAIT_MS=900, SCROLL_IDLE_LIMIT=8,
//      MIN_COVERAGE_PCT=95, COVERAGE_STRICT=0, EXPECTED_FOLLOWING (header-count override)
// Output: stdout JSON { date, handle, count, file, scannedTotal, mutualCount, nonRecipCount,
//                       headerFollowingCount, coveragePct, coverageWarning }
//         writes XU_DATA_DIR/snapshots/<date>.jsonl
//
// NOTE: per-row follower counts from the /following list are rough (X rarely renders
// them). They are best-effort only; the authoritative count comes from profile-counts.cjs.

const fs = require('fs');
const path = require('path');
const os = require('os');
const { chromium } = require('playwright');
const { gotoRobust } = require(path.join(__dirname, 'lib', 'nav-helper.cjs'));
const { detectAnomaly, writeAlert, EXIT_CODES } = require(path.join(__dirname, 'lib', 'anomaly.cjs'));
const { todayInShanghai } = require(path.join(__dirname, 'lib', 'hygiene.cjs'));
const { parseCount } = require(path.join(__dirname, 'lib', 'filters.cjs'));
const { parseCell, mergeObservation } = require(path.join(__dirname, 'lib', 'cell-parse.cjs'));

const HANDLE = (process.env.MY_HANDLE || '').replace(/^@/, '').trim();
const PROFILE_DIR = process.env.PROFILE_DIR || path.join(os.homedir(), '.config/playwright-chrome-profile-campaign');
const DATA_DIR = process.env.XU_DATA_DIR || path.join(os.homedir(), '.config/x-unfollow-data');
const SNAP_DIR = path.join(DATA_DIR, 'snapshots');
const ALERT_PATH = process.env.ALERT_PATH || path.join(DATA_DIR, 'ALERT.txt');
const DATE = process.env.SNAPSHOT_DATE || todayInShanghai();

const MAX_SCROLL_ROUNDS = parseInt(process.env.MAX_SCROLL_ROUNDS || '300', 10);
const SCROLL_WAIT_MS = parseInt(process.env.SCROLL_WAIT_MS || '900', 10);
const SCROLL_IDLE_LIMIT = parseInt(process.env.SCROLL_IDLE_LIMIT || '8', 10);
const MIN_COVERAGE_PCT = parseInt(process.env.MIN_COVERAGE_PCT || '95', 10);
const COVERAGE_STRICT = process.env.COVERAGE_STRICT === '1';
const EXPECTED_FOLLOWING = parseInt(process.env.EXPECTED_FOLLOWING || '0', 10);
const LIMIT = parseInt((process.argv.find((a) => a.startsWith('--limit=')) || '').split('=')[1] || '0', 10);

const EXIT_COVERAGE_LOW = 17; // outside anomaly codes 10-14

if (!HANDLE) { console.error('FATAL: MY_HANDLE env var required (your X handle, no @)'); process.exit(2); }
function ensureDir(p) { if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true }); }
const say = (m) => process.stderr.write(`[snapshot] ${m}\n`);

// Thin page-side collector: raw attributes only, ALL decisions happen in Node via
// lib/cell-parse.cjs so they stay unit-testable. Runs once per scroll round.
const collectCells = () => {
  const cells = [];
  for (const cell of document.querySelectorAll('[data-testid="UserCell"]')) {
    const av = cell.querySelector('[data-testid^="UserAvatar-Container-"]');
    const nameEl = cell.querySelector('div[dir="ltr"]');
    cells.push({
      avatarTestId: av ? av.getAttribute('data-testid') : null,
      hrefs: Array.from(cell.querySelectorAll('a[href^="/"]')).map((a) => a.getAttribute('href')),
      hasFollowIndicator: !!cell.querySelector('[data-testid="userFollowIndicator"]'),
      hasActionButton: !!cell.querySelector('[data-testid$="-follow"], [data-testid$="-unfollow"]'),
      nameText: ((nameEl && nameEl.innerText) || '').split('\n')[0].trim(),
      innerText: cell.innerText || '',
    });
  }
  return { cells, scrollHeight: document.documentElement.scrollHeight };
};

// Bottom-of-list soft error ("出错了。请尝试重新加载。" with a retry button).
const bottomError = () => /出错了|尝试重新加载|Something went wrong|Try reloading/i
  .test((document.body && document.body.innerText) || '');
const clickRetry = () => {
  for (const el of document.querySelectorAll('button, div[role="button"]')) {
    const t = (el.innerText || '').trim();
    if (/^(重试|重新加载|Retry|Try again)$/i.test(t)) { el.click(); return t; }
  }
  return null;
};

async function haltOnAnomaly(page, ctx, where) {
  const anomaly = await detectAnomaly(page);
  if (anomaly && anomaly.type !== 'EVAL_ERROR' && anomaly.type !== 'EMPTY_PAGE') {
    writeAlert(ALERT_PATH, { ...anomaly, where, handle: HANDLE, url: page.url(), profileDir: PROFILE_DIR, dataDir: DATA_DIR });
    say(`ANOMALY ${anomaly.type} at ${where} — see ${ALERT_PATH}`);
    await ctx.close();
    process.exit(EXIT_CODES[anomaly.type] || 99);
  }
}

async function main() {
  ensureDir(SNAP_DIR);
  say(`@${HANDLE} /following  date=${DATE}  rounds<=${MAX_SCROLL_ROUNDS} idle=${SCROLL_IDLE_LIMIT} wait=${SCROLL_WAIT_MS}ms`);

  const ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
    channel: 'chrome', headless: false, viewport: { width: 1400, height: 1000 },
    ignoreDefaultArgs: ['--enable-automation'], args: ['--disable-blink-features=AutomationControlled'],
  });
  const page = ctx.pages()[0] || await ctx.newPage();

  // ---- Phase A: profile header hop — expected following count (coverage baseline).
  // Non-fatal on failure: coverage becomes unknown; EXPECTED_FOLLOWING env overrides.
  let headerFollowingCount = EXPECTED_FOLLOWING > 0 ? EXPECTED_FOLLOWING : null;
  if (headerFollowingCount === null) {
    const navProfile = await gotoRobust(page, `https://x.com/${HANDLE}`, {
      needSel: `a[href="/${HANDLE}/following"]`, settle: 6000, retries: 3,
    });
    await haltOnAnomaly(page, ctx, 'profile-header');
    if (navProfile.ok) {
      const raw = await page.evaluate((h) => {
        const el = document.querySelector(`a[href="/${h}/following"]`);
        return el ? el.innerText : null;
      }, HANDLE);
      const parsed = parseCount(String(raw || '').replace(/\n/g, ' '));
      headerFollowingCount = parsed > 0 ? parsed : null; // parseCount is -1 on failure; <=0 => unknown
      say(`header following count = ${headerFollowingCount === null ? 'unknown' : headerFollowingCount} (raw="${String(raw || '').replace(/\n/g, '|')}")`);
    } else {
      say(`WARN: profile header never rendered (${navProfile.attempts} attempts) — coverage will be unknown`);
    }
  }

  // ---- Phase B: the /following list itself (hard-fail on anomaly / login redirect).
  const nav = await gotoRobust(page, `https://x.com/${HANDLE}/following`, {
    needSel: '[data-testid="UserCell"], [data-testid="primaryColumn"]', settle: 5000, retries: 4,
  });
  await haltOnAnomaly(page, ctx, 'following-nav');
  if (!nav.ok) {
    writeAlert(ALERT_PATH, { type: 'LOGIN_REDIRECT', text: '/following did not render', handle: HANDLE, url: page.url(), profileDir: PROFILE_DIR, dataDir: DATA_DIR });
    say(`/following did not render after ${nav.attempts} attempts (login expired?) — see ${ALERT_PATH}`);
    await ctx.close();
    process.exit(EXIT_CODES.LOGIN_REDIRECT);
  }
  await page.waitForTimeout(1500);

  // ---- Phase C: Node-side scroll loop. Idle counts SCANNED-set + scrollHeight
  // stagnation (never the flagged subset), with read-only recovery paths.
  const scanned = new Map();
  const coverageFloor = headerFollowingCount ? Math.round(headerFollowingCount * MIN_COVERAGE_PCT / 100) : null;
  let idle = 0, prevCount = 0, prevHeight = 0, retryClicks = 0, recoveries = 0, rounds = 0;
  for (rounds = 1; rounds <= MAX_SCROLL_ROUNDS; rounds++) {
    const { cells, scrollHeight } = await page.evaluate(collectCells);
    for (const c of cells) mergeObservation(scanned, parseCell(c));
    if (scanned.size > prevCount || scrollHeight > prevHeight) idle = 0; else idle++;
    prevCount = scanned.size; prevHeight = scrollHeight;

    if (rounds % 20 === 0) {
      say(`round ${rounds}/${MAX_SCROLL_ROUNDS}: scanned=${scanned.size} idle=${idle}`);
      await haltOnAnomaly(page, ctx, `scroll-round-${rounds}`);
    }

    if (idle >= SCROLL_IDLE_LIMIT) {
      // Recovery 1: bottom "出错了/重试" soft error -> backoff, click retry (read-only reload).
      if (retryClicks < 3 && await page.evaluate(bottomError)) {
        const wait = 20000 * Math.pow(2, retryClicks);
        retryClicks++;
        say(`bottom error detected; backoff ${wait / 1000}s then retry click (${retryClicks}/3)`);
        await page.waitForTimeout(wait);
        await page.evaluate(clickRetry);
        await page.waitForTimeout(6000);
        idle = 0;
        continue;
      }
      // Recovery 2: coverage shortfall -> scroll up, slow re-scroll to re-trigger hydration.
      if (coverageFloor && scanned.size < coverageFloor && recoveries < 2) {
        recoveries++;
        say(`stalled at ${scanned.size} (<${MIN_COVERAGE_PCT}% of ${headerFollowingCount}); recovery ${recoveries}/2`);
        await page.evaluate(() => window.scrollBy(0, -4000));
        await page.waitForTimeout(3500);
        for (let i = 0; i < 5; i++) {
          await page.evaluate(() => window.scrollBy(0, window.innerHeight * 0.85));
          await page.waitForTimeout(1500);
          const b = await page.evaluate(collectCells);
          for (const c of b.cells) mergeObservation(scanned, parseCell(c));
        }
        await page.waitForTimeout(6000);
        idle = 0;
        continue;
      }
      say(`stable: scanned=${scanned.size} unchanged for ${SCROLL_IDLE_LIMIT} rounds; stopping`);
      break;
    }

    await page.evaluate(() => window.scrollBy(0, window.innerHeight * 0.85));
    await page.waitForTimeout(SCROLL_WAIT_MS);
  }
  { // final sweep
    const fin = await page.evaluate(collectCells);
    for (const c of fin.cells) mergeObservation(scanned, parseCell(c));
  }
  await ctx.close();

  // ---- Output: ALL scanned rows, real isFollowingMe. --limit is a test aid.
  let rows = Array.from(scanned.values());
  const scannedTotal = rows.length;
  if (LIMIT > 0) rows = rows.slice(0, LIMIT);
  const mutualCount = rows.filter((r) => r.isFollowingMe === true).length;
  const nonRecipCount = rows.length - mutualCount;
  const coveragePct = headerFollowingCount
    ? Math.round((scannedTotal / headerFollowingCount) * 1000) / 10
    : null;
  const coverageWarning = coveragePct !== null && coveragePct < MIN_COVERAGE_PCT;

  const file = path.join(SNAP_DIR, `${DATE}.jsonl`);
  const extractedAt = new Date().toISOString();
  const lines = rows.map((r) => JSON.stringify({
    handle: r.handle, name: r.name, followers: r.followers, isFollowingMe: r.isFollowingMe, extractedAt,
  }));
  fs.writeFileSync(file, lines.join('\n') + (lines.length ? '\n' : ''), 'utf8');

  say(`wrote ${rows.length} rows (${nonRecipCount} non-recip, ${mutualCount} mutual) -> ${file}`);
  say(`coverage: scanned=${scannedTotal} expected=${headerFollowingCount === null ? 'unknown' : headerFollowingCount} pct=${coveragePct === null ? 'n/a' : coveragePct} rounds=${rounds} recoveries=${recoveries} retryClicks=${retryClicks}`);
  if (coverageWarning) say(`WARN: coverage ${coveragePct}% < ${MIN_COVERAGE_PCT}% — some followed accounts were NOT scanned; they are simply absent today (fail-safe), rerun or raise MAX_SCROLL_ROUNDS`);

  console.log(JSON.stringify({
    date: DATE, handle: HANDLE, count: rows.length, file,
    scannedTotal, mutualCount, nonRecipCount, headerFollowingCount, coveragePct, coverageWarning,
  }, null, 2));

  if (coverageWarning && COVERAGE_STRICT) process.exit(EXIT_COVERAGE_LOW);
}

main().catch((e) => { console.error('FATAL', e.stack || e); process.exit(99); });
