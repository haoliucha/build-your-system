#!/usr/bin/env node
// unfollow.cjs — execute unfollows for the ELIGIBLE_FOR_UNFOLLOW candidates, hardened the
// same way as x-follow's campaign.cjs. Unfollowing is destructive and not one-click
// reversible, so the safety bar is HIGHER than for following:
//
//   - candidates come ONLY from classify rows with decision === 'candidate_unfollow'
//   - clicks ONLY a button whose aria-label's @-token EQUALS the exact target handle
//     (data-testid$="-unfollow"); anything else -> safety_abort_btn_mismatch (no click)
//   - if the target now FOLLOWS YOU -> skip (now_follows_you), never unfollow
//   - confirms via button[data-testid="confirmationSheetConfirm"]; verifies the button flipped
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
const { chromium } = require('playwright');
const { gotoRobust } = require(path.join(__dirname, 'lib', 'nav-helper.cjs'));
const { detectAnomaly, writeAlert, EXIT_CODES } = require(path.join(__dirname, 'lib', 'anomaly.cjs'));
const { todayInShanghai } = require(path.join(__dirname, 'lib', 'hygiene.cjs'));

const PROFILE_DIR = process.env.PROFILE_DIR || path.join(os.homedir(), '.config/playwright-chrome-profile-campaign');
const DATA_DIR = process.env.XU_DATA_DIR || path.join(os.homedir(), '.config/x-unfollow-data');
const REPORTS_DIR = path.join(DATA_DIR, 'reports');
const ALERT_PATH = process.env.ALERT_PATH || path.join(DATA_DIR, 'ALERT.txt');
const LOG_PATH = process.env.LOG_PATH || path.join(DATA_DIR, 'unfollow.log');

const argv = process.argv.slice(2);
const DATE = (argv.find((a) => a.startsWith('--date=')) || '').split('=')[1] || process.env.SNAPSHOT_DATE || todayInShanghai();
const LIMIT = parseInt((argv.find((a) => a.startsWith('--limit=')) || '').split('=')[1] || '0', 10);
const HANDLES_ARG = (argv.find((a) => a.startsWith('--handles=')) || '').split('=')[1] || '';

const DRY_RUN = process.env.DRY_RUN === '1';
const WAIT_MIN = parseInt(process.env.UNFOLLOW_WAIT_MIN_MS || '20000', 10);
const WAIT_MAX = parseInt(process.env.UNFOLLOW_WAIT_MAX_MS || '45000', 10);
const LONG_BREAK_EVERY = parseInt(process.env.LONG_BREAK_EVERY || '15', 10);
const LONG_BREAK_MS = parseInt(process.env.LONG_BREAK_MS || '120000', 10);
const SETTLE = parseInt(process.env.POST_CLICK_SETTLE_MS || '4000', 10);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rand = (a, b) => a + Math.floor(Math.random() * (b - a));
function ensureDir(p) { if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true }); }
function log(msg) { const line = `[${new Date().toISOString()}] ${msg}\n`; try { fs.appendFileSync(LOG_PATH, line); } catch {} process.stdout.write(line); }

function loadCandidates() {
  if (HANDLES_ARG) return HANDLES_ARG.split(',').map((s) => s.trim().replace(/^@/, '')).filter(Boolean);
  const file = path.join(REPORTS_DIR, `non-recip-reasons-${DATE}.json`);
  if (!fs.existsSync(file)) { console.error(`FATAL: classify report not found: ${file} (run classify.cjs first)`); process.exit(2); }
  const obj = JSON.parse(fs.readFileSync(file, 'utf8'));
  return (obj.rows || []).filter((r) => r.decision === 'candidate_unfollow').map((r) => r.handle);
}

// Runs in the page: locate the EXACT target's unfollow button, assert, click, confirm, verify.
function buildUnfollowJs(handle, settle, dryRun) {
  return `(async () => {
    const H = ${JSON.stringify(handle)};
    const s = (ms) => new Promise(r => setTimeout(r, ms));
    for (let i = 0; i < 12; i++) { if (document.querySelector('div[data-testid="UserName"]')) break; await s(500); }
    const UN = document.querySelector('div[data-testid="UserName"]');
    if (!UN) { const err = document.querySelector('div[data-testid="empty_state_header_text"]'); return { handle: H, action: 'none', result: err ? 'profile_unavailable' : 'no_username' }; }

    const matchExact = () => [...document.querySelectorAll('button[data-testid$="-unfollow"]')].find(b => {
      const m = (b.getAttribute('aria-label') || '').match(/@([A-Za-z0-9_]+)/);
      return m && m[1].toLowerCase() === H.toLowerCase();
    });

    const followsYou = /关注了你|Follows you/.test((document.body && document.body.innerText) || '');
    const exact = matchExact();
    const followBtn = document.querySelector('button[data-testid$="-follow"]');

    if (!exact) return { handle: H, action: 'none', result: followBtn ? 'not_following' : 'no_unfollow_btn' };
    if (followsYou) return { handle: H, action: 'skip', result: 'now_follows_you' };
    if (${dryRun}) return { handle: H, action: 'dry_run_would_unfollow', result: 'ok' };

    // SAFETY: re-assert the exact @-token right before clicking.
    const lbl = exact.getAttribute('aria-label') || '';
    const tok = (lbl.match(/@([A-Za-z0-9_]+)/) || [])[1];
    if (!tok || tok.toLowerCase() !== H.toLowerCase()) return { handle: H, action: 'safety_abort_btn_mismatch', result: lbl };

    exact.scrollIntoView({ block: 'center' });
    await s(300 + Math.random() * 400);
    exact.click();
    await s(1500);
    const confirm = document.querySelector('button[data-testid="confirmationSheetConfirm"]');
    if (confirm) { confirm.click(); }
    await s(${settle});

    const stillUnfollow = !!matchExact();
    const nowFollow = !!document.querySelector('button[data-testid$="-follow"]');
    if (!stillUnfollow) return { handle: H, action: 'unfollowed', result: nowFollow ? 'ok' : 'ok_no_followbtn' };
    return { handle: H, action: 'unfollow_assumed', result: 'still_unfollow_btn' };
  })()`;
}

