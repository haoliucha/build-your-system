#!/usr/bin/env node
// unfollow.cjs — execute unfollows for the ELIGIBLE_FOR_UNFOLLOW candidates, hardened the
// same way as x-follow's campaign.cjs. Unfollowing is destructive and not one-click
// reversible, so the safety bar is HIGHER than for following:
//
//   - candidates come ONLY from classify rows with decision === 'candidate_unfollow'
//   - clicks ONLY a button explicitly labelled Following/正在关注 or Unfollow/取消关注 for the exact target;
//     never trusts data-testid$="-unfollow" because X also assigns it to Subscribe buttons
//   - if the target now FOLLOWS YOU -> skip (now_follows_you), never unfollow
//   - confirms only inside a dialog that explicitly says Unfollow/取消关注 @target
//   - NEVER follows / likes / comments / blocks / changes settings
//   - any anomaly (CAPTCHA / rate-limit / login / restricted) -> ALERT.txt + nonzero exit
//
// Usage: node unfollow.cjs [--date=YYYY-MM-DD] [--limit=N]
//        node unfollow.cjs --handles=a,b,c          # explicit list (still safety-gated)
// Env: MY_HANDLE (unused for clicks, logged), PROFILE_DIR, XU_DATA_DIR, ALERT_PATH,
//      DRY_RUN=1, UNFOLLOW_WAIT_MIN_MS/MAX_MS, LONG_BREAK_EVERY/MS, POST_CLICK_SETTLE_MS

const fs = require('fs');
const path = require('path');
const os = require('os');
const { cdpSessionOptions } = require(path.join(__dirname, 'lib', 'browser-launch.cjs'));
const { BrowserConfigError, withAuthenticatedContext, XAuthenticationError } = require(path.join(__dirname, 'lib', 'cdp-browser.cjs'));
const { captureXResponseEvidence, gotoRobust } = require(path.join(__dirname, 'lib', 'nav-helper.cjs'));
const { detectAnomaly, writeAlert, EXIT_CODES } = require(path.join(__dirname, 'lib', 'anomaly.cjs'));
const { todayInShanghai } = require(path.join(__dirname, 'lib', 'hygiene.cjs'));
const { assertRunToken } = require(path.join(__dirname, 'lib', 'rate-gate.cjs'));
const { normalizeHandle, loadResults, mergeResultsByHandle, writeActionLog } = require(path.join(__dirname, 'lib', 'action-log.cjs'));
const {
  UNFOLLOW_CONFIRM_CONTAINER_SELECTOR,
  isExactUnfollowControl,
  isExactFollowControl,
  isExactUnfollowConfirmation,
  isExactUnfollowMenuItem,
  isVerifiedNotFollowingState,
  isTargetProfileFollowingYou,
  shouldSkipMutual,
} = require(path.join(__dirname, 'lib', 'unfollow-safety.cjs'));
const {
  UNFOLLOW_DEFAULT_LIMIT,
  UNFOLLOW_WAIT_MIN_MS,
  UNFOLLOW_WAIT_MAX_MS,
  UNFOLLOW_LONG_BREAK_EVERY,
  UNFOLLOW_LONG_BREAK_MS,
  PROFILE_WAIT_MIN_MS,
  PROFILE_WAIT_MAX_MS,
  boundedInt,
} = require(path.join(__dirname, 'lib', 'rate-policy.cjs'));

const PROFILE_DIR = process.env.PROFILE_DIR || path.join(os.homedir(), '.config/playwright-chrome-profile-campaign');
const DATA_DIR = process.env.XU_DATA_DIR || path.join(os.homedir(), '.config/x-unfollow-data');
const REPORTS_DIR = path.join(DATA_DIR, 'reports');
const ALERT_PATH = process.env.ALERT_PATH || path.join(DATA_DIR, 'ALERT.txt');
const LOG_PATH = process.env.LOG_PATH || path.join(DATA_DIR, 'unfollow.log');

