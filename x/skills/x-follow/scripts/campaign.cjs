#!/usr/bin/env node
// campaign.cjs — X 蓝V互关 main follow loop (hardened).
//
// Robustness features (see README.md "Architecture"):
//   - gotoRobust: every navigation tolerates VPN latency + HTTP 429 (exponential backoff)
//   - startup login gate waits for real content (not a fixed timer) and ignores EMPTY_PAGE
//   - anomaly detection scoped to page chrome (not tweet text) -> no crypto-tweet false +ve
//   - never clicks unless the button is exactly 'aria-label="关注 @{handle}"'
//   - post-click settle default 6000ms -> reliably flips to 正在关注 under latency
//   - followed_assumed entries are reconciled by verify-follows.cjs after the run
//
// 配置(env):
//   TARGET (必填,如 100)         PROFILE_DIR (默认 ~/.config/playwright-chrome-profile-campaign)
//   MY_HANDLE                     QUEUE_PATH / TRACKER_PATH / LOG_PATH / ALERT_PATH (默认 cwd)
//   VERIFIED_REQUIRED (true)      FOLLOWING_GT_FOLLOWERS (true)        FERS_MAX (1100)
//   BIO_BLACKLIST (内置 crypto)   BIO_WHITELIST (空)
//   FOLLOW_WAIT_MIN/MAX_MS (25000/55000)   REJECT_WAIT_MIN/MAX_MS (5000/12000)
//   LONG_BREAK_EVERY/MS (12/180000)        POST_CLICK_SETTLE_MS (6000)
//   MAX_FOLLOWS_PER_HOUR (0=off) QUIET_HOURS ("2,7")  DRY_RUN (1)  RELOAD_QUEUE_EVERY (20)

const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright');
const { EXIT_CODES, detectAnomaly, writeAlert } = require(path.join(__dirname, 'lib', 'anomaly.cjs'));
const { gotoRobust } = require(path.join(__dirname, 'lib', 'nav-helper.cjs'));
const { CRYPTO_TOKENS } = require(path.join(__dirname, 'lib', 'filters.cjs'));
const { shouldSkipReason } = require(path.join(__dirname, 'lib', 'skipset.cjs'));

// ============ CONFIG ============
const CFG = {
  TARGET: parseInt(process.env.TARGET || '0', 10),
  PROFILE_DIR: process.env.PROFILE_DIR || `${process.env.HOME}/.config/playwright-chrome-profile-campaign`,
  MY_HANDLE: process.env.MY_HANDLE || '',
  QUEUE_PATH: process.env.QUEUE_PATH || path.resolve('queue.json'),
  TRACKER_PATH: process.env.TRACKER_PATH || path.resolve('tracker.json'),
  LOG_PATH: process.env.LOG_PATH || path.resolve('campaign.log'),
  ALERT_PATH: process.env.ALERT_PATH || path.resolve('ALERT.txt'),

  VERIFIED_REQUIRED: process.env.VERIFIED_REQUIRED !== 'false',
  FOLLOWING_GT_FOLLOWERS: process.env.FOLLOWING_GT_FOLLOWERS !== 'false',
  FERS_MAX: parseInt(process.env.FERS_MAX || '1100', 10),
  // Default blacklist = shared CRYPTO_TOKENS. Override with BIO_BLACKLIST. To DISABLE the
  // crypto filter, pass a never-matching token (empty string falls back to this default).
  BIO_BLACKLIST: (process.env.BIO_BLACKLIST || CRYPTO_TOKENS.join(',')).split(',').map(s => s.trim()).filter(Boolean),
  BIO_WHITELIST: (process.env.BIO_WHITELIST || '').split(',').map(s => s.trim()).filter(Boolean),

  FOLLOW_WAIT_MIN_MS: parseInt(process.env.FOLLOW_WAIT_MIN_MS || '25000', 10),
  FOLLOW_WAIT_MAX_MS: parseInt(process.env.FOLLOW_WAIT_MAX_MS || '55000', 10),
  REJECT_WAIT_MIN_MS: parseInt(process.env.REJECT_WAIT_MIN_MS || '5000', 10),
  REJECT_WAIT_MAX_MS: parseInt(process.env.REJECT_WAIT_MAX_MS || '12000', 10),
  LONG_BREAK_EVERY: parseInt(process.env.LONG_BREAK_EVERY || '12', 10),
  LONG_BREAK_MS: parseInt(process.env.LONG_BREAK_MS || '180000', 10),
  // 6000 (was 2500): gives the follow button time to flip to 正在关注 under VPN latency,
  // which sharply reduces unverifiable 'followed_assumed' outcomes.
  POST_CLICK_SETTLE_MS: parseInt(process.env.POST_CLICK_SETTLE_MS || '6000', 10),

  MAX_FOLLOWS_PER_HOUR: parseInt(process.env.MAX_FOLLOWS_PER_HOUR || '0', 10),
  QUIET_HOURS: (process.env.QUIET_HOURS || '').split(',').map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n)),

  DRY_RUN: process.env.DRY_RUN === '1',
  RELOAD_QUEUE_EVERY: parseInt(process.env.RELOAD_QUEUE_EVERY || '20', 10),
  // Reason-prefixes to RE-EVALUATE (un-skip) because the current config is more permissive
  // than the run that produced the prior reject. Transient errors are always re-evaluated.
  REEVAL_REASONS: (process.env.REEVAL_REASONS || '').split(',').map((s) => s.trim()).filter(Boolean),
};

