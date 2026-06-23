#!/usr/bin/env node
// harvest.cjs — unified, latency/429-tolerant candidate harvester (replaces the old
// harvest-search / harvest-replies / harvest-followers trio).
//
// Usage:
//   node harvest.cjs search   "<query>"                 [scrolls] [--tab live|top]
//   node harvest.cjs search-multi "<q1,q2,q3,...>"      [scrolls] [--tab live|top]
//   node harvest.cjs replies  "<statusUrl>"             [scrolls]
//   node harvest.cjs followers "<handle>" "<followers|following>" [scrolls]
// Env: PROFILE_DIR (default ~/.config/playwright-chrome-profile-campaign)
// Output: stdout JSON { count, items:[{handle, displayName, blue, text}], perQuery }
//         (or {count:0,error} on nav failure)
//
// 429 STRATEGY (rewritten after measuring real storms in jobs 50i/50j):
//   The earlier "all queries in ONE long session" assumption was WRONG for f=live search —
//   logs proved 429 reliably trips on the 3rd query of a single session (after ~2 clean
//   SearchTimeline fetches) and then CASCADES, because the backoff waits happen inside the
//   same throttled session whose IP/session budget never resets. The old one-query-per-launch
//   jobs almost never 429'd because each fresh launch reset the budget.
//   So search-multi now:
//     1. runs at most SESSION_SIZE (default 2) queries per browser session, then closes +
//        relaunches after a SESSION_COOLDOWN (default 75s) — a fresh session resets the budget;
//     2. paces QUERY_PACING_MS (default 25s + jitter) between queries inside a session;
//     3. uses a deeper search backoff (base 45s) so a retry lands OUTSIDE the ~140s live-search
//        window (the only observed recoveries happened past the old 80s ceiling);
//     4. ABORTS the round after 2 consecutive hard nav failures (the session is throttled —
//        the remaining queries are guaranteed to fail too) and reports rateLimited:true so the
//        orchestrator can cool down instead of mis-counting it as a dry (pool-exhausted) round.

const path = require('path');
const { chromium } = require('playwright');
const { gotoRobust, sleep } = require(path.join(__dirname, 'lib', 'nav-helper.cjs'));

const PROFILE_DIR = process.env.PROFILE_DIR || `${process.env.HOME}/.config/playwright-chrome-profile-campaign`;
const argv = process.argv.slice(2);
const mode = argv[0];

function fail(msg) { console.error(msg); process.exit(2); }
if (!['search', 'search-multi', 'replies', 'followers'].includes(mode)) {
  fail('Usage: harvest.cjs search|search-multi|replies|followers ...');
}

// ---- build the list of navigation targets (one per query / status / list) ----
const ARTICLE_SEL = 'article[role="article"]';
const USERCELL_SEL = '[data-testid="UserCell"]';
let targets = [];          // [{ url, label }]
let needSel, extractKind, scrolls;

function searchUrl(query, tab) {
  return `https://x.com/search?q=${encodeURIComponent(query)}&src=typed_query&f=${tab}`;
}

if (mode === 'search' || mode === 'search-multi') {
  const tabArg = argv.indexOf('--tab');
  const tab = tabArg !== -1 ? argv[tabArg + 1] : 'live';
  scrolls = parseInt(argv[2] && /^\d+$/.test(argv[2]) ? argv[2] : '20', 10);
  needSel = ARTICLE_SEL;
  extractKind = 'article';
  if (mode === 'search') {
    const query = argv[1];
    if (!query) fail('search needs a query');
    targets = [{ url: searchUrl(query, tab), label: query }];
  } else {
    const queries = (argv[1] || '').split(',').map(s => s.trim()).filter(Boolean);
    if (!queries.length) fail('search-multi needs a comma-separated query list');
    targets = queries.map(q => ({ url: searchUrl(q, tab), label: q }));
  }
} else if (mode === 'replies') {
  const url = argv[1];
  if (!url || !url.includes('/status/')) fail('replies needs a status URL');
  scrolls = parseInt(argv[2] && /^\d+$/.test(argv[2]) ? argv[2] : '25', 10);
  needSel = ARTICLE_SEL;
  extractKind = 'article';
  targets = [{ url, label: 'replies' }];
} else {
  const handle = argv[1], type = argv[2];
  if (!handle || (type !== 'followers' && type !== 'following')) fail('followers needs <handle> <followers|following>');
  scrolls = parseInt(argv[3] && /^\d+$/.test(argv[3]) ? argv[3] : '25', 10);
  needSel = USERCELL_SEL;
  extractKind = 'usercell';
  targets = [{ url: `https://x.com/${handle}/${type}`, label: `${handle}/${type}` }];
}