const argv = process.argv.slice(2);
const DATE = (argv.find((a) => a.startsWith('--date=')) || '').split('=')[1] || process.env.SNAPSHOT_DATE || todayInShanghai();
const requestedLimit = (argv.find((a) => a.startsWith('--limit=')) || '').split('=')[1];
const LIMIT = boundedInt(requestedLimit, UNFOLLOW_DEFAULT_LIMIT, { min: 1, max: UNFOLLOW_DEFAULT_LIMIT });
const HANDLES_ARG = (argv.find((a) => a.startsWith('--handles=')) || '').split('=')[1] || '';
const ALLOW_MUTUAL = process.env.ALLOW_MUTUAL === '1' && Boolean(HANDLES_ARG);

const DRY_RUN = process.env.DRY_RUN === '1';
const WAIT_MIN = boundedInt(process.env.UNFOLLOW_WAIT_MIN_MS, UNFOLLOW_WAIT_MIN_MS, { min: UNFOLLOW_WAIT_MIN_MS });
const WAIT_MAX = boundedInt(process.env.UNFOLLOW_WAIT_MAX_MS, UNFOLLOW_WAIT_MAX_MS, { min: WAIT_MIN });
const LONG_BREAK_EVERY = boundedInt(process.env.LONG_BREAK_EVERY, UNFOLLOW_LONG_BREAK_EVERY, { min: 1, max: UNFOLLOW_LONG_BREAK_EVERY });
const LONG_BREAK_MS = boundedInt(process.env.LONG_BREAK_MS, UNFOLLOW_LONG_BREAK_MS, { min: UNFOLLOW_LONG_BREAK_MS });
const SKIP_WAIT_MIN = PROFILE_WAIT_MIN_MS;
const SKIP_WAIT_MAX = PROFILE_WAIT_MAX_MS;
const SETTLE = parseInt(process.env.POST_CLICK_SETTLE_MS || '4000', 10);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rand = (a, b) => a + Math.floor(Math.random() * (b - a));
function ensureDir(p) { if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true }); }
function log(msg) { const line = `[${new Date().toISOString()}] ${msg}\n`; try { fs.appendFileSync(LOG_PATH, line); } catch {} process.stdout.write(line); }

class WorkflowExitError extends Error {
  constructor(type, message, exitCode) {
    super(message);
    this.name = 'WorkflowExitError';
    this.type = type;
    this.exitCode = exitCode;
  }
}

function loadCandidates() {
  if (HANDLES_ARG) return HANDLES_ARG.split(',').map((s) => s.trim().replace(/^@/, '')).filter(Boolean);
  const file = path.join(REPORTS_DIR, 'latest-non-recip.json');
  if (!fs.existsSync(file)) { console.error(`FATAL: classify report not found: ${file} (run classify.cjs first)`); process.exit(2); }
  const obj = JSON.parse(fs.readFileSync(file, 'utf8'));
  return (obj.rows || []).filter((r) => r.decision === 'candidate_unfollow').map((r) => r.handle);
}

