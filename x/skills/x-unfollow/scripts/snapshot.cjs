#!/usr/bin/env node
// snapshot.cjs — capture the accounts MY_HANDLE follows that do NOT follow back
// (non-reciprocal), into a dated JSONL snapshot. Cross-day snapshots accumulate so
// classify.cjs can compute "days not following back".
//
// Ported from the Codex follow-cleanup.cjs scraper, hardened for this skill:
//   - handle is parameterized via MY_HANDLE (no hardcoded account)
//   - navigation goes through gotoRobust (HTTP 429 / VPN-latency tolerant)
//   - anomaly gate (CAPTCHA / rate-limit / login / restricted) -> ALERT.txt + nonzero exit
//   - state lives under XU_DATA_DIR/snapshots (no vault coupling)
//
// Usage:
//   MY_HANDLE=you NODE_PATH=~/.config/playwright-mcp-server/node_modules node snapshot.cjs [--limit=N]
// Env: MY_HANDLE (required), PROFILE_DIR, XU_DATA_DIR, ALERT_PATH, SNAPSHOT_DATE (YYYY-MM-DD)
// Output: stdout JSON { date, handle, count, file }; writes XU_DATA_DIR/snapshots/<date>.jsonl
//
// NOTE: per-row follower counts from the /following list are rough (X renders them
// inconsistently). They are only used for a coarse MAX_FOLLOWERS pre-filter; the
// authoritative count comes later from profile-counts.cjs.

const fs = require('fs');
const path = require('path');
const os = require('os');
const { chromium } = require('playwright');
const { gotoRobust } = require(path.join(__dirname, 'lib', 'nav-helper.cjs'));
const { detectAnomaly, writeAlert, EXIT_CODES } = require(path.join(__dirname, 'lib', 'anomaly.cjs'));
const { todayInShanghai } = require(path.join(__dirname, 'lib', 'hygiene.cjs'));

const HANDLE = (process.env.MY_HANDLE || '').replace(/^@/, '').trim();
const PROFILE_DIR = process.env.PROFILE_DIR || path.join(os.homedir(), '.config/playwright-chrome-profile-campaign');
const DATA_DIR = process.env.XU_DATA_DIR || path.join(os.homedir(), '.config/x-unfollow-data');
const SNAP_DIR = path.join(DATA_DIR, 'snapshots');
const ALERT_PATH = process.env.ALERT_PATH || path.join(DATA_DIR, 'ALERT.txt');
const DATE = process.env.SNAPSHOT_DATE || todayInShanghai();

const MAX_FOLLOWERS = parseInt(process.env.MAX_FOLLOWERS || '20000', 10);
const MAX_SCROLL_ROUNDS = parseInt(process.env.MAX_SCROLL_ROUNDS || '120', 10);
const SCROLL_WAIT_MS = parseInt(process.env.SCROLL_WAIT_MS || '900', 10);
const SCROLL_IDLE_LIMIT = parseInt(process.env.SCROLL_IDLE_LIMIT || '5', 10);
const LIMIT = parseInt((process.argv.find((a) => a.startsWith('--limit=')) || '').split('=')[1] || '0', 10);

if (!HANDLE) { console.error('FATAL: MY_HANDLE env var required (your X handle, no @)'); process.exit(2); }
function ensureDir(p) { if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true }); }

