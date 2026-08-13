#!/usr/bin/env node
// verify-follows.cjs — read-only confirmation that followed accounts are truly 正在关注.
//
// WHY: campaign's 'followed_assumed' action is optimistic — under VPN latency the button
// sometimes doesn't flip before the verify window closes, and a fraction of those never
// actually registered. This script loads each profile and checks for the unfollow button
// (= following) vs a follow button (= NOT following), so a top-up pass can re-follow the
// stragglers and the final count is real.
//
// Usage:
//   node verify-follows.cjs handle1,handle2,...     # verify a specific list
//   node verify-follows.cjs --assumed               # verify all followed_assumed in tracker.json
//   node verify-follows.cjs --sample N              # verify N spread-sampled 'followed' + all assumed
// Env: PROFILE_DIR, TRACKER_PATH (default ./tracker.json), FIX_TRACKER=1 (demote failed from followed)
// Output: stdout JSON { confirmed:[...], failed:[...], checked:N }

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const { gotoRobust } = require(path.join(__dirname, 'lib', 'nav-helper.cjs'));

const PROFILE_DIR = process.env.PROFILE_DIR || `${process.env.HOME}/.config/playwright-chrome-profile-campaign`;
const TRACKER_PATH = process.env.TRACKER_PATH || path.resolve('tracker.json');
const FIX_TRACKER = process.env.FIX_TRACKER === '1';
const argv = process.argv.slice(2);

function loadTracker() { try { return JSON.parse(fs.readFileSync(TRACKER_PATH, 'utf8')); } catch { return null; } }

let handles = [];
if (argv[0] === '--assumed') {
  const t = loadTracker();
  handles = ((t && t.followed) || []).filter((x) => x.action === 'followed_assumed').map((x) => x.handle);
} else if (argv[0] === '--sample') {
  const n = parseInt(argv[1] || '10', 10);
  const t = loadTracker();
  const fol = ((t && t.followed) || []);
  const assumed = fol.filter((x) => x.action === 'followed_assumed').map((x) => x.handle);
  const confirmed = fol.filter((x) => x.action === 'followed').map((x) => x.handle);
  const pick = [];
  for (let i = 0; i < confirmed.length && pick.length < n; i += Math.max(1, Math.floor(confirmed.length / n))) pick.push(confirmed[i]);
  handles = [...new Set([...assumed, ...pick])];
} else if (argv[0]) {
  handles = argv[0].split(',').map((s) => s.trim()).filter(Boolean);
}
if (!handles.length) { console.error('No handles to verify (pass list, --assumed, or --sample N)'); process.exit(2); }

async function main() {
  const ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
    channel: 'chrome', headless: false, chromiumSandbox: true, viewport: { width: 1280, height: 820 },
    ignoreDefaultArgs: ['--enable-automation'], args: ['--disable-blink-features=AutomationControlled'],
  });
  const page = ctx.pages()[0] || await ctx.newPage();
  const confirmed = [], failed = [];
  for (const h of handles) {
    await gotoRobust(page, `https://x.com/${h}`, { needSel: 'div[data-testid="UserName"]', settle: 3500, retries: 3 });
    await page.waitForTimeout(1000);
    const st = await page.evaluate(() => ({
      following: !!document.querySelector('button[data-testid$="-unfollow"]'),
      notFollowing: !!document.querySelector('button[data-testid$="-follow"]'),
      exists: !!document.querySelector('div[data-testid="UserName"]'),
    }));
    if (st.following) { confirmed.push(h); process.stderr.write(`@${h}: ✅ 正在关注\n`); }
    else { failed.push(h); process.stderr.write(`@${h}: ❌ NOT following (exists=${st.exists})\n`); }
    await page.waitForTimeout(1200);
  }
  await ctx.close();

  // Optionally demote failed from followed so a top-up campaign re-attempts them.
  if (FIX_TRACKER && failed.length) {
    const t = loadTracker();
    if (t) {
      const bad = new Set(failed);
      const before = t.followed.length;
      t.followed = t.followed.filter((x) => !bad.has(x.handle));
      t.rejected = (t.rejected || []).filter((r) => !bad.has(r.h)); // keep them eligible
      fs.writeFileSync(TRACKER_PATH, JSON.stringify(t));
      process.stderr.write(`[verify] demoted ${before - t.followed.length} unconfirmed from followed (now ${t.followed.length})\n`);
    }
  }
  console.log(JSON.stringify({ confirmed, failed, checked: handles.length }, null, 2));
}

main().catch((e) => { console.error('FATAL', e.message); process.exit(99); });