// Runs in the page: locate the EXACT target's unfollow button, assert, click, confirm, verify.
function buildUnfollowJs(handle, settle, dryRun, allowMutual, explicitHandles) {
  return `(async () => {
    const H = ${JSON.stringify(handle)};
    const s = (ms) => new Promise(r => setTimeout(r, ms));
    const isExactUnfollowControl = ${isExactUnfollowControl.toString()};
    const isExactFollowControl = ${isExactFollowControl.toString()};
    const isExactUnfollowConfirmation = ${isExactUnfollowConfirmation.toString()};
    const isExactUnfollowMenuItem = ${isExactUnfollowMenuItem.toString()};
    const isVerifiedNotFollowingState = ${isVerifiedNotFollowingState.toString()};
    const isTargetProfileFollowingYou = ${isTargetProfileFollowingYou.toString()};
    const shouldSkipMutual = ${shouldSkipMutual.toString()};
    const UNFOLLOW_CONFIRM_CONTAINER_SELECTOR = ${JSON.stringify(UNFOLLOW_CONFIRM_CONTAINER_SELECTOR)};
    for (let i = 0; i < 12; i++) { if (document.querySelector('div[data-testid="UserName"]')) break; await s(500); }
    const UN = document.querySelector('div[data-testid="UserName"]');
    if (!UN) { const err = document.querySelector('div[data-testid="empty_state_header_text"]'); return { handle: H, action: 'none', result: err ? 'profile_unavailable' : 'no_username' }; }

    const profileButtons = () => [...document.querySelectorAll('div[data-testid="primaryColumn"] button[aria-label]')]
      .filter(b => !b.closest('[data-testid="UserCell"]'));
    const descriptor = (b) => ({
      ariaLabel: b.getAttribute('aria-label') || '',
      text: (b.innerText || '').trim(),
      testid: b.getAttribute('data-testid'),
    });
    const matchExact = () => profileButtons().find(b => isExactUnfollowControl(descriptor(b), H));
    const matchFollow = () => profileButtons().find(b => isExactFollowControl(descriptor(b), H));

    const followsYou = isTargetProfileFollowingYou({
      userNameText: UN.innerText || '',
      profileHeaderText: (UN.parentElement && UN.parentElement.innerText) || '',
    });
    const exact = matchExact();
    const followBtn = matchFollow();

    if (!exact) return { handle: H, action: 'none', result: followBtn ? 'not_following' : 'no_unfollow_btn' };
    if (shouldSkipMutual({ followsYou, allowMutual: ${allowMutual}, explicitHandles: ${explicitHandles} })) {
      return { handle: H, action: 'skip', result: 'now_follows_you' };
    }
    if (${dryRun}) return { handle: H, action: 'dry_run_would_unfollow', result: 'ok' };

    // SAFETY: require explicit unfollow semantics, not X's misleading *-unfollow testid.
    const lbl = exact.getAttribute('aria-label') || '';
    if (!isExactUnfollowControl(descriptor(exact), H)) return { handle: H, action: 'safety_abort_btn_mismatch', result: lbl };

    exact.scrollIntoView({ block: 'center' });
    await s(300 + Math.random() * 400);
    exact.click();
    await s(1500);
    let dialog = [...document.querySelectorAll(UNFOLLOW_CONFIRM_CONTAINER_SELECTOR)]
      .find(d => isExactUnfollowConfirmation((d.innerText || '').trim(), H));
    if (!dialog) {
      const menuItem = [...document.querySelectorAll('[role="menu"] [role="menuitem"]')]
        .find(item => isExactUnfollowMenuItem((item.innerText || '').trim(), H));
      if (!menuItem) return { handle: H, action: 'safety_abort_confirm_mismatch', result: 'missing_exact_unfollow_menu_or_dialog' };
      menuItem.click();
      await s(${settle});
      const directState = { stillUnfollow: !!matchExact(), nowFollow: !!matchFollow() };
      if (isVerifiedNotFollowingState(directState)) {
        return { handle: H, action: 'unfollowed', result: 'ok_direct_menu' };
      }
      dialog = [...document.querySelectorAll(UNFOLLOW_CONFIRM_CONTAINER_SELECTOR)]
        .find(d => isExactUnfollowConfirmation((d.innerText || '').trim(), H));
    }
    if (!dialog) return { handle: H, action: 'safety_abort_confirm_mismatch', result: 'missing_exact_unfollow_dialog' };
    const confirm = dialog.querySelector('button[data-testid="confirmationSheetConfirm"]');
    if (!confirm) return { handle: H, action: 'safety_abort_confirm_mismatch', result: 'missing_confirm_button' };
    confirm.click();
    await s(${settle});

    const state = { stillUnfollow: !!matchExact(), nowFollow: !!matchFollow() };
    if (isVerifiedNotFollowingState(state)) return { handle: H, action: 'unfollowed', result: 'ok' };
    return { handle: H, action: 'safety_abort_unfollow_unverified', result: 'still_unfollow_btn' };
  })()`;
}

