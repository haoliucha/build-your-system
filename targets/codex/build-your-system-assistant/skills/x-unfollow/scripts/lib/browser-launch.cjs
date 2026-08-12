'use strict';

function resolveHeadless(env = process.env) {
  const raw = env.XU_HEADLESS === undefined ? '1' : String(env.XU_HEADLESS);
  if (raw === '1') return true;
  if (raw === '0') return false;
  throw new Error('XU_HEADLESS must be 0 or 1');
}

function persistentContextOptions({ width, height }, env = process.env) {
  return {
    channel: 'chrome',
    headless: resolveHeadless(env),
    viewport: { width, height },
    ignoreDefaultArgs: ['--enable-automation'],
    args: ['--disable-blink-features=AutomationControlled'],
  };
}

module.exports = { resolveHeadless, persistentContextOptions };
