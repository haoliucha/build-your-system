#!/usr/bin/env node
'use strict';

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

const ROOT = path.join(__dirname, '..');
const Browser = require(path.join(ROOT, 'scripts', 'lib', 'cdp-browser.cjs'));
const Nav = require(path.join(ROOT, 'scripts', 'lib', 'nav-helper.cjs'));
const Anomaly = require(path.join(ROOT, 'scripts', 'lib', 'anomaly.cjs'));

let passed = 0;
async function test(name, fn) {
  await fn();
  passed += 1;
  process.stdout.write(`  ✅ ${name}\n`);
}

function fixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'x-cdp-test-'));
  const source = path.join(root, 'Chrome');
  const sourceProfile = path.join(source, 'Profile Dynamic');
  const target = path.join(root, 'campaign');
  const executable = path.join(root, 'Google Chrome');
  const configPath = path.join(root, 'config', 'account.json');
  fs.mkdirSync(sourceProfile, { recursive: true });
  fs.writeFileSync(path.join(source, 'Local State'), JSON.stringify({
    profile: { info_cache: { 'Profile Dynamic': { user_name: 'operator@example.com', name: 'Operator' } } },
  }));
  fs.writeFileSync(path.join(sourceProfile, 'Cookies'), 'cookie-db');
  fs.mkdirSync(path.join(sourceProfile, 'IndexedDB'));
  fs.writeFileSync(path.join(sourceProfile, 'IndexedDB', 'state'), 'auth-state');
  fs.writeFileSync(path.join(sourceProfile, 'History'), 'must-not-copy');
  fs.writeFileSync(executable, '#!/bin/sh\n');
  fs.chmodSync(executable, 0o755);
  const env = {
    HOME: root,
    X_BROWSER_CONFIG_PATH: configPath,
    X_CHROME_EXECUTABLE: executable,
    X_CHROME_USER_DATA_DIR: source,
    PROFILE_DIR: target,
  };
  return { configPath, env, executable, root, source, sourceProfile, target };
}

