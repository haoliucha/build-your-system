// lib/nav-helper.cjs — latency-tolerant navigation with evidence-based HTTP classification.
//
// A generic "Something went wrong" page is not proof of HTTP 429. Only an observed
// navigation/API response status may produce RATE_LIMIT. Generic pages retain bounded
// latency backoff, while a real 429 returns immediately so the caller can fail closed or
// apply its explicit harvest cooldown policy.
//
// gotoRobust(page, url, { needSel, settle, retries, backoffBase, backoffCap, label })
//   needSel     CSS selector that must be present for the page to count as "loaded"
//   settle      ms to wait after goto before checking (default 5000)
//   retries     max attempts (default 6)
//   backoffBase first backoff in ms (default 20000) — grows base*2^(n-1)
//   backoffCap  max backoff in ms (default 300000)
// Returns { ok, attempts, waitedMs }.

const { backoffMs } = require('./filters.cjs');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function isRelevantXResponse(response) {
  try {
    const url = new URL(response.url());
    return url.hostname === 'x.com' || url.hostname.endsWith('.x.com')
      || url.hostname === 'twitter.com' || url.hostname.endsWith('.twitter.com');
  } catch { return false; }
}

function isRelatedXApiResponse(response) {
  if (!isRelevantXResponse(response)) return false;
  try {
    const url = new URL(response.url());
    return url.hostname === 'api.x.com'
      || url.pathname.includes('/i/api/')
      || url.pathname.includes('/graphql/')
      || /timeline/i.test(url.pathname);
  } catch { return false; }
}

function responseEvidence(response, options = {}) {
  if (!response || !isRelevantXResponse(response)) return null;
  // The document returned by page.goto is evidence for that navigation. Background
  // responses count only when they are an X API/timeline request; an unrelated asset or
  // telemetry response must never turn the whole workflow into RATE_LIMIT.
  if (!options.navigation && !isRelatedXApiResponse(response)) return null;
  const status = response.status();
  if (status === 429) return { reason: 'RATE_LIMIT', httpStatus: status, responseUrl: response.url() };
  if (status === 401) return { reason: 'LOGIN_REDIRECT', httpStatus: status, responseUrl: response.url() };
  return null;
}

// Observe API/timeline responses produced after navigation (scrolling or a mutation).
// page.goto responses are classified inside gotoRobust; this monitor intentionally uses
// responseEvidence's stricter background-response rules so assets and telemetry cannot
// manufacture RATE_LIMIT. The listener is always removed after the supplied operation.
async function captureXResponseEvidence(page, operation) {
  let evidence = null;
  const observe = (response) => { evidence = evidence || responseEvidence(response); };
  if (typeof page.on === 'function') page.on('response', observe);
  try {
    const value = await operation();
    return { value, evidence };
  } finally {
    if (typeof page.off === 'function') page.off('response', observe);
    else if (typeof page.removeListener === 'function') page.removeListener('response', observe);
  }
}

function loginUrl(value) {
  try {
    const pathname = new URL(value).pathname;
    return pathname.includes('/login') || pathname.includes('/i/flow/login') || pathname.includes('/i/flow/signup');
  } catch { return false; }
}

// Probe: is there a generic error page / is the needed selector present?
async function pageState(page, needSel) {
  return await page.evaluate((needSel) => {
    const b = (document.body && document.body.innerText) || '';
    const hasSel = needSel ? !!document.querySelector(needSel) : true;
    const errorText = /出错了|尝试重新加载|重新加载|Something went wrong|Try reloading/i.test(b);
    const retryButton = [...document.querySelectorAll('button, [role="button"]')]
      .some((element) => /重试|再试一次|Try again|Retry/i.test(element.innerText || element.textContent || ''));
    const hasGenericError = errorText && (retryButton || !hasSel);
    return { hasErr: hasGenericError, hasGenericError, hasSel, len: b.length };
  }, needSel || null);
}