const EXTRACT_JS = `(async (KIND, SCROLLS) => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const RESERVED = ['home','explore','notifications','i','search','compose','settings','messages','bookmarks','jobs','lists','communities','articles','premium','hashtag','status'];
  const collected = new Map();

  const fromArticles = () => {
    for (const art of document.querySelectorAll('article[role="article"]')) {
      let handle = null;
      for (const a of art.querySelectorAll('a[href^="/"]')) {
        const m = (a.getAttribute('href') || '').match(/^\\/([A-Za-z0-9_]+)(\\/.*)?$/);
        if (m && !RESERVED.includes(m[1])) { handle = m[1]; break; }
      }
      const nameEl = art.querySelector('div[data-testid="User-Name"]');
      const blue = !!(nameEl && nameEl.querySelector('svg[aria-label="认证账号"]'));
      const textEl = art.querySelector('div[data-testid="tweetText"]');
      const displayName = nameEl ? nameEl.innerText.split('\\n')[0].slice(0, 60) : '';
      const text = textEl ? textEl.innerText.slice(0, 120) : '';
      if (handle && !collected.has(handle)) collected.set(handle, { handle, displayName, blue, text });
    }
  };
  const fromUserCells = () => {
    for (const cell of document.querySelectorAll('[data-testid="UserCell"]')) {
      let handle = null;
      const av = cell.querySelector('[data-testid^="UserAvatar-Container-"]');
      if (av) { const m = (av.getAttribute('data-testid')||'').match(/^UserAvatar-Container-(.+)$/); if (m) handle = m[1]; }
      if (!handle) { const a = cell.querySelector('a[href^="/"]'); const m = a && (a.getAttribute('href')||'').match(/^\\/([A-Za-z0-9_]+)$/); if (m) handle = m[1]; }
      const blue = !!cell.querySelector('svg[aria-label="认证账号"]');
      if (handle && !collected.has(handle)) collected.set(handle, { handle, displayName: '', blue, text: '' });
    }
  };
  const extract = KIND === 'usercell' ? fromUserCells : fromArticles;

  let stall = 0, prev = -1;
  for (let i = 0; i < SCROLLS; i++) {
    extract();
    if (collected.size === prev) { stall++; if (stall > 5) break; } else { stall = 0; prev = collected.size; }
    window.scrollBy(0, 1800);
    await sleep(1300);  // slower than original — high-latency render headroom
  }
  extract();
  return { count: collected.size, items: Array.from(collected.values()) };
})(${JSON.stringify(extractKind)}, ${scrolls})`;

// Search backoff base: 45s (vs the 20s default) so a retry lands past the ~140s live-search
// rate-limit window. retries:3 -> waits 45s then 90s (135s total) before giving up — matching
// the only observed recovery point. Non-search modes keep the gentler default.
const SEARCH_BACKOFF_BASE = parseInt(process.env.SEARCH_BACKOFF_BASE || '45000', 10);
const SEARCH_RETRIES = parseInt(process.env.SEARCH_RETRIES || '3', 10);

