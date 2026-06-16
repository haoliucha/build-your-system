#!/usr/bin/env node
// snapshot-following.cjs — capture a handle's /following list (usually your own, for pre-filter).
// Usage: node snapshot-following.cjs <handle>
// Env: PROFILE_DIR (default ~/.config/playwright-chrome-profile-campaign)
// Output: stdout JSON { count, handles: [string] }
//
// FIX (was returning 0): the original gave up before /following rendered. Now we
// gotoRobust + waitForSelector('[data-testid="UserCell"]') BEFORE scrolling, extract the
// handle from the UserAvatar-Container-{handle} testid (more reliable than the row link),
// and exclude self.

const path = require('path');
const { chromium } = require('playwright');
const { gotoRobust } = require(path.join(__dirname, 'lib', 'nav-helper.cjs'));

const PROFILE_DIR = process.env.PROFILE_DIR || `${process.env.HOME}/.config/playwright-chrome-profile-campaign`;
const handle = process.argv[2];
if (!handle) {
  console.error('Usage: node snapshot-following.cjs <handle>  (e.g. haoliucha)');
  process.exit(2);
}

const EXTRACT_JS = `(async (me) => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const collected = new Set();
  const meLower = (me || '').toLowerCase();

  const extract = () => {
    for (const cell of document.querySelectorAll('[data-testid="UserCell"]')) {
      // Prefer the avatar-container testid: UserAvatar-Container-{handle}
      let h = null;
      const av = cell.querySelector('[data-testid^="UserAvatar-Container-"]');
      if (av) {
        const m = (av.getAttribute('data-testid') || '').match(/^UserAvatar-Container-(.+)$/);
        if (m) h = m[1];
      }
      if (!h) {
        const a = cell.querySelector('a[href^="/"]');
        const m = a && (a.getAttribute('href') || '').match(/^\\/([A-Za-z0-9_]+)$/);
        if (m) h = m[1];
      }
      if (h && h.toLowerCase() !== meLower) collected.add(h);
    }
  };

  let stall = 0, prev = -1;
  for (let i = 0; i < 200; i++) {  // up to ~10000 following
    extract();
    if (collected.size === prev) { stall++; if (stall > 6) break; } else { stall = 0; prev = collected.size; }
    window.scrollBy(0, 1800);
    await sleep(800);
  }
  extract();
  return { count: collected.size, handles: Array.from(collected) };
})(${JSON.stringify(handle)})`;

async function main() {
  const ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
    channel: 'chrome', headless: false, viewport: { width: 1280, height: 820 },
    ignoreDefaultArgs: ['--enable-automation'], args: ['--disable-blink-features=AutomationControlled'],
  });
  const page = ctx.pages()[0] || await ctx.newPage();
  const url = `https://x.com/${handle}/following`;
  process.stderr.write(`[snapshot-following] navigating to ${url}\n`);

  // Wait for the list to actually render before scrolling (the original "returns 0" bug).
  const nav = await gotoRobust(page, url, { needSel: '[data-testid="UserCell"]', settle: 5000, retries: 4 });
  if (!nav.ok) {
    process.stderr.write(`[snapshot-following] /following did not render after ${nav.attempts} attempts\n`);
    console.log(JSON.stringify({ count: 0, handles: [], error: 'no_render' }, null, 2));
    await ctx.close();
    return;
  }
  await page.waitForTimeout(1500);

  const result = await page.evaluate(EXTRACT_JS);
  process.stderr.write(`[snapshot-following] @${handle} follows ${result.count} accounts\n`);
  console.log(JSON.stringify(result, null, 2));
  await ctx.close();
}

main().catch(e => { console.error('FATAL', e); process.exit(99); });
