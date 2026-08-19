'use strict';

const fs = require('fs');
const fsp = fs.promises;
const os = require('os');
const path = require('path');
const { spawn, execFileSync } = require('child_process');
const crypto = require('crypto');

const DEFAULT_CHROME_EXECUTABLE = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const AUTH_COOKIE_NAMES = new Set(['auth_token', 'ct0']);
const PROFILE_AUTH_ENTRIES = [
  'Cookies',
  'Cookies-journal',
  'IndexedDB',
  'Local Storage',
  'Network',
  'Network Persistent State',
  'Preferences',
  'Secure Preferences',
  'Session Storage',
  'Storage',
  'Trust Tokens',
  'Trust Tokens-journal',
  'WebStorage',
];

class BrowserConfigError extends Error {
  constructor(message, code = 'BROWSER_CONFIG_ERROR') {
    super(message);
    this.name = 'BrowserConfigError';
    this.code = code;
  }
}

class XAuthenticationError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = 'XAuthenticationError';
    this.code = 'LOGIN_REDIRECT';
    this.details = details;
  }
}

function homeFrom(env = process.env) {
  return env.HOME || os.homedir();
}

function accountConfigPath(env = process.env) {
  return env.X_BROWSER_CONFIG_PATH || path.join(homeFrom(env), '.config', 'x-browser', 'account.json');
}

function normalizeEmail(value) {
  const email = String(value || '').trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    throw new BrowserConfigError('Chrome account email is missing or invalid', 'ACCOUNT_CONFIG_REQUIRED');
  }
  return email;
}

function maskEmail(value) {
  const [local, domain] = normalizeEmail(value).split('@');
  return `${local.slice(0, 1)}***@${domain}`;
}

function readAccountConfig(env = process.env, fsModule = fs) {
  const configPath = accountConfigPath(env);
  let parsed;
  try {
    parsed = JSON.parse(fsModule.readFileSync(configPath, 'utf8'));
  } catch (error) {
    if (error.code === 'ENOENT') {
      throw new BrowserConfigError(
        `X browser account is not configured. Ask the user for the Chrome account email, then run: node scripts/configure-account.cjs set --email=<email> (config: ${configPath})`,
        'ACCOUNT_CONFIG_REQUIRED',
      );
    }
    throw new BrowserConfigError(`Cannot read X browser account config ${configPath}: ${error.message}`, 'ACCOUNT_CONFIG_INVALID');
  }
  if (!parsed || parsed.schemaVersion !== 1 || typeof parsed.chromeAccountEmail !== 'string') {
    throw new BrowserConfigError(`Invalid X browser account config schema: ${configPath}`, 'ACCOUNT_CONFIG_INVALID');
  }
  return { configPath, email: normalizeEmail(parsed.chromeAccountEmail) };
}

function resolveAccountEmail(env = process.env, fsModule = fs) {
  if (String(env.X_CHROME_ACCOUNT_EMAIL || '').trim()) {
    return { configPath: accountConfigPath(env), email: normalizeEmail(env.X_CHROME_ACCOUNT_EMAIL), source: 'env' };
  }
  const configured = readAccountConfig(env, fsModule);
  return { ...configured, source: 'config' };
}

function writeAccountConfig(email, env = process.env, fsModule = fs) {
  const normalized = normalizeEmail(email);
  const configPath = accountConfigPath(env);
  const dir = path.dirname(configPath);
  fsModule.mkdirSync(dir, { recursive: true, mode: 0o700 });
  try { fsModule.chmodSync(dir, 0o700); } catch {}
  const temporary = `${configPath}.tmp-${process.pid}-${Date.now()}`;
  const payload = `${JSON.stringify({ schemaVersion: 1, chromeAccountEmail: normalized }, null, 2)}\n`;
  try {
    fsModule.writeFileSync(temporary, payload, { encoding: 'utf8', mode: 0o600 });
    fsModule.chmodSync(temporary, 0o600);
    fsModule.renameSync(temporary, configPath);
    fsModule.chmodSync(configPath, 0o600);
  } finally {
    try { fsModule.rmSync(temporary, { force: true }); } catch {}
  }
  return { configPath, email: normalized };
}