async function harvestOne(page, target) {
  process.stderr.write(`[harvest] ${mode}: ${target.url}\n`);
  const isSearch = mode === 'search' || mode === 'search-multi';
  const navOpts = isSearch
    ? { needSel, settle: 5000, retries: SEARCH_RETRIES, backoffBase: SEARCH_BACKOFF_BASE }
    : { needSel, settle: 5000, retries: 4 };
  const nav = await gotoRobust(page, target.url, navOpts);
  if (!nav.ok) {
    process.stderr.write(`[harvest] page error after ${nav.attempts} retries (${target.label}) — likely rate-limited\n`);
    return { ok: false, items: [], rl: true };
  }
  await page.waitForTimeout(1500);
  const result = await page.evaluate(EXTRACT_JS);
  process.stderr.write(`[harvest] ${target.label}: collected ${result.count}\n`);
  return { ok: true, items: result.items, rl: false };
}

function launchCtx() {
  return chromium.launchPersistentContext(PROFILE_DIR, {
    channel: 'chrome', headless: false, chromiumSandbox: true, viewport: { width: 1280, height: 820 },
    ignoreDefaultArgs: ['--enable-automation'], args: ['--disable-blink-features=AutomationControlled'],
  });
}

async function main() {
  // 429 pacing/session knobs (see header). search-multi splits queries across short sessions;
  // single-target modes (search/replies/followers) run one query so they ignore SESSION_SIZE.
  const SESSION_SIZE = parseInt(process.env.SESSION_SIZE || '2', 10);
  const PACING_MS = parseInt(process.env.QUERY_PACING_MS || '25000', 10);
  const PACING_JITTER = parseInt(process.env.QUERY_PACING_JITTER_MS || '15000', 10);
  const SESSION_COOLDOWN_MS = parseInt(process.env.SESSION_COOLDOWN_MS || '75000', 10);
  const isSearchMulti = mode === 'search-multi';

  // Merge all targets into ONE deduped item map (handle-keyed). The first time we see a
  // handle wins — and we OR the blue flag so a verified sighting in any query sticks.
  const merged = new Map();
  const perQuery = {};
  let anyOk = false, rateLimited = false, consecFail = 0;
  let ctx = null, page = null, inSession = 0;

  for (let t = 0; t < targets.length; t++) {
    if (!ctx) { ctx = await launchCtx(); page = ctx.pages()[0] || await ctx.newPage(); inSession = 0; }
    const tg = targets[t];
    const r = await harvestOne(page, tg);
    if (r.ok) { anyOk = true; consecFail = 0; }
    else { rateLimited = rateLimited || !!r.rl; consecFail++; }
    let added = 0;
    for (const it of r.items) {
      const ex = merged.get(it.handle);
      if (!ex) { merged.set(it.handle, it); added++; }
      else if (it.blue && !ex.blue) ex.blue = true;  // verified sighting wins
    }
    perQuery[tg.label] = (perQuery[tg.label] || 0) + added;
    inSession++;

    // Hard-throttle abort: once 2 queries in a row fail, the session/IP is rate-limited and
    // the remaining f=live queries will fail too (50i: 4/4). Bail and let the orchestrator
    // cool down instead of burning ~10min of backoff for zero new candidates.
    if (consecFail >= 2) {
      process.stderr.write('[harvest] 2 consecutive nav failures — aborting round (rate-limited)\n');
      rateLimited = true;
      break;
    }
    if (t < targets.length - 1) {
      if (isSearchMulti && inSession >= SESSION_SIZE) {
        // session full -> fresh launch resets X's rate-limit budget
        await ctx.close(); ctx = null;
        const cd = Math.round(SESSION_COOLDOWN_MS / 1000);
        process.stderr.write(`[harvest] session full (${SESSION_SIZE} queries) — close + cooldown ${cd}s + relaunch\n`);
        await sleep(SESSION_COOLDOWN_MS);
      } else {
        await sleep(PACING_MS + Math.floor(Math.random() * PACING_JITTER));
      }
    }
  }

  if (ctx) await ctx.close();

  if (!anyOk && merged.size === 0) {
    console.log(JSON.stringify({ count: 0, error: 'page_error_after_retries', items: [], rateLimited: true }, null, 2));
    return;
  }
  const items = Array.from(merged.values());
  console.log(JSON.stringify({ count: items.length, items, perQuery, rateLimited }, null, 2));
}

main().catch(e => { console.error('FATAL', e); process.exit(99); });
