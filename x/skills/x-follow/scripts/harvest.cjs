#!/usr/bin/env node
// harvest.cjs — unified, latency/429-tolerant candidate harvester (replaces the old
// harvest-search / harvest-replies / harvest-followers trio).
//
// Usage:
//   node harvest.cjs search   "<query>"           [scrolls] [--tab live|top]
//   node harvest.cjs replies  "<statusUrl>"       [scrolls]
//   node harvest.cjs followers "<handle>" "<followers|following>" [scrolls]
// Env: PROFILE_DIR (default ~/.config/playwright-chrome-profile-campaign)
// Output: stdout JSON { count, items:[{handle, displayName, blue, text}] }  (or {count:0,error} on nav failure)
//
// All navigation goes through gotoRobust so HTTP 429 ("出错了") and slow VPN renders are
// handled by exponential backoff rather than retry-hammering.

const path = require('path');
const { chromium } = require('playwright');
const { gotoRobust } = require(path.join(__dirname, 'lib', 'nav-helper.cjs'));

const PROFILE_DIR = process.env.PROFILE_DIR || `${process.env.HOME}/.config/playwright-chrome-profile-campaign`;
const argv = process.argv.slice(2);
const mode = argv[0];

function fail(msg) { console.error(msg); process.exit(2); }
if (!['search', 'replies', 'followers'].includes(mode)) {
  fail('Usage: harvest.cjs search|replies|followers ...');
}

let url, needSel, scrolls, extractKind;
if (mode === 'search') {
  const query = argv[1];
  if (!query) fail('search needs a query');
  const tabArg = argv.indexOf('--tab');
  const tab = tabArg !== -1 ? argv[tabArg + 1] : 'live';
  scrolls = parseInt(argv[2] && /^\d+$/.test(argv[2]) ? argv[2] : '20', 10);
  url = `https://x.com/search?q=${encodeURIComponent(query)}&src=typed_query&f=${tab}`;
  needSel = 'article[role="article"]';
  extractKind = 'article';
} else if (mode === 'replies') {
  url = argv[1];
  if (!url || !url.includes('/status/')) fail('replies needs a status URL');
  scrolls = parseInt(argv[2] && /^\d+$/.test(argv[2]) ? argv[2] : '25', 10);
  needSel = 'article[role="article"]';
  extractKind = 'article';
} else {
  const handle = argv[1], type = argv[2];
  if (!handle || (type !== 'followers' && type !== 'following')) fail('followers needs <handle> <followers|following>');
  scrolls = parseInt(argv[3] && /^\d+$/.test(argv[3]) ? argv[3] : '25', 10);
  url = `https://x.com/${handle}/${type}`;
  needSel = '[data-testid="UserCell"]';
  extractKind = 'usercell';
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

async function main() {
  const ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
    channel: 'chrome', headless: false, viewport: { width: 1280, height: 820 },
    ignoreDefaultArgs: ['--enable-automation'], args: ['--disable-blink-features=AutomationControlled'],
  });
  const page = ctx.pages()[0] || await ctx.newPage();
  process.stderr.write(`[harvest] ${mode}: ${url}\n`);
  const nav = await gotoRobust(page, url, { needSel, settle: 5000, retries: 4 });
  if (!nav.ok) {
    process.stderr.write(`[harvest] page error after ${nav.attempts} retries\n`);
    console.log(JSON.stringify({ count: 0, error: 'page_error_after_retries', items: [] }, null, 2));
    await ctx.close();
    return;
  }
  await page.waitForTimeout(1500);
  const result = await page.evaluate(EXTRACT_JS);
  process.stderr.write(`[harvest] collected ${result.count}\n`);
  console.log(JSON.stringify(result, null, 2));
  await ctx.close();
}

main().catch(e => { console.error('FATAL', e); process.exit(99); });