async function main() {
  ensureDir(REPORTS_DIR);
  let candidates = loadCandidates();
  if (LIMIT > 0) candidates = candidates.slice(0, LIMIT);

  log(`=== UNFOLLOW START === date=${DATE} candidates=${candidates.length} DRY_RUN=${DRY_RUN}`);
  log(`SAFETY: clicks ONLY the exact target's data-testid$="-unfollow" button; skips if it now follows you; never follow/like/comment/block/settings.`);
  if (!candidates.length) { log('No candidates to unfollow.'); console.log(JSON.stringify({ date: DATE, results: [], counts: {} }, null, 2)); return; }

  const ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
    channel: 'chrome', headless: false, viewport: { width: 1280, height: 820 },
    ignoreDefaultArgs: ['--enable-automation'], args: ['--disable-blink-features=AutomationControlled'],
  });
  const page = ctx.pages()[0] || await ctx.newPage();

  // Startup login gate.
  const nav = await gotoRobust(page, 'https://x.com/home', {
    needSel: 'a[data-testid="SideNav_NewTweet_Button"], [data-testid="AppTabBar_Home_Link"], [data-testid="primaryColumn"]', settle: 5000, retries: 4,
  });
  const initial = await detectAnomaly(page);
  if (initial && initial.type !== 'EVAL_ERROR' && initial.type !== 'EMPTY_PAGE') {
    writeAlert(ALERT_PATH, { ...initial, url: page.url(), profileDir: PROFILE_DIR, dataDir: DATA_DIR });
    log(`FATAL anomaly on /home: ${initial.type}`); await ctx.close(); process.exit(EXIT_CODES[initial.type] || 99);
  }
  if (!nav.ok) {
    writeAlert(ALERT_PATH, { type: 'LOGIN_REDIRECT', text: 'home content missing', url: page.url(), profileDir: PROFILE_DIR, dataDir: DATA_DIR });
    log('FATAL: /home did not render logged-in content (login expired?)'); await ctx.close(); process.exit(EXIT_CODES.LOGIN_REDIRECT);
  }
  log(`Logged in OK: ${page.url()}`);

  const results = [];
  let done = 0;
  for (const handle of candidates) {
    let r;
    try {
      await gotoRobust(page, `https://x.com/${handle}`, { needSel: 'div[data-testid="UserName"]', settle: 4000, retries: 3 });
      await page.waitForTimeout(1200);
      r = await page.evaluate(buildUnfollowJs(handle, SETTLE, DRY_RUN));
    } catch (e) {
      r = { handle, action: 'error', result: e.message };
    }
    r.at = new Date().toISOString();
    results.push(r);
    log(`@${handle} -> ${r.action} (${r.result})`);

    // Persist incrementally so a mid-run halt still records progress.
    fs.writeFileSync(path.join(REPORTS_DIR, `unfollow-${DATE}.json`), JSON.stringify({ date: DATE, generatedAt: new Date().toISOString(), results }, null, 2) + '\n');

    // Anomaly check after action.
    const anomaly = await detectAnomaly(page);
    if (anomaly && anomaly.type !== 'EVAL_ERROR' && anomaly.type !== 'EMPTY_PAGE') {
      writeAlert(ALERT_PATH, { ...anomaly, handle, url: page.url(), profileDir: PROFILE_DIR, dataDir: DATA_DIR });
      log(`!!! ANOMALY ${anomaly.type} after @${handle} — HALT.`); await ctx.close(); process.exit(EXIT_CODES[anomaly.type] || 99);
    }

    if (r.action === 'unfollowed' || r.action === 'unfollow_assumed') {
      done++;
      const w = rand(WAIT_MIN, WAIT_MAX); log(`-- sleep ${(w / 1000).toFixed(0)}s --`); await sleep(w);
      if (done % LONG_BREAK_EVERY === 0) { log(`-- LONG BREAK ${LONG_BREAK_MS / 1000}s after ${done} --`); await sleep(LONG_BREAK_MS); }
    } else {
      await sleep(rand(4000, 9000));
    }
  }

  await ctx.close();
  const counts = {};
  for (const r of results) counts[r.action] = (counts[r.action] || 0) + 1;
  log(`=== UNFOLLOW END === ${JSON.stringify(counts)}`);
  console.log(JSON.stringify({ date: DATE, results, counts }, null, 2));
}

main().catch((e) => { log(`FATAL: ${e.stack || e}`); process.exit(99); });
