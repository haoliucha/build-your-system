'use strict';

function resolveHeadless(env = process.env) {
  const raw = env.XU_HEADLESS === undefined ? '1' : String(env.XU_HEADLESS);
  if (raw === '1') return true;
  if (raw === '0') return false;
  throw new Error('XU_HEADLESS must be 0 or 1');
}

function cdpSessionOptions({ width, height }, env = process.env) {
  return { headless: resolveHeadless(env), width, height };
}

module.exports = { cdpSessionOptions, resolveHeadless };
