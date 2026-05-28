// detect-anomaly.cjs — 异常感知模块,被 campaign.cjs / smoke-test.cjs 复用
// 在 page evaluate 内检测 CAPTCHA / RATE_LIMIT / LOGIN_REDIRECT / ACCOUNT_RESTRICTED / WEBDRIVER_DETECTED

// 注入到浏览器内的检测函数(string form,供 page.evaluate)
const ANOMALY_DETECTOR_JS = `(() => {
  // a) Captcha / human-verification 模态
  const captcha = document.querySelector(
    'iframe[src*="captcha"], iframe[src*="arkose"], div[data-testid*="captcha"], div[id*="recaptcha"], div[data-testid*="OCFLogin"], div[data-testid*="LoginForm_Login_Button"]'
  );
  if (captcha) return { type: 'CAPTCHA', text: 'human verification or login challenge appeared' };

  // b) Rate limit 文本(en + zh)
  const body = (document.body && document.body.innerText || '').slice(0, 3000).toLowerCase();
  const rlPatterns = [
    'rate limit', 'rate-limit', 'rate_limit',
    'try again later', 'try again in',
    'temporary restriction', 'temporarily restricted',
    'limit reached', 'limit exceeded',
    '操作太频繁', '操作过于频繁',
    '请稍后再试', '请稍候再试',
    '你目前无法关注', '现在无法关注',
    'unable to follow at this time'
  ];
  for (const p of rlPatterns) {
    if (body.includes(p.toLowerCase())) return { type: 'RATE_LIMIT', text: p };
  }

  // c) 跳到登录页 / 重新认证
  const path = window.location.pathname;
  if (path.includes('/login') || path.includes('/i/flow/login') || path.includes('/i/flow/signup')) {
    return { type: 'LOGIN_REDIRECT', text: path };
  }

  // d) Account suspended / locked
  const lockPatterns = [
    'account has been locked', 'your account has been locked',
    'account suspended', 'has been suspended',
    'account is restricted', 'account is currently restricted',
    '账号被锁定', '账号已被锁定', '账号已被冻结', '账号已暂停',
    '账户已被锁定', '账户已暂停', '账户被限制'
  ];
  for (const p of lockPatterns) {
    if (body.includes(p.toLowerCase())) return { type: 'ACCOUNT_RESTRICTED', text: p };
  }

  // e) webdriver 突然变 true(被反向注入 / 启动参数失效)
  if (navigator.webdriver === true) return { type: 'WEBDRIVER_DETECTED', text: 'navigator.webdriver=true' };

  // f) 整页空白(可能 X 故障 / 网络异常)
  if (!document.body || document.body.innerText.length < 50) {
    return { type: 'EMPTY_PAGE', text: 'body innerText < 50 chars' };
  }

  return null;
})()`;

// Exit codes for each anomaly type — campaign.cjs reads these
const EXIT_CODES = {
  CAPTCHA: 10,
  RATE_LIMIT: 11,
  LOGIN_REDIRECT: 12,
  ACCOUNT_RESTRICTED: 13,
  WEBDRIVER_DETECTED: 14,
  CONSECUTIVE_ERRORS: 15,
  EMPTY_PAGE: 16,
};

// Helper: detect anomalies on the given page, return null or {type, text}
async function detectAnomaly(page) {
  try {
    return await page.evaluate(ANOMALY_DETECTOR_JS);
  } catch (e) {
    // page closed or eval failed — treat as soft error, caller decides
    return { type: 'EVAL_ERROR', text: e.message };
  }
}

// Helper: write ALERT.txt for human triage
const fs = require('fs');
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
    `Recent log lines (last 20):`,
  ];
  if (info.recentLog) {
    lines.push(info.recentLog);
  }
  fs.writeFileSync(alertPath, lines.join('\n') + '\n');
}

module.exports = {
  ANOMALY_DETECTOR_JS,
  EXIT_CODES,
  detectAnomaly,
  writeAlert,
};