if (!CFG.TARGET || CFG.TARGET < 1) {
  console.error('FATAL: TARGET env var required (e.g., TARGET=100)');
  process.exit(2);
}

// ============ LOGGING ============
function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}\n`;
  try { fs.appendFileSync(CFG.LOG_PATH, line); } catch {}
  process.stdout.write(line);
}
function loadJSON(p, fallback) {
  try { return JSON.parse(fs.readFileSync(p, 'utf-8')); } catch { return fallback; }
}
function saveJSON(p, obj) { fs.writeFileSync(p, JSON.stringify(obj, null, 2)); }
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const rand = (min, max) => min + Math.floor(Math.random() * (max - min));

// ============ VERIFY + FOLLOW JS (runs in browser context) ============
// NOTE: this string runs INSIDE the page, so it cannot require lib/filters. Its decision
// order MUST match lib/filters.decide() (which the unit tests assert against).
function buildVerifyJs(cfg) {
  const enRegexSource = cfg.BIO_BLACKLIST.filter(t => /^[a-z0-9_.-]+$/i.test(t)).join('|');
  const zhTokens = cfg.BIO_BLACKLIST.filter(t => !/^[a-z0-9_.-]+$/i.test(t));
  const enTokens = cfg.BIO_BLACKLIST.filter(t => /^[a-z0-9_.-]+$/i.test(t));
  const whitelist = cfg.BIO_WHITELIST;

  return `(async () => {
    const H = window.location.pathname.slice(1).split('/')[0];
    const s = (ms) => new Promise(r => setTimeout(r, ms));

    for (let i = 0; i < 12; i++) { if (document.querySelector('div[data-testid="UserName"]')) break; await s(500); }
    for (let i = 0; i < 10; i++) {
      const hasBtn = document.querySelector('button[data-testid$="-follow"], button[data-testid$="-unfollow"]');
      const hasBadge = document.querySelector('div[data-testid="UserName"] svg[aria-label="认证账号"], div[data-testid="UserName"] svg[aria-label="Verified organization"]');
      if (hasBtn || hasBadge) break;
      await s(500);
    }

    const UN = document.querySelector('div[data-testid="UserName"]');
    const UD = document.querySelector('div[data-testid="UserDescription"]');
    if (!UN) {
      const err = document.querySelector('div[data-testid="empty_state_header_text"]');
      return { handle: H, error: err ? 'profile_unavailable' : 'no_username' };
    }

    const blue = !!UN.querySelector('svg[aria-label="认证账号"]');
    const gold = !!UN.querySelector('svg[aria-label="Verified organization"], svg[aria-label="Government account"]');
    const bio = UD ? UD.innerText : '';

    let fers = null, fing = null;
    document.querySelectorAll('a[href$="/followers"], a[href$="/verified_followers"], a[href$="/following"]').forEach(a => {
      const h = a.getAttribute('href'), t = a.innerText;
      if (h.endsWith('/following')) fing = fing || t;
      else if (h.endsWith('/followers')) fers = t;
      else if (h.endsWith('/verified_followers')) fers = fers || t;
    });
    const pc = (v) => {  // MUST mirror lib/filters.parseCount (incl. lowercase k/m/b)
      if (!v) return -1;
      const m = v.match(/([\\d,.]+)\\s*([万千亿KkMmBb])?/);
      if (!m) return -1;
      let n = parseFloat(m[1].replace(/,/g, ''));
      if (isNaN(n)) return -1;
      const u = m[2];
      if (u === '亿') n *= 1e8; else if (u === '万') n *= 1e4;
      else if (u === 'K' || u === 'k' || u === '千') n *= 1e3;
      else if (u === 'M' || u === 'm') n *= 1e6;
      else if (u === 'B' || u === 'b') n *= 1e9;
      return Math.round(n);
    };
    const fN = pc(fers), fgN = pc(fing);

    const fB = document.querySelector(\`button[data-testid$="-follow"][aria-label="关注 @\${H}"], button[data-testid$="-follow"][aria-label="Follow @\${H}"]\`);
    const uB = document.querySelector(\`button[data-testid$="-unfollow"][aria-label*="@\${H}"]\`);

    const enRegex = ${enRegexSource ? `new RegExp('\\\\b(' + ${JSON.stringify(enRegexSource)} + ')\\\\b', 'i')` : 'null'};
    const zhTokens = ${JSON.stringify(zhTokens)};
    const enTokens = ${JSON.stringify(enTokens)};
    const whitelist = ${JSON.stringify(whitelist)};

    let cryptoMatch = null;
    if (enRegex) { const m = bio.match(enRegex); if (m) cryptoMatch = m[0]; }
    if (!cryptoMatch) cryptoMatch = zhTokens.find(k => bio.includes(k)) || null;
    if (!cryptoMatch) { const hl = H.toLowerCase(); cryptoMatch = enTokens.find(k => hl.includes(k.toLowerCase())) || null; }

    let whitelistFail = false;
    if (whitelist.length > 0) { const bl = bio.toLowerCase(); if (!whitelist.some(w => bl.includes(w.toLowerCase()))) whitelistFail = true; }

    // Decision — order MUST match lib/filters.decide()
    let d = 'pass';
    const VERIFIED_REQUIRED = ${cfg.VERIFIED_REQUIRED};
    const FOLLOWING_GT_FOLLOWERS = ${cfg.FOLLOWING_GT_FOLLOWERS};
    const FERS_MAX = ${cfg.FERS_MAX};
    if (VERIFIED_REQUIRED && !blue) d = 'reject:not_blue';
    else if (gold) d = 'reject:gold_org';
    else if (uB) d = 'reject:already_following';
    else if (!fB) d = 'reject:no_follow_btn';
    else if (fN < 0 || fgN < 0) d = 'reject:cant_parse_stats';
    else if (fN > FERS_MAX) d = \`reject:fers>${cfg.FERS_MAX}(\${fN})\`;
    else if (FOLLOWING_GT_FOLLOWERS && fgN <= fN) d = \`reject:fing<=fers(\${fgN}<=\${fN})\`;
    else if (cryptoMatch) d = \`reject:blacklist(\${cryptoMatch})\`;
    else if (whitelistFail) d = 'reject:not_in_whitelist';

    const r = { handle: H, bio: bio.slice(0, 200), blue, gold, fN, fgN, cryptoMatch, decision: d, action: 'none' };

    const DRY_RUN = ${cfg.DRY_RUN};
    if (d === 'pass' && !DRY_RUN) {
      if (!fB || (fB.getAttribute('aria-label') !== \`关注 @\${H}\` && fB.getAttribute('aria-label') !== \`Follow @\${H}\`)) {
        r.action = 'safety_abort_btn_mismatch';
      } else {
        fB.scrollIntoView({ block: 'center' });
        await s(${Math.round(cfg.POST_CLICK_SETTLE_MS / 8 + 300)} + Math.random() * 400);
        fB.click();
        await s(${cfg.POST_CLICK_SETTLE_MS});
        const u1 = document.querySelector(\`button[data-testid$="-unfollow"][aria-label*="@\${H}"]\`);
        if (u1) { r.action = 'followed'; }
        else {
          const cf = document.querySelector('div[data-testid="confirmationSheetConfirm"]');
          if (cf) {
            cf.click(); await s(2000);
            const u2 = document.querySelector(\`button[data-testid$="-unfollow"][aria-label*="@\${H}"]\`);
            r.action = u2 ? 'followed_via_confirm' : 'click_initiated_no_verify';
          } else {
            r.action = 'followed_assumed'; // DOM lag — verify-follows.cjs reconciles post-run
          }
        }
      }
    } else if (d === 'pass' && DRY_RUN) {
      r.action = 'dry_run_would_follow';
    }
    return r;
  })()`;
}

const isFollowAction = (a) => a === 'followed' || a === 'followed_via_confirm' || a === 'followed_assumed';

// ============ MAIN ============
async function main() {
  log(`=== CAMPAIGN START ===`);
  log(`Config: TARGET=${CFG.TARGET}, FERS_MAX=${CFG.FERS_MAX}, SETTLE=${CFG.POST_CLICK_SETTLE_MS}ms, DRY_RUN=${CFG.DRY_RUN}`);
  log(`SAFETY MANIFEST:`);
  log(`  - Will only click follow buttons matching 'aria-label="关注 @{handle}"' (or "Follow @{handle}")`);
  log(`  - Will NEVER click unfollow / block / report / like / tweet / dm`);
  log(`  - Will exit on any anomaly (CAPTCHA/RATE_LIMIT/LOGIN/LOCK) without retry beyond budget`);
  log(`  - Works on profile copy at ${CFG.PROFILE_DIR}; original profile untouched`);

  let tracker = loadJSON(CFG.TRACKER_PATH, { followed: [], rejected: [], stats: { profiles_checked: 0, follow_success: 0 } });
  let queue = loadJSON(CFG.QUEUE_PATH, []);
  const followedSet = new Set(tracker.followed.map(f => f.handle));
  // Reason-aware skip: only seed the in-memory reject skip with rejects that are STILL binding
  // under this run's config. Config-bound rejects opened by REEVAL_REASONS (and transient
  // errors) are intentionally left out so they get re-evaluated this run.
  const rejectedSet = new Set((tracker.rejected || []).filter(r => shouldSkipReason(r.r || r.reason, CFG.REEVAL_REASONS)).map(r => r.h));
  log(`Followed: ${tracker.followed.length}/${CFG.TARGET}, Queue: ${queue.length}, FollowedSet: ${followedSet.size}, RejectedSet: ${rejectedSet.size}, reeval=[${CFG.REEVAL_REASONS.join(',')}]`);

  const ctx = await chromium.launchPersistentContext(CFG.PROFILE_DIR, {
    channel: 'chrome', headless: false, viewport: { width: 1280, height: 820 },
    ignoreDefaultArgs: ['--enable-automation'], args: ['--disable-blink-features=AutomationControlled'],
  });
  let page = ctx.pages()[0] || await ctx.newPage();

  // Startup login gate — gotoRobust waits for a logged-in element (not a fixed timer);
  // EMPTY_PAGE is excluded because the /home SPA shell is briefly <50 chars under latency.
  const nav = await gotoRobust(page, 'https://x.com/home', {
    needSel: 'a[data-testid="SideNav_NewTweet_Button"], [data-testid="AppTabBar_Home_Link"], [data-testid="primaryColumn"]',
    settle: 5000, retries: 4,
  });
  const initialAnomaly = await detectAnomaly(page);
  if (initialAnomaly && initialAnomaly.type !== 'EVAL_ERROR' && initialAnomaly.type !== 'EMPTY_PAGE') {
    log(`FATAL: anomaly on /home: ${JSON.stringify(initialAnomaly)}`);
    writeAlert(CFG.ALERT_PATH, { ...initialAnomaly, profileDir: CFG.PROFILE_DIR, url: page.url() });
    await ctx.close();
    process.exit(EXIT_CODES[initialAnomaly.type] || 99);
  }
  if (!nav.ok) {
    log(`FATAL: /home did not render logged-in content after ${nav.attempts} attempts (login expired?)`);
    writeAlert(CFG.ALERT_PATH, { type: 'LOGIN_REDIRECT', text: 'home content missing', profileDir: CFG.PROFILE_DIR, url: page.url() });
    await ctx.close();
    process.exit(EXIT_CODES.LOGIN_REDIRECT);
  }
  log(`Logged in OK: ${page.url()}`);

  let shouldExit = false;
  ['SIGTERM', 'SIGINT'].forEach(sig => process.on(sig, () => { log(`Got ${sig}, exiting after current iteration`); shouldExit = true; }));

  let consecutiveErrors = 0, consecutiveRateLimits = 0, processedSinceReload = 0;
  const VERIFY_JS = buildVerifyJs(CFG);
  const followTimestamps = [];
  const inQuietHours = () => {
    if (CFG.QUIET_HOURS.length !== 2) return false;
    const [start, end] = CFG.QUIET_HOURS; const h = new Date().getHours();
    // support overnight windows (e.g. 22,7 -> 22:00..06:59)
    return start <= end ? (h >= start && h < end) : (h >= start || h < end);
  };

  for (let i = 0; i < queue.length; i++) {
    if (shouldExit) { log('Exiting gracefully'); break; }
    if (tracker.followed.length >= CFG.TARGET) { log(`TARGET REACHED: ${tracker.followed.length} follows`); break; }

    if (processedSinceReload >= CFG.RELOAD_QUEUE_EVERY) {
      const newQueue = loadJSON(CFG.QUEUE_PATH, []);
      if (newQueue.length > queue.length) { log(`Hot-reloaded queue: +${newQueue.length - queue.length} (total ${newQueue.length})`); queue = newQueue; }
      processedSinceReload = 0;
    }
    processedSinceReload++;

    const handle = queue[i];
    if (followedSet.has(handle)) { log(`SKIP ${handle}: already followed`); continue; }
    if (rejectedSet.has(handle)) { log(`SKIP ${handle}: already rejected`); continue; }

    while (inQuietHours()) { log(`Quiet hours [${CFG.QUIET_HOURS.join(',')}], sleeping 10 min...`); await sleep(600_000); }

    if (CFG.MAX_FOLLOWS_PER_HOUR > 0) {
      const oneHourAgo = Date.now() - 3600_000;
      while (followTimestamps.length > 0 && followTimestamps[0] < oneHourAgo) followTimestamps.shift();
      if (followTimestamps.length >= CFG.MAX_FOLLOWS_PER_HOUR) {
        const sleepFor = followTimestamps[0] + 3600_000 - Date.now() + 5000;
        log(`Hourly cap reached (${CFG.MAX_FOLLOWS_PER_HOUR}/h), sleeping ${(sleepFor/1000).toFixed(0)}s`);
        await sleep(sleepFor);
      }
    }

    let result;
    try {
      // gotoRobust: tolerate latency + 429 on profile loads (UserByScreenName quota)
      await gotoRobust(page, `https://x.com/${handle}`, { needSel: 'div[data-testid="UserName"]', settle: 4000, retries: 3 });
      await page.waitForTimeout(1500);
      result = await page.evaluate(VERIFY_JS);
    } catch (e) {
      log(`ERROR ${handle}: ${e.message}`);
      if (++consecutiveErrors >= 5) {
        log(`FATAL: ${consecutiveErrors} consecutive errors. Pausing 5 min and exiting.`);
        writeAlert(CFG.ALERT_PATH, { type: 'CONSECUTIVE_ERRORS', text: '5+ errors', handle, url: page.url(), profileDir: CFG.PROFILE_DIR });
        await sleep(300_000); await ctx.close(); process.exit(EXIT_CODES.CONSECUTIVE_ERRORS);
      }
      await sleep(15_000); continue;
    }
    consecutiveErrors = 0;

    if (!result || typeof result !== 'object') { log(`WARN ${handle}: evaluate returned ${result}, skipping`); await sleep(8000); continue; }
    if (result.error) {
      log(`${handle} -> ERROR ${result.error}`);
      tracker.rejected = tracker.rejected || [];
      tracker.rejected.push({ h: handle, r: 'eval_error:' + result.error });
      rejectedSet.add(handle); saveJSON(CFG.TRACKER_PATH, tracker);
      await sleep(rand(CFG.REJECT_WAIT_MIN_MS, CFG.REJECT_WAIT_MAX_MS)); continue;
    }

    log(`${handle} -> ${result.decision} | bio=${(result.bio||'').slice(0,80).replace(/\n/g,' ')}`);
    tracker.stats.profiles_checked = (tracker.stats.profiles_checked || 0) + 1;

    if (isFollowAction(result.action)) {
      tracker.followed.push({ handle: result.handle, bio: result.bio, fers: result.fN, fing: result.fgN, action: result.action, at: new Date().toISOString() });
      tracker.stats.follow_success = (tracker.stats.follow_success || 0) + 1;
      followedSet.add(handle); followTimestamps.push(Date.now());
      log(`✅ FOLLOW #${tracker.followed.length}: ${handle} (${result.action})`);
      consecutiveRateLimits = 0;
    } else if (result.decision && result.decision.startsWith('reject')) {
      tracker.rejected = tracker.rejected || [];
      tracker.rejected.push({ h: handle, r: result.decision });
      rejectedSet.add(handle);
    }
    saveJSON(CFG.TRACKER_PATH, tracker);

    // Anomaly check AFTER action (esp. after a follow). EMPTY_PAGE excluded (latency artifact).
    const anomaly = await detectAnomaly(page);
    if (anomaly && anomaly.type !== 'EVAL_ERROR' && anomaly.type !== 'EMPTY_PAGE') {
      log(`!!! ANOMALY DETECTED: ${anomaly.type} - ${anomaly.text}`);
      writeAlert(CFG.ALERT_PATH, { ...anomaly, handle, url: page.url(), profileDir: CFG.PROFILE_DIR, trackerPath: CFG.TRACKER_PATH });
      if (anomaly.type === 'RATE_LIMIT') {
        if (++consecutiveRateLimits >= 2) { log(`RATE_LIMIT twice, exiting`); await ctx.close(); process.exit(EXIT_CODES.RATE_LIMIT); }
        log(`RATE_LIMIT first hit, pause 30 min and retry once`); await sleep(1800_000); continue;
      }
      await ctx.close(); process.exit(EXIT_CODES[anomaly.type] || 99);
    }

    // Pace
    if (isFollowAction(result.action)) {
      const w = rand(CFG.FOLLOW_WAIT_MIN_MS, CFG.FOLLOW_WAIT_MAX_MS);
      log(`-- sleep ${(w/1000).toFixed(0)}s --`); await sleep(w);
      if (tracker.stats.follow_success % CFG.LONG_BREAK_EVERY === 0) {
        log(`-- LONG BREAK ${CFG.LONG_BREAK_MS/1000}s after ${tracker.stats.follow_success} follows --`);
        await sleep(CFG.LONG_BREAK_MS);
      }
    } else {
      await sleep(rand(CFG.REJECT_WAIT_MIN_MS, CFG.REJECT_WAIT_MAX_MS));
    }
  }

  log(`=== CAMPAIGN END === Total follows: ${tracker.followed.length}/${CFG.TARGET}`);
  await ctx.close();
  process.exit(0);
}

main().catch(e => { log(`FATAL: ${e.stack || e}`); process.exit(99); });
