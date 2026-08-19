#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { cdpSessionOptions } = require('./lib/browser-launch.cjs');
const { BrowserConfigError, withAuthenticatedContext, XAuthenticationError } = require('./lib/cdp-browser.cjs');
const { gotoRobust } = require('./lib/nav-helper.cjs');
const { detectAnomaly, writeAlert, EXIT_CODES } = require('./lib/anomaly.cjs');
const { parseCell, parseMembershipCell, mergeObservation } = require('./lib/cell-parse.cjs');
const { normalizeHandle, todayInShanghai } = require('./lib/hygiene.cjs');
const { assertRunToken } = require('./lib/rate-gate.cjs');
const Scan = require('./lib/list-scan-state.cjs');
const Timeline = require('./lib/timeline-response.cjs');
const Capture = require('./lib/capture-source.cjs');
const {
  SNAPSHOT_WAIT_MIN_MS, SNAPSHOT_WAIT_MAX_MS,
  SNAPSHOT_LONG_BREAK_EVERY, SNAPSHOT_LONG_BREAK_MS, SNAPSHOT_WATCHDOG_MS,
  boundedInt, jitterMs,
} = require('./lib/rate-policy.cjs');

const arg = (name) => (process.argv.find((item) => item.startsWith(`${name}=`)) || '').slice(name.length + 1);
const HANDLE = String(process.env.MY_HANDLE || '').replace(/^@/, '').trim();
const LIST_TYPE = arg('--list') || 'following';
const RUN_ID = arg('--run-id') || process.env.XU_RUN_TOKEN || '';
const DATA_DIR = process.env.XU_DATA_DIR || path.join(os.homedir(), '.config/x-unfollow-data');
const PROFILE_DIR = process.env.PROFILE_DIR || path.join(os.homedir(), '.config/playwright-chrome-profile-campaign');
const ALERT_PATH = process.env.ALERT_PATH || path.join(DATA_DIR, 'ALERT.txt');
const STAGING_DIR = path.join(DATA_DIR, '.staging', RUN_ID);
const WAIT_MIN = boundedInt(process.env.SCROLL_WAIT_MS, SNAPSHOT_WAIT_MIN_MS, { min: SNAPSHOT_WAIT_MIN_MS });
const WAIT_MAX = boundedInt(process.env.SCROLL_WAIT_MAX_MS, SNAPSHOT_WAIT_MAX_MS, { min: WAIT_MIN });
const STABLE_LIMIT = boundedInt(process.env.SCROLL_IDLE_LIMIT, 8, { min: 8 });
const WATCHDOG_MS = boundedInt(process.env.SNAPSHOT_WATCHDOG_MS, SNAPSHOT_WATCHDOG_MS, { min: SNAPSHOT_WATCHDOG_MS });
const RESPONSE_TIMEOUT_MS = 20000;
const EXPECTED_OPERATION = LIST_TYPE === 'followers' ? 'Followers' : 'Following';
const say = (message) => process.stderr.write(`[list-snapshot] ${message}\n`);
let detectedDriftUrl = null;

class WorkflowExitError extends Error {
  constructor(type, message, exitCode) {
    super(message);
    this.name = 'WorkflowExitError';
    this.type = type;
    this.exitCode = exitCode;
  }
}

if (!HANDLE || !/^[A-Za-z0-9_]{1,15}$/.test(HANDLE)) throw new Error('MY_HANDLE required');
if (!['following', 'followers'].includes(LIST_TYPE)) throw new Error('--list must be following or followers');
if (!RUN_ID) throw new Error('--run-id required');

