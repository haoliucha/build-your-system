#!/usr/bin/env node
// campaign.cjs — X 蓝V互关 main follow loop (hardened).
//
// Robustness features (see README.md "Architecture"):
//   - gotoRobust: bounded latency/generic-error recovery; observed HTTP 429 stops immediately
//   - startup login gate waits for real content (not a fixed timer) and ignores EMPTY_PAGE
//   - anomaly detection scoped to page chrome (not tweet text) -> no crypto-tweet false +ve
//   - never clicks unless the button is exactly 'aria-label="关注 @{handle}"'
//   - post-click settle default 6000ms -> reliably flips to 正在关注 under latency
//   - followed_assumed entries are reconciled by verify-follows.cjs after the run
//
// 配置(env):
//   TARGET (必填,如 100)         PROFILE_DIR (默认 ~/.config/playwright-chrome-profile-campaign)
//   MY_HANDLE                     QUEUE_PATH / TRACKER_PATH / LOG_PATH / ALERT_PATH (resolved from shared JOB_DIR)
//   VERIFIED_REQUIRED (true)      FOLLOWING_GT_FOLLOWERS (true)        FERS_MAX (3000)
//   FILTER_CRYPTO (0=default)    BIO_BLACKLIST (explicit override)     BIO_WHITELIST (空)
//   PROFILE_VISIT_MIN/MAX_INTERVAL_MS (90000/150000) MAX_PROFILE_VISITS_PER_HOUR (30)
//   FOLLOW_WAIT_MIN/MAX_MS (25000/55000)   REJECT_WAIT_MIN/MAX_MS (5000/12000)
//   LONG_BREAK_EVERY/MS (12/180000)        POST_CLICK_SETTLE_MS (6000)
//   RATE_LIMIT_COOLDOWN_MS (1800000)       MAX_FOLLOWS_PER_HOUR (0=off)
//   QUIET_HOURS ("2,7")  DRY_RUN (1)  RELOAD_QUEUE_EVERY (20)

const path = require('path');
const fs = require('fs');
const { EXIT_CODES, detectAnomaly, writeAlert, writeAlertWithEvidence } = require(path.join(__dirname, 'lib', 'anomaly.cjs'));
const { captureXResponseEvidence, gotoRobust } = require(path.join(__dirname, 'lib', 'nav-helper.cjs'));
const { generateComment } = require(path.join(__dirname, 'lib', 'comment-generator.cjs'));
const { resolveCommentPolicy } = require(path.join(__dirname, 'lib', 'comment-policy.cjs'));
const { prepareXFacingRuntime } = require(path.join(__dirname, 'lib', 'runtime-gate.cjs'));
const { resolveFilterPolicy } = require(path.join(__dirname, 'lib', 'runtime-state.cjs'));
const { createProfilePacer } = require(path.join(__dirname, 'lib', 'profile-pacer.cjs'));
const { createTraceRecorder } = require(path.join(__dirname, 'lib', 'trace-recorder.cjs'));
const { BrowserConfigError, withAuthenticatedContext, XAuthenticationError } = require(path.join(__dirname, 'lib', 'cdp-browser.cjs'));

let RUNTIME;
let FILTER_POLICY;
let COMMENT_POLICY;
try {
  // Commenting is a separate mutation and must be rejected before any browser/account
  // preflight when the second authorization token is absent.
  COMMENT_POLICY = resolveCommentPolicy(process.env);
  RUNTIME = prepareXFacingRuntime(process.env);
  FILTER_POLICY = resolveFilterPolicy(process.env);
} catch (error) {
  console.error(`FATAL: ${error.message}`);
  process.exit(2);
}