async function executeUnfollow({ context, confirmAuthenticated, disableAuthRefresh }, state) {
  const { actionReport, candidates, existingResults } = state;
  const page = context.pages()[0] || await context.newPage();

  // Startup login gate.
  const nav = await gotoRobust(page, 'https://x.com/home', {
    needSel: 'a[data-testid="SideNav_NewTweet_Button"], [data-testid="AppTabBar_Home_Link"], [data-testid="primaryColumn"]', settle: 5000, retries: 4,
  });
  if (nav.reason === 'RATE_LIMIT') {
    writeAlert(ALERT_PATH, { type: 'RATE_LIMIT', text: `HTTP 429 ${nav.responseUrl || '/home'}`, url: page.url(), profileDir: PROFILE_DIR, dataDir: DATA_DIR });
    throw new WorkflowExitError('RATE_LIMIT', 'HTTP 429 during startup navigation', EXIT_CODES.RATE_LIMIT);
  }
  if (nav.reason === 'LOGIN_REDIRECT') throw new XAuthenticationError(`startup navigation requires login: ${page.url()}`, nav);
  const initial = await detectAnomaly(page);
  if (initial && initial.type !== 'EVAL_ERROR' && initial.type !== 'EMPTY_PAGE') {
    if (initial.type === 'LOGIN_REDIRECT') throw new XAuthenticationError(initial.text, { url: page.url() });
    writeAlert(ALERT_PATH, { ...initial, url: page.url(), profileDir: PROFILE_DIR, dataDir: DATA_DIR });
    log(`FATAL anomaly on /home: ${initial.type}`);
    throw new WorkflowExitError(initial.type, initial.text, EXIT_CODES[initial.type] || 99);
  }
  await confirmAuthenticated(page, { expectedPath: '/home' });
  if (!nav.ok) {
    const type = nav.reason === 'GENERIC_NAV_ERROR' ? 'GENERIC_NAV_ERROR' : 'LOGIN_REDIRECT';
    if (type === 'LOGIN_REDIRECT') throw new XAuthenticationError('home content missing', { url: page.url(), nav });
    writeAlert(ALERT_PATH, { type, text: 'generic X navigation error page after bounded retries', url: page.url(), profileDir: PROFILE_DIR, dataDir: DATA_DIR });
    throw new WorkflowExitError(type, 'generic X navigation error page after bounded retries', EXIT_CODES[type]);
  }
  log(`Logged in OK: ${page.url()}`);
  // A mutating workflow must never restart from the beginning after the first authorization
  // gate, because doing so could duplicate already-completed unfollows.
  disableAuthRefresh();

  const results = [];
  let done = 0;
  for (const handle of candidates) {
    let r;
    try {
      const profileNav = await gotoRobust(page, `https://x.com/${handle}`, { needSel: 'div[data-testid="UserName"]', settle: 4000, retries: 3 });
      if (profileNav.reason === 'RATE_LIMIT') {
        writeAlert(ALERT_PATH, { type: 'RATE_LIMIT', text: `HTTP 429 ${profileNav.responseUrl || handle}`, handle, url: page.url(), profileDir: PROFILE_DIR, dataDir: DATA_DIR });
        throw new WorkflowExitError('RATE_LIMIT', `HTTP 429 at @${handle}`, EXIT_CODES.RATE_LIMIT);
      }
      if (profileNav.reason === 'LOGIN_REDIRECT') throw new XAuthenticationError(`login required at @${handle}`, { handle, url: page.url() });
      if (!profileNav.ok) {
        writeAlert(ALERT_PATH, { type: 'GENERIC_NAV_ERROR', text: `${profileNav.reason} at @${handle}`, handle, url: page.url(), profileDir: PROFILE_DIR, dataDir: DATA_DIR });
        throw new WorkflowExitError('GENERIC_NAV_ERROR', `profile navigation failed at @${handle}: ${profileNav.reason}`, EXIT_CODES.GENERIC_NAV_ERROR);
      }
      await page.waitForTimeout(1200);
      const observed = await captureXResponseEvidence(
        page,
        () => page.evaluate(buildUnfollowJs(handle, SETTLE, DRY_RUN, ALLOW_MUTUAL, Boolean(HANDLES_ARG))),
      );
      if (observed.evidence?.reason === 'RATE_LIMIT') {
        writeAlert(ALERT_PATH, { type: 'RATE_LIMIT', text: `HTTP 429 ${observed.evidence.responseUrl}`, handle, url: page.url(), profileDir: PROFILE_DIR, dataDir: DATA_DIR });
        throw new WorkflowExitError('RATE_LIMIT', `HTTP 429 during unfollow action at @${handle}`, EXIT_CODES.RATE_LIMIT);
      }
      if (observed.evidence?.reason === 'LOGIN_REDIRECT') {
        throw new XAuthenticationError(`unfollow action lost authentication at @${handle}`, { handle, url: page.url(), evidence: observed.evidence });
      }
      r = observed.value;
    } catch (e) {
      if (e instanceof WorkflowExitError || e instanceof XAuthenticationError) throw e;
      r = { handle, action: 'error', result: e.message };
    }
    r.at = new Date().toISOString();
    results.push(r);
    log(`@${handle} -> ${r.action} (${r.result})`);

    // Persist incrementally so a mid-run halt still records progress.
    writeActionLog(actionReport, DATE, mergeResultsByHandle(existingResults, results));

    // Anomaly check after action.
    const anomaly = await detectAnomaly(page);
    if (anomaly && anomaly.type !== 'EVAL_ERROR' && anomaly.type !== 'EMPTY_PAGE') {
      if (anomaly.type === 'LOGIN_REDIRECT') throw new XAuthenticationError(anomaly.text, { handle, url: page.url() });
      writeAlert(ALERT_PATH, { ...anomaly, handle, url: page.url(), profileDir: PROFILE_DIR, dataDir: DATA_DIR });
      log(`!!! ANOMALY ${anomaly.type} after @${handle} — HALT.`);
      throw new WorkflowExitError(anomaly.type, anomaly.text, EXIT_CODES[anomaly.type] || 99);
    }

    if (r.action === 'unfollowed') {
      done++;
      const w = rand(WAIT_MIN, WAIT_MAX); log(`-- sleep ${(w / 1000).toFixed(0)}s --`); await sleep(w);
      if (done % LONG_BREAK_EVERY === 0) { log(`-- LONG BREAK ${LONG_BREAK_MS / 1000}s after ${done} --`); await sleep(LONG_BREAK_MS); }
    } else {
      await sleep(rand(SKIP_WAIT_MIN, SKIP_WAIT_MAX));
    }
  }

  const counts = {};
  for (const r of results) counts[r.action] = (counts[r.action] || 0) + 1;
  const mergedResults = mergeResultsByHandle(existingResults, results);
  writeActionLog(actionReport, DATE, mergedResults);
  log(`=== UNFOLLOW END === ${JSON.stringify(counts)}`);
  console.log(JSON.stringify({ date: DATE, results: mergedResults, thisRunResults: results, counts }, null, 2));
}

