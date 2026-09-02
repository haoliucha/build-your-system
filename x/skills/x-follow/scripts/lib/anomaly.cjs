// lib/anomaly.cjs — anomaly detection (CAPTCHA / GENERIC_NAV_ERROR / LOGIN_REDIRECT /
// ACCOUNT_RESTRICTED / WEBDRIVER_DETECTED / EMPTY_PAGE), reused by campaign / smoke-test.
//
// KEY FIX: rate-limit / restriction phrases are matched ONLY against the page "chrome"
// (X's own banners/interstitials), NOT against ANY user-controlled text. User content
// includes not just TWEETS but also the profile BIO (UserDescription), display name
// (UserName), search/followers list rows (UserCell), and profile header fields
// (location / website). Otherwise an account whose bio or tweets contain "请稍后再试 /
// 账户被限制 / account suspended" false-triggers navigation/restriction handling — and a
// malicious account could halt a campaign just by putting such a phrase in its bio.
// inChrome(p) = body.includes(p) && !userText.includes(p), where userText is the union
// of all user-controlled regions.
//
// The matching logic lives in the PURE classifyAnomaly() so it is unit-testable without
// a browser; the browser-injected ANOMALY_DETECTOR_JS gathers the DOM facts and calls the
// same logic (patterns injected from the shared constants below).

const fs = require('fs');
const path = require('path');

const RL_PATTERNS = [
  'rate limit', 'rate-limit', 'rate_limit',
  'try again later', 'try again in',
  'temporary restriction', 'temporarily restricted',
  'limit reached', 'limit exceeded',
  '操作太频繁', '操作过于频繁',
  '请稍后再试', '请稍候再试',
  '你目前无法关注', '现在无法关注',
  'unable to follow at this time',
];

const LOCK_PATTERNS = [
  'account has been locked', 'your account has been locked',
  'account suspended', 'has been suspended',
  'account is restricted', 'account is currently restricted',
  '账号被锁定', '账号已被锁定', '账号已被冻结', '账号已暂停',
  '账户已被锁定', '账户已暂停', '账户被限制',
];

// Exit codes per anomaly type — the watchdog (run.sh) HALTs on 10-14.
const EXIT_CODES = {
  CAPTCHA: 10,
  RATE_LIMIT: 11,
  LOGIN_REDIRECT: 12,
  ACCOUNT_RESTRICTED: 13,
  WEBDRIVER_DETECTED: 14,
  CONSECUTIVE_ERRORS: 15,
  EMPTY_PAGE: 16,
  GENERIC_NAV_ERROR: 18,
};

// PURE classifier. input: { bodyText, userText, path, webdriver, hasCaptcha }
// `userText` = union of all user-controlled regions (tweets + bio + name + usercells…).
// `tweetText` is still accepted as a backward-compatible alias for `userText`.
// Returns { type, text } or null. inChrome scopes phrase matching to non-user UI.
function classifyAnomaly(input) {
  const bodyFull = (input.bodyText || '').toLowerCase();
  const userText = (input.userText != null ? input.userText : (input.tweetText || '')).toLowerCase();
  const inChrome = (p) => {
    const lp = p.toLowerCase();
    return bodyFull.includes(lp) && !userText.includes(lp);
  };

  const path = input.path || '';
  if (input.hasLoginUi || path.includes('/login') || path.includes('/i/flow/login') || path.includes('/i/flow/signup')) {
    return { type: 'LOGIN_REDIRECT', text: path || 'login UI visible' };
  }

  if (input.hasCaptcha) return { type: 'CAPTCHA', text: 'human verification challenge appeared' };

  // Text alone is not HTTP evidence. X uses these phrases on generic retry/error pages,
  // so only the response observer in nav-helper may produce RATE_LIMIT.
  for (const p of RL_PATTERNS) if (inChrome(p)) return { type: 'GENERIC_NAV_ERROR', text: p };

  for (const p of LOCK_PATTERNS) if (inChrome(p)) return { type: 'ACCOUNT_RESTRICTED', text: p };

  if (input.webdriver === true) return { type: 'WEBDRIVER_DETECTED', text: 'navigator.webdriver=true' };

  if (!bodyFull || bodyFull.length < 50) return { type: 'EMPTY_PAGE', text: 'body innerText < 50 chars' };

  return null;
}