async function main() {
  await test('local account config is atomic, mode 0600, and env override wins', async () => {
    const f = fixture();
    const saved = Browser.writeAccountConfig('Operator@Example.com', f.env);
    assert.strictEqual(saved.email, 'operator@example.com');
    assert.strictEqual(fs.statSync(f.configPath).mode & 0o777, 0o600);
    assert.strictEqual(Browser.resolveAccountEmail(f.env).email, 'operator@example.com');
    assert.strictEqual(Browser.resolveAccountEmail({ ...f.env, X_CHROME_ACCOUNT_EMAIL: 'override@example.com' }).email, 'override@example.com');
  });

  await test('missing account config fails before any browser dependency', async () => {
    const f = fixture();
    assert.throws(() => Browser.preflightBrowserConfig(f.env), (error) => error.code === 'ACCOUNT_CONFIG_REQUIRED');
  });

  await test('Chrome email uniquely resolves a dynamic profile directory', async () => {
    const f = fixture();
    Browser.writeAccountConfig('operator@example.com', f.env);
    const config = Browser.preflightBrowserConfig(f.env);
    assert.strictEqual(config.profileDirectory, 'Profile Dynamic');
    assert.strictEqual(config.sourceProfileDir, f.sourceProfile);
    const statePath = path.join(f.source, 'Local State');
    fs.writeFileSync(statePath, JSON.stringify({ profile: { info_cache: {} } }));
    assert.throws(() => Browser.preflightBrowserConfig(f.env), /found 0/);
    fs.writeFileSync(statePath, JSON.stringify({ profile: { info_cache: {
      One: { user_name: 'operator@example.com' }, Two: { user_name: 'OPERATOR@example.com' },
    } } }));
    fs.mkdirSync(path.join(f.source, 'One'));
    fs.mkdirSync(path.join(f.source, 'Two'));
    assert.throws(() => Browser.preflightBrowserConfig(f.env), /found 2/);
  });

  await test('profile refresh copies only auth storage and rolls back atomically', async () => {
    const f = fixture();
    Browser.writeAccountConfig('operator@example.com', f.env);
    const config = Browser.preflightBrowserConfig(f.env);
    fs.mkdirSync(f.target);
    fs.writeFileSync(path.join(f.target, 'sentinel'), 'old-profile');
    const first = await Browser.beginProfileRefresh(config, { source: config });
    assert.strictEqual(fs.readFileSync(path.join(f.target, 'Profile Dynamic', 'Cookies'), 'utf8'), 'cookie-db');
    assert.strictEqual(fs.readFileSync(path.join(f.target, 'Profile Dynamic', 'IndexedDB', 'state'), 'utf8'), 'auth-state');
    assert.ok(!fs.existsSync(path.join(f.target, 'Profile Dynamic', 'History')));
    assert.strictEqual(fs.readFileSync(path.join(first.backupDir, 'sentinel'), 'utf8'), 'old-profile');
    await Browser.rollbackProfileRefresh(first);
    assert.strictEqual(fs.readFileSync(path.join(f.target, 'sentinel'), 'utf8'), 'old-profile');

    const second = await Browser.beginProfileRefresh(config, { source: config });
    await Browser.commitProfileRefresh(second);
    assert.ok(!fs.existsSync(second.backupDir));
    assert.ok(fs.existsSync(path.join(f.target, 'Profile Dynamic', 'Cookies')));
  });

  await test('CDP args use an independent profile, localhost random port, and explicit headless policy', async () => {
    const f = fixture();
    Browser.writeAccountConfig('operator@example.com', f.env);
    const config = Browser.preflightBrowserConfig(f.env);
    const headed = Browser.buildChromeArgs(config, { headless: false, profileDirectory: config.profileDirectory });
    const headless = Browser.buildChromeArgs(config, { headless: true, profileDirectory: config.profileDirectory });
    assert.ok(headed.includes('--remote-debugging-address=127.0.0.1'));
    assert.ok(headed.includes('--remote-debugging-port=0'));
    assert.ok(headed.includes(`--user-data-dir=${config.profileCanonicalPath}`));
    assert.ok(headed.includes('--profile-directory=Profile Dynamic'));
    assert.ok(headed.includes('--disable-blink-features=AutomationControlled'));
    assert.ok(!headed.includes('--headless=new'));
    assert.ok(headless.includes('--headless=new'));
  });

  await test('profile lease blocks a live owner and recovers a stale owner', async () => {
    const f = fixture();
    Browser.writeAccountConfig('operator@example.com', f.env);
    const config = Browser.preflightBrowserConfig(f.env);
    const first = Browser.acquireProfileLease(config);
    assert.throws(() => Browser.acquireProfileLease(config), (error) => error.code === 'PROFILE_LOCK_ACTIVE');
    assert.strictEqual(first.release(), true);
    fs.mkdirSync(first.lockPath);
    fs.writeFileSync(path.join(first.lockPath, 'owner.json'), JSON.stringify({
      schemaVersion: 1, pid: 999999, childPid: null, token: 'stale', profileDir: config.profileCanonicalPath,
    }));
    const recovered = Browser.acquireProfileLease(config);
    assert.strictEqual(recovered.release(), true);
    fs.mkdirSync(first.lockPath);
    fs.writeFileSync(path.join(first.lockPath, 'owner.json'), '{}');
    assert.throws(() => Browser.acquireProfileLease(config), (error) => error.code === 'PROFILE_LOCK_INVALID');
    fs.rmSync(first.lockPath, { recursive: true, force: true });
    const exactCommand = `${config.executablePath} --user-data-dir=${config.profileCanonicalPath} --remote-debugging-port=0`;
    assert.strictEqual(Browser.commandMatchesProfile(exactCommand, config.profileCanonicalPath, config.executablePath), true);
    assert.strictEqual(Browser.commandMatchesProfile(
      `${config.executablePath} --user-data-dir=${config.profileCanonicalPath}-other --remote-debugging-port=0`,
      config.profileCanonicalPath,
      config.executablePath,
    ), false);
    assert.strictEqual(Browser.commandMatchesProfile(
      `/tmp/not-chrome --user-data-dir=${config.profileCanonicalPath}`,
      config.profileCanonicalPath,
      config.executablePath,
    ), false);

    const exactChildConfig = { ...config, executablePath: process.execPath };
    const exactChild = spawn(process.execPath, [
      '-e', 'setInterval(() => {}, 1000)', '--', `--user-data-dir=${config.profileCanonicalPath}`,
    ], { stdio: 'ignore' });
    await new Promise((resolve) => setTimeout(resolve, 150));
    assert.strictEqual(exactChild.exitCode, null, 'exact child must be live before stale-lock recovery');
    fs.mkdirSync(first.lockPath);
    fs.writeFileSync(path.join(first.lockPath, 'owner.json'), JSON.stringify({
      schemaVersion: 1,
      pid: 999999,
      childPid: exactChild.pid,
      token: 'stale-with-exact-child',
      profileDir: config.profileCanonicalPath,
    }));
    const afterExactRecovery = Browser.acquireProfileLease(exactChildConfig);
    const childExitDeadline = Date.now() + 2000;
    while (exactChild.exitCode === null && exactChild.signalCode === null && Date.now() < childExitDeadline) {
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    assert.ok(exactChild.exitCode !== null || exactChild.signalCode !== null);
    assert.strictEqual(afterExactRecovery.release(), true);
  });

  await test('SIGTERM closes only the owned CDP session and releases its profile lock', async () => {
    const f = fixture();
    Browser.writeAccountConfig('operator@example.com', f.env);
    const config = Browser.preflightBrowserConfig(f.env);
    fs.mkdirSync(f.target);
    const ready = path.join(f.root, 'ready');
    const closed = path.join(f.root, 'closed');
    const modulePath = path.join(ROOT, 'scripts', 'lib', 'cdp-browser.cjs');
    const program = `
      const fs = require('fs');
      const B = require(process.env.TEST_CDP_MODULE);
      const config = JSON.parse(process.env.TEST_CDP_CONFIG);
      B.withAuthenticatedContext({ config, headless: true }, async (api) => {
        await api.confirmAuthenticated({});
        fs.writeFileSync(process.env.TEST_READY, 'ready');
        setInterval(() => {}, 1000);
        await new Promise(() => {});
      }, {
        launchCdpBrowser: async () => ({
          browser: {}, child: null, context: {},
          close: async () => fs.writeFileSync(process.env.TEST_CLOSED, 'closed'),
        }),
        authCookieState: async () => ({ authenticated: true, missing: [] }),
        pageAuthenticationState: async () => ({ authenticated: true, url: 'https://x.com/home' }),
      }).catch((error) => { console.error(error); process.exit(99); });
    `;
    const child = spawn(process.execPath, ['-e', program], {
      env: {
        ...process.env,
        TEST_CDP_MODULE: modulePath,
        TEST_CDP_CONFIG: JSON.stringify(config),
        TEST_READY: ready,
        TEST_CLOSED: closed,
      },
      stdio: 'ignore',
    });
    const deadline = Date.now() + 3000;
    while (!fs.existsSync(ready) && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    assert.ok(fs.existsSync(ready), 'child did not install the authenticated CDP session');
    const exitPromise = new Promise((resolve) => child.once('exit', (code, signal) => resolve({ code, signal })));
    child.kill('SIGTERM');
    const exit = await exitPromise;
    assert.deepStrictEqual(exit, { code: 143, signal: null });
    assert.ok(fs.existsSync(closed));
    assert.ok(!fs.existsSync(`${config.profileCanonicalPath}.cdp.lock`));
  });

  await test('missing cookies trigger one refresh before the operation, then authenticate', async () => {
    const f = fixture();
    Browser.writeAccountConfig('operator@example.com', f.env);
    const config = Browser.preflightBrowserConfig(f.env);
    fs.mkdirSync(f.target);
    let launches = 0;
    let refreshes = 0;
    let operationCalls = 0;
    let committed = 0;
    const result = await Browser.withAuthenticatedContext({ config, headless: true }, async (api) => {
      operationCalls += 1;
      await api.confirmAuthenticated({});
      return 'ok';
    }, {
      launchCdpBrowser: async () => {
        launches += 1;
        return { browser: {}, child: null, context: { attempt: launches }, close: async () => {} };
      },
      authCookieState: async (context) => context.attempt === 1
        ? { authenticated: false, missing: ['auth_token', 'ct0'] }
        : { authenticated: true, missing: [] },
      beginProfileRefresh: async () => { refreshes += 1; return { committed: false, rolledBack: false }; },
      commitProfileRefresh: async (tx) => { tx.committed = true; committed += 1; },
      rollbackProfileRefresh: async (tx) => { tx.rolledBack = true; },
      pageAuthenticationState: async () => ({ authenticated: true, url: 'https://x.com/home' }),
    });
    assert.strictEqual(result, 'ok');
    assert.strictEqual(launches, 2);
    assert.strictEqual(refreshes, 1);
    assert.strictEqual(operationCalls, 1);
    assert.strictEqual(committed, 1);
  });

  await test('a second authentication failure rolls back and fails closed', async () => {
    const f = fixture();
    Browser.writeAccountConfig('operator@example.com', f.env);
    const config = Browser.preflightBrowserConfig(f.env);
    fs.mkdirSync(f.target);
    let launches = 0;
    let rollbacks = 0;
    await assert.rejects(
      Browser.withAuthenticatedContext({ config, headless: true }, async () => 'must-not-run', {
        launchCdpBrowser: async () => {
          launches += 1;
          return { browser: {}, child: null, context: {}, close: async () => {} };
        },
        authCookieState: async () => ({ authenticated: false, missing: ['auth_token', 'ct0'] }),
        beginProfileRefresh: async () => ({ committed: false, rolledBack: false }),
        rollbackProfileRefresh: async (tx) => { tx.rolledBack = true; rollbacks += 1; },
      }),
      (error) => error instanceof Browser.XAuthenticationError,
    );
    assert.strictEqual(launches, 2);
    assert.strictEqual(rollbacks, 1);
  });

  await test('protected-list public-profile redirects are login failures until logged-in chrome is proven', async () => {
    const context = {
      cookies: async () => [{ name: 'auth_token' }, { name: 'ct0' }],
    };
    const loggedOutRedirect = {
      context: () => context,
      url: () => 'https://x.com/haoliucha',
      evaluate: async () => ({ hasAuthenticatedChrome: false, hasLoginUi: false }),
    };
    const unauthenticated = await Browser.pageAuthenticationState(loggedOutRedirect, {
      expectedPath: '/haoliucha/following',
    });
    assert.strictEqual(unauthenticated.protectedRedirect, true);
    assert.strictEqual(unauthenticated.authenticated, false);

    const confirmedChrome = {
      ...loggedOutRedirect,
      evaluate: async () => ({ hasAuthenticatedChrome: true, hasLoginUi: false }),
    };
    const authenticatedDrift = await Browser.pageAuthenticationState(confirmedChrome, {
      expectedPath: '/haoliucha/following',
    });
    assert.strictEqual(authenticatedDrift.protectedRedirect, false);
    assert.strictEqual(authenticatedDrift.authenticated, true);

    const missingCookiePage = {
      context: () => ({ cookies: async () => [{ name: 'ct0' }] }),
      url: () => 'https://x.com/haoliucha/following',
      evaluate: async () => ({ hasAuthenticatedChrome: true, hasLoginUi: false }),
    };
    const missingCookie = await Browser.pageAuthenticationState(missingCookiePage, {
      expectedPath: '/haoliucha/following',
    });
    assert.strictEqual(missingCookie.authenticated, false);
    assert.deepStrictEqual(missingCookie.cookieState.missing, ['auth_token']);
  });

  await test('HTTP evidence distinguishes real 429 from a generic error page', async () => {
    const response = (status, url = 'https://x.com/i/api/graphql/Following') => ({ status: () => status, url: () => url });
    assert.deepStrictEqual(Nav.responseEvidence(response(429)), {
      reason: 'RATE_LIMIT', httpStatus: 429, responseUrl: 'https://x.com/i/api/graphql/Following',
    });
    assert.strictEqual(Nav.responseEvidence(response(200)), null);
    assert.strictEqual(Nav.responseEvidence(response(429, 'https://example.com/')), null);
    assert.strictEqual(Nav.responseEvidence(response(429, 'https://x.com/assets/app.js')), null);
    assert.strictEqual(Nav.responseEvidence(response(429, 'https://x.com/haoliucha/following'), { navigation: true }).reason, 'RATE_LIMIT');
    assert.strictEqual(Anomaly.EXIT_CODES.GENERIC_NAV_ERROR, 18);
    assert.strictEqual(Anomaly.classifyAnomaly({ bodyText: 'try again later '.repeat(8) }).type, 'GENERIC_NAV_ERROR');
    assert.strictEqual(Anomaly.classifyAnomaly({ bodyText: 'normal content '.repeat(8), hasLoginUi: true }).type, 'LOGIN_REDIRECT');

    const listeners = new Set();
    const page = {
      on(event, listener) { if (event === 'response') listeners.add(listener); },
      off(event, listener) { if (event === 'response') listeners.delete(listener); },
    };
    const captured = await Nav.captureXResponseEvidence(page, async () => {
      for (const listener of listeners) listener(response(429));
      return 'operation-result';
    });
    assert.strictEqual(captured.value, 'operation-result');
    assert.strictEqual(captured.evidence.reason, 'RATE_LIMIT');
    assert.strictEqual(listeners.size, 0);
  });

  await test('both standalone Skills vendor the same CDP implementation without private identifiers', async () => {
    const unfollow = fs.readFileSync(path.join(ROOT, 'scripts', 'lib', 'cdp-browser.cjs'), 'utf8');
    const follow = fs.readFileSync(path.join(ROOT, '..', 'x-follow', 'scripts', 'lib', 'cdp-browser.cjs'), 'utf8');
    assert.strictEqual(follow, unfollow);
    assert.doesNotMatch(unfollow, /@gmail\.com/i);
    assert.doesNotMatch(unfollow, /profile\s+9/i);
    assert.doesNotMatch(follow, /x-unfollow/);
  });

  process.stdout.write(`\n${passed} CDP checks passed\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exit(1);
});