function resolveCanonicalPath(value, fsModule = fs) {
  const resolved = path.resolve(String(value));
  const missing = [];
  let existing = resolved;
  while (true) {
    try {
      const realpath = fsModule.realpathSync.native || fsModule.realpathSync;
      return path.join(realpath.call(fsModule, existing), ...missing);
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      const parent = path.dirname(existing);
      if (parent === existing) return resolved;
      missing.unshift(path.basename(existing));
      existing = parent;
    }
  }
}

function containsPath(parent, candidate) {
  const relative = path.relative(parent, candidate);
  return relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative));
}

function resolveSourceUserDataDir(env = process.env) {
  return env.X_CHROME_USER_DATA_DIR
    || env.SOURCE_PROFILE_DIR
    || env.X_FOLLOW_SOURCE_PROFILE_DIR
    || path.join(homeFrom(env), 'Library', 'Application Support', 'Google', 'Chrome');
}

function resolveBrowserConfig(env = process.env, fsModule = fs) {
  const account = resolveAccountEmail(env, fsModule);
  const sourceUserDataDir = resolveSourceUserDataDir(env);
  const profileDir = env.PROFILE_DIR || path.join(homeFrom(env), '.config', 'playwright-chrome-profile-campaign');
  const executablePath = env.X_CHROME_EXECUTABLE || DEFAULT_CHROME_EXECUTABLE;
  const sourceCanonicalPath = resolveCanonicalPath(sourceUserDataDir, fsModule);
  const profileCanonicalPath = resolveCanonicalPath(profileDir, fsModule);
  if (containsPath(sourceCanonicalPath, profileCanonicalPath) || containsPath(profileCanonicalPath, sourceCanonicalPath)) {
    throw new BrowserConfigError('PROFILE_DIR must be independent from X_CHROME_USER_DATA_DIR; refusing overlapping Chrome profiles', 'PROFILE_OVERLAP');
  }
  return {
    accountEmail: account.email,
    accountSource: account.source,
    configPath: account.configPath,
    executablePath,
    profileDir,
    profileCanonicalPath,
    sourceUserDataDir,
    sourceCanonicalPath,
  };
}

function findChromeProfileByEmail(config, fsModule = fs) {
  const localStatePath = path.join(config.sourceUserDataDir, 'Local State');
  let localState;
  try {
    localState = JSON.parse(fsModule.readFileSync(localStatePath, 'utf8'));
  } catch (error) {
    throw new BrowserConfigError(`Cannot read Chrome Local State ${localStatePath}: ${error.message}`, 'CHROME_LOCAL_STATE_INVALID');
  }
  const expected = normalizeEmail(config.accountEmail);
  const matches = Object.entries(localState?.profile?.info_cache || {}).filter(
    ([, profile]) => String(profile?.user_name || '').trim().toLowerCase() === expected,
  );
  if (matches.length !== 1) {
    throw new BrowserConfigError(`Chrome account ${maskEmail(expected)} must match exactly one profile; found ${matches.length}`, 'CHROME_PROFILE_MATCH_ERROR');
  }
  const profileDirectory = matches[0][0];
  const sourceProfileDir = path.join(config.sourceUserDataDir, profileDirectory);
  let stat;
  try { stat = fsModule.statSync(sourceProfileDir); } catch (error) {
    throw new BrowserConfigError(`Chrome profile directory is unavailable: ${sourceProfileDir}: ${error.message}`, 'CHROME_PROFILE_MISSING');
  }
  if (!stat.isDirectory()) throw new BrowserConfigError(`Chrome profile is not a directory: ${sourceProfileDir}`, 'CHROME_PROFILE_MISSING');
  return { localStatePath, profileDirectory, sourceProfileDir };
}

