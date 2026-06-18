#!/usr/bin/env node
// verify-unfollow.cjs — read-only confirmation that targets are no longer followed.
//
// WHY: unfollow.cjs marks 'unfollow_assumed' when the button didn't visibly flip within
// the settle window. This re-opens each target and checks for the exact unfollow button:
// absent => not_following (success). Stragglers get one retry of re-verification.
//
// Usage:
//   node verify-unfollow.cjs [--date=YYYY-MM-DD]      # verify all unfollow-<date>.json results
//   node verify-unfollow.cjs --unconfirmed [--date=]  # only 'unfollow_assumed' rows
//   node verify-unfollow.cjs --handles=a,b,c
// Env: PROFILE_DIR, XU_DATA_DIR
// Output: stdout JSON { date, results:[{handle, not_following, exists}], counts };
//         writes XU_DATA_DIR/reports/verify-unfollow-<date>.json

const fs = require('fs');
const path = require('path');
const os = require('os');
const { chromium } = require('playwright');
const { gotoRobust } = require(path.join(__dirname, 'lib', 'nav-helper.cjs'));
const { todayInShanghai } = require(path.join(__dirname, 'lib', 'hygiene.cjs'));

const PROFILE_DIR = process.env.PROFILE_DIR || path.join(os.homedir(), '.config/playwright-chrome-profile-campaign');
const DATA_DIR = process.env.XU_DATA_DIR || path.join(os.homedir(), '.config/x-unfollow-data');
const REPORTS_DIR = path.join(DATA_DIR, 'reports');

const argv = process.argv.slice(2);
const DATE = (argv.find((a) => a.startsWith('--date=')) || '').split('=')[1] || todayInShanghai();
const ONLY_UNCONFIRMED = argv.includes('--unconfirmed');
const HANDLES_ARG = (argv.find((a) => a.startsWith('--handles=')) || '').split('=')[1] || '';

function ensureDir(p) { if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true }); }

function loadHandles() {
  if (HANDLES_ARG) return HANDLES_ARG.split(',').map((s) => s.trim().replace(/^@/, '')).filter(Boolean);
  const file = path.join(REPORTS_DIR, `unfollow-${DATE}.json`);
  if (!fs.existsSync(file)) { console.error(`FATAL: unfollow log not found: ${file}`); process.exit(2); }
  const obj = JSON.parse(fs.readFileSync(file, 'utf8'));
  let rows = (obj.results || []).filter((r) => r.action === 'unfollowed' || r.action === 'unfollow_assumed');
  if (ONLY_UNCONFIRMED) rows = rows.filter((r) => r.action === 'unfollow_assumed');
  return [...new Set(rows.map((r) => r.handle))];
}

// not_following == no unfollow button whose @-token equals the exact handle.
async function checkHandle(page, h) {
  await gotoRobust(page, `https://x.com/${h}`, { needSel: 'div[data-testid="UserName"]', settle: 3500, retries: 3 });
  await page.waitForTimeout(1000);
  return await page.evaluate((H) => {
    const exists = !!document.querySelector('div[data-testid="UserName"]');
    const stillUnfollow = [...document.querySelectorAll('button[data-testid$="-unfollow"]')].some((b) => {
      const m = (b.getAttribute('aria-label') || '').match(/@([A-Za-z0-9_]+)/);
      return m && m[1].toLowerCase() === H.toLowerCase();
    });
    return { exists, not_following: !stillUnfollow };
  }, h);
}

async function main() {
  ensureDir(REPORTS_DIR);
  const handles = loadHandles();
  if (!handles.length) { console.log(JSON.stringify({ date: DATE, results: [], counts: {} }, null, 2)); return; }

  const ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
    channel: 'chrome', headless: false, viewport: { width: 1280, height: 820 },
    ignoreDefaultArgs: ['--enable-automation'], args: ['--disable-blink-features=AutomationControlled'],
  });
  const page = ctx.pages()[0] || await ctx.newPage();

  const results = [];
  for (const h of handles) {
    let st;
    try { st = await checkHandle(page, h); } catch (e) { st = { exists: false, not_following: false, error: e.message }; }
    // One retry for stragglers that still show following.
    if (!st.not_following && !st.error) { await page.waitForTimeout(1500); try { st = await checkHandle(page, h); } catch (e) { st.error = e.message; } }
    results.push({ handle: h, ...st });
    process.stderr.write(`@${h}: ${st.not_following ? '✅ not following' : '❌ still following'} (exists=${st.exists})\n`);
    await page.waitForTimeout(1000);
  }
  await ctx.close();

  fs.writeFileSync(path.join(REPORTS_DIR, `verify-unfollow-${DATE}.json`), JSON.stringify({ date: DATE, generatedAt: new Date().toISOString(), results }, null, 2) + '\n');
  const counts = { checked: results.length, not_following: results.filter((r) => r.not_following).length, still_following: results.filter((r) => !r.not_following).length };
  console.log(JSON.stringify({ date: DATE, results, counts }, null, 2));
}

main().catch((e) => { console.error('FATAL', e.message); process.exit(99); });