// Extraction runs inside the page; parseNum is defined INLINE so it actually resolves
// in browser context (the original module-scope version silently failed there).
const EXTRACT_JS = `(async (MAX_ROUNDS, WAIT_MS, IDLE_LIMIT, MAX_FOLLOWERS) => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const parseNum = (s) => {
    if (!s) return 0;
    s = String(s).trim().replace(/[,，]/g, '');
    if (/^\\d+$/.test(s)) return parseInt(s, 10);
    const m = s.match(/^([\\d.]+)\\s*([KMB万千]?)$/i);
    if (!m) return 0;
    let n = parseFloat(m[1]); const u = (m[2] || '').toUpperCase();
    if (u === 'K') n *= 1e3; else if (u === 'M') n *= 1e6; else if (u === 'B') n *= 1e9;
    else if (u === '万') n *= 1e4; else if (u === '千') n *= 1e3;
    return Math.round(n);
  };
  const out = new Map();
  const extractBatch = () => {
    const rows = document.querySelectorAll('div[role="listitem"], div[data-testid*="User"], article, div.css-175oi2r');
    const found = [];
    for (const row of rows) {
      try {
        const text = row.innerText || '';
        if (!text || text.length < 10) continue;
        let handle = null;
        for (const a of row.querySelectorAll('a[href^="/"][role="link"]')) {
          const h = (a.getAttribute('href') || '').replace(/^\\//, '').split('/')[0];
          if (/^[A-Za-z0-9_]{1,15}$/.test(h) && h !== 'home' && h !== 'explore') { handle = h; break; }
        }
        if (!handle) continue;
        const isFollowingMe = /Follows you|关注了你|关注你/.test(text);
        let followers = 0;
        for (const s of row.querySelectorAll('span')) {
          const t = (s.innerText || '').trim();
          if (/[\\d.,]+\\s*(K|M|B|万|千)?\\s*(followers?|关注者)/i.test(t)) { followers = parseNum(t); break; }
        }
        if (!followers) { const m = text.match(/([\\d.,]+[KMB万]?)\\s*(关注者|followers?)/i); if (m) followers = parseNum(m[1]); }
        const name = (row.querySelector('div[dir="ltr"]')?.innerText || '').split('\\n')[0].trim() || handle;
        found.push({ handle, name, followers, isFollowingMe });
      } catch (e) {}
    }
    return found;
  };

  let idle = 0, prevSize = 0;
  for (let round = 0; round < MAX_ROUNDS; round++) {
    for (const r of extractBatch()) {
      if (r.followers <= MAX_FOLLOWERS && r.isFollowingMe === false) out.set(r.handle, r);
    }
    if (out.size === prevSize) idle++; else idle = 0;
    prevSize = out.size;
    if (idle >= IDLE_LIMIT) break;
    window.scrollBy(0, window.innerHeight * 0.85);
    await sleep(WAIT_MS);
  }
  for (const r of extractBatch()) {
    if (r.followers <= MAX_FOLLOWERS && r.isFollowingMe === false) out.set(r.handle, r);
  }
  return Array.from(out.values());
})(${MAX_SCROLL_ROUNDS}, ${SCROLL_WAIT_MS}, ${SCROLL_IDLE_LIMIT}, ${MAX_FOLLOWERS})`;

async function main() {
  ensureDir(SNAP_DIR);
  process.stderr.write(`[snapshot] @${HANDLE} /following  date=${DATE}  maxFollowers=${MAX_FOLLOWERS}\n`);

  const ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
    channel: 'chrome', headless: false, viewport: { width: 1400, height: 1000 },
    ignoreDefaultArgs: ['--enable-automation'], args: ['--disable-blink-features=AutomationControlled'],
  });
  const page = ctx.pages()[0] || await ctx.newPage();

  const nav = await gotoRobust(page, `https://x.com/${HANDLE}/following`, {
    needSel: '[data-testid="UserCell"], [data-testid="primaryColumn"]', settle: 5000, retries: 4,
  });

  const anomaly = await detectAnomaly(page);
  if (anomaly && anomaly.type !== 'EVAL_ERROR' && anomaly.type !== 'EMPTY_PAGE') {
    writeAlert(ALERT_PATH, { ...anomaly, handle: HANDLE, url: page.url(), profileDir: PROFILE_DIR, dataDir: DATA_DIR });
    process.stderr.write(`[snapshot] ANOMALY ${anomaly.type} — see ${ALERT_PATH}\n`);
    await ctx.close();
    process.exit(EXIT_CODES[anomaly.type] || 99);
  }
  if (!nav.ok) {
    writeAlert(ALERT_PATH, { type: 'LOGIN_REDIRECT', text: '/following did not render', handle: HANDLE, url: page.url(), profileDir: PROFILE_DIR, dataDir: DATA_DIR });
    process.stderr.write(`[snapshot] /following did not render after ${nav.attempts} attempts (login expired?) — see ${ALERT_PATH}\n`);
    await ctx.close();
    process.exit(EXIT_CODES.LOGIN_REDIRECT);
  }

  await page.waitForTimeout(1500);
  let rows = await page.evaluate(EXTRACT_JS);
  await ctx.close();
  if (LIMIT > 0) rows = rows.slice(0, LIMIT);

  const file = path.join(SNAP_DIR, `${DATE}.jsonl`);
  const lines = rows.map((r) => JSON.stringify({
    handle: r.handle, name: r.name, followers: r.followers, isFollowingMe: false, extractedAt: new Date().toISOString(),
  }));
  fs.writeFileSync(file, lines.join('\n') + (lines.length ? '\n' : ''), 'utf8');
  process.stderr.write(`[snapshot] wrote ${rows.length} non-recip rows -> ${file}\n`);
  console.log(JSON.stringify({ date: DATE, handle: HANDLE, count: rows.length, file }, null, 2));
}

main().catch((e) => { console.error('FATAL', e.stack || e); process.exit(99); });