// Browser-injected detector string: gathers DOM facts, then applies the SAME logic
// (patterns + inChrome) inline. Kept in sync with classifyAnomaly via shared constants.
const ANOMALY_DETECTOR_JS = `(() => {
  const RL = ${JSON.stringify(RL_PATTERNS)};
  const LOCK = ${JSON.stringify(LOCK_PATTERNS)};
  const captcha = document.querySelector(
    'iframe[src*="captcha"], iframe[src*="arkose"], div[data-testid*="captcha"], div[id*="recaptcha"], div[data-testid*="OCFLogin"]'
  );
  const path = window.location.pathname;
  const loginUi = document.querySelector('a[href="/login"], a[href*="/i/flow/login"], [data-testid="loginButton"], [data-testid="LoginForm_Login_Button"]');
  if (loginUi || path.includes('/login') || path.includes('/i/flow/login') || path.includes('/i/flow/signup')) {
    return { type: 'LOGIN_REDIRECT', text: path || 'login UI visible' };
  }
  if (captcha) return { type: 'CAPTCHA', text: 'human verification challenge appeared' };

  const bodyFull = ((document.body && document.body.innerText) || '').toLowerCase();
  let userText = '';
  try { userText = [...document.querySelectorAll('[data-testid="tweetText"], article[role="article"], [data-testid="UserDescription"], [data-testid="UserName"], [data-testid="UserCell"], [data-testid="UserProfileHeader_Items"]')].map(e => (e.innerText || '')).join(' ').toLowerCase(); } catch (e) {}
  const inChrome = (p) => { const lp = p.toLowerCase(); return bodyFull.includes(lp) && !userText.includes(lp); };

  for (const p of RL) { if (inChrome(p)) return { type: 'GENERIC_NAV_ERROR', text: p }; }

  for (const p of LOCK) { if (inChrome(p)) return { type: 'ACCOUNT_RESTRICTED', text: p }; }

  if (navigator.webdriver === true) return { type: 'WEBDRIVER_DETECTED', text: 'navigator.webdriver=true' };

  if (!document.body || document.body.innerText.length < 50) {
    return { type: 'EMPTY_PAGE', text: 'body innerText < 50 chars' };
  }
  return null;
})()`;

async function detectAnomaly(page) {
  try {
    return await page.evaluate(ANOMALY_DETECTOR_JS);
  } catch (e) {
    return { type: 'EVAL_ERROR', text: e.message };
  }
}

function writeAlert(alertPath, info) {
  const lines = [
    `=== X-FOLLOW CAMPAIGN ALERT ===`,
    `Timestamp: ${new Date().toISOString()}`,
    `Anomaly Type: ${info.type}`,
    `Text: ${info.text || ''}`,
    `Handle (if any): ${info.handle || 'N/A'}`,
    `URL: ${info.url || 'N/A'}`,
    `Exit Code: ${EXIT_CODES[info.type] || 99}`,
    `Screenshot: ${info.screenshotPath || 'N/A'}`,
    `Fallback Screenshot: ${info.fallbackScreenshotPath || 'N/A'}`,
    `Evidence JSON: ${info.evidencePath || 'N/A'}`,
    `Capture Error: ${info.captureError || 'N/A'}`,
    `Rate-limit cooldown until: ${info.rateLimitCooldownUntil || 'N/A'}`,
    ``,
    `=== ACTION REQUIRED ===`,
    `1. Inspect this alert and the run log; the dedicated CDP Chrome child has been closed`,
    `2. If CAPTCHA: solve it and decide whether to resume`,
    `3. If RATE_LIMIT: an HTTP 429 was observed; wait before the next campaign`,
    `4. If LOGIN_REDIRECT: verify the configured Chrome account; one selective refresh is automatic`,
    `5. If ACCOUNT_RESTRICTED: STOP. Account may be flagged. Wait days, do not retry.`,
    `6. If GENERIC_NAV_ERROR: X showed a generic retry page without HTTP 429 evidence`,
    `7. If WEBDRIVER_DETECTED: check the CDP launch args, then re-run smoke-test`,
    ``,
    `=== RECENT CONTEXT ===`,
    `Profile dir: ${info.profileDir || 'N/A'}`,
    `Tracker: ${info.trackerPath || 'N/A'}`,
  ];
  if (info.recentLog) lines.push(`Recent log:`, info.recentLog);
  fs.writeFileSync(alertPath, lines.join('\n') + '\n');
}

