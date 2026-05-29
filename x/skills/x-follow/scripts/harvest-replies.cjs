#!/usr/bin/env node
// harvest-replies.cjs — 从某个帖子的回复区提取候选 handles
// Usage: node harvest-replies.cjs <statusUrl> [--scrolls 35]
//   statusUrl 例: https://x.com/SomeUser/status/1234567890
// Env: PROFILE_DIR (默认 ~/.config/playwright-chrome-profile-campaign)
// Output: stdout JSON {count, items:[{handle, displayName, blue, text}]}

const { chromium } = require('playwright');

const PROFILE_DIR = process.env.PROFILE_DIR || `${process.env.HOME}/.config/playwright-chrome-profile-campaign`;

const argv = process.argv.slice(2);
const statusUrl = argv[0];
if (!statusUrl || !statusUrl.includes('/status/')) {
  console.error('Usage: node harvest-replies.cjs <statusUrl> [--scrolls N]');
  console.error('Example: node harvest-replies.cjs "https://x.com/Ace_yexin/status/2059456728190869596"');
  process.exit(2);
}
const scrollsArg = argv.indexOf('--scrolls');
const SCROLLS = scrollsArg !== -1 ? parseInt(argv[scrollsArg + 1], 10) : 35;

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
      // Blue check MUST be scoped to User-Name to avoid OP badge pollution
      const nameEl = art.querySelector('div[data-testid="User-Name"]');
      const blue = !!(nameEl && nameEl.querySelector('svg[aria-label="认证账号"]'));
      const textEl = art.querySelector('div[data-testid="tweetText"]');
      const text = textEl ? textEl.innerText.slice(0, 120) : '';
      const displayName = nameEl ? nameEl.innerText.split('\\n')[0].slice(0, 60) : null;
      if (handle && !collected.has(handle)) collected.set(handle, { handle, displayName, blue, text });
    }
  };

  let stall = 0, prev = -1;
  for (let i = 0; i < SCROLLS; i++) {
    extract();
    if (collected.size === prev) {
      stall++;
      if (stall > 4) break;
    } else {
      stall = 0;
      prev = collected.size;
    }
    window.scrollBy(0, 1800);
    await sleep(900);
  }
  extract();
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
  process.stderr.write(`[harvest-replies] navigating to ${statusUrl}\n`);
  await page.goto(statusUrl, { waitUntil: 'domcontentloaded', timeout: 30_000 });
  await page.waitForTimeout(2500);

  const result = await page.evaluate(EXTRACT_JS);
  process.stderr.write(`[harvest-replies] collected ${result.count} handles\n`);

  console.log(JSON.stringify(result, null, 2));

  await ctx.close();
}

main().catch(e => { console.error('FATAL', e); process.exit(99); });