function preflightBrowserConfig(env = process.env, fsModule = fs) {
  const config = resolveBrowserConfig(env, fsModule);
  let executable;
  try { executable = fsModule.statSync(config.executablePath); } catch (error) {
    throw new BrowserConfigError(`Google Chrome executable is unavailable: ${config.executablePath}: ${error.message}`, 'CHROME_EXECUTABLE_MISSING');
  }
  if (!executable.isFile()) throw new BrowserConfigError(`Google Chrome executable is not a file: ${config.executablePath}`, 'CHROME_EXECUTABLE_MISSING');
  try { fsModule.accessSync(config.executablePath, fs.constants.X_OK); }
  catch (error) { throw new BrowserConfigError(`Google Chrome executable is not executable: ${config.executablePath}: ${error.message}`, 'CHROME_EXECUTABLE_MISSING'); }
  return { ...config, ...findChromeProfileByEmail(config, fsModule) };
}

async function pathExists(value, fsPromises = fsp) {
  try { await fsPromises.access(value); return true; } catch { return false; }
}

async function beginProfileRefresh(config, deps = {}) {
  const fsPromises = deps.fsPromises || fsp;
  const source = deps.source || findChromeProfileByEmail(config, deps.fsModule || fs);
  const suffix = `${Date.now()}-${process.pid}-${crypto.randomBytes(4).toString('hex')}`;
  const targetRoot = config.profileCanonicalPath;
  const stagingDir = `${targetRoot}.refreshing-${suffix}`;
  const backupDir = `${targetRoot}.backup-${suffix}`;
  const copiedEntries = [];
  let existingMoved = false;
  await fsPromises.mkdir(path.dirname(targetRoot), { recursive: true, mode: 0o700 });
  await fsPromises.mkdir(path.join(stagingDir, source.profileDirectory), { recursive: true, mode: 0o700 });
  try {
    await fsPromises.copyFile(source.localStatePath, path.join(stagingDir, 'Local State'));
    for (const entry of PROFILE_AUTH_ENTRIES) {
      const from = path.join(source.sourceProfileDir, entry);
      if (!(await pathExists(from, fsPromises))) continue;
      await fsPromises.cp(from, path.join(stagingDir, source.profileDirectory, entry), {
        recursive: true,
        force: true,
        dereference: true,
      });
      copiedEntries.push(entry);
    }
    if (!copiedEntries.includes('Cookies') && !copiedEntries.includes('Network')) {
      throw new Error('selected Chrome profile has no Cookie storage');
    }
    if (await pathExists(targetRoot, fsPromises)) {
      await fsPromises.rename(targetRoot, backupDir);
      existingMoved = true;
    }
    try {
      await fsPromises.rename(stagingDir, targetRoot);
    } catch (error) {
      if (existingMoved && !(await pathExists(targetRoot, fsPromises))) await fsPromises.rename(backupDir, targetRoot);
      throw error;
    }
    return {
      backupDir: existingMoved ? backupDir : null,
      copiedEntries,
      profileDirectory: source.profileDirectory,
      targetRoot,
      committed: false,
      rolledBack: false,
    };
  } catch (error) {
    await fsPromises.rm(stagingDir, { recursive: true, force: true }).catch(() => {});
    throw new BrowserConfigError(`Failed to refresh independent Chrome profile: ${error.message}`, 'PROFILE_REFRESH_FAILED');
  }
}

async function commitProfileRefresh(transaction, fsPromises = fsp) {
  if (!transaction || transaction.committed || transaction.rolledBack) return;
  if (transaction.backupDir) await fsPromises.rm(transaction.backupDir, { recursive: true, force: true });
  transaction.committed = true;
}

async function rollbackProfileRefresh(transaction, fsPromises = fsp) {
  if (!transaction || transaction.committed || transaction.rolledBack) return;
  await fsPromises.rm(transaction.targetRoot, { recursive: true, force: true });
  if (transaction.backupDir && await pathExists(transaction.backupDir, fsPromises)) {
    await fsPromises.rename(transaction.backupDir, transaction.targetRoot);
  }
  transaction.rolledBack = true;
}

function pidAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try { process.kill(pid, 0); return true; } catch (error) { return error.code === 'EPERM'; }
}

function processCommand(pid) {
  try { return execFileSync('/bin/ps', ['-p', String(pid), '-o', 'command='], { encoding: 'utf8' }).trim(); }
  catch { return ''; }
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function commandMatchesProfile(command, profileCanonicalPath, executablePath) {
  if (!command || !command.startsWith(`${executablePath} `)) return false;
  const profile = escapeRegExp(profileCanonicalPath);
  return new RegExp(`(?:^|\\s)--user-data-dir=(?:"${profile}"|'${profile}'|${profile})(?=\\s|$)`).test(command);
}

function childMatchesProfile(pid, profileCanonicalPath, executablePath) {
  return commandMatchesProfile(processCommand(pid), profileCanonicalPath, executablePath);
}

function stopExactChild(pid, profileCanonicalPath, executablePath) {
  if (!pidAlive(pid) || !childMatchesProfile(pid, profileCanonicalPath, executablePath)) return false;
  try { process.kill(pid, 'SIGTERM'); } catch { return false; }
  const waitArray = new Int32Array(new SharedArrayBuffer(4));
  for (let attempt = 0; attempt < 20 && pidAlive(pid); attempt += 1) Atomics.wait(waitArray, 0, 0, 50);
  if (pidAlive(pid) && childMatchesProfile(pid, profileCanonicalPath, executablePath)) {
    try { process.kill(pid, 'SIGKILL'); } catch {}
  }
  return true;
}

function readLeaseOwner(lockPath, fsModule = fs) {
  try {
    const owner = JSON.parse(fsModule.readFileSync(path.join(lockPath, 'owner.json'), 'utf8'));
    if (!owner || owner.schemaVersion !== 1 || !Number.isInteger(owner.pid)
      || typeof owner.token !== 'string' || typeof owner.profileDir !== 'string'
      || !(owner.childPid === null || Number.isInteger(owner.childPid))) return null;
    return owner;
  } catch { return null; }
}

function writeLeaseOwner(lockPath, owner, fsModule = fs) {
  const ownerPath = path.join(lockPath, 'owner.json');
  const temporary = path.join(lockPath, `.owner-${process.pid}-${crypto.randomBytes(4).toString('hex')}.tmp`);
  fsModule.writeFileSync(temporary, `${JSON.stringify(owner, null, 2)}\n`, { encoding: 'utf8', mode: 0o600 });
  fsModule.renameSync(temporary, ownerPath);
}

function acquireProfileLease(config, deps = {}) {
  const fsModule = deps.fsModule || fs;
  const ownerPid = deps.pid || process.pid;
  const lockPath = `${config.profileCanonicalPath}.cdp.lock`;
  const token = crypto.randomBytes(16).toString('hex');
  fsModule.mkdirSync(path.dirname(lockPath), { recursive: true, mode: 0o700 });
  for (let attempt = 0; attempt < 12; attempt += 1) {
    try {
      fsModule.mkdirSync(lockPath, { mode: 0o700 });
      const owner = {
        schemaVersion: 1,
        pid: ownerPid,
        childPid: null,
        token,
        profileDir: config.profileCanonicalPath,
        startedAt: new Date().toISOString(),
      };
      writeLeaseOwner(lockPath, owner, fsModule);
      let released = false;
      const updateChild = (childPid) => {
        if (released) return;
        const current = readLeaseOwner(lockPath, fsModule);
        if (!current || current.pid !== ownerPid || current.token !== token) return;
        owner.childPid = Number.isInteger(childPid) ? childPid : null;
        writeLeaseOwner(lockPath, owner, fsModule);
      };
      const release = () => {
        if (released) return false;
        const current = readLeaseOwner(lockPath, fsModule);
        if (!current || current.pid !== ownerPid || current.token !== token) { released = true; return false; }
        if (Number.isInteger(current.childPid)) stopExactChild(current.childPid, config.profileCanonicalPath, config.executablePath);
        fsModule.rmSync(lockPath, { recursive: true, force: true });
        released = true;
        return true;
      };
      return { lockPath, owner, release, updateChild };
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      const current = readLeaseOwner(lockPath, fsModule);
      if (!current) {
        throw new BrowserConfigError(`CDP profile lock is invalid; refusing unsafe recovery: ${lockPath}`, 'PROFILE_LOCK_INVALID');
      }
      if (pidAlive(current.pid)) {
        throw new BrowserConfigError(`CDP profile is already active (pid ${current.pid}): ${config.profileDir}`, 'PROFILE_LOCK_ACTIVE');
      }
      if (current.profileDir !== config.profileCanonicalPath) {
        throw new BrowserConfigError(`Stale CDP lock profile does not match its canonical lock path; refusing cleanup: ${lockPath}`, 'PROFILE_LOCK_UNSAFE');
      }
      if (current && Number.isInteger(current.childPid) && pidAlive(current.childPid)) {
        if (!childMatchesProfile(current.childPid, config.profileCanonicalPath, config.executablePath)) {
          throw new BrowserConfigError(`Stale CDP lock names an unrelated live process; refusing cleanup: ${lockPath}`, 'PROFILE_LOCK_UNSAFE');
        }
        stopExactChild(current.childPid, config.profileCanonicalPath, config.executablePath);
      }
      const stale = `${lockPath}.stale-${ownerPid}-${token}-${attempt}`;
      try { fsModule.renameSync(lockPath, stale); }
      catch (renameError) {
        if (renameError.code === 'ENOENT' || renameError.code === 'EEXIST') continue;
        throw renameError;
      }
      fsModule.rmSync(stale, { recursive: true, force: true });
    }
  }
  throw new BrowserConfigError(`Unable to acquire CDP profile lock: ${lockPath}`, 'PROFILE_LOCK_CONTENDED');
}

function buildChromeArgs(config, { headless, profileDirectory, width = 1400, height = 1000 }) {
  const args = [
    '--remote-debugging-address=127.0.0.1',
    '--remote-debugging-port=0',
    `--user-data-dir=${config.profileCanonicalPath}`,
    `--profile-directory=${profileDirectory}`,
    `--window-size=${width},${height}`,
    '--lang=zh-CN',
    '--disable-blink-features=AutomationControlled',
    '--disable-background-networking',
    '--disable-component-update',
    '--disable-sync',
    '--no-default-browser-check',
    '--no-first-run',
  ];
  if (headless) args.unshift('--headless=new');
  args.push('about:blank');
  return args;
}

async function waitForCdpEndpoint(config, child, stderrText, launchError, timeoutMs = 15000) {
  const markerPath = path.join(config.profileCanonicalPath, 'DevToolsActivePort');
  const deadline = Date.now() + timeoutMs;
  while (Date.now() <= deadline) {
    if (launchError()) throw launchError();
    if (child.exitCode !== null) throw new Error(`Chrome CDP exited ${child.exitCode}: ${stderrText()}`);
    try {
      const [port] = (await fsp.readFile(markerPath, 'utf8')).trim().split(/\r?\n/);
      if (/^\d+$/.test(port)) return `http://127.0.0.1:${port}`;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for Chrome CDP endpoint: ${stderrText()}`);
}

async function waitForExit(child, timeoutMs = 3000) {
  if (child.exitCode !== null) return;
  await Promise.race([
    new Promise((resolve) => child.once('exit', resolve)),
    new Promise((resolve) => setTimeout(resolve, timeoutMs)),
  ]);
}

async function launchCdpBrowser(config, options = {}, deps = {}) {
  const spawnFn = deps.spawn || spawn;
  const connect = deps.connectOverCDP || (async (endpoint) => {
    const { chromium } = require('playwright');
    return chromium.connectOverCDP(endpoint);
  });
  const lease = options.lease;
  await fsp.mkdir(config.profileCanonicalPath, { recursive: true, mode: 0o700 });
  await fsp.rm(path.join(config.profileCanonicalPath, 'DevToolsActivePort'), { force: true });
  let stderr = '';
  const child = spawnFn(
    config.executablePath,
    buildChromeArgs(config, options),
    { stdio: ['ignore', 'ignore', 'pipe'] },
  );
  let childLaunchError = null;
  child.once('error', (error) => { childLaunchError = error; });
  lease?.updateChild(child.pid);
  child.stderr?.on('data', (chunk) => { stderr = `${stderr}${chunk}`.slice(-4000); });
  let browser;
  let closed = false;
  const close = async () => {
    if (closed) return;
    closed = true;
    await browser?.close().catch(() => {});
    if (child.exitCode === null) {
      try { child.kill('SIGTERM'); } catch {}
      await waitForExit(child);
    }
    if (child.exitCode === null && childMatchesProfile(child.pid, config.profileCanonicalPath, config.executablePath)) {
      try { child.kill('SIGKILL'); } catch {}
      await waitForExit(child, 1000);
    }
    lease?.updateChild(null);
  };
  try {
    const endpoint = await waitForCdpEndpoint(config, child, () => stderr.trim(), () => childLaunchError, options.cdpTimeoutMs);
    browser = await connect(endpoint);
    const contexts = browser.contexts();
    if (contexts.length !== 1) throw new Error(`Chrome CDP default context count is ${contexts.length}, expected 1`);
    return { browser, child, close, context: contexts[0], endpoint };
  } catch (error) {
    await close();
    throw new BrowserConfigError(`Failed to launch independent Chrome over CDP: ${error.message}`, 'CDP_LAUNCH_FAILED');
  }
}

async function authCookieState(context) {
  const cookies = await context.cookies(['https://x.com', 'https://twitter.com']);
  const names = new Set(cookies.map((cookie) => cookie.name));
  const missing = [...AUTH_COOKIE_NAMES].filter((name) => !names.has(name));
  return { authenticated: missing.length === 0, missing };
}

function isLoginUrl(value) {
  try {
    const url = new URL(value);
    return url.pathname.includes('/login') || url.pathname.includes('/i/flow/login') || url.pathname.includes('/i/flow/signup');
  } catch { return false; }
}

async function pageAuthenticationState(page, options = {}) {
  const cookieState = await authCookieState(page.context());
  const url = page.url();
  const dom = await page.evaluate(() => ({
    hasAuthenticatedChrome: Boolean(document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"], [data-testid="AppTabBar_Home_Link"], a[data-testid="SideNav_NewTweet_Button"]')),
    hasLoginUi: Boolean(document.querySelector('a[href="/login"], a[href*="/i/flow/login"], [data-testid="loginButton"], [data-testid="LoginForm_Login_Button"]')),
  })).catch(() => ({ hasAuthenticatedChrome: false, hasLoginUi: false }));
  let protectedRedirect = false;
  if (options.expectedPath) {
    try {
      const actualPath = new URL(url).pathname.replace(/\/$/, '');
      const expectedPath = String(options.expectedPath).replace(/\/$/, '');
      protectedRedirect = actualPath !== expectedPath && (!dom.hasAuthenticatedChrome || dom.hasLoginUi);
    } catch {}
  }
  return {
    authenticated: cookieState.authenticated && !isLoginUrl(url) && !dom.hasLoginUi && !protectedRedirect,
    cookieState,
    dom,
    protectedRedirect,
    url,
  };
}

async function withAuthenticatedContext(options, operation, deps = {}) {
  const config = options.config || preflightBrowserConfig(options.env || process.env, deps.fsModule || fs);
  const beginRefresh = deps.beginProfileRefresh || beginProfileRefresh;
  const commitRefresh = deps.commitProfileRefresh || commitProfileRefresh;
  const rollbackRefresh = deps.rollbackProfileRefresh || rollbackProfileRefresh;
  const launchBrowser = deps.launchCdpBrowser || launchCdpBrowser;
  const readAuthCookies = deps.authCookieState || authCookieState;
  const readPageAuth = deps.pageAuthenticationState || pageAuthenticationState;
  const lease = acquireProfileLease(config, deps);
  let active = null;
  let transaction = null;
  let refreshed = false;
  let refreshAllowed = true;
  let confirmed = false;
  let shuttingDown = false;

  const closeActive = async () => {
    if (!active) return;
    const handle = active;
    active = null;
    await handle.close();
  };
  const signalExit = async (code) => {
    if (shuttingDown) return;
    shuttingDown = true;
    await closeActive().catch(() => {});
    if (transaction && !transaction.committed) await rollbackRefresh(transaction).catch(() => {});
    lease.release();
    process.exit(code);
  };
  const onInt = () => { void signalExit(130); };
  const onTerm = () => { void signalExit(143); };
  process.once('SIGINT', onInt);
  process.once('SIGTERM', onTerm);
  const onExit = () => {
    if (active?.child && active.child.exitCode === null) stopExactChild(active.child.pid, config.profileCanonicalPath, config.executablePath);
    lease.release();
  };
  process.once('exit', onExit);

  try {
    if (!fs.existsSync(config.profileCanonicalPath)) {
      transaction = await beginRefresh(config, { source: config });
      refreshed = true;
    }
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        active = await launchBrowser(config, {
          headless: Boolean(options.headless),
          profileDirectory: config.profileDirectory,
          width: options.width,
          height: options.height,
          lease,
        }, deps);
        const cookies = await readAuthCookies(active.context);
        if (!cookies.authenticated) {
          throw new XAuthenticationError(`independent Chrome profile is missing authentication cookies: ${cookies.missing.join(', ')}`, { stage: 'cookie-gate' });
        }
        const api = {
          browser: active.browser,
          config,
          context: active.context,
          disableAuthRefresh() { refreshAllowed = false; },
          profileDirectory: config.profileDirectory,
          refreshed,
          async confirmAuthenticated(page, authOptions = {}) {
            const state = await readPageAuth(page, authOptions);
            if (!state.authenticated) throw new XAuthenticationError(`X authentication check failed at ${state.url}`, state);
            confirmed = true;
            if (transaction) {
              await commitRefresh(transaction);
              transaction = null;
            }
            return state;
          },
        };
        const result = await operation(api);
        if (!confirmed) throw new Error('X-facing operation completed without confirmAuthenticated()');
        return result;
      } catch (error) {
        await closeActive();
        if (error instanceof XAuthenticationError && refreshAllowed && !refreshed) {
          transaction = await beginRefresh(config, { source: config });
          refreshed = true;
          confirmed = false;
          continue;
        }
        if (transaction && !transaction.committed) {
          await rollbackRefresh(transaction);
          transaction = null;
        }
        throw error;
      }
    }
    throw new XAuthenticationError('X authentication still failed after one profile refresh');
  } finally {
    await closeActive().catch(() => {});
    if (transaction && !transaction.committed) await rollbackRefresh(transaction).catch(() => {});
    process.removeListener('SIGINT', onInt);
    process.removeListener('SIGTERM', onTerm);
    process.removeListener('exit', onExit);
    lease.release();
  }
}

module.exports = {
  AUTH_COOKIE_NAMES,
  PROFILE_AUTH_ENTRIES,
  BrowserConfigError,
  XAuthenticationError,
  accountConfigPath,
  acquireProfileLease,
  authCookieState,
  beginProfileRefresh,
  buildChromeArgs,
  commandMatchesProfile,
  commitProfileRefresh,
  findChromeProfileByEmail,
  isLoginUrl,
  launchCdpBrowser,
  maskEmail,
  normalizeEmail,
  pageAuthenticationState,
  preflightBrowserConfig,
  readAccountConfig,
  resolveAccountEmail,
  resolveBrowserConfig,
  resolveCanonicalPath,
  resolveSourceUserDataDir,
  rollbackProfileRefresh,
  stopExactChild,
  withAuthenticatedContext,
  writeAccountConfig,
};
