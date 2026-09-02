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
const { writeAlertWithEvidence } = require(path.join(__dirname, 'lib', 'anomaly.cjs'));
const { captureXResponseEvidence, gotoRobust } = require(path.join(__dirname, 'lib', 'nav-helper.cjs'));
const { createProfilePacer } = require(path.join(__dirname, 'lib', 'profile-pacer.cjs'));
const { prepareXFacingRuntime } = require(path.join(__dirname, 'lib', 'runtime-gate.cjs'));
const { BrowserConfigError, withAuthenticatedContext, XAuthenticationError } = require(path.join(__dirname, 'lib', 'cdp-browser.cjs'));

const PROFILE_DIR = process.env.PROFILE_DIR || `${process.env.HOME}/.config/playwright-chrome-profile-campaign`;
const handle = process.argv[2];
if (!handle) {
  console.error('Usage: node snapshot-following.cjs <handle>  (e.g. haoliucha)');
  process.exit(2);
}
let RUNTIME;
try { RUNTIME = prepareXFacingRuntime(process.env); }
catch (error) { console.error(`FATAL: ${error.message}`); process.exit(2); }
const PROFILE_PACER = createProfilePacer({
  statePath: RUNTIME.state.pacingPath,
  minIntervalMs: parseInt(process.env.PROFILE_VISIT_MIN_INTERVAL_MS || '90000', 10),
  maxIntervalMs: parseInt(process.env.PROFILE_VISIT_MAX_INTERVAL_MS || '150000', 10),
  maxVisitsPerHour: parseInt(process.env.MAX_PROFILE_VISITS_PER_HOUR || '30', 10),
  rateLimitCooldownMs: parseInt(process.env.RATE_LIMIT_COOLDOWN_MS || '1800000', 10),
  log: (message) => process.stderr.write(`[snapshot-following] ${message}\n`),
});

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

async function snapshot({ context, confirmAuthenticated }) {
  const page = context.pages()[0] || await context.newPage();
  const url = `https://x.com/${handle}/following`;
  process.stderr.write(`[snapshot-following] navigating to ${url}\n`);
  try {

  // Wait for the list to actually render before scrolling (the original "returns 0" bug).
  const nav = await gotoRobust(page, url, { needSel: '[data-testid="UserCell"]', settle: 5000, retries: 4 });
  if (nav.reason === 'RATE_LIMIT') throw Object.assign(new Error(`HTTP 429 ${nav.responseUrl || url}`), { exitCode: 11 });
  if (nav.reason === 'LOGIN_REDIRECT') throw new XAuthenticationError(`following snapshot requires login: ${page.url()}`, nav);
  await confirmAuthenticated(page, { expectedPath: `/${handle}/following` });
  if (!nav.ok) {
    process.stderr.write(`[snapshot-following] /following did not render after ${nav.attempts} attempts\n`);
    await writeAlertWithEvidence(page, RUNTIME.state.alertPath, {
      type: 'GENERIC_NAV_ERROR', text: `/following did not render: ${nav.reason || 'NO_CONTENT'}`,
      handle, context: 'following_snapshot', url: page.url(), profileDir: PROFILE_DIR,
    });
    console.log(JSON.stringify({ count: 0, handles: [], error: 'no_render' }, null, 2));
    process.exitCode = 3;
    return false;
  }
  await page.waitForTimeout(1500);

  const observed = await captureXResponseEvidence(page, () => page.evaluate(EXTRACT_JS));
  if (observed.evidence?.reason === 'RATE_LIMIT') {
    throw Object.assign(new Error(`HTTP 429 ${observed.evidence.responseUrl}`), { exitCode: 11 });
  }
  if (observed.evidence?.reason === 'LOGIN_REDIRECT') {
    throw new XAuthenticationError(`following snapshot lost authentication: ${page.url()}`, observed.evidence);
  }
  const result = observed.value;
  process.stderr.write(`[snapshot-following] @${handle} follows ${result.count} accounts\n`);
  console.log(JSON.stringify(result, null, 2));
  return true;
  } catch (error) {
    let type = 'UNEXPECTED_ERROR';
    if (error instanceof XAuthenticationError) type = 'LOGIN_REDIRECT';
    else if (error.exitCode === 11 || /HTTP 429/.test(error.message || '')) type = 'RATE_LIMIT';
    else if (error.exitCode === 18) type = 'GENERIC_NAV_ERROR';
    let cooldown = null;
    if (type === 'RATE_LIMIT') cooldown = PROFILE_PACER.noteRateLimit({ handle: `${handle}/following`, responseUrl: error.message });
    await writeAlertWithEvidence(page, RUNTIME.state.alertPath, {
      type, text: error.message || String(error), handle, context: 'following_snapshot',
      rateLimitCooldownUntil: cooldown?.cooldownUntil || null,
      url: (() => { try { return page.url(); } catch { return url; } })(), profileDir: PROFILE_DIR,
    });
    throw error;
  }
}

async function main() {
  await PROFILE_PACER.beforeNetwork(`following snapshot @${handle}`);
  await PROFILE_PACER.beforeVisit(`${handle}/following`);
  await withAuthenticatedContext(
    { config: RUNTIME.browser, headless: false, width: 1280, height: 820 },
    snapshot,
  );
}

main().catch((error) => {
  console.error('FATAL', error.message || error);
  if (error instanceof BrowserConfigError) process.exitCode = 2;
  else if (error instanceof XAuthenticationError) process.exitCode = 12;
  else if (Number.isInteger(error.exitCode)) process.exitCode = error.exitCode;
  else process.exitCode = 99;
});
