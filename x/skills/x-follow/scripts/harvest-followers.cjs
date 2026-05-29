#!/usr/bin/env node
// harvest-followers.cjs — 从某用户的 /followers 或 /following 提取候选 handles
// Usage: node harvest-followers.cjs <handle> <followers|following> [--scrolls 30]
// Env: PROFILE_DIR (默认 ~/.config/playwright-chrome-profile-campaign)
// Output: stdout JSON {total, blueCount, handles: [string]}

const { chromium } = require('playwright');

const PROFILE_DIR = process.env.PROFILE_DIR || `${process.env.HOME}/.config/playwright-chrome-profile-campaign`;

const argv = process.argv.slice(2);
const handle = argv[0];
const type = argv[1];
if (!handle || (type !== 'followers' && type !== 'following')) {
  console.error('Usage: node harvest-followers.cjs <handle> <followers|following> [--scrolls N]');
  console.error('Example: node harvest-followers.cjs lanchen4588 followers');
  process.exit(2);
}
const scrollsArg = argv.indexOf('--scrolls');
const SCROLLS = scrollsArg !== -1 ? parseInt(argv[scrollsArg + 1], 10) : 30;

const EXTRACT_JS = `(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const collected = new Map();
  const SCROLLS = ${SCROLLS};

  const extract = () => {
    const cells = document.querySelectorAll('button[data-testid="UserCell"], div[data-testid="UserCell"]');
    for (const cell of cells) {
      const a = cell.querySelector('a[href^="/"]');
      if (!a) continue;
      const m = a.getAttribute('href').match(/^\\/([A-Za-z0-9_]+)$/);
      if (!m) continue;
      const handle = m[1];
      const blue = !!cell.querySelector('svg[aria-label="认证账号"]');
      const displayName = cell.querySelector('div[dir="ltr"] span, span[dir="ltr"]')?.innerText?.slice(0,60) || '';
      if (!collected.has(handle)) collected.set(handle, { handle, displayName, blue });
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
    window.scrollBy(0, 1500);
    await sleep(700);
  }
  extract();
  const all = Array.from(collected.values());
  const blueOnly = all.filter(x => x.blue);
  return { total: all.length, blueCount: blueOnly.length, handles: blueOnly.map(x => x.handle), items: blueOnly };
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
  const url = `https://x.com/${handle}/${type}`;
  process.stderr.write(`[harvest-followers] navigating to ${url}\n`);
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 });
  await page.waitForTimeout(2500);

  const result = await page.evaluate(EXTRACT_JS);
  process.stderr.write(`[harvest-followers] collected ${result.total} (blue ${result.blueCount}) from /${handle}/${type}\n`);

  console.log(JSON.stringify(result, null, 2));

  await ctx.close();
}

main().catch(e => { console.error('FATAL', e); process.exit(99); });