async function main() {
  assertRunToken();
  ensureDir(REPORTS_DIR);
  const actionReport = process.env.XU_ACTION_REPORT || path.join(DATA_DIR, '.staging', process.env.XU_RUN_TOKEN || 'manual', 'unfollow.json');
  ensureDir(path.dirname(actionReport));
  const existingResults = loadResults(actionReport);
  const alreadyDone = new Set(existingResults.filter((row) => row.action === 'unfollowed').map((row) => normalizeHandle(row.handle)));
  let candidates = loadCandidates();
  if (!HANDLES_ARG) candidates = candidates.filter((handle) => !alreadyDone.has(normalizeHandle(handle)));
  candidates = candidates.slice(0, LIMIT);

  log(`=== UNFOLLOW START === date=${DATE} candidates=${candidates.length} DRY_RUN=${DRY_RUN} ALLOW_MUTUAL=${ALLOW_MUTUAL}`);
  log(`SAFETY: clicks ONLY an explicit Following/正在关注 or Unfollow/取消关注 aria-label for the exact target, then requires a matching unfollow menu/dialog; skips if it now follows you; never subscribe/follow/like/comment/block/settings.`);
  if (!candidates.length) { log('No candidates to unfollow.'); console.log(JSON.stringify({ date: DATE, results: [], counts: {} }, null, 2)); return; }

  await withAuthenticatedContext(
    cdpSessionOptions({ width: 1280, height: 820 }),
    (api) => executeUnfollow(api, { actionReport, candidates, existingResults }),
  );
}

main().catch((error) => {
  if (error instanceof BrowserConfigError) {
    log(`FATAL BROWSER_CONFIG: ${error.message}`);
    process.exitCode = 2;
    return;
  }
  if (error instanceof XAuthenticationError) {
    writeAlert(ALERT_PATH, { type: 'LOGIN_REDIRECT', text: error.message, url: error.details?.url, profileDir: PROFILE_DIR, dataDir: DATA_DIR });
    log(`FATAL LOGIN_REDIRECT: ${error.message}`);
    process.exitCode = EXIT_CODES.LOGIN_REDIRECT;
    return;
  }
  if (error instanceof WorkflowExitError) {
    log(`FATAL ${error.type}: ${error.message}`);
    process.exitCode = error.exitCode;
    return;
  }
  log(`FATAL: ${error.stack || error}`);
  process.exitCode = 99;
});
