// lib/nav-helper.cjs — latency- & rate-limit-tolerant navigation
//
// WHY: X serves HTTP 429 (SearchTimeline / UserByScreenName quota) as a page that
// renders "出错了。请尝试重新加载。" with a retry button. Naively reloading on error
// FEEDS the 429 (each reload is another request). The correct response is to WAIT
// (the rate-limit window is the recovery) with an exponentially growing interval,
// THEN re-navigate. High-latency VPNs also make fixed `sleep` waits lose the race
// against slow SPA rendering — so we wait for the real content selector, not a timer.
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

// Probe: is there an error page / is the needed selector present?
async function pageState(page, needSel) {
  return await page.evaluate((needSel) => {
    const b = (document.body && document.body.innerText) || '';
    const hasErr = /出错了|尝试重新加载|重新加载|Something went wrong|Try reloading/i.test(b);
    const hasSel = needSel ? !!document.querySelector(needSel) : true;
    return { hasErr, hasSel, len: b.length };
  }, needSel || null);
}

async function gotoRobust(page, url, opts = {}) {
  const needSel = opts.needSel || null;
  const settle = opts.settle != null ? opts.settle : 5000;
  const maxAttempts = opts.retries != null ? opts.retries : 6;
  const base = opts.backoffBase != null ? opts.backoffBase : 20000;
  const cap = opts.backoffCap != null ? opts.backoffCap : 300000;
  const label = opts.label || url.replace(/^https:\/\/x\.com\//, '');
  // Jitter source — tests inject () => 0 for determinism.
  const rnd = typeof opts.randomFn === 'function' ? opts.randomFn : Math.random;
  let waitedMs = 0;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    } catch (e) {
      /* nav timeout under latency — treat as soft fail -> backoff */
    }
    await sleep(settle);
    if (needSel) {
      try { await page.waitForSelector(needSel, { timeout: 15000 }); } catch {}
    }
    const st = await pageState(page, needSel);
    if (st.hasSel && !st.hasErr) return { ok: true, attempts: attempt, waitedMs };
    if (attempt >= maxAttempts) break;

    const wait = backoffMs(attempt, base, cap) + Math.floor(rnd() * 5000);
    waitedMs += wait;
    process.stderr.write(
      `[nav] ${label}: ${st.hasErr ? '出错了/429' : 'no-content'} -> backoff ${Math.round(wait / 1000)}s (next try ${attempt + 1}/${maxAttempts})\n`
    );
    await sleep(wait); // the WAIT is the recovery; next loop re-navigates
  }

  const fin = await pageState(page, needSel);
  return { ok: fin.hasSel && !fin.hasErr, attempts: maxAttempts, waitedMs };
}

module.exports = { gotoRobust, pageState, sleep };
