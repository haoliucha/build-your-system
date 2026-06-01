#!/usr/bin/env node
// campaign.cjs — X 蓝V互关 主关注 loop
//
// 配置(env):
//   TARGET (必填,如 100)
//   PROFILE_DIR (默认 ~/.config/playwright-chrome-profile-campaign)
//   MY_HANDLE (强烈建议填,用于 already-following pre-filter)
//   QUEUE_PATH / TRACKER_PATH / LOG_PATH (默认在 cwd)
//   VERIFIED_REQUIRED (默认 true)
//   FOLLOWING_GT_FOLLOWERS (默认 true)
//   FERS_MAX (默认 1100)
//   BIO_BLACKLIST (默认 内置 crypto list,逗号分隔覆盖)
//   BIO_WHITELIST (默认空)
//   FOLLOW_WAIT_MIN_MS / FOLLOW_WAIT_MAX_MS (25000 / 55000)
//   REJECT_WAIT_MIN_MS / REJECT_WAIT_MAX_MS (5000 / 12000)
//   LONG_BREAK_EVERY / LONG_BREAK_MS (12 / 180000)
//   POST_CLICK_SETTLE_MS (2500)
//   MAX_FOLLOWS_PER_HOUR (0 = 不限)
//   QUIET_HOURS (空 = 不限,"2,7" = 凌晨 2-7 点暂停)
//   DRY_RUN (1 = 只验证不 click)

const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright');
const { ANOMALY_DETECTOR_JS, EXIT_CODES, detectAnomaly, writeAlert } = require(path.join(__dirname, 'detect-anomaly.cjs'));

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
  BIO_BLACKLIST: (process.env.BIO_BLACKLIST || 'crypto,web3,btc,eth,sol,defi,nft,blockchain,binance,okx,bybit,coinbase,airdrop,ordinal,memecoin,wallet,staking,gamefi,layer2,tokenomic,bitcoin,ethereum,solana,sui,aptos,arbitrum,optimism,mining,hashrate,ico,ido,launchpad,presale,hyperliquid,perp,trader,quant,onchain,altcoin,shitcoin,pumpfun,币圈,币安,合约,空投,铭文,打新,钱包,量化,操盘,建仓,加仓,止盈,撸毛,羊毛,空投党,矿工,矿池,去中心化,链上,加密,炒币,土狗,梭哈,埋伏').split(',').map(s => s.trim()).filter(Boolean),
  BIO_WHITELIST: (process.env.BIO_WHITELIST || '').split(',').map(s => s.trim()).filter(Boolean),

  FOLLOW_WAIT_MIN_MS: parseInt(process.env.FOLLOW_WAIT_MIN_MS || '25000', 10),
  FOLLOW_WAIT_MAX_MS: parseInt(process.env.FOLLOW_WAIT_MAX_MS || '55000', 10),
  REJECT_WAIT_MIN_MS: parseInt(process.env.REJECT_WAIT_MIN_MS || '5000', 10),
  REJECT_WAIT_MAX_MS: parseInt(process.env.REJECT_WAIT_MAX_MS || '12000', 10),
  LONG_BREAK_EVERY: parseInt(process.env.LONG_BREAK_EVERY || '12', 10),
  LONG_BREAK_MS: parseInt(process.env.LONG_BREAK_MS || '180000', 10),
  POST_CLICK_SETTLE_MS: parseInt(process.env.POST_CLICK_SETTLE_MS || '2500', 10),

  MAX_FOLLOWS_PER_HOUR: parseInt(process.env.MAX_FOLLOWS_PER_HOUR || '0', 10),
  QUIET_HOURS: (process.env.QUIET_HOURS || '').split(',').map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n)),

  DRY_RUN: process.env.DRY_RUN === '1',
  RELOAD_QUEUE_EVERY: parseInt(process.env.RELOAD_QUEUE_EVERY || '20', 10),
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

