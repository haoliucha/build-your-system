#!/usr/bin/env node
// harvest.cjs — unified, latency/error-tolerant candidate harvester (replaces the old
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
// NETWORK STRATEGY:
//   1. search-multi runs at most SESSION_SIZE (default 2) queries per bounded CDP session;
//   2. QUERY_PACING_MS plus jitter limits query bursts, and SESSION_COOLDOWN separates sessions;
//   3. only a navigation or related X API/Timeline HTTP 429 sets rateLimited:true;
//   4. a generic retry page remains a normal navigation failure, never inferred as HTTP 429;
//   5. a real 429 aborts the round for the orchestrator's bounded cooldown policy.

const path = require('path');
const { captureXResponseEvidence, gotoRobust, sleep } = require(path.join(__dirname, 'lib', 'nav-helper.cjs'));
const { prepareXFacingRuntime } = require(path.join(__dirname, 'lib', 'runtime-gate.cjs'));
const { BrowserConfigError, withAuthenticatedContext, XAuthenticationError } = require(path.join(__dirname, 'lib', 'cdp-browser.cjs'));

const PROFILE_DIR = process.env.PROFILE_DIR || `${process.env.HOME}/.config/playwright-chrome-profile-campaign`;
const argv = process.argv.slice(2);
const mode = argv[0];

function fail(msg) { console.error(msg); process.exit(2); }
if (!['search', 'search-multi', 'replies', 'followers'].includes(mode)) {
  fail('Usage: harvest.cjs search|search-multi|replies|followers ...');
}
let RUNTIME;
try { RUNTIME = prepareXFacingRuntime(process.env); }
catch (error) { console.error(`FATAL: ${error.message}`); process.exit(2); }

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

// Search backoff applies only to latency/no-content/generic-error recovery. A real HTTP 429
// returns immediately and is handed to the orchestrator cooldown without navigation replay.
const SEARCH_BACKOFF_BASE = parseInt(process.env.SEARCH_BACKOFF_BASE || '45000', 10);
const SEARCH_RETRIES = parseInt(process.env.SEARCH_RETRIES || '3', 10);

async function harvestOne(page, target, confirmAuthentication) {
  process.stderr.write(`[harvest] ${mode}: ${target.url}\n`);
  const isSearch = mode === 'search' || mode === 'search-multi';
  const navOpts = isSearch
    ? { needSel, settle: 5000, retries: SEARCH_RETRIES, backoffBase: SEARCH_BACKOFF_BASE }
    : { needSel, settle: 5000, retries: 4 };
  const nav = await gotoRobust(page, target.url, navOpts);
  if (nav.reason === 'RATE_LIMIT') {
    await confirmAuthentication(page, { expectedPath: new URL(target.url).pathname });
    process.stderr.write(`[harvest] HTTP 429 evidence (${target.label}): ${nav.responseUrl || target.url}\n`);
    return { ok: false, items: [], rl: true, reason: 'RATE_LIMIT' };
  }
  if (nav.reason === 'LOGIN_REDIRECT') throw new XAuthenticationError(`harvest requires login: ${page.url()}`, nav);
  await confirmAuthentication(page, { expectedPath: new URL(target.url).pathname });
  if (!nav.ok) {
    process.stderr.write(`[harvest] ${nav.reason || 'navigation failure'} after ${nav.attempts} attempts (${target.label}); no HTTP 429 observed\n`);
    return { ok: false, items: [], rl: false, reason: nav.reason || 'NO_CONTENT' };
  }
  await page.waitForTimeout(1500);
  const observed = await captureXResponseEvidence(page, () => page.evaluate(EXTRACT_JS));
  if (observed.evidence?.reason === 'RATE_LIMIT') {
    process.stderr.write(`[harvest] HTTP 429 evidence while scrolling (${target.label}): ${observed.evidence.responseUrl}\n`);
    return { ok: false, items: [], rl: true, reason: 'RATE_LIMIT' };
  }
  if (observed.evidence?.reason === 'LOGIN_REDIRECT') {
    throw new XAuthenticationError(`harvest lost authentication while scrolling: ${page.url()}`, observed.evidence);
  }
  const result = observed.value;
  process.stderr.write(`[harvest] ${target.label}: collected ${result.count}\n`);
  return { ok: true, items: result.items, rl: false };
}

async function runSession({ context, confirmAuthenticated }, sessionTargets, pacingMs, pacingJitter) {
  const page = context.pages()[0] || await context.newPage();
  const results = [];
  let authenticationConfirmed = false;
  const confirm = async (targetPage, options) => {
    if (authenticationConfirmed) return;
    await confirmAuthenticated(targetPage, options);
    authenticationConfirmed = true;
  };
  for (let index = 0; index < sessionTargets.length; index += 1) {
    results.push({ target: sessionTargets[index], result: await harvestOne(page, sessionTargets[index], confirm) });
    if (results.at(-1).result.rl) break;
    if (index < sessionTargets.length - 1) await sleep(pacingMs + Math.floor(Math.random() * pacingJitter));
  }
  return results;
}

async function main() {
  // Network pacing/session knobs (see header). search-multi splits queries across short sessions;
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
  const batchSize = isSearchMulti ? Math.max(1, SESSION_SIZE) : 1;
  let aborted = false;
  for (let offset = 0; offset < targets.length && !aborted; offset += batchSize) {
    const sessionTargets = targets.slice(offset, offset + batchSize);
    const sessionResults = await withAuthenticatedContext(
      { config: RUNTIME.browser, headless: false, width: 1280, height: 820 },
      (api) => runSession(api, sessionTargets, PACING_MS, PACING_JITTER),
    );
    for (const { target: tg, result: r } of sessionResults) {
      if (r.ok) { anyOk = true; consecFail = 0; }
      else { rateLimited = rateLimited || Boolean(r.rl); consecFail += 1; }
      let added = 0;
      for (const it of r.items) {
        const ex = merged.get(it.handle);
        if (!ex) { merged.set(it.handle, it); added += 1; }
        else if (it.blue && !ex.blue) ex.blue = true;
      }
      perQuery[tg.label] = (perQuery[tg.label] || 0) + added;
      if (r.rl) {
        process.stderr.write('[harvest] real HTTP 429 — aborting round for orchestrator cooldown\n');
        aborted = true;
        break;
      }
      if (consecFail >= 2) {
        process.stderr.write('[harvest] 2 consecutive generic navigation failures — aborting round without claiming HTTP 429\n');
        aborted = true;
        break;
      }
    }
    if (!aborted && offset + batchSize < targets.length) {
      const seconds = Math.round(SESSION_COOLDOWN_MS / 1000);
      process.stderr.write(`[harvest] session full (${sessionTargets.length} queries) — CDP close + cooldown ${seconds}s + relaunch\n`);
      await sleep(SESSION_COOLDOWN_MS);
    }
  }

  if (!anyOk && merged.size === 0) {
    console.log(JSON.stringify({ count: 0, error: rateLimited ? 'http_429' : 'page_error_after_retries', items: [], rateLimited }, null, 2));
    return;
  }
  const items = Array.from(merged.values());
  console.log(JSON.stringify({ count: items.length, items, perQuery, rateLimited }, null, 2));
}

main().catch((error) => {
  console.error('FATAL', error.message || error);
  if (error instanceof BrowserConfigError) process.exitCode = 2;
  else if (error instanceof XAuthenticationError) process.exitCode = 12;
  else if (Number.isInteger(error.exitCode)) process.exitCode = error.exitCode;
  else process.exitCode = 99;
});