const collectCells = () => {
  const root = document.querySelector('[data-testid="primaryColumn"]') || document;
  const cells = [...root.querySelectorAll('[data-testid="UserCell"]')];
  return {
    cells: cells.map((cell) => {
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
    tailTestId: cells.at(-1)?.querySelector('[data-testid^="UserAvatar-Container-"]')?.getAttribute('data-testid') || null,
    atBottom: window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 8,
  };
};

const scrollToTail = () => {
  const root = document.querySelector('[data-testid="primaryColumn"]') || document;
  const cells = [...root.querySelectorAll('[data-testid="UserCell"]')];
  if (cells.length) cells.at(-1).scrollIntoView({ block: 'end' });
  window.scrollTo(0, document.documentElement.scrollHeight);
  return cells.length;
};

function responseChannel() {
  const queue = [];
  const waiters = [];
  return {
    publish(value) {
      const waiter = waiters.shift();
      if (waiter) { clearTimeout(waiter.timer); waiter.resolve(value); }
      else queue.push(value);
    },
    take(timeoutMs) {
      if (queue.length) return Promise.resolve(queue.shift());
      if (timeoutMs <= 0) return Promise.resolve(null);
      return new Promise((resolve) => {
        const waiter = { resolve, timer: null };
        waiter.timer = setTimeout(() => {
          const index = waiters.indexOf(waiter);
          if (index >= 0) waiters.splice(index, 1);
          resolve(null);
        }, timeoutMs);
        waiters.push(waiter);
      });
    },
  };
}

function removeStaging() { fs.rmSync(STAGING_DIR, { recursive: true, force: true }); }
function pageDrift(actualUrl) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  writeAlert(ALERT_PATH, {
    type: 'PAGE_DRIFT', text: `expected https://x.com${Scan.expectedListPath(HANDLE, LIST_TYPE)}; actual ${actualUrl}`,
    expectedUrl: `https://x.com${Scan.expectedListPath(HANDLE, LIST_TYPE)}`, actualUrl,
    handle: HANDLE, url: actualUrl, profileDir: PROFILE_DIR, dataDir: DATA_DIR,
  });
}

function mergeRow(seen, row) {
  if (!row?.handle) return;
  const key = normalizeHandle(row.handle);
  const previous = seen.get(key);
  if (!previous) { seen.set(key, { ...row }); return; }
  if (row.isFollowingMe === true && previous.isFollowingMe !== true) previous.isFollowingMe = true;
  else if (typeof previous.isFollowingMe !== 'boolean' && typeof row.isFollowingMe === 'boolean') previous.isFollowingMe = row.isFollowingMe;
  if ((!previous.name || previous.name === previous.handle) && row.name) previous.name = row.name;
}

async function scanList({ context, confirmAuthenticated }) {
  removeStaging();
  fs.mkdirSync(STAGING_DIR, { recursive: true });
  const expectedUrl = `https://x.com${Scan.expectedListPath(HANDLE, LIST_TYPE)}`;
  say(`target=${LIST_TYPE} url=${expectedUrl} capture=passive-${EXPECTED_OPERATION} cadence=${WAIT_MIN}-${WAIT_MAX}ms pause=${SNAPSHOT_LONG_BREAK_MS / 1000}s/${SNAPSHOT_LONG_BREAK_EVERY}-responses watchdog=${WATCHDOG_MS / 60000}min`);
  const page = context.pages()[0] || await context.newPage();
  const channel = responseChannel();
  const responseTasks = new Set();
  let armed = false;
  let driftUrl = null;

  page.on('response', (response) => {
    if (Timeline.operationFromUrl(response.url()) !== EXPECTED_OPERATION) return;
    const task = (async () => {
      const status = response.status();
      if (status === 429) return channel.publish({ errorType: 'RATE_LIMIT', error: `HTTP ${status} ${EXPECTED_OPERATION}` });
      if (status === 401) return channel.publish({ errorType: 'LOGIN_REDIRECT', error: `HTTP ${status} ${EXPECTED_OPERATION}` });
      if (status < 200 || status >= 300) return channel.publish({ errorType: 'COUNT_ANOMALY', error: `HTTP ${status} ${EXPECTED_OPERATION}` });
      try {
        const payload = await response.json();
        const parsed = Timeline.extractTimelineResponse(payload, { listType: LIST_TYPE });
        channel.publish({ ...parsed, requestCursor: Timeline.requestCursorFromUrl(response.url()) });
      } catch (error) {
        channel.publish({ errorType: 'COUNT_ANOMALY', error: `RESPONSE_PARSE_FAILED: ${error.message}` });
      }
    })();
    responseTasks.add(task);
    void task.finally(() => responseTasks.delete(task));
  });

  page.on('framenavigated', (frame) => {
    if (armed && frame === page.mainFrame() && !Scan.isExpectedListUrl(frame.url(), HANDLE, LIST_TYPE)) {
      driftUrl = frame.url(); detectedDriftUrl = driftUrl;
      pageDrift(driftUrl); removeStaging();
      void page.close().catch(() => {});
    }
  });

  const assertTarget = async (where) => {
    const actual = page.url();
    if (driftUrl || !Scan.isExpectedListUrl(actual, HANDLE, LIST_TYPE)) {
      pageDrift(driftUrl || actual); removeStaging();
      say(`PAGE_DRIFT at ${where}: expected=${expectedUrl} actual=${driftUrl || actual}`);
      throw new WorkflowExitError('PAGE_DRIFT', `expected=${expectedUrl} actual=${driftUrl || actual}`, 15);
    }
  };

  const stopWithAlert = async (type, text, details = {}) => {
    const recentLog = JSON.stringify(details, null, 2);
    writeAlert(ALERT_PATH, { type, text, handle: HANDLE, url: page.url(), profileDir: PROFILE_DIR, dataDir: DATA_DIR, recentLog });
    removeStaging();
    throw new WorkflowExitError(type, text, EXIT_CODES[type] || 17);
  };

  const haltAnomaly = async (where) => {
    const anomaly = await detectAnomaly(page);
    if (anomaly && !['EVAL_ERROR', 'EMPTY_PAGE'].includes(anomaly.type)) {
      if (anomaly.type === 'LOGIN_REDIRECT') throw new XAuthenticationError(anomaly.text, { where, url: page.url() });
      await stopWithAlert(anomaly.type, anomaly.text, { where });
    }
  };

  const nav = await gotoRobust(page, expectedUrl, { needSel: '[data-testid="UserCell"], [data-testid="primaryColumn"]', settle: 3000, retries: 4 });
  if (nav.reason === 'RATE_LIMIT') await stopWithAlert('RATE_LIMIT', `HTTP 429 ${nav.responseUrl || expectedUrl}`, nav);
  if (nav.reason === 'LOGIN_REDIRECT') throw new XAuthenticationError(`navigation requires login: ${page.url()}`, nav);
  await haltAnomaly(`${LIST_TYPE}-nav`);
  await confirmAuthenticated(page, { expectedPath: Scan.expectedListPath(HANDLE, LIST_TYPE) });
  if (nav.reason === 'GENERIC_NAV_ERROR') await stopWithAlert('GENERIC_NAV_ERROR', 'generic X navigation error page after bounded retries', nav);
  if (!nav.ok || !Scan.isExpectedListUrl(page.url(), HANDLE, LIST_TYPE)) {
    pageDrift(page.url()); removeStaging();
    throw new WorkflowExitError('PAGE_DRIFT', `expected=${expectedUrl} actual=${page.url()}`, 15);
  }
  armed = true;
  await assertTarget('navigation-complete');

  const startedAtMs = Date.now();
  const networkSeen = new Map();
  const domSeen = new Map();
  let cursorState = Timeline.initialCursorState();
  let networkStarted = false;
  let completionEvidence = null;
  let terminalReason = null;
  let scrollAttempts = 0;
  let domStableRounds = 0;
  let lastDomUniqueCount = 0;
  let noResponseAttempts = 0;
  let lastBreakPage = 0;
  let lastProgressAt = new Date(startedAtMs).toISOString();
  const authoritativeSeen = () => Capture.authoritativeMap({ networkStarted, networkRows: networkSeen, domRows: domSeen });

  const collectDom = async () => {
    const batch = await page.evaluate(collectCells);
    for (const raw of batch.cells) {
      const parsed = LIST_TYPE === 'following' ? parseCell(raw) : parseMembershipCell(raw);
      if (LIST_TYPE === 'following') mergeObservation(domSeen, parsed);
      else mergeRow(domSeen, parsed);
    }
    domStableRounds = domSeen.size === lastDomUniqueCount ? domStableRounds + 1 : 0;
    if (!networkStarted && domSeen.size > lastDomUniqueCount) lastProgressAt = new Date().toISOString();
    lastDomUniqueCount = domSeen.size;
    return batch;
  };

  const processResponse = async (event) => {
    if (!event) return false;
    if (event.error) {
      await stopWithAlert(event.errorType || 'COUNT_ANOMALY', event.error, {
        responsesSeen: cursorState.responsesSeen,
        cursorPages: cursorState.cursorPages,
        uniqueCount: authoritativeSeen().size,
      });
      return false;
    }
    networkStarted = true;
    const before = networkSeen.size;
    for (const row of event.rows) mergeRow(networkSeen, row);
    const newUniqueCount = networkSeen.size - before;
    try {
      cursorState = Timeline.advanceCursorState(cursorState, {
        requestCursor: event.requestCursor,
        bottomCursor: event.bottomCursor,
        userCount: event.rows.length,
        newUniqueCount,
      });
    } catch (error) {
      await stopWithAlert('COUNT_ANOMALY', error.message, {
        responsesSeen: cursorState.responsesSeen,
        cursorPages: cursorState.cursorPages,
        uniqueCount: networkSeen.size,
        requestCursorPresent: !!event.requestCursor,
        bottomCursorPresent: !!event.bottomCursor,
      });
      return false;
    }
    if (newUniqueCount > 0) lastProgressAt = new Date().toISOString();
    noResponseAttempts = 0;
    say(`response=${cursorState.responsesSeen} page=${cursorState.cursorPages} users=${event.rows.length} new=${newUniqueCount} unique=${networkSeen.size} terminal=${cursorState.cursorChainComplete}`);
    return true;
  };

  await collectDom();
  const initialEvent = await channel.take(RESPONSE_TIMEOUT_MS);
  if (initialEvent) await processResponse(initialEvent);

  while (Date.now() - startedAtMs < WATCHDOG_MS) {
    await assertTarget(`scroll-${scrollAttempts}-before`);
    await haltAnomaly(`scroll-${scrollAttempts}`);
    if (cursorState.cursorChainComplete) {
      completionEvidence = 'cursor_exhausted';
      terminalReason = cursorState.terminalReason;
      break;
    }

    let queued = await channel.take(0);
    if (queued) {
      while (queued) { await processResponse(queued); queued = await channel.take(0); }
      continue;
    }

    if (networkStarted && cursorState.cursorPages - lastBreakPage >= SNAPSHOT_LONG_BREAK_EVERY) {
      await page.waitForTimeout(SNAPSHOT_LONG_BREAK_MS);
      lastBreakPage = cursorState.cursorPages;
    }
    await page.waitForTimeout(jitterMs(WAIT_MIN, WAIT_MAX));
    await page.evaluate(scrollToTail);
    scrollAttempts++;

    const event = await channel.take(RESPONSE_TIMEOUT_MS);
    if (event) await processResponse(event);
    else noResponseAttempts++;
    const dom = await collectDom();

    if (networkStarted && noResponseAttempts >= 2 && domStableRounds >= 2) {
      cursorState = { ...cursorState, cursorChainComplete: true, terminalReason: 'no_response_after_bottom' };
      completionEvidence = 'cursor_exhausted';
      terminalReason = cursorState.terminalReason;
      break;
    }
    if (!networkStarted && dom.atBottom && domStableRounds >= STABLE_LIMIT) {
      completionEvidence = 'stable_bottom';
      terminalReason = 'dom_stable_bottom';
      break;
    }
  }

  await Promise.allSettled([...responseTasks]);
  if (!completionEvidence) {
    await stopWithAlert('COUNT_ANOMALY', 'WATCHDOG_EXPIRED', {
      elapsedMs: Date.now() - startedAtMs,
      watchdogLimitMs: WATCHDOG_MS,
      responsesSeen: cursorState.responsesSeen,
      cursorPages: cursorState.cursorPages,
      duplicateResponses: cursorState.duplicateResponses,
      uniqueCount: authoritativeSeen().size,
      lastProgressAt,
    });
  }

  await assertTarget('final');
  const finalUrl = page.url();
  const generatedAt = new Date().toISOString();
  const rows = Capture.authoritativeRows({ networkStarted, networkRows: networkSeen, domRows: domSeen })
    .map((row) => ({ ...row, observedAt: generatedAt }));
  const meta = {
    schemaVersion: 4,
    runId: RUN_ID,
    listType: LIST_TYPE,
    handle: HANDLE,
    observedDate: todayInShanghai(),
    generatedAt,
    expectedUrl,
    finalUrl,
    count: rows.length,
    headerCount: null,
    coveragePct: null,
    captureMode: networkStarted ? 'network_response' : 'dom_fallback',
    completionEvidence,
    responsesSeen: cursorState.responsesSeen,
    userEntriesSeen: cursorState.userEntriesSeen,
    networkUniqueCount: networkSeen.size,
    domEntriesSeen: domSeen.size,
    cursorPages: cursorState.cursorPages,
    cursorChainComplete: cursorState.cursorChainComplete,
    duplicateResponses: cursorState.duplicateResponses,
    elapsedMs: Date.now() - startedAtMs,
    watchdogLimitMs: WATCHDOG_MS,
    terminalReason,
    lastProgressAt,
    rounds: scrollAttempts,
    stableRounds: domStableRounds,
    recoveries: 0,
    stopReason: terminalReason,
    complete: true,
    usableForNegativeDiff: true,
  };
  fs.writeFileSync(path.join(STAGING_DIR, `${LIST_TYPE}.jsonl`), rows.map((row) => JSON.stringify(row)).join('\n') + (rows.length ? '\n' : ''));
  fs.writeFileSync(path.join(STAGING_DIR, `${LIST_TYPE}.meta.json`), `${JSON.stringify(meta, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify(meta, null, 2)}\n`);
}

async function main() {
  assertRunToken();
  await withAuthenticatedContext(
    cdpSessionOptions({ width: 1400, height: 1000 }),
    scanList,
  );
}

main().catch((error) => {
  removeStaging();
  if (error instanceof BrowserConfigError) {
    console.error(`BROWSER_CONFIG: ${error.message}`);
    process.exitCode = 2;
    return;
  }
  if (error instanceof XAuthenticationError) {
    writeAlert(ALERT_PATH, { type: 'LOGIN_REDIRECT', text: error.message, handle: HANDLE, url: error.details?.url, profileDir: PROFILE_DIR, dataDir: DATA_DIR });
    console.error(`LOGIN_REDIRECT: ${error.message}`);
    process.exitCode = EXIT_CODES.LOGIN_REDIRECT;
    return;
  }
  if (error instanceof WorkflowExitError) {
    console.error(`${error.type}: ${error.message}`);
    process.exitCode = error.exitCode;
    return;
  }
  if (detectedDriftUrl) { console.error(`PAGE_DRIFT: ${detectedDriftUrl}`); process.exitCode = 15; return; }
  console.error(error.stack || error); process.exitCode = 99;
});