// ============ CONFIG ============
const CFG = {
  TARGET: parseInt(process.env.TARGET || '0', 10),
  PROFILE_DIR: process.env.PROFILE_DIR || `${process.env.HOME}/.config/playwright-chrome-profile-campaign`,
  MY_HANDLE: process.env.MY_HANDLE || '',
  QUEUE_PATH: RUNTIME.state.queuePath,
  TRACKER_PATH: RUNTIME.state.trackerPath,
  LOG_PATH: RUNTIME.state.logPath,
  ALERT_PATH: RUNTIME.state.alertPath,
  STATUS_PATH: RUNTIME.state.statusPath,
  PACING_PATH: RUNTIME.state.pacingPath,
  TRACE_DIR: RUNTIME.state.traceDir,
  LAST_STABLE_PATH: RUNTIME.state.lastStablePath,

  VERIFIED_REQUIRED: process.env.VERIFIED_REQUIRED !== 'false',
  FOLLOWING_GT_FOLLOWERS: process.env.FOLLOWING_GT_FOLLOWERS !== 'false',
  // FERS_MAX 3000 (was 1100): blue-V accounts skew to higher follower counts; 1100 rejected
  // ~half the harvested pool. Data: rejects in the 1100-3000 band are still small enough to
  // reciprocate a follow; the bulk of fers>1100 rejects are 10k+ (median 14k) and stay out.
  FERS_MAX: parseInt(process.env.FERS_MAX || '3000', 10),
  // FOLLOW_RATIO_MIN 0.5: reject only clear one-way broadcasters (fing < fers*0.5), not every
  // account whose followers slightly exceed their following. See lib/filters.decide() note.
  FOLLOW_RATIO_MIN: parseFloat(process.env.FOLLOW_RATIO_MIN || '0.5'),
  // FILTER_CRYPTO defaults off. Explicit BIO_BLACKLIST remains the highest-priority override.
  BIO_BLACKLIST: FILTER_POLICY.bioBlacklist,
  BIO_WHITELIST: (process.env.BIO_WHITELIST || '').split(',').map(s => s.trim()).filter(Boolean),

  FOLLOW_WAIT_MIN_MS: parseInt(process.env.FOLLOW_WAIT_MIN_MS || '25000', 10),
  FOLLOW_WAIT_MAX_MS: parseInt(process.env.FOLLOW_WAIT_MAX_MS || '55000', 10),
  REJECT_WAIT_MIN_MS: parseInt(process.env.REJECT_WAIT_MIN_MS || '5000', 10),
  REJECT_WAIT_MAX_MS: parseInt(process.env.REJECT_WAIT_MAX_MS || '12000', 10),
  // Every profile visit produces profile GraphQL traffic, even when the account is
  // rejected without a click. These controls pace navigation starts and persist across
  // process resumes, closing the old reject-heavy burst path.
  PROFILE_VISIT_MIN_INTERVAL_MS: parseInt(process.env.PROFILE_VISIT_MIN_INTERVAL_MS || '90000', 10),
  PROFILE_VISIT_MAX_INTERVAL_MS: parseInt(process.env.PROFILE_VISIT_MAX_INTERVAL_MS || '150000', 10),
  MAX_PROFILE_VISITS_PER_HOUR: parseInt(process.env.MAX_PROFILE_VISITS_PER_HOUR || '30', 10),
  RATE_LIMIT_COOLDOWN_MS: parseInt(process.env.RATE_LIMIT_COOLDOWN_MS || '1800000', 10),
  LONG_BREAK_EVERY: parseInt(process.env.LONG_BREAK_EVERY || '12', 10),
  LONG_BREAK_MS: parseInt(process.env.LONG_BREAK_MS || '180000', 10),
  // 6000 (was 2500): gives the follow button time to flip to 正在关注 under VPN latency,
  // which sharply reduces unverifiable 'followed_assumed' outcomes.
  POST_CLICK_SETTLE_MS: parseInt(process.env.POST_CLICK_SETTLE_MS || '6000', 10),

  MAX_FOLLOWS_PER_HOUR: parseInt(process.env.MAX_FOLLOWS_PER_HOUR || '0', 10),
  QUIET_HOURS: (process.env.QUIET_HOURS || '').split(',').map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n)),

  DRY_RUN: process.env.DRY_RUN === '1',
  TRACE_ENABLED: process.env.X_FOLLOW_TRACE === '1',
  TRACE_PROFILE_LIMIT: parseInt(process.env.TRACE_PROFILE_LIMIT || '0', 10),
  // Mirror the verified manual flow by entering profiles from search results and
  // returning with Back. Direct profile goto remains available as an explicit fallback.
  PROFILE_NAV_MODE: process.env.PROFILE_NAV_MODE || 'search-click',
  RELOAD_QUEUE_EVERY: parseInt(process.env.RELOAD_QUEUE_EVERY || '20', 10),
  // COMMENT_AFTER_FOLLOW: after a successful follow, reply to the target's pinned post with
  // a varied follow引流 comment hinting at reciprocal following. Only comments on pinned posts
  // (no pinned post → skip silently). Varied templates avoid spam-signal pattern repetition.
  COMMENT_AFTER_FOLLOW: COMMENT_POLICY.enabled,
};

