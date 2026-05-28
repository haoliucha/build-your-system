#!/usr/bin/env node
// snapshot-following.cjs — 抓取某 handle 的 /following 列表(通常是自己,用于 pre-filter)
// Usage: node snapshot-following.cjs <handle>
// Env: PROFILE_DIR (默认 ~/.config/playwright-chrome-profile-campaign)
// Output: stdout JSON {count, handles: [string]}

const { chromium } = require('playwright');

const PROFILE_DIR = process.env.PROFILE_DIR || `${process.env.HOME}/.config/playwright-chrome-profile-campaign`;

const handle = process.argv[2];
if (!handle) {
  console.error('Usage: node snapshot-following.cjs <handle>');
  console.error('Example: node snapshot-following.cjs haoliucha');
  process.exit(2);
}

// Aggressive scroll until exhausted (handle 关注列表可能很长)
const EXTRACT_JS = `(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const collected = new Set();

  const extract = () => {
    const cells = document.querySelectorAll('button[data-testid="UserCell"], div[data-testid="UserCell"]');
    for (const cell of cells) {
      const a = cell.querySelector('a[href^="/"]');
      if (!a) continue;
      const m = a.getAttribute('href').match(/^\\/([A-Za-z0-9_]+)$/);
      if (m) collected.add(m[1]);
    }
  };

  let stall = 0, prev = -1;
  for (let i = 0; i < 200; i++) {  // 200 scrolls max — supports ~10000 following
    extract();
    if (collected.size === prev) {
      stall++;
      if (stall > 6) break;
    } else {
      stall = 0;
      prev = collected.size;
    }
    window.scrollBy(0, 1800);
    await sleep(700);
  }
  extract();
  return { count: collected.size, handles: Array.from(collected) };
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
  const url = `https://x.com/${handle}/following`;
  process.stderr.write(`[snapshot-following] navigating to ${url}\n`);
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 });
  await page.waitForTimeout(2500);

  const result = await page.evaluate(EXTRACT_JS);
  process.stderr.write(`[snapshot-following] @${handle} follows ${result.count} accounts\n`);

  console.log(JSON.stringify(result, null, 2));

  await ctx.close();
}

main().catch(e => { console.error('FATAL', e); process.exit(99); });
