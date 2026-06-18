#!/usr/bin/env node
// smoke-test.cjs — pre-run health check for the x-unfollow skill.
// Usage: PROFILE_DIR=~/.config/playwright-chrome-profile-campaign MY_HANDLE=you node smoke-test.cjs

const path = require('path');
const fs = require('fs');
const os = require('os');
const { chromium } = require('playwright');
const { detectAnomaly } = require(path.join(__dirname, 'lib', 'anomaly.cjs'));
const { gotoRobust } = require(path.join(__dirname, 'lib', 'nav-helper.cjs'));

const PROFILE_DIR = process.env.PROFILE_DIR || path.join(os.homedir(), '.config/playwright-chrome-profile-campaign');
const MY_HANDLE = (process.env.MY_HANDLE || '').replace(/^@/, '').trim();

const G = '\x1b[32m', R = '\x1b[31m', Y = '\x1b[33m', X = '\x1b[0m';
const ok = (m) => console.log(`${G}✅ PASS${X} ${m}`);
const fail = (m) => console.log(`${R}❌ FAIL${X} ${m}`);
const info = (m) => console.log(`${Y}ℹ️  ${X} ${m}`);

async function main() {
  console.log(`\n=== X-UNFOLLOW SMOKE TEST ===`);
  console.log(`PROFILE_DIR: ${PROFILE_DIR}`);
  console.log(`MY_HANDLE: ${MY_HANDLE || '(not set)'}\n`);

  if (!fs.existsSync(PROFILE_DIR)) {
    fail(`Profile dir does not exist: ${PROFILE_DIR}`);
    console.log(`\nFix: cp -R ~/.config/playwright-chrome-profile ${PROFILE_DIR} && rm -f ${PROFILE_DIR}/Singleton*`);
    process.exit(3);
  }
  ok(`Profile dir exists`);
  if (fs.existsSync(path.join(PROFILE_DIR, 'SingletonLock'))) {
    fail(`SingletonLock present`);
    console.log(`\nFix: rm -f ${PROFILE_DIR}/Singleton*`);
    process.exit(3);
  }
  ok(`No SingletonLock`);

  let ctx, page, allPass = true;
  try {
    ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
      channel: 'chrome', headless: false, viewport: { width: 1280, height: 820 },
      ignoreDefaultArgs: ['--enable-automation'], args: ['--disable-blink-features=AutomationControlled'],
    });
    ok(`Chromium launched`);
    page = ctx.pages()[0] || await ctx.newPage();

    await gotoRobust(page, 'https://x.com/home', {
      needSel: 'a[data-testid="SideNav_NewTweet_Button"], [data-testid="AppTabBar_Home_Link"], [data-testid="primaryColumn"]', settle: 5000, retries: 3,
    });

    const sig = await page.evaluate(() => ({
      webdriver: navigator.webdriver, hasChrome: !!window.chrome, hasPlugins: navigator.plugins.length,
      hwConcurrency: navigator.hardwareConcurrency, languages: navigator.languages, userAgent: navigator.userAgent,
    }));
    console.log(`\n  navigator fingerprint:`);
    Object.entries(sig).forEach(([k, v]) => console.log(`    ${k}: ${JSON.stringify(v)}`));
    console.log();

    if (sig.webdriver === true) { fail(`navigator.webdriver=true`); allPass = false; } else ok(`navigator.webdriver=false`);
    if (!sig.hasChrome) { fail(`window.chrome missing`); allPass = false; } else ok(`window.chrome present`);
    if (sig.hasPlugins < 1) { fail(`plugins.length=0`); allPass = false; } else ok(`plugins.length=${sig.hasPlugins}`);
    if (/HeadlessChrome/.test(sig.userAgent)) { fail(`UA contains HeadlessChrome`); allPass = false; } else ok(`UA looks natural`);

    const url = page.url();
    if (url.includes('/login') || url.includes('/i/flow')) { fail(`Redirected to login: ${url}`); allPass = false; }
    else ok(`Logged in (URL: ${url})`);

    const anomaly = await detectAnomaly(page);
    if (anomaly && anomaly.type !== 'EVAL_ERROR' && anomaly.type !== 'EMPTY_PAGE') { fail(`Anomaly on /home: ${anomaly.type}`); allPass = false; }
    else ok(`No anomaly on /home`);

    // /following renders UserCells (proves the snapshot scrape + unfollow targeting DOM works).
    if (MY_HANDLE) {
      await gotoRobust(page, `https://x.com/${MY_HANDLE}/following`, { needSel: '[data-testid="UserCell"], [data-testid="primaryColumn"]', settle: 4000, retries: 3 });
      await page.waitForTimeout(1500);
      const cells = await page.evaluate(() => document.querySelectorAll('[data-testid="UserCell"]').length);
      if (cells > 0) ok(`/following renders ${cells} UserCells`);
      else { fail(`/following rendered 0 UserCells — DOM may have changed or list empty`); allPass = false; }
    } else {
      info(`MY_HANDLE not set — skipping /following render check`);
    }
  } catch (e) {
    fail(`Smoke test threw: ${e.message}`); allPass = false;
  } finally {
    if (ctx) await ctx.close().catch(() => {});
  }

  console.log(``);
  if (allPass) { console.log(`${G}=== ALL GREEN — safe to run ===${X}`); process.exit(0); }
  console.log(`${R}=== RED — refuse to run. Fix issues above. ===${X}`); process.exit(1);
}

main().catch((e) => { console.error('FATAL', e); process.exit(99); });
