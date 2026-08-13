#!/usr/bin/env node
// smoke-test.cjs — Campaign 启动前 6 项体检
// Usage: PROFILE_DIR=~/.config/playwright-chrome-profile-campaign \
//        MY_HANDLE=haoliucha \
//        node smoke-test.cjs

const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright');
const { detectAnomaly } = require(path.join(__dirname, 'lib', 'anomaly.cjs'));
const { gotoRobust } = require(path.join(__dirname, 'lib', 'nav-helper.cjs'));

const PROFILE_DIR = process.env.PROFILE_DIR || `${process.env.HOME}/.config/playwright-chrome-profile-campaign`;
const MY_HANDLE = process.env.MY_HANDLE || '';

const G = '\x1b[32m', R = '\x1b[31m', Y = '\x1b[33m', X = '\x1b[0m';
const ok = (m) => console.log(`${G}✅ PASS${X} ${m}`);
const fail = (m) => console.log(`${R}❌ FAIL${X} ${m}`);
const info = (m) => console.log(`${Y}ℹ️  ${X} ${m}`);

async function main() {
  console.log(`\n=== X-FOLLOW SMOKE TEST ===`);
  console.log(`PROFILE_DIR: ${PROFILE_DIR}`);
  console.log(`MY_HANDLE: ${MY_HANDLE || '(not set)'}`);
  console.log(``);

  // Pre-check: profile dir exists
  if (!fs.existsSync(PROFILE_DIR)) {
    fail(`Profile dir does not exist: ${PROFILE_DIR}`);
    console.log(`\nFix: cp -R ~/.config/playwright-chrome-profile ${PROFILE_DIR} && rm -f ${PROFILE_DIR}/SingletonLock*`);
    process.exit(3);
  }
  ok(`Profile dir exists`);

  // Pre-check: no leftover SingletonLock
  const lockPath = path.join(PROFILE_DIR, 'SingletonLock');
  if (fs.existsSync(lockPath)) {
    fail(`SingletonLock present: ${lockPath}`);
    console.log(`\nFix: rm -f ${PROFILE_DIR}/SingletonLock ${PROFILE_DIR}/SingletonCookie ${PROFILE_DIR}/SingletonSocket`);
    process.exit(3);
  }
  ok(`No SingletonLock`);

  let ctx, page;
  let allPass = true;
  try {
    ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
      channel: 'chrome',
      headless: false,
      chromiumSandbox: true,  // suppress the "--no-sandbox / security will suffer" infobar
      viewport: { width: 1280, height: 820 },
      ignoreDefaultArgs: ['--enable-automation'],
      args: ['--disable-blink-features=AutomationControlled'],
    });
    ok(`Chromium launched`);

    page = ctx.pages()[0] || await ctx.newPage();

    // 1. Browser fingerprint check — gotoRobust waits for real content (latency/429 tolerant)
    await gotoRobust(page, 'https://x.com/home', {
      needSel: 'a[data-testid="SideNav_NewTweet_Button"], [data-testid="AppTabBar_Home_Link"], [data-testid="primaryColumn"]',
      settle: 5000, retries: 3,
    });

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
    if (url.includes('/login') || url.includes('/i/flow')) {
      fail(`Redirected to login: ${url}`);
      console.log(`\nFix: log into X manually in the SOURCE profile, then re-copy to campaign dir`);
      allPass = false;
    } else {
      ok(`Logged in (URL: ${url})`);

      // Try to confirm handle
      const profileLink = await page.evaluate(() =>
        document.querySelector('a[href^="/"][aria-label*="个人资料"], a[href^="/"][aria-label*="Profile"]')?.getAttribute('href')
      );
      if (profileLink) {
        const handle = profileLink.replace('/', '');
        ok(`Profile link: /${handle}`);
        if (MY_HANDLE && handle !== MY_HANDLE) {
          fail(`Handle mismatch: expected ${MY_HANDLE}, got ${handle}`);
          allPass = false;
        }
      } else {
        info(`Could not extract profile handle (non-fatal)`);
      }
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
    await gotoRobust(page, 'https://x.com/search?q=test', { needSel: '[data-testid="primaryColumn"]', settle: 4000, retries: 3 });
    const searchUrl = page.url();
    if (searchUrl.includes('/search')) ok(`/search accessible`);
    else { fail(`/search not accessible (URL: ${searchUrl})`); allPass = false; }

    // 5. Test that follow-button selector works on a profile (DOES NOT CLICK)
    await gotoRobust(page, 'https://x.com/elonmusk', { needSel: 'div[data-testid="UserName"]', settle: 4000, retries: 3 });
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

  } catch (e) {
    fail(`Smoke test threw: ${e.message}`);
    allPass = false;
  } finally {
    if (ctx) await ctx.close().catch(() => {});
  }

  console.log(``);
  if (allPass) {
    console.log(`${G}=== ALL GREEN — campaign safe to launch ===${X}`);
    process.exit(0);
  } else {
    console.log(`${R}=== RED — refuse to launch campaign. Fix issues above. ===${X}`);
    process.exit(1);
  }
}

main().catch(e => { console.error('FATAL', e); process.exit(99); });
