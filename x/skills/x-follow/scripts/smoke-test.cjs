#!/usr/bin/env node
// smoke-test.cjs — Campaign 启动前 6 项体检
// Usage: PROFILE_DIR=~/.config/playwright-chrome-profile-campaign \
//        MY_HANDLE=haoliucha \
//        node smoke-test.cjs

const path = require('path');
const { detectAnomaly, writeAlertWithEvidence } = require(path.join(__dirname, 'lib', 'anomaly.cjs'));
const { gotoRobust } = require(path.join(__dirname, 'lib', 'nav-helper.cjs'));
const { createProfilePacer } = require(path.join(__dirname, 'lib', 'profile-pacer.cjs'));
const { prepareXFacingRuntime } = require(path.join(__dirname, 'lib', 'runtime-gate.cjs'));
const { BrowserConfigError, withAuthenticatedContext, XAuthenticationError } = require(path.join(__dirname, 'lib', 'cdp-browser.cjs'));

let RUNTIME;
try { RUNTIME = prepareXFacingRuntime(process.env); }
catch (error) { console.error(`FATAL: ${error.message}`); process.exit(2); }

const PROFILE_DIR = process.env.PROFILE_DIR || `${process.env.HOME}/.config/playwright-chrome-profile-campaign`;
const MY_HANDLE = process.env.MY_HANDLE || '';
const PROFILE_PACER = createProfilePacer({
  statePath: RUNTIME.state.pacingPath,
  minIntervalMs: parseInt(process.env.PROFILE_VISIT_MIN_INTERVAL_MS || '90000', 10),
  maxIntervalMs: parseInt(process.env.PROFILE_VISIT_MAX_INTERVAL_MS || '150000', 10),
  maxVisitsPerHour: parseInt(process.env.MAX_PROFILE_VISITS_PER_HOUR || '30', 10),
  rateLimitCooldownMs: parseInt(process.env.RATE_LIMIT_COOLDOWN_MS || '1800000', 10),
  log: (message) => console.log(`[smoke] ${message}`),
});

const G = '\x1b[32m', R = '\x1b[31m', Y = '\x1b[33m', X = '\x1b[0m';
const ok = (m) => console.log(`${G}✅ PASS${X} ${m}`);
const fail = (m) => console.log(`${R}❌ FAIL${X} ${m}`);
const info = (m) => console.log(`${Y}ℹ️  ${X} ${m}`);

class SmokeExitError extends Error {
  constructor(message, exitCode, details = {}) { super(message); this.exitCode = exitCode; this.details = details; }
}

