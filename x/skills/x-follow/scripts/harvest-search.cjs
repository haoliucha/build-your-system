#!/usr/bin/env node
// harvest-search.cjs — 从 X 搜索页提取候选 handles
// Usage: node harvest-search.cjs "蓝V互关" [--scrolls 30] [--tab live|top|user]
// Env: PROFILE_DIR (默认 ~/.config/playwright-chrome-profile-campaign)
// Output: stdout JSON {count, items:[{handle, displayName, blue, text}]}

const { chromium } = require('playwright');

const PROFILE_DIR = process.env.PROFILE_DIR || `${process.env.HOME}/.config/playwright-chrome-profile-campaign`;

const argv = process.argv.slice(2);
const query = argv[0];
if (!query) {
  console.error('Usage: node harvest-search.cjs "<query>" [--scrolls N] [--tab live|top|user]');
  process.exit(2);
}
const scrollsArg = argv.indexOf('--scrolls');
const SCROLLS = scrollsArg !== -1 ? parseInt(argv[scrollsArg + 1], 10) : 30;
const tabArg = argv.indexOf('--tab');
const TAB = tabArg !== -1 ? argv[tabArg + 1] : 'live';

const EXTRACT_JS = `(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const collected = new Map();
  const SCROLLS = ${SCROLLS};

  const extract = () => {
    const articles = document.querySelectorAll('article[role="article"]');
    for (const art of articles) {
      let handle = null;
      const allLinks = art.querySelectorAll('a[href^="/"]');
      for (const a of allLinks) {
        const href = a.getAttribute('href');
        const m = href.match(/^\\/([A-Za-z0-9_]+)(\\/.*)?$/);
        if (m && !['home','explore','notifications','i','search','compose','settings','messages','bookmarks','jobs','lists','communities','articles','premium','hashtag'].includes(m[1])) {
          if (!handle) handle = m[1];
        }
      }
      const nameEl = art.querySelector('div[data-testid="User-Name"]');
      const blue = !!(nameEl && nameEl.querySelector('svg[aria-label="认证账号"]'));
      const textEl = art.querySelector('div[data-testid="tweetText"]');
      const text = textEl ? textEl.innerText.slice(0, 120) : '';
      const displayName = nameEl ? nameEl.innerText.split('\\n')[0].slice(0, 60) : null;
      if (handle && !collected.has(handle)) collected.set(handle, { handle, displayName, blue, text });
    }
  };

  // Also try UserCell (for --tab=user)
  const extractUserCells = () => {
    const cells = document.querySelectorAll('button[data-testid="UserCell"], div[data-testid="UserCell"]');
    for (const cell of cells) {
      const a = cell.querySelector('a[href^="/"]');
      if (!a) continue;
      const m = a.getAttribute('href').match(/^\\/([A-Za-z0-9_]+)$/);
      if (!m) continue;
      const handle = m[1];
      const blue = !!cell.querySelector('svg[aria-label="认证账号"]');
      const displayName = cell.querySelector('div[dir="ltr"] span, span[dir="ltr"]')?.innerText?.slice(0,60) || '';
      if (!collected.has(handle)) collected.set(handle, { handle, displayName, blue, text: '' });
    }
  };

  let stall = 0, prev = -1;
  for (let i = 0; i < SCROLLS; i++) {
    extract();
    extractUserCells();
    if (collected.size === prev) {
      stall++;
      if (stall > 4) break;
    } else {
      stall = 0;
      prev = collected.size;
    }
    window.scrollBy(0, 2000);
    await sleep(1000);
  }
  extract();
  extractUserCells();
  return { count: collected.size, items: Array.from(collected.values()) };
})()`;

async function main() {
  const ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
    channel: 'chrome',
    headless: false,
    viewport: { width: 1280, height: 820 },
    ignoreDefaultArgs: ['--enable-automation'],
    args: ['--disable-blink-features=AutomationControlled'],
  });

  let page = ctx.pages()[0] || await ctx.newPage();
  const url = `https://x.com/search?q=${encodeURIComponent(query)}&src=typed_query&f=${TAB}`;
  process.stderr.write(`[harvest-search] navigating to ${url}\n`);
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 });
  await page.waitForTimeout(2500);

  const result = await page.evaluate(EXTRACT_JS);
  process.stderr.write(`[harvest-search] collected ${result.count} handles\n`);

  console.log(JSON.stringify(result, null, 2));

  await ctx.close();
}

main().catch(e => { console.error('FATAL', e); process.exit(99); });
