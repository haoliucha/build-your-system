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
const { writeAlertWithEvidence } = require(path.join(__dirname, 'lib', 'anomaly.cjs'));
const { captureXResponseEvidence, gotoRobust } = require(path.join(__dirname, 'lib', 'nav-helper.cjs'));
const { createProfilePacer } = require(path.join(__dirname, 'lib', 'profile-pacer.cjs'));
const { prepareXFacingRuntime } = require(path.join(__dirname, 'lib', 'runtime-gate.cjs'));
const { BrowserConfigError, withAuthenticatedContext, XAuthenticationError } = require(path.join(__dirname, 'lib', 'cdp-browser.cjs'));

const PROFILE_DIR = process.env.PROFILE_DIR || `${process.env.HOME}/.config/playwright-chrome-profile-campaign`;
let RUNTIME;
try { RUNTIME = prepareXFacingRuntime(process.env); }
catch (error) { console.error(`FATAL: ${error.message}`); process.exit(2); }
const TRACKER_PATH = RUNTIME.state.trackerPath;
const FIX_TRACKER = process.env.FIX_TRACKER === '1';
const argv = process.argv.slice(2);
const PROFILE_PACER = createProfilePacer({
  statePath: RUNTIME.state.pacingPath,
  minIntervalMs: parseInt(process.env.PROFILE_VISIT_MIN_INTERVAL_MS || '90000', 10),
  maxIntervalMs: parseInt(process.env.PROFILE_VISIT_MAX_INTERVAL_MS || '150000', 10),
  maxVisitsPerHour: parseInt(process.env.MAX_PROFILE_VISITS_PER_HOUR || '30', 10),
  rateLimitCooldownMs: parseInt(process.env.RATE_LIMIT_COOLDOWN_MS || '1800000', 10),
  log: (message) => process.stderr.write(`[verify] ${message}\n`),
});

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
const EMPTY_AUTOMATIC_SELECTION = !handles.length && (argv[0] === '--assumed' || argv[0] === '--sample');
if (!handles.length && !EMPTY_AUTOMATIC_SELECTION) {
  console.error('No handles to verify (pass list, --assumed, or --sample N)');
  process.exit(2);
}

async function verify({ context, confirmAuthenticated }) {
  const page = context.pages()[0] || await context.newPage();
  const confirmed = [], failed = [];
  let authenticationConfirmed = false;
  let currentHandle = null;
  try {
  for (const h of handles) {
    currentHandle = h;
    await PROFILE_PACER.beforeVisit(h);
    const nav = await gotoRobust(page, `https://x.com/${h}`, { needSel: 'div[data-testid="UserName"]', settle: 3500, retries: 3 });
    if (nav.reason === 'RATE_LIMIT') throw Object.assign(new Error(`HTTP 429 ${nav.responseUrl || h}`), { exitCode: 11 });
    if (nav.reason === 'LOGIN_REDIRECT') throw new XAuthenticationError(`follow verification requires login: ${page.url()}`, nav);
    if (!authenticationConfirmed) {
      await confirmAuthenticated(page, { expectedPath: `/${h}` });
      authenticationConfirmed = true;
    }
    if (!nav.ok) throw Object.assign(new Error(`profile navigation failed at @${h}: ${nav.reason}`), { exitCode: 18 });
    const observed = await captureXResponseEvidence(page, async () => {
      await page.waitForTimeout(1000);
      return page.evaluate(() => ({
        following: !!document.querySelector('button[data-testid$="-unfollow"]'),
        notFollowing: !!document.querySelector('button[data-testid$="-follow"]'),
        exists: !!document.querySelector('div[data-testid="UserName"]'),
      }));
    });
    if (observed.evidence?.reason === 'RATE_LIMIT') throw Object.assign(new Error(`HTTP 429 ${observed.evidence.responseUrl}`), { exitCode: 11 });
    if (observed.evidence?.reason === 'LOGIN_REDIRECT') throw new XAuthenticationError(`follow verification lost authentication at @${h}`, observed.evidence);
    const st = observed.value;
    if (st.following) { confirmed.push(h); process.stderr.write(`@${h}: ✅ 正在关注\n`); }
    else { failed.push(h); process.stderr.write(`@${h}: ❌ NOT following (exists=${st.exists})\n`); }
    await page.waitForTimeout(1200);
  }
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
  } catch (error) {
    let type = 'UNEXPECTED_ERROR';
    if (error instanceof XAuthenticationError) type = 'LOGIN_REDIRECT';
    else if (error.exitCode === 11 || /HTTP 429/.test(error.message || '')) type = 'RATE_LIMIT';
    else if (error.exitCode === 18) type = 'GENERIC_NAV_ERROR';
    let rateLimitCooldownUntil = null;
    if (type === 'RATE_LIMIT') {
      rateLimitCooldownUntil = PROFILE_PACER.noteRateLimit({ handle: currentHandle, responseUrl: error.message });
    }
    await writeAlertWithEvidence(page, RUNTIME.state.alertPath, {
      type,
      text: error.message || String(error),
      handle: currentHandle,
      url: (() => { try { return page.url(); } catch { return null; } })(),
      profileDir: PROFILE_DIR,
      trackerPath: TRACKER_PATH,
      rateLimitCooldownUntil: rateLimitCooldownUntil?.cooldownUntil || null,
    });
    throw error;
  }
}

async function main() {
  if (EMPTY_AUTOMATIC_SELECTION) {
    console.log(JSON.stringify({ confirmed: [], failed: [], checked: 0 }, null, 2));
    return;
  }
  await PROFILE_PACER.beforeNetwork('follow verification');
  await withAuthenticatedContext(
    { config: RUNTIME.browser, headless: false, width: 1280, height: 820 },
    verify,
  );
}

main().catch((error) => {
  console.error('FATAL', error.message || error);
  if (error instanceof BrowserConfigError) process.exitCode = 2;
  else if (error instanceof XAuthenticationError) process.exitCode = 12;
  else if (Number.isInteger(error.exitCode)) process.exitCode = error.exitCode;
  else process.exitCode = 99;
});
