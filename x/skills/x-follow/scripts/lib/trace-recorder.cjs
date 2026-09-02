// lib/trace-recorder.cjs — minimal, redacted page/network trace for x-follow.
//
// The recorder is intentionally not a HAR writer. It stores semantic page phases and
// X API/GraphQL metadata only: operation, status, duration, resource type, and the three
// x-rate-limit headers. Cookies, auth/CSRF headers, request bodies, GraphQL variables,
// and full query strings never reach disk.

const fs = require('fs');
const path = require('path');

function safeSegment(value, fallback = 'item') {
  const segment = String(value || '').replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '');
  return segment || fallback;
}

function isXHost(hostname) {
  return hostname === 'x.com' || hostname.endsWith('.x.com')
    || hostname === 'twitter.com' || hostname.endsWith('.twitter.com');
}

function normalizeXUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    if (!isXHost(url.hostname)) return null;
    const graphql = url.pathname.match(/\/(?:i\/api\/)?graphql\/[^/]+\/([^/]+)/i);
    const operation = graphql ? decodeURIComponent(graphql[1]) : null;
    return {
      host: url.hostname,
      path: url.pathname,
      operation,
      endpointKey: operation ? `graphql:${operation}` : url.pathname,
    };
  } catch { return null; }
}

function pickRateLimitHeaders(headers = {}) {
  const lower = {};
  for (const [key, value] of Object.entries(headers || {})) lower[String(key).toLowerCase()] = String(value);
  const picked = {};
  for (const name of ['x-rate-limit-limit', 'x-rate-limit-remaining', 'x-rate-limit-reset']) {
    if (Object.prototype.hasOwnProperty.call(lower, name)) picked[name] = lower[name];
  }
  return picked;
}

function ensurePrivateDir(dir) {
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  try { fs.chmodSync(dir, 0o700); } catch {}
}

function appendPrivateJsonl(filePath, event) {
  ensurePrivateDir(path.dirname(filePath));
  fs.appendFileSync(filePath, `${JSON.stringify(event)}\n`, { mode: 0o600 });
  try { fs.chmodSync(filePath, 0o600); } catch {}
}

function createTraceRecorder(options = {}) {
  const enabled = options.enabled === true;
  const traceDir = options.traceDir;
  const source = options.source || 'auto';
  const nowFn = options.nowFn || Date.now;
  const flowPath = path.join(traceDir, `${source}-flow.jsonl`);
  const screenshotDir = path.join(traceDir, 'screenshots');
  const lastStablePath = options.lastStablePath;
  const pending = new Set();
  const requestStart = new WeakMap();
  let context = { correlationId: null, handle: null, phase: 'idle' };
  let attached = null;
  let sequence = 0;

  function snapshotContext() { return { ...context }; }

  function mark(event, data = {}) {
    if (!enabled) return null;
    const record = {
      schemaVersion: 1,
      sequence: ++sequence,
      at: new Date(nowFn()).toISOString(),
      source,
      event,
      ...snapshotContext(),
      ...data,
    };
    appendPrivateJsonl(flowPath, record);
    return record;
  }

  function setContext(next = {}) {
    context = { ...context, ...next };
    return snapshotContext();
  }

  function track(promise) {
    pending.add(promise);
    promise.finally(() => pending.delete(promise));
  }

  function attach(page) {
    if (!enabled || attached) return;
    const onRequest = (request) => {
      const normalized = normalizeXUrl(request.url());
      if (!normalized) return;
      const startedAt = nowFn();
      requestStart.set(request, { startedAt, context: snapshotContext(), normalized });
      mark('network_request', {
        ...normalized,
        method: request.method(),
        resourceType: request.resourceType(),
      });
    };
    const onResponse = (response) => {
      const request = response.request();
      const started = requestStart.get(request);
      const normalized = started?.normalized || normalizeXUrl(response.url());
      if (!normalized) return;
      const task = (async () => {
        let headers = {};
        try { headers = await response.allHeaders(); } catch {}
        const startedAt = started?.startedAt || nowFn();
        const requestContext = started?.context || snapshotContext();
        mark('network_response', {
          ...requestContext,
          ...normalized,
          method: request.method(),
          resourceType: request.resourceType(),
          status: response.status(),
          durationMs: Math.max(0, nowFn() - startedAt),
          rateLimit: pickRateLimitHeaders(headers),
        });
      })();
      track(task);
    };
    const onRequestFailed = (request) => {
      const started = requestStart.get(request);
      const normalized = started?.normalized || normalizeXUrl(request.url());
      if (!normalized) return;
      mark('network_failed', {
        ...(started?.context || snapshotContext()),
        ...normalized,
        method: request.method(),
        resourceType: request.resourceType(),
        durationMs: Math.max(0, nowFn() - (started?.startedAt || nowFn())),
        failure: request.failure()?.errorText || 'unknown',
      });
    };
    const onCrash = () => mark('page_crash');
    const onClose = () => mark('page_close');
    page.on('request', onRequest);
    page.on('response', onResponse);
    page.on('requestfailed', onRequestFailed);
    page.on('crash', onCrash);
    page.on('close', onClose);
    attached = { page, onRequest, onResponse, onRequestFailed, onCrash, onClose };
  }

  async function checkpoint(page, details = {}) {
    const handle = details.handle || context.handle || 'page';
    const phase = details.phase || context.phase || 'stable';
    let destination = lastStablePath;
    if (enabled) {
      ensurePrivateDir(screenshotDir);
      destination = path.join(screenshotDir, `${String(++sequence).padStart(4, '0')}-${safeSegment(handle)}-${safeSegment(phase)}.png`);
    } else if (destination) {
      ensurePrivateDir(path.dirname(destination));
    }
    if (!destination) return null;
    await page.screenshot({ path: destination, fullPage: false, animations: 'disabled', timeout: 10000 });
    try { fs.chmodSync(destination, 0o600); } catch {}
    if (enabled && lastStablePath) {
      fs.copyFileSync(destination, lastStablePath);
      try { fs.chmodSync(lastStablePath, 0o600); } catch {}
    }
    mark('checkpoint', { handle, phase, screenshotPath: destination });
    return destination;
  }

  async function flush() {
    if (pending.size) await Promise.allSettled([...pending]);
  }

  async function detach() {
    if (!attached) return;
    const { page, onRequest, onResponse, onRequestFailed, onCrash, onClose } = attached;
    page.off('request', onRequest);
    page.off('response', onResponse);
    page.off('requestfailed', onRequestFailed);
    page.off('crash', onCrash);
    page.off('close', onClose);
    attached = null;
    await flush();
  }

  return {
    enabled,
    flowPath,
    lastStablePath,
    mark,
    setContext,
    attach,
    checkpoint,
    flush,
    detach,
  };
}

module.exports = {
  appendPrivateJsonl,
  createTraceRecorder,
  normalizeXUrl,
  pickRateLimitHeaders,
  safeSegment,
};