async function smoke({ context, confirmAuthenticated }) {
  console.log(`\n=== X-FOLLOW SMOKE TEST ===`);
  console.log(`PROFILE_DIR: ${PROFILE_DIR}`);
  console.log(`MY_HANDLE: ${MY_HANDLE || '(not set)'}`);
  console.log(`TRANSPORT: CDP (${RUNTIME.browser.profileDirectory})`);
  console.log(``);
  let allPass = true;
  ok(`System Chrome account uniquely selected; source remains read-only`);
  ok(`Chrome launched over localhost CDP`);
  const page = context.pages()[0] || await context.newPage();
  let currentStage = 'home';
  try {

    // 1. Browser fingerprint check — gotoRobust waits for real content (latency/429 tolerant)
    const homeNav = await gotoRobust(page, 'https://x.com/home', {
      needSel: 'a[data-testid="SideNav_NewTweet_Button"], [data-testid="AppTabBar_Home_Link"], [data-testid="primaryColumn"]',
      settle: 5000, retries: 3,
    });
    if (homeNav.reason === 'RATE_LIMIT') throw new SmokeExitError('HTTP 429 during /home smoke navigation', 11, homeNav);
    if (homeNav.reason === 'LOGIN_REDIRECT') throw new XAuthenticationError(`smoke navigation requires login: ${page.url()}`, homeNav);
    await confirmAuthenticated(page, { expectedPath: '/home' });
    if (!homeNav.ok) { fail(`/home navigation failed: ${homeNav.reason}`); allPass = false; }

    const sig = await page.evaluate(() => ({
      webdriver: navigator.webdriver,
      hasChrome: !!window.chrome,
      hasPlugins: navigator.plugins.length,
      hwConcurrency: navigator.hardwareConcurrency,
      languages: navigator.languages,
      userAgent: navigator.userAgent,
      vendor: navigator.vendor,
    }));

    console.log(`\n  navigator fingerprint:`);
    Object.entries(sig).forEach(([k, v]) => console.log(`    ${k}: ${JSON.stringify(v)}`));
    console.log();

    if (sig.webdriver === true) { fail(`navigator.webdriver=true`); allPass = false; }
    else ok(`navigator.webdriver=false`);

    if (!sig.hasChrome) { fail(`window.chrome missing`); allPass = false; }
    else ok(`window.chrome present`);

    if (sig.hasPlugins < 1) { fail(`plugins.length=0`); allPass = false; }
    else ok(`plugins.length=${sig.hasPlugins}`);

    if (sig.hwConcurrency < 1 || sig.hwConcurrency > 64) { fail(`hardwareConcurrency=${sig.hwConcurrency} suspicious`); allPass = false; }
    else ok(`hardwareConcurrency=${sig.hwConcurrency}`);

    if (!sig.languages || !sig.languages.length) { fail(`languages empty`); allPass = false; }
    else ok(`languages=${JSON.stringify(sig.languages)}`);

    if (/HeadlessChrome/.test(sig.userAgent)) { fail(`UA contains HeadlessChrome`); allPass = false; }
    else ok(`UA looks natural`);

    // 2. Login state check
    const url = page.url();
    ok(`Logged in (URL: ${url})`);

      // Try to confirm handle
      const profileLink = await page.evaluate(() =>
        document.querySelector('a[href^="/"][aria-label*="个人资料"], a[href^="/"][aria-label*="Profile"]')?.getAttribute('href')
      );
      if (profileLink) {
        const handle = profileLink.replace('/', '');
        info(`Authenticated X profile link: /${handle} (informational; Chrome email selects the profile)`);
      } else {
        info(`Could not extract profile handle (non-fatal)`);
      }

    // 3. Anomaly detector sanity check.
    // EMPTY_PAGE is excluded: the /home SPA shell is transiently <50 chars under VPN
    // latency, which is NOT a real anomaly (the gotoRobust above already waited for
    // logged-in content). Treating it as RED was a known false-positive.
    const anomaly = await detectAnomaly(page);
    if (anomaly && anomaly.type !== 'EVAL_ERROR' && anomaly.type !== 'EMPTY_PAGE') {
      fail(`Anomaly detected on /home: ${anomaly.type} - ${anomaly.text}`);
      allPass = false;
    } else {
      ok(`No anomaly on /home`);
    }

    // 4. Search page accessible
    currentStage = 'search';
    const searchNav = await gotoRobust(page, 'https://x.com/search?q=test', { needSel: '[data-testid="primaryColumn"]', settle: 4000, retries: 3 });
    if (searchNav.reason === 'RATE_LIMIT') throw new SmokeExitError('HTTP 429 during /search smoke navigation', 11, searchNav);
    if (searchNav.reason === 'LOGIN_REDIRECT') throw new XAuthenticationError(`search requires login: ${page.url()}`, searchNav);
    const searchUrl = page.url();
    if (searchNav.ok && searchUrl.includes('/search')) ok(`/search accessible`);
    else { fail(`/search not accessible (URL: ${searchUrl})`); allPass = false; }

    // 5. Test that follow-button selector works on a profile (DOES NOT CLICK)
    currentStage = 'elonmusk';
    await PROFILE_PACER.beforeVisit('elonmusk');
    const profileNav = await gotoRobust(page, 'https://x.com/elonmusk', { needSel: 'div[data-testid="UserName"]', settle: 4000, retries: 3 });
    if (profileNav.reason === 'RATE_LIMIT') throw new SmokeExitError('HTTP 429 during profile smoke navigation', 11, profileNav);
    if (profileNav.reason === 'LOGIN_REDIRECT') throw new XAuthenticationError(`profile requires login: ${page.url()}`, profileNav);
    if (!profileNav.ok) { fail(`Profile navigation failed: ${profileNav.reason}`); allPass = false; }
    await page.waitForTimeout(1200);
    const btnState = await page.evaluate(() => {
      const fB = document.querySelector('button[data-testid$="-follow"][aria-label="关注 @elonmusk"]');
      const uB = document.querySelector('button[data-testid$="-unfollow"][aria-label*="@elonmusk"]');
      return { follow: !!fB, unfollow: !!uB };
    });
    if (btnState.follow || btnState.unfollow) {
      ok(`Follow button selector works on /elonmusk (follow=${btnState.follow}, unfollow=${btnState.unfollow})`);
    } else {
      fail(`Could not find follow/unfollow button on /elonmusk — X DOM may have changed`);
      allPass = false;
    }

  console.log(``);
  if (allPass) {
    console.log(`${G}=== ALL GREEN — campaign safe to launch ===${X}`);
    return true;
  } else {
    console.log(`${R}=== RED — refuse to launch campaign. Fix issues above. ===${X}`);
    await writeAlertWithEvidence(page, RUNTIME.state.alertPath, {
      type: 'SMOKE_RED', text: 'one or more smoke checks failed', context: currentStage,
      url: page.url(), profileDir: PROFILE_DIR,
    });
    return false;
  }
  } catch (error) {
    let type = 'UNEXPECTED_ERROR';
    if (error instanceof XAuthenticationError) type = 'LOGIN_REDIRECT';
    else if (error.exitCode === 11 || /HTTP 429/.test(error.message || '')) type = 'RATE_LIMIT';
    let cooldown = null;
    if (type === 'RATE_LIMIT') cooldown = PROFILE_PACER.noteRateLimit({ handle: currentStage, responseUrl: error.details?.responseUrl });
    await writeAlertWithEvidence(page, RUNTIME.state.alertPath, {
      type, text: error.message || String(error), context: currentStage,
      httpStatus: error.details?.httpStatus, responseUrl: error.details?.responseUrl,
      rateLimitCooldownUntil: cooldown?.cooldownUntil || null,
      url: (() => { try { return page.url(); } catch { return null; } })(), profileDir: PROFILE_DIR,
    });
    throw error;
  }
}

async function main() {
  await PROFILE_PACER.beforeNetwork('smoke /home');
  const passed = await withAuthenticatedContext(
    { config: RUNTIME.browser, headless: false, width: 1280, height: 820 },
    smoke,
  );
  if (!passed) process.exitCode = 1;
}

main().catch((error) => {
  console.error('FATAL', error.message || error);
  if (error instanceof BrowserConfigError) process.exitCode = 2;
  else if (error instanceof XAuthenticationError) process.exitCode = 12;
  else if (Number.isInteger(error.exitCode)) process.exitCode = error.exitCode;
  else process.exitCode = 99;
});