async function gotoRobust(page, url, opts = {}) {
  const needSel = opts.needSel || null;
  const settle = opts.settle != null ? opts.settle : 5000;
  const maxAttempts = opts.retries != null ? opts.retries : 6;
  const base = opts.backoffBase != null ? opts.backoffBase : 20000;
  const cap = opts.backoffCap != null ? opts.backoffCap : 300000;
  const label = opts.label || url.replace(/^https:\/\/x\.com\//, '');
  const traceFn = typeof opts.trace === 'function' ? opts.trace : null;
  const trace = (event, data = {}) => { try { traceFn?.(event, { label, ...data }); } catch {} };
  // Jitter source — tests inject () => 0 for determinism.
  const rnd = typeof opts.randomFn === 'function' ? opts.randomFn : Math.random;
  let waitedMs = 0;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    trace('goto_attempt_start', { attempt, maxAttempts });
    let evidence = null;
    const observe = (response) => { evidence = evidence || responseEvidence(response); };
    if (typeof page.on === 'function') page.on('response', observe);
    try {
      try {
        const navigationResponse = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
        evidence = evidence || responseEvidence(navigationResponse, { navigation: true });
        trace('goto_document_response', { attempt, status: navigationResponse?.status?.() || null });
      } catch (e) {
        /* nav timeout under latency — treat as soft fail -> backoff */
        trace('goto_exception', { attempt, error: e.message || String(e) });
      }
      if (evidence) { trace('goto_attempt_end', { attempt, ok: false, reason: evidence.reason }); return { ok: false, attempts: attempt, waitedMs, ...evidence }; }
      await sleep(settle);
      if (evidence) { trace('goto_attempt_end', { attempt, ok: false, reason: evidence.reason }); return { ok: false, attempts: attempt, waitedMs, ...evidence }; }
      if (needSel) {
        try { await page.waitForSelector(needSel, { timeout: 15000 }); } catch {}
      }
      if (evidence) { trace('goto_attempt_end', { attempt, ok: false, reason: evidence.reason }); return { ok: false, attempts: attempt, waitedMs, ...evidence }; }
      const st = await pageState(page, needSel);
      if (loginUrl(page.url())) { trace('goto_attempt_end', { attempt, ok: false, reason: 'LOGIN_REDIRECT' }); return { ok: false, attempts: attempt, waitedMs, reason: 'LOGIN_REDIRECT' }; }
      if (st.hasSel && !st.hasGenericError) { trace('goto_attempt_end', { attempt, ok: true, reason: null, bodyLength: st.len }); return { ok: true, attempts: attempt, waitedMs, reason: null }; }
      if (attempt >= maxAttempts) break;

      const wait = backoffMs(attempt, base, cap) + Math.floor(rnd() * 5000);
      waitedMs += wait;
      process.stderr.write(
        `[nav] ${label}: ${st.hasGenericError ? 'generic-error-page' : 'no-content'} -> backoff ${Math.round(wait / 1000)}s (next try ${attempt + 1}/${maxAttempts})\n`
      );
      trace('goto_backoff', { attempt, waitMs: wait, reason: st.hasGenericError ? 'GENERIC_NAV_ERROR' : 'NO_CONTENT' });
      await sleep(wait); // the WAIT is the recovery; next loop re-navigates
    } finally {
      if (typeof page.off === 'function') page.off('response', observe);
      else if (typeof page.removeListener === 'function') page.removeListener('response', observe);
    }
  }

  const fin = await pageState(page, needSel);
  trace('goto_end', { ok: fin.hasSel && !fin.hasGenericError, attempts: maxAttempts, reason: fin.hasGenericError ? 'GENERIC_NAV_ERROR' : 'NO_CONTENT' });
  return {
    ok: fin.hasSel && !fin.hasGenericError,
    attempts: maxAttempts,
    waitedMs,
    reason: fin.hasGenericError ? 'GENERIC_NAV_ERROR' : 'NO_CONTENT',
  };
}

module.exports = { captureXResponseEvidence, gotoRobust, isRelatedXApiResponse, isRelevantXResponse, loginUrl, pageState, responseEvidence, sleep };