if (!CFG.TARGET || CFG.TARGET < 1) {
  console.error('FATAL: TARGET env var required (e.g., TARGET=100)');
  process.exit(2);
}
if (!['direct', 'search-click'].includes(CFG.PROFILE_NAV_MODE)) {
  console.error('FATAL: PROFILE_NAV_MODE must be direct or search-click');
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
// Heartbeat/progress file — a single small JSON the orchestrator (and the human) can read
// at any time to see live progress without tailing logs. Written on every iteration so a
// stale `ts` also signals a hung run. Best-effort: failures here never break the campaign.
function writeStatus(obj) {
  try { fs.writeFileSync(CFG.STATUS_PATH, JSON.stringify({ ...obj, ts: new Date().toISOString() }, null, 2)); } catch {}
}
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const rand = (min, max) => min + Math.floor(Math.random() * (max - min));
let alertWrittenThisRun = false;
let PROFILE_PACER;
let TRACE;
try {
  PROFILE_PACER = createProfilePacer({
    statePath: CFG.PACING_PATH,
    minIntervalMs: CFG.PROFILE_VISIT_MIN_INTERVAL_MS,
    maxIntervalMs: CFG.PROFILE_VISIT_MAX_INTERVAL_MS,
    maxVisitsPerHour: CFG.MAX_PROFILE_VISITS_PER_HOUR,
    rateLimitCooldownMs: CFG.RATE_LIMIT_COOLDOWN_MS,
    log,
  });
  TRACE = createTraceRecorder({
    enabled: CFG.TRACE_ENABLED,
    traceDir: CFG.TRACE_DIR,
    lastStablePath: CFG.LAST_STABLE_PATH,
    source: 'auto',
  });
} catch (error) {
  console.error(`FATAL: ${error.message}`);
  process.exit(2);
}

async function recordFailure(page, info) {
  await TRACE?.flush?.();
  if (info.type === 'RATE_LIMIT') {
    const cooldown = PROFILE_PACER.noteRateLimit(info);
    info = { ...info, rateLimitCooldownUntil: cooldown.cooldownUntil };
  }
  const evidence = await writeAlertWithEvidence(page, CFG.ALERT_PATH, {
    profileDir: CFG.PROFILE_DIR,
    trackerPath: CFG.TRACKER_PATH,
    lastStablePath: CFG.LAST_STABLE_PATH,
    ...info,
  });
  alertWrittenThisRun = true;
  log(`EVIDENCE ${info.type}: screenshot=${evidence.screenshotPath || 'unavailable'} json=${evidence.evidencePath || 'unavailable'}`);
  return evidence;
}

async function navigateProfileViaSearch(page, handle) {
  const inputSelector = 'input[data-testid="SearchBox_Search_Input"]';
  const query = `from:${handle}`;
  TRACE.setContext({ phase: 'search_profile' });
  TRACE.mark('search_profile_start', { queryType: 'from_handle' });

  if (!/\/search(?:\?|$)/.test(page.url())) {
    const searchUrl = `https://x.com/search?q=${encodeURIComponent(query)}&src=typed_query&f=live`;
    const nav = await gotoRobust(page, searchUrl, {
      needSel: inputSelector, settle: 2500, retries: 3,
      trace: (event, data) => TRACE.mark(event, data),
    });
    if (!nav.ok) return nav;
  } else {
    const searchObserved = await captureXResponseEvidence(page, async () => {
      const input = page.locator(inputSelector);
      await input.waitFor({ state: 'visible', timeout: 15000 });
      await input.fill(query);
      await input.press('Enter');
      await page.waitForTimeout(2000);
    });
    if (searchObserved.evidence) return { ok: false, attempts: 1, waitedMs: 0, ...searchObserved.evidence };
  }

  const link = page.locator(`a[href="/${handle}" i]`).first();
  try { await link.waitFor({ state: 'visible', timeout: 15000 }); }
  catch { return { ok: false, attempts: 1, waitedMs: 0, reason: 'PROFILE_LINK_NOT_FOUND' }; }
  const clickObserved = await captureXResponseEvidence(page, async () => {
    await link.click();
    await page.waitForURL(new RegExp(`https://x\\.com/${handle}(?:/)?(?:\\?.*)?$`, 'i'), { timeout: 15000 });
    await page.waitForSelector('div[data-testid="UserName"]', { timeout: 15000 });
  });
  if (clickObserved.evidence) return { ok: false, attempts: 1, waitedMs: 0, ...clickObserved.evidence };
  TRACE.mark('search_profile_end', { ok: true });
  return { ok: true, attempts: 1, waitedMs: 0, reason: null };
}

async function returnToSearchResults(page, handle) {
  if (CFG.PROFILE_NAV_MODE !== 'search-click') return;
  TRACE.setContext({ phase: 'back_to_search' });
  TRACE.mark('back_to_search_start');
  const observed = await captureXResponseEvidence(page, async () => {
    await page.goBack({ waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForSelector('input[data-testid="SearchBox_Search_Input"]', { timeout: 15000 });
  });
  if (observed.evidence?.reason === 'RATE_LIMIT') {
    await recordFailure(page, { type: 'RATE_LIMIT', text: `HTTP 429 ${observed.evidence.responseUrl}`, httpStatus: observed.evidence.httpStatus, responseUrl: observed.evidence.responseUrl, handle, url: page.url(), context: 'back_to_search' });
    throw new CampaignExitError('RATE_LIMIT', `HTTP 429 returning from @${handle}`, EXIT_CODES.RATE_LIMIT);
  }
  TRACE.mark('back_to_search_end');
}

class CampaignExitError extends Error {
  constructor(type, message, exitCode) {
    super(message);
    this.name = 'CampaignExitError';
    this.type = type;
    this.exitCode = exitCode;
  }
}

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
    const trace = [];
    const mark = (phase) => trace.push({ phase, at: Date.now() });

    mark('dom_wait_start');
    for (let i = 0; i < 12; i++) { if (document.querySelector('div[data-testid="UserName"]')) break; await s(500); }
    for (let i = 0; i < 10; i++) {
      const hasBtn = document.querySelector('button[data-testid$="-follow"], button[data-testid$="-unfollow"]');
      const hasBadge = document.querySelector('div[data-testid="UserName"] svg[aria-label="认证账号"], div[data-testid="UserName"] svg[aria-label="Verified organization"]');
      if (hasBtn || hasBadge) break;
      await s(500);
    }
    mark('dom_wait_end');

    const UN = document.querySelector('div[data-testid="UserName"]');
    const UD = document.querySelector('div[data-testid="UserDescription"]');
    if (!UN) {
      const err = document.querySelector('div[data-testid="empty_state_header_text"]');
      return { handle: H, error: err ? 'profile_unavailable' : 'no_username', trace };
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
    const FOLLOW_RATIO_MIN = ${cfg.FOLLOW_RATIO_MIN};
    if (VERIFIED_REQUIRED && !blue) d = 'reject:not_blue';
    else if (gold) d = 'reject:gold_org';
    else if (uB) d = 'reject:already_following';
    else if (!fB) d = 'reject:no_follow_btn';
    else if (fN < 0 || fgN < 0) d = 'reject:cant_parse_stats';
    else if (fN > FERS_MAX) d = \`reject:fers>${cfg.FERS_MAX}(\${fN})\`;
    else if (FOLLOWING_GT_FOLLOWERS && fgN < fN * FOLLOW_RATIO_MIN) d = \`reject:fing<fers*${cfg.FOLLOW_RATIO_MIN}(\${fgN}<\${fN})\`;
    else if (cryptoMatch) d = \`reject:blacklist(\${cryptoMatch})\`;
    else if (whitelistFail) d = 'reject:not_in_whitelist';

    mark('decision_ready');
    const r = { handle: H, bio: bio.slice(0, 200), blue, gold, fN, fgN, cryptoMatch, decision: d, action: 'none', trace };

    const DRY_RUN = ${cfg.DRY_RUN};
    if (d === 'pass' && !DRY_RUN) {
      if (!fB || (fB.getAttribute('aria-label') !== \`关注 @\${H}\` && fB.getAttribute('aria-label') !== \`Follow @\${H}\`)) {
        r.action = 'safety_abort_btn_mismatch';
      } else {
        mark('scroll_follow_button');
        fB.scrollIntoView({ block: 'center' });
        await s(${Math.round(cfg.POST_CLICK_SETTLE_MS / 8 + 300)} + Math.random() * 400);
        mark('follow_click');
        fB.click();
        await s(${cfg.POST_CLICK_SETTLE_MS});
        mark('follow_verify');
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

// ============ COMMENT ON PINNED POST ============
// Called after a confirmed follow when COMMENT_AFTER_FOLLOW=true. Tries to reply to the
// target's pinned post with a varied引流 comment. Silently skips if:
//   - no pinned post found on the current profile page
//   - reply composer doesn't open within timeout
//   - tweet button is absent or disabled
// Any anomaly detected AFTER posting is returned in {status:'anomaly'} and the caller halts.
async function commentOnPinnedPost(page, handle, cfg) {
  try {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(1000 + Math.floor(Math.random() * 500));

    const socialCtx = await page.$('[data-testid="socialContext"]');
    if (!socialCtx) { log(`COMMENT SKIP ${handle}: no pinned post`); return { status: 'no_pinned_post' }; }
    const ctxText = await socialCtx.textContent().catch(() => '');
    if (!ctxText.includes('置顶') && !ctxText.includes('Pinned')) {
      log(`COMMENT SKIP ${handle}: socialContext not pinned ("${ctxText.slice(0, 30)}")`);
      return { status: 'no_pinned_post' };
    }

    const replyBtn = await page.$('article[data-testid="tweet"] [data-testid="reply"]');
    if (!replyBtn) { log(`COMMENT SKIP ${handle}: no reply button`); return { status: 'no_reply_btn' }; }

    const comment = generateComment();

    if (cfg.DRY_RUN) {
      log(`COMMENT DRY_RUN ${handle}: would post "${comment}"`);
      return { status: 'dry_run', comment };
    }

    log(`COMMENT ${handle}: replying to pinned post: "${comment}"`);
    await replyBtn.scrollIntoViewIfNeeded();
    await page.waitForTimeout(400 + Math.floor(Math.random() * 600));
    await replyBtn.click();

    const textarea = await page.waitForSelector('[data-testid="tweetTextarea_0"]', { timeout: 6000 }).catch(() => null);
    if (!textarea) { log(`COMMENT SKIP ${handle}: composer didn't open`); return { status: 'no_composer' }; }

    await textarea.click();
    await page.waitForTimeout(300 + Math.floor(Math.random() * 200));
    await page.keyboard.type(comment, { delay: 30 + Math.floor(Math.random() * 35) });
    await page.waitForTimeout(700 + Math.floor(Math.random() * 500));

    const tweetBtn = await page.$('[data-testid="tweetButton"]:not([disabled])');
    if (!tweetBtn) {
      log(`COMMENT SKIP ${handle}: submit button absent/disabled`);
      await page.keyboard.press('Escape');
      return { status: 'no_submit_btn' };
    }

    await tweetBtn.click();
    await page.waitForTimeout(cfg.POST_CLICK_SETTLE_MS);
    log(`✅ COMMENT POSTED ${handle}: "${comment}"`);
    return { status: 'posted', comment };
  } catch (e) {
    log(`COMMENT ERROR ${handle}: ${e.message}`);
    try { await page.keyboard.press('Escape'); } catch {}
    return { status: 'error', error: e.message };
  }
}

// ============ MAIN ============
async function runCampaign({ context, confirmAuthenticated, disableAuthRefresh }) {
  log(`=== CAMPAIGN START ===`);
  log(`Config: TARGET=${CFG.TARGET}, FERS_MAX=${CFG.FERS_MAX}, SETTLE=${CFG.POST_CLICK_SETTLE_MS}ms, DRY_RUN=${CFG.DRY_RUN}, COMMENT=${CFG.COMMENT_AFTER_FOLLOW}`);
  log(`Profile pacer: interval=${CFG.PROFILE_VISIT_MIN_INTERVAL_MS}-${CFG.PROFILE_VISIT_MAX_INTERVAL_MS}ms, cap=${CFG.MAX_PROFILE_VISITS_PER_HOUR}/h, persisted=${CFG.PACING_PATH}`);
  log(`Trace: enabled=${CFG.TRACE_ENABLED}, profileLimit=${CFG.TRACE_PROFILE_LIMIT || 'none'}, dir=${CFG.TRACE_DIR}`);
  log(`Profile navigation mode: ${CFG.PROFILE_NAV_MODE}`);
  log(`SAFETY MANIFEST:`);
  log(`  - Will only click follow buttons matching 'aria-label="关注 @{handle}"' (or "Follow @{handle}")`);
  log(`  - Will NEVER click unfollow / block / report / like / dm`);
  log(`  - Comment (if COMMENT_AFTER_FOLLOW): ONLY on pinned post of just-followed account; varied templates`);
  log(`  - Will exit on any anomaly (CAPTCHA/RATE_LIMIT/LOGIN/LOCK) without retry beyond budget`);
  log(`  - Works on profile copy at ${CFG.PROFILE_DIR}; original profile untouched`);

  let tracker = loadJSON(CFG.TRACKER_PATH, { followed: [], rejected: [], stats: { profiles_checked: 0, follow_success: 0 } });
  let queue = loadJSON(CFG.QUEUE_PATH, []);
  const followedSet = new Set(tracker.followed.map(f => f.handle));
  const rejectedSet = new Set((tracker.rejected || []).map(r => r.h));
  log(`Followed: ${tracker.followed.length}/${CFG.TARGET}, Queue: ${queue.length}, FollowedSet: ${followedSet.size}, RejectedSet: ${rejectedSet.size}`);

  const ctx = context;
  let page = ctx.pages()[0] || await ctx.newPage();
  let currentHandle = null;
  let tracedProfiles = 0;
  TRACE.attach(page);
  TRACE.setContext({ correlationId: 'session', handle: null, phase: 'startup' });
  TRACE.mark('session_start', { dryRun: CFG.DRY_RUN, target: CFG.TARGET });

  try {

  // Startup login gate — gotoRobust waits for a logged-in element (not a fixed timer);
  // EMPTY_PAGE is excluded because the /home SPA shell is briefly <50 chars under latency.
  const nav = await gotoRobust(page, 'https://x.com/home', {
    needSel: 'a[data-testid="SideNav_NewTweet_Button"], [data-testid="AppTabBar_Home_Link"], [data-testid="primaryColumn"]',
    settle: 5000, retries: 4,
    trace: (event, data) => TRACE.mark(event, data),
  });
  if (nav.reason === 'RATE_LIMIT') {
    await recordFailure(page, { type: 'RATE_LIMIT', text: `HTTP 429 ${nav.responseUrl || '/home'}`, httpStatus: nav.httpStatus, responseUrl: nav.responseUrl, url: page.url() });
    throw new CampaignExitError('RATE_LIMIT', 'HTTP 429 during startup navigation', EXIT_CODES.RATE_LIMIT);
  }
  if (nav.reason === 'LOGIN_REDIRECT') throw new XAuthenticationError(`campaign startup requires login: ${page.url()}`, nav);
  const initialAnomaly = await detectAnomaly(page);
  if (initialAnomaly && initialAnomaly.type !== 'EVAL_ERROR' && initialAnomaly.type !== 'EMPTY_PAGE') {
    if (initialAnomaly.type === 'LOGIN_REDIRECT') throw new XAuthenticationError(initialAnomaly.text, { url: page.url() });
    log(`FATAL: anomaly on /home: ${JSON.stringify(initialAnomaly)}`);
    await recordFailure(page, { ...initialAnomaly, url: page.url() });
    throw new CampaignExitError(initialAnomaly.type, initialAnomaly.text, EXIT_CODES[initialAnomaly.type] || 99);
  }
  await confirmAuthenticated(page, { expectedPath: '/home' });
  if (!nav.ok) {
    const type = nav.reason === 'GENERIC_NAV_ERROR' ? 'GENERIC_NAV_ERROR' : 'LOGIN_REDIRECT';
    if (type === 'LOGIN_REDIRECT') throw new XAuthenticationError('home content missing', { url: page.url(), nav });
    await recordFailure(page, { type, text: 'generic X navigation error page after bounded retries', url: page.url() });
    throw new CampaignExitError(type, 'generic X navigation error page after bounded retries', EXIT_CODES[type]);
  }
  log(`Logged in OK: ${page.url()}`);
  // Never restart a mutating campaign after this point; a replay could duplicate follows.
  disableAuthRefresh();

  let shouldExit = false;

  let consecutiveErrors = 0, processedSinceReload = 0;
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
    currentHandle = handle;
    if (followedSet.has(handle)) { log(`SKIP ${handle}: already followed`); continue; }
    if (rejectedSet.has(handle)) { log(`SKIP ${handle}: already rejected`); continue; }
    if (CFG.TRACE_ENABLED && CFG.TRACE_PROFILE_LIMIT > 0 && tracedProfiles >= CFG.TRACE_PROFILE_LIMIT) {
      log(`TRACE PROFILE LIMIT REACHED: ${tracedProfiles}/${CFG.TRACE_PROFILE_LIMIT}`);
      TRACE.mark('trace_limit_reached', { tracedProfiles, limit: CFG.TRACE_PROFILE_LIMIT });
      break;
    }
    tracedProfiles++;
    TRACE.setContext({ correlationId: `profile-${tracedProfiles}`, handle, phase: 'profile_start' });
    TRACE.mark('profile_iteration_start', { queueIndex: i, tracedProfileIndex: tracedProfiles });

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

    TRACE.setContext({ phase: 'pacer_wait' });
    TRACE.mark('pacer_wait_start');
    const pacing = await PROFILE_PACER.beforeVisit(handle);
    TRACE.mark('pacer_wait_end', pacing);
    log(`PROFILE VISIT @${handle}: ${pacing.visitsLastHour}/${CFG.MAX_PROFILE_VISITS_PER_HOUR || 'unlimited'} in rolling hour; next interval ${Math.round(pacing.intervalMs / 1000)}s`);

    let result;
    try {
      TRACE.setContext({ phase: 'goto_profile' });
      const profileNav = CFG.PROFILE_NAV_MODE === 'search-click'
        ? await navigateProfileViaSearch(page, handle)
        : await gotoRobust(page, `https://x.com/${handle}`, {
          needSel: 'div[data-testid="UserName"]', settle: 4000, retries: 3,
          trace: (event, data) => TRACE.mark(event, data),
        });
      if (profileNav.reason === 'RATE_LIMIT') {
        await recordFailure(page, { type: 'RATE_LIMIT', text: `HTTP 429 ${profileNav.responseUrl || handle}`, httpStatus: profileNav.httpStatus, responseUrl: profileNav.responseUrl, handle, url: page.url() });
        throw new CampaignExitError('RATE_LIMIT', `HTTP 429 at @${handle}`, EXIT_CODES.RATE_LIMIT);
      }
      if (profileNav.reason === 'LOGIN_REDIRECT') throw new XAuthenticationError(`campaign requires login at @${handle}`, { handle, url: page.url() });
      if (!profileNav.ok) {
        await recordFailure(page, { type: 'GENERIC_NAV_ERROR', text: `${profileNav.reason} at @${handle}`, handle, url: page.url() });
        throw new CampaignExitError('GENERIC_NAV_ERROR', `profile navigation failed at @${handle}: ${profileNav.reason}`, EXIT_CODES.GENERIC_NAV_ERROR);
      }
      TRACE.setContext({ phase: 'hydrate' });
      TRACE.mark('hydrate_wait_start');
      await page.waitForTimeout(1500);
      TRACE.mark('hydrate_wait_end');
      try {
        const checkpointPath = await TRACE.checkpoint(page, { handle, phase: 'hydrated' });
        if (checkpointPath) TRACE.mark('last_stable_updated', { screenshotPath: checkpointPath });
      } catch (checkpointError) {
        TRACE.mark('checkpoint_failed', { error: checkpointError.message || String(checkpointError) });
      }
      TRACE.setContext({ phase: 'evaluate' });
      TRACE.mark('evaluate_start');
      const observed = await captureXResponseEvidence(page, () => page.evaluate(VERIFY_JS));
      TRACE.mark('evaluate_end', { evidenceReason: observed.evidence?.reason || null });
      if (observed.evidence?.reason === 'RATE_LIMIT') {
        await recordFailure(page, { type: 'RATE_LIMIT', text: `HTTP 429 ${observed.evidence.responseUrl}`, httpStatus: observed.evidence.httpStatus, responseUrl: observed.evidence.responseUrl, handle, url: page.url() });
        throw new CampaignExitError('RATE_LIMIT', `HTTP 429 during follow action at @${handle}`, EXIT_CODES.RATE_LIMIT);
      }
      if (observed.evidence?.reason === 'LOGIN_REDIRECT') {
        throw new XAuthenticationError(`follow action lost authentication at @${handle}`, { handle, url: page.url(), evidence: observed.evidence });
      }
      result = observed.value;
      for (const browserEvent of (Array.isArray(result?.trace) ? result.trace : [])) {
        TRACE.mark(`browser_${browserEvent.phase}`, { browserAt: browserEvent.at });
      }
    } catch (e) {
      if (e instanceof CampaignExitError || e instanceof XAuthenticationError) throw e;
      log(`ERROR ${handle}: ${e.message}`);
      if (/Target crashed/i.test(e.message || '')) {
        TRACE.mark('target_crashed', { error: e.message || String(e) });
        await TRACE.flush();
        await recordFailure(page, { type: 'CONSECUTIVE_ERRORS', text: 'Target crashed', handle, url: page.url() });
        throw new CampaignExitError('CONSECUTIVE_ERRORS', 'Target crashed', EXIT_CODES.CONSECUTIVE_ERRORS);
      }
      if (++consecutiveErrors >= 5) {
        log(`FATAL: ${consecutiveErrors} consecutive errors. Pausing 5 min and exiting.`);
        await recordFailure(page, { type: 'CONSECUTIVE_ERRORS', text: '5+ errors', handle, url: page.url() });
        await sleep(300_000);
        throw new CampaignExitError('CONSECUTIVE_ERRORS', '5+ errors', EXIT_CODES.CONSECUTIVE_ERRORS);
      }
      await sleep(15_000); continue;
    }
    consecutiveErrors = 0;

    if (!result || typeof result !== 'object') {
      log(`WARN ${handle}: evaluate returned ${result}, skipping`);
      await returnToSearchResults(page, handle);
      await sleep(8000); continue;
    }
    if (result.error) {
      log(`${handle} -> ERROR ${result.error}`);
      if (!(CFG.TRACE_ENABLED && CFG.DRY_RUN)) {
        tracker.rejected = tracker.rejected || [];
        // `at` lets lib/skipset apply TTL/transient release later. eval_error is a transient
        // tier (released next run), so this account gets re-evaluated rather than blacklisted.
        tracker.rejected.push({ h: handle, r: 'eval_error:' + result.error, at: new Date().toISOString() });
        rejectedSet.add(handle); saveJSON(CFG.TRACKER_PATH, tracker);
      } else {
        TRACE.mark('diagnostic_error', { error: result.error });
      }
      await returnToSearchResults(page, handle);
      await sleep(rand(CFG.REJECT_WAIT_MIN_MS, CFG.REJECT_WAIT_MAX_MS)); continue;
    }

    log(`${handle} -> ${result.decision} | bio=${(result.bio||'').slice(0,80).replace(/\n/g,' ')}`);
    const diagnosticNoMutation = CFG.TRACE_ENABLED && CFG.DRY_RUN;
    if (!diagnosticNoMutation) {
      tracker.stats.profiles_checked = (tracker.stats.profiles_checked || 0) + 1;

      if (isFollowAction(result.action)) {
        tracker.followed.push({ handle: result.handle, bio: result.bio, fers: result.fN, fing: result.fgN, action: result.action, at: new Date().toISOString() });
        tracker.stats.follow_success = (tracker.stats.follow_success || 0) + 1;
        followedSet.add(handle); followTimestamps.push(Date.now());
        log(`✅ FOLLOW #${tracker.followed.length}: ${handle} (${result.action})`);
      } else if (result.decision && result.decision.startsWith('reject')) {
        tracker.rejected = tracker.rejected || [];
        tracker.rejected.push({ h: handle, r: result.decision, at: new Date().toISOString() });
        rejectedSet.add(handle);
      }
      saveJSON(CFG.TRACKER_PATH, tracker);
    } else {
      TRACE.mark('diagnostic_decision', { decision: result.decision, action: result.action, fN: result.fN, fgN: result.fgN });
    }
    writeStatus({ phase: 'campaign', followed: tracker.followed.length, target: CFG.TARGET,
      queue_total: queue.length, processed: i + 1, diagnostic_processed: tracedProfiles,
      last: { handle, decision: result.decision || result.action } });

    // Anomaly check AFTER action (esp. after a follow). EMPTY_PAGE excluded (latency artifact).
    const anomaly = await detectAnomaly(page);
    if (anomaly && anomaly.type !== 'EVAL_ERROR' && anomaly.type !== 'EMPTY_PAGE') {
      if (anomaly.type === 'LOGIN_REDIRECT') throw new XAuthenticationError(anomaly.text, { handle, url: page.url() });
      log(`!!! ANOMALY DETECTED: ${anomaly.type} - ${anomaly.text}`);
      await recordFailure(page, { ...anomaly, handle, url: page.url() });
      throw new CampaignExitError(anomaly.type, anomaly.text, EXIT_CODES[anomaly.type] || 99);
    }

    // Comment on pinned post (引流回关): only when follow succeeded, no prior anomaly, feature enabled.
    if (isFollowAction(result.action) && CFG.COMMENT_AFTER_FOLLOW) {
      await page.waitForTimeout(1500 + Math.floor(Math.random() * 1000));
      const observedComment = await captureXResponseEvidence(page, () => commentOnPinnedPost(page, handle, CFG));
      if (observedComment.evidence?.reason === 'RATE_LIMIT') {
        await recordFailure(page, { type: 'RATE_LIMIT', text: `HTTP 429 ${observedComment.evidence.responseUrl}`, httpStatus: observedComment.evidence.httpStatus, responseUrl: observedComment.evidence.responseUrl, handle, url: page.url(), context: 'after_comment' });
        throw new CampaignExitError('RATE_LIMIT', `HTTP 429 during comment action at @${handle}`, EXIT_CODES.RATE_LIMIT);
      }
      if (observedComment.evidence?.reason === 'LOGIN_REDIRECT') {
        throw new XAuthenticationError(`comment action lost authentication at @${handle}`, { handle, url: page.url(), evidence: observedComment.evidence });
      }
      const cr = observedComment.value;
      tracker.followed[tracker.followed.length - 1].comment = cr;
      saveJSON(CFG.TRACKER_PATH, tracker);
      // Re-check anomaly after comment interaction (typing/clicking can trigger rate limits).
      if (cr.status === 'posted' || cr.status === 'error') {
        const ca = await detectAnomaly(page);
        if (ca && ca.type !== 'EVAL_ERROR' && ca.type !== 'EMPTY_PAGE') {
          if (ca.type === 'LOGIN_REDIRECT') throw new XAuthenticationError(ca.text, { handle, url: page.url() });
          log(`!!! ANOMALY AFTER COMMENT: ${ca.type} - ${ca.text}`);
          await recordFailure(page, { ...ca, handle, url: page.url(), context: 'after_comment' });
          throw new CampaignExitError(ca.type, ca.text, EXIT_CODES[ca.type] || 99);
        }
      }
    }

    await returnToSearchResults(page, handle);

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
  } catch (error) {
    if (!alertWrittenThisRun) {
      const type = error instanceof XAuthenticationError
        ? 'LOGIN_REDIRECT'
        : (error instanceof CampaignExitError ? error.type : 'UNEXPECTED_ERROR');
      await recordFailure(page, {
        type,
        text: error.message || String(error),
        handle: currentHandle,
        url: (() => { try { return page.url(); } catch { return null; } })(),
      });
    }
    throw error;
  } finally {
    TRACE.mark('session_end', { followed: tracker.followed.length, tracedProfiles });
    await TRACE.detach();
  }
}

async function main() {
  await PROFILE_PACER.beforeNetwork('campaign startup /home');
  await withAuthenticatedContext(
    { config: RUNTIME.browser, headless: false, width: 1280, height: 820 },
    runCampaign,
  );
}

main().catch((error) => {
  if (error instanceof BrowserConfigError) {
    log(`FATAL BROWSER_CONFIG: ${error.message}`);
    process.exitCode = 2;
    return;
  }
  if (error instanceof XAuthenticationError) {
    if (!alertWrittenThisRun) writeAlert(CFG.ALERT_PATH, { type: 'LOGIN_REDIRECT', text: error.message, url: error.details?.url, profileDir: CFG.PROFILE_DIR });
    log(`FATAL LOGIN_REDIRECT: ${error.message}`);
    process.exitCode = EXIT_CODES.LOGIN_REDIRECT;
    return;
  }
  if (error instanceof CampaignExitError) {
    log(`FATAL ${error.type}: ${error.message}`);
    process.exitCode = error.exitCode;
    return;
  }
  log(`FATAL: ${error.stack || error}`);
  process.exitCode = 99;
});
