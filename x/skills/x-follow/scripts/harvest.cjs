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
// PERF: `search-multi` runs ALL queries inside ONE browser context (one launch / one close)
// instead of cold-starting Chrome per query. This cuts startup cost ~6x AND avoids the 429
// storm that back-to-back launches provoke (each fresh session = a new burst of requests).
//
// All navigation goes through gotoRobust so HTTP 429 ("出错了") and slow VPN renders are
// handled by exponential backoff rather than retry-hammering.

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

async function harvestOne(page, target) {
  process.stderr.write(`[harvest] ${mode}: ${target.url}\n`);
  const nav = await gotoRobust(page, target.url, { needSel, settle: 5000, retries: 4 });
  if (!nav.ok) {
    process.stderr.write(`[harvest] page error after ${nav.attempts} retries (${target.label})\n`);
    return { ok: false, items: [] };
  }
  await page.waitForTimeout(1500);
  const result = await page.evaluate(EXTRACT_JS);
  process.stderr.write(`[harvest] ${target.label}: collected ${result.count}\n`);
  return { ok: true, items: result.items };
}

async function main() {
  const ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
    channel: 'chrome', headless: false, viewport: { width: 1280, height: 820 },
    ignoreDefaultArgs: ['--enable-automation'], args: ['--disable-blink-features=AutomationControlled'],
  });
  const page = ctx.pages()[0] || await ctx.newPage();

  // Merge all targets into ONE deduped item map (handle-keyed). The first time we see a
  // handle wins — and we OR the blue flag so a verified sighting in any query sticks.
  const merged = new Map();
  const perQuery = {};
  let anyOk = false;
  for (let t = 0; t < targets.length; t++) {
    const tg = targets[t];
    const r = await harvestOne(page, tg);
    if (r.ok) anyOk = true;
    let added = 0;
    for (const it of r.items) {
      const ex = merged.get(it.handle);
      if (!ex) { merged.set(it.handle, it); added++; }
      else if (it.blue && !ex.blue) ex.blue = true;  // verified sighting wins
    }
    perQuery[tg.label] = (perQuery[tg.label] || 0) + added;
    // gentle pacing between queries inside the same session (skip after the last one)
    if (t < targets.length - 1) await sleep(6000);
  }

  await ctx.close();

  if (!anyOk && merged.size === 0) {
    console.log(JSON.stringify({ count: 0, error: 'page_error_after_retries', items: [] }, null, 2));
    return;
  }
  const items = Array.from(merged.values());
  console.log(JSON.stringify({ count: items.length, items, perQuery }, null, 2));
}

main().catch(e => { console.error('FATAL', e); process.exit(99); });
