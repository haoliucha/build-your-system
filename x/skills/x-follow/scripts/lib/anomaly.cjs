// lib/anomaly.cjs — anomaly detection (CAPTCHA / RATE_LIMIT / LOGIN_REDIRECT /
// ACCOUNT_RESTRICTED / WEBDRIVER_DETECTED / EMPTY_PAGE), reused by campaign / smoke-test.
//
// KEY FIX (was a job-local-only patch): rate-limit / restriction phrases are matched
// ONLY against the page "chrome" (frames/banners), NOT tweet text. Otherwise viewing a
// crypto account whose TWEETS mention "账户被限制 / rate limit" false-triggers
// ACCOUNT_RESTRICTED/RATE_LIMIT. inChrome(p) = body.includes(p) && !tweetText.includes(p).
//
// The matching logic lives in the PURE classifyAnomaly() so it is unit-testable without
// a browser; the browser-injected ANOMALY_DETECTOR_JS gathers the DOM facts and calls the
// same logic (patterns injected from the shared constants below).

const fs = require('fs');

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
};

// PURE classifier. input: { bodyText, tweetText, path, webdriver, hasCaptcha }
// Returns { type, text } or null. inChrome scopes phrase matching to non-tweet UI.
function classifyAnomaly(input) {
  const bodyFull = (input.bodyText || '').toLowerCase();
  const tweetTexts = (input.tweetText || '').toLowerCase();
  const inChrome = (p) => {
    const lp = p.toLowerCase();
    return bodyFull.includes(lp) && !tweetTexts.includes(lp);
  };

  if (input.hasCaptcha) return { type: 'CAPTCHA', text: 'human verification or login challenge appeared' };

  for (const p of RL_PATTERNS) if (inChrome(p)) return { type: 'RATE_LIMIT', text: p };

  const path = input.path || '';
  if (path.includes('/login') || path.includes('/i/flow/login') || path.includes('/i/flow/signup')) {
    return { type: 'LOGIN_REDIRECT', text: path };
  }

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
    'iframe[src*="captcha"], iframe[src*="arkose"], div[data-testid*="captcha"], div[id*="recaptcha"], div[data-testid*="OCFLogin"], div[data-testid*="LoginForm_Login_Button"]'
  );
  if (captcha) return { type: 'CAPTCHA', text: 'human verification or login challenge appeared' };

  const bodyFull = ((document.body && document.body.innerText) || '').toLowerCase();
  let tweetTexts = '';
  try { tweetTexts = [...document.querySelectorAll('[data-testid="tweetText"], article[role="article"]')].map(e => (e.innerText || '')).join(' ').toLowerCase(); } catch (e) {}
  const inChrome = (p) => { const lp = p.toLowerCase(); return bodyFull.includes(lp) && !tweetTexts.includes(lp); };

  for (const p of RL) { if (inChrome(p)) return { type: 'RATE_LIMIT', text: p }; }

  const path = window.location.pathname;
  if (path.includes('/login') || path.includes('/i/flow/login') || path.includes('/i/flow/signup')) {
    return { type: 'LOGIN_REDIRECT', text: path };
  }

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
    ``,
    `=== ACTION REQUIRED ===`,
    `1. Open the Chrome window (still running) and inspect manually`,
    `2. If CAPTCHA: solve it and decide whether to resume`,
    `3. If RATE_LIMIT: wait 24h before next campaign, or reduce target/pace`,
    `4. If LOGIN_REDIRECT: re-login profile dir, then re-launch campaign`,
    `5. If ACCOUNT_RESTRICTED: STOP. Account may be flagged. Wait days, do not retry.`,
    `6. If WEBDRIVER_DETECTED: check campaign.cjs launch args, re-run smoke-test`,
    ``,
    `=== RECENT CONTEXT ===`,
    `Profile dir: ${info.profileDir || 'N/A'}`,
    `Tracker: ${info.trackerPath || 'N/A'}`,
  ];
  if (info.recentLog) lines.push(`Recent log:`, info.recentLog);
  fs.writeFileSync(alertPath, lines.join('\n') + '\n');
}

module.exports = {
  RL_PATTERNS, LOCK_PATTERNS, EXIT_CODES,
  classifyAnomaly, ANOMALY_DETECTOR_JS, detectAnomaly, writeAlert,
};