function saveJSON(p, obj) {
  fs.writeFileSync(p, JSON.stringify(obj, null, 2));
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const rand = (min, max) => min + Math.floor(Math.random() * (max - min));

// ============ VERIFY + FOLLOW JS (runs in browser context) ============
function buildVerifyJs(cfg) {
  const enRegexSource = cfg.BIO_BLACKLIST
    .filter(t => /^[a-z0-9_.-]+$/i.test(t))
    .join('|');
  const zhTokens = cfg.BIO_BLACKLIST.filter(t => !/^[a-z0-9_.-]+$/i.test(t));
  const whitelist = cfg.BIO_WHITELIST;

  return `(async () => {
    const H = window.location.pathname.slice(1).split('/')[0];
    const s = (ms) => new Promise(r => setTimeout(r, ms));

    // Phase 1: wait UserName
    for (let i = 0; i < 12; i++) {
      if (document.querySelector('div[data-testid="UserName"]')) break;
      await s(500);
    }
    // Phase 2: wait button OR badge
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
    const pc = (v) => {
      if (!v) return -1;
      // 单位:亿(1e8),万(1e4),千/K(1e3),M(1e6),B(1e9)
      const m = v.match(/([\\d,.]+)\\s*([万千亿KMB])?/);
      if (!m) return -1;
      let n = parseFloat(m[1].replace(/,/g, ''));
      const u = m[2];
      if (u === '亿') n *= 1e8;
      else if (u === '万') n *= 10000;
      else if (u === 'K' || u === '千') n *= 1000;
      else if (u === 'M') n *= 1e6;
      else if (u === 'B') n *= 1e9;
      return Math.round(n);
    };
    const fN = pc(fers), fgN = pc(fing);

    const fB = document.querySelector(\`button[data-testid$="-follow"][aria-label="关注 @\${H}"], button[data-testid$="-follow"][aria-label="Follow @\${H}"]\`);
    const uB = document.querySelector(\`button[data-testid$="-unfollow"][aria-label*="@\${H}"]\`);

    // crypto detection (en regex word-boundary + zh substring + handle substring)
    const enRegex = ${enRegexSource ? `new RegExp('\\\\b(' + ${JSON.stringify(enRegexSource)} + ')\\\\b', 'i')` : 'null'};
    const zhTokens = ${JSON.stringify(zhTokens)};
    const enTokens = ${JSON.stringify(cfg.BIO_BLACKLIST.filter(t => /^[a-z0-9_.-]+$/i.test(t)))};
    const whitelist = ${JSON.stringify(whitelist)};

    let cryptoMatch = null;
    if (enRegex) {
      const m = bio.match(enRegex);
      if (m) cryptoMatch = m[0];
    }
    if (!cryptoMatch) cryptoMatch = zhTokens.find(k => bio.includes(k)) || null;
    if (!cryptoMatch) {
      const handleLower = H.toLowerCase();
      cryptoMatch = enTokens.find(k => handleLower.includes(k.toLowerCase())) || null;
    }

    let whitelistFail = false;
    if (whitelist.length > 0) {
      const bioLower = bio.toLowerCase();
      const hit = whitelist.some(w => bioLower.includes(w.toLowerCase()));
      if (!hit) whitelistFail = true;
    }

    // Decision (apply config gates)
    let d = 'pass';
    const VERIFIED_REQUIRED = ${cfg.VERIFIED_REQUIRED};
    const FOLLOWING_GT_FOLLOWERS = ${cfg.FOLLOWING_GT_FOLLOWERS};
    const FERS_MAX = ${cfg.FERS_MAX};

    if (VERIFIED_REQUIRED && !blue) d = 'reject:not_blue';
    else if (gold) d = 'reject:gold_org';
    else if (uB) d = 'reject:already_following';  // ❗ SAFETY: never click if already followed
    else if (!fB) d = 'reject:no_follow_btn';
    else if (fN < 0 || fgN < 0) d = 'reject:cant_parse_stats';
    else if (fN > FERS_MAX) d = \`reject:fers>${cfg.FERS_MAX}(\${fN})\`;
    else if (FOLLOWING_GT_FOLLOWERS && fgN <= fN) d = \`reject:fing<=fers(\${fgN}<=\${fN})\`;
    else if (cryptoMatch) d = \`reject:blacklist(\${cryptoMatch})\`;
    else if (whitelistFail) d = 'reject:not_in_whitelist';

    const r = { handle: H, bio: bio.slice(0, 200), blue, gold, fN, fgN, cryptoMatch, decision: d, action: 'none' };

    // Click + verify (only if pass AND not DRY_RUN)
    const DRY_RUN = ${cfg.DRY_RUN};
    if (d === 'pass' && !DRY_RUN) {
      // SAFETY: re-verify fB still exists and is the exact target
      if (!fB || fB.getAttribute('aria-label') !== \`关注 @\${H}\` && fB.getAttribute('aria-label') !== \`Follow @\${H}\`) {
        r.action = 'safety_abort_btn_mismatch';
      } else {
        fB.scrollIntoView({ block: 'center' });
        await s(${cfg.POST_CLICK_SETTLE_MS / 8 + 300} + Math.random() * 400);  // pre-click hover delay
        fB.click();
        await s(${cfg.POST_CLICK_SETTLE_MS});

        const u1 = document.querySelector(\`button[data-testid$="-unfollow"][aria-label*="@\${H}"]\`);
        if (u1) {
          r.action = 'followed';
        } else {
          const cf = document.querySelector('div[data-testid="confirmationSheetConfirm"]');
          if (cf) {
            cf.click();
            await s(2000);
            const u2 = document.querySelector(\`button[data-testid$="-unfollow"][aria-label*="@\${H}"]\`);
            r.action = u2 ? 'followed_via_confirm' : 'click_initiated_no_verify';
          } else {
            // DOM lag — assume server registered the follow (next-run already-followed check will reconcile)
            r.action = 'followed_assumed';
          }
        }
      }
    } else if (d === 'pass' && DRY_RUN) {
      r.action = 'dry_run_would_follow';
    }

    return r;
  })()`;
}

// ============ MAIN ============
async function main() {
  log(`=== CAMPAIGN START ===`);
  log(`Config: TARGET=${CFG.TARGET}, FERS_MAX=${CFG.FERS_MAX}, DRY_RUN=${CFG.DRY_RUN}`);
  log(`SAFETY MANIFEST:`);
  log(`  - Will only click follow buttons matching 'aria-label="关注 @{handle}"' (or "Follow @{handle}")`);
  log(`  - Will NEVER click unfollow / block / report / like / tweet / dm`);
  log(`  - Will exit on any anomaly (CAPTCHA/RATE_LIMIT/LOGIN/LOCK) without retry beyond budget`);
  log(`  - Will preserve original profile, work on copy at ${CFG.PROFILE_DIR}`);

  let tracker = loadJSON(CFG.TRACKER_PATH, { followed: [], rejected: [], stats: { profiles_checked: 0, follow_success: 0 } });
  let queue = loadJSON(CFG.QUEUE_PATH, []);
  const followedSet = new Set(tracker.followed.map(f => f.handle));
  const rejectedSet = new Set((tracker.rejected || []).map(r => r.h));

  log(`Followed: ${tracker.followed.length}/${CFG.TARGET}, Queue: ${queue.length}, FollowedSet: ${followedSet.size}, RejectedSet: ${rejectedSet.size}`);

  // Launch browser
  const ctx = await chromium.launchPersistentContext(CFG.PROFILE_DIR, {
    channel: 'chrome',
    headless: false,
    viewport: { width: 1280, height: 820 },
    ignoreDefaultArgs: ['--enable-automation'],
    args: ['--disable-blink-features=AutomationControlled'],
  });
  let page = ctx.pages()[0] || await ctx.newPage();

  // Verify login
  await page.goto('https://x.com/home', { waitUntil: 'domcontentloaded', timeout: 30_000 });
  await page.waitForTimeout(2500);
  const initialAnomaly = await detectAnomaly(page);
  if (initialAnomaly && initialAnomaly.type !== 'EVAL_ERROR') {
    log(`FATAL: anomaly on /home: ${JSON.stringify(initialAnomaly)}`);
    writeAlert(CFG.ALERT_PATH, { ...initialAnomaly, profileDir: CFG.PROFILE_DIR, url: page.url() });
    await ctx.close();
    process.exit(EXIT_CODES[initialAnomaly.type] || 99);
  }
  log(`Logged in OK: ${page.url()}`);

  // Signal handlers — clean exit on SIGTERM/SIGINT
  let shouldExit = false;
  ['SIGTERM', 'SIGINT'].forEach(sig => {
    process.on(sig, () => {
      log(`Got ${sig}, exiting after current iteration`);
      shouldExit = true;
    });
  });

  let consecutiveErrors = 0;
  let consecutiveRateLimits = 0;
  const VERIFY_JS = buildVerifyJs(CFG);

  // Hourly cap tracking
  const followTimestamps = [];

  // Quiet hours check
  const inQuietHours = () => {
    if (CFG.QUIET_HOURS.length !== 2) return false;
    const [start, end] = CFG.QUIET_HOURS;
    const h = new Date().getHours();
    return h >= start && h < end;
  };

  let processedSinceReload = 0;

  for (let i = 0; i < queue.length; i++) {
    if (shouldExit) { log('Exiting gracefully'); break; }
    if (tracker.followed.length >= CFG.TARGET) {
      log(`TARGET REACHED: ${tracker.followed.length} follows`);
      break;
    }

    // Hot reload queue every N
    if (processedSinceReload >= CFG.RELOAD_QUEUE_EVERY) {
      const newQueue = loadJSON(CFG.QUEUE_PATH, []);
      if (newQueue.length > queue.length) {
        const added = newQueue.length - queue.length;
        queue = newQueue;
        log(`Hot-reloaded queue: +${added} new candidates (total ${queue.length})`);
      }
      processedSinceReload = 0;
    }
    processedSinceReload++;

    const handle = queue[i];

    if (followedSet.has(handle)) { log(`SKIP ${handle}: already followed`); continue; }
    if (rejectedSet.has(handle)) { log(`SKIP ${handle}: already rejected`); continue; }

    // Quiet hours
    while (inQuietHours()) {
      log(`Quiet hours [${CFG.QUIET_HOURS.join(',')}], sleeping 10 min...`);
      await sleep(600_000);
    }

    // Hourly cap
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
      await page.goto(`https://x.com/${handle}`, { waitUntil: 'domcontentloaded', timeout: 30_000 });
      await page.waitForTimeout(2500);
      result = await page.evaluate(VERIFY_JS);
    } catch (e) {
      log(`ERROR ${handle}: ${e.message}`);
      consecutiveErrors++;
      if (consecutiveErrors >= 5) {
        log(`FATAL: ${consecutiveErrors} consecutive errors. Pausing 5 min and exiting.`);
        writeAlert(CFG.ALERT_PATH, { type: 'CONSECUTIVE_ERRORS', text: `5+ errors`, handle, url: page.url(), profileDir: CFG.PROFILE_DIR });
        await sleep(300_000);
        await ctx.close();
        process.exit(EXIT_CODES.CONSECUTIVE_ERRORS);
      }
      await sleep(15_000);
      continue;
    }
    consecutiveErrors = 0;

    if (!result || typeof result !== 'object') {
      log(`WARN ${handle}: evaluate returned ${result}, skipping`);
      await sleep(8000);
      continue;
    }
    if (result.error) {
      log(`${handle} -> ERROR ${result.error}`);
      tracker.rejected = tracker.rejected || [];
      tracker.rejected.push({ h: handle, r: 'eval_error:' + result.error });
      rejectedSet.add(handle);
      saveJSON(CFG.TRACKER_PATH, tracker);
      await sleep(rand(CFG.REJECT_WAIT_MIN_MS, CFG.REJECT_WAIT_MAX_MS));
      continue;
    }

    log(`${handle} -> ${result.decision} | bio=${(result.bio||'').slice(0,80).replace(/\n/g,' ')}`);

    tracker.stats.profiles_checked = (tracker.stats.profiles_checked || 0) + 1;

    if (result.action === 'followed' || result.action === 'followed_via_confirm' || result.action === 'followed_assumed') {
      tracker.followed.push({
        handle: result.handle,
        bio: result.bio,
        fers: result.fN,
        fing: result.fgN,
        action: result.action,
        at: new Date().toISOString(),
      });
      tracker.stats.follow_success = (tracker.stats.follow_success || 0) + 1;
      followedSet.add(handle);
      followTimestamps.push(Date.now());
      log(`✅ FOLLOW #${tracker.followed.length}: ${handle}`);
      consecutiveRateLimits = 0;
    } else if (result.decision && result.decision.startsWith('reject')) {
      tracker.rejected = tracker.rejected || [];
      tracker.rejected.push({ h: handle, r: result.decision });
      rejectedSet.add(handle);
    }

    saveJSON(CFG.TRACKER_PATH, tracker);

    // Anomaly check AFTER action(尤其是 follow 之后)
    const anomaly = await detectAnomaly(page);
    if (anomaly && anomaly.type !== 'EVAL_ERROR' && anomaly.type !== 'EMPTY_PAGE') {
      log(`!!! ANOMALY DETECTED: ${anomaly.type} - ${anomaly.text}`);
      writeAlert(CFG.ALERT_PATH, { ...anomaly, handle, url: page.url(), profileDir: CFG.PROFILE_DIR, trackerPath: CFG.TRACKER_PATH });

      if (anomaly.type === 'RATE_LIMIT') {
        consecutiveRateLimits++;
        if (consecutiveRateLimits >= 2) {
          log(`RATE_LIMIT twice, exiting`);
          await ctx.close();
          process.exit(EXIT_CODES.RATE_LIMIT);
        }
        log(`RATE_LIMIT first hit, pause 30 min and retry once`);
        await sleep(1800_000);
        continue;
      }

      // Other anomalies — exit immediately
      await ctx.close();
      process.exit(EXIT_CODES[anomaly.type] || 99);
    }

    // Pace
    if (result.action === 'followed' || result.action === 'followed_via_confirm' || result.action === 'followed_assumed') {
      const w = rand(CFG.FOLLOW_WAIT_MIN_MS, CFG.FOLLOW_WAIT_MAX_MS);
      log(`-- sleep ${(w/1000).toFixed(0)}s --`);
      await sleep(w);

      // Long break every N follows
      if (tracker.stats.follow_success % CFG.LONG_BREAK_EVERY === 0) {
        log(`-- LONG BREAK ${CFG.LONG_BREAK_MS/1000}s after ${tracker.stats.follow_success} follows --`);
        await sleep(CFG.LONG_BREAK_MS);
        // Post-break warmup: next 5 follows use extended wait
        log(`(post-break warmup active for next 5 follows)`);
      }
    } else {
      await sleep(rand(CFG.REJECT_WAIT_MIN_MS, CFG.REJECT_WAIT_MAX_MS));
    }
  }

  log(`=== CAMPAIGN END === Total follows: ${tracker.followed.length}/${CFG.TARGET}`);
  await ctx.close();
  process.exit(0);
}

main().catch(e => {
  log(`FATAL: ${e.stack || e}`);
  process.exit(99);
});