function safeSegment(value, fallback) {
  const normalized = String(value || '').replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '');
  return normalized || fallback;
}

function writeJsonAtomic(filePath, value) {
  const temporaryPath = path.join(path.dirname(filePath), `.${path.basename(filePath)}.${process.pid}.tmp`);
  fs.writeFileSync(temporaryPath, JSON.stringify(value, null, 2), { mode: 0o600 });
  fs.renameSync(temporaryPath, filePath);
  try { fs.chmodSync(filePath, 0o600); } catch {}
}

// Capture the visible browser state BEFORE the CDP context closes. A background API 429
// may leave the visible profile looking normal, so the PNG is paired with structured
// network evidence, the current URL/title, viewport, and a bounded page-text excerpt.
async function captureFailureEvidence(page, alertPath, info = {}) {
  const timestamp = new Date().toISOString();
  const evidenceDir = path.join(path.dirname(alertPath), 'evidence');
  fs.mkdirSync(evidenceDir, { recursive: true, mode: 0o700 });
  try { fs.chmodSync(evidenceDir, 0o700); } catch {}
  const stem = [
    timestamp.replace(/[:.]/g, '-'),
    safeSegment(info.type, 'ERROR'),
    safeSegment(info.handle, 'page'),
  ].join('-');
  const screenshotPath = path.join(evidenceDir, `${stem}.png`);
  const evidencePath = path.join(evidenceDir, `${stem}.json`);
  const captureErrors = [];

  let pageState = {};
  try {
    pageState = await page.evaluate(() => ({
      url: window.location.href,
      title: document.title || '',
      bodyText: ((document.body && document.body.innerText) || '').slice(0, 5000),
      viewport: { width: window.innerWidth, height: window.innerHeight, devicePixelRatio: window.devicePixelRatio },
    }));
  } catch (error) {
    captureErrors.push(`page-state: ${error.message}`);
    try { pageState.url = page.url(); } catch {}
  }

  let savedScreenshotPath = null;
  let fallbackScreenshotPath = null;
  try {
    await page.screenshot({ path: screenshotPath, fullPage: false, animations: 'disabled', timeout: 10000 });
    try { fs.chmodSync(screenshotPath, 0o600); } catch {}
    savedScreenshotPath = screenshotPath;
  } catch (error) {
    captureErrors.push(`screenshot: ${error.message}`);
    if (info.lastStablePath && fs.existsSync(info.lastStablePath)) fallbackScreenshotPath = info.lastStablePath;
  }

  const evidence = {
    schemaVersion: 1,
    capturedAt: timestamp,
    anomaly: {
      type: info.type || 'UNKNOWN',
      text: info.text || '',
      handle: info.handle || null,
      context: info.context || null,
      httpStatus: info.httpStatus || null,
      responseUrl: info.responseUrl || null,
      rateLimitCooldownUntil: info.rateLimitCooldownUntil || null,
    },
    page: pageState,
    screenshotPath: savedScreenshotPath,
    fallbackScreenshotPath,
    captureErrors,
  };
  let savedEvidencePath = null;
  try {
    writeJsonAtomic(evidencePath, evidence);
    savedEvidencePath = evidencePath;
  } catch (error) {
    captureErrors.push(`evidence-json: ${error.message}`);
  }
  return {
    screenshotPath: savedScreenshotPath,
    fallbackScreenshotPath,
    evidencePath: savedEvidencePath,
    captureError: captureErrors.length ? captureErrors.join(' | ') : null,
    pageTitle: pageState.title || null,
    url: pageState.url || info.url || null,
  };
}

async function writeAlertWithEvidence(page, alertPath, info) {
  let evidence;
  try { evidence = await captureFailureEvidence(page, alertPath, info); }
  catch (error) { evidence = { screenshotPath: null, evidencePath: null, captureError: error.message }; }
  const merged = { ...info, ...evidence };
  fs.mkdirSync(path.dirname(alertPath), { recursive: true, mode: 0o700 });
  writeAlert(alertPath, merged);
  return merged;
}

module.exports = {
  RL_PATTERNS, LOCK_PATTERNS, EXIT_CODES,
  classifyAnomaly, ANOMALY_DETECTOR_JS, detectAnomaly,
  captureFailureEvidence, writeAlert, writeAlertWithEvidence,
};
