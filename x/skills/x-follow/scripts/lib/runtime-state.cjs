#!/usr/bin/env node
// runtime-state.cjs — host-neutral x-follow runtime locations and input validation.

const os = require('os');
const path = require('path');
const { CRYPTO_TOKENS } = require('./filters.cjs');

function validateRunId(runId) {
  if (!/^[A-Za-z0-9._-]+$/.test(runId) || runId === '.' || runId === '..') {
    throw new Error('X_FOLLOW_RUN_ID must be a safe single path segment (letters, digits, ., _, -; not . or ..)');
  }
  return runId;
}

function resolveRuntimeState(env = process.env) {
  const home = env.HOME || process.env.HOME || os.homedir();
  const dataDir = env.X_FOLLOW_DATA_DIR || path.join(home, '.config', 'x-follow-data');
  const runId = validateRunId(env.X_FOLLOW_RUN_ID || 'current');
  const jobDir = env.JOB_DIR || path.join(dataDir, 'runs', runId);
  return {
    dataDir,
    runId,
    jobDir,
    queuePath: env.QUEUE_PATH || path.join(jobDir, 'queue.json'),
    trackerPath: env.TRACKER_PATH || path.join(jobDir, 'tracker.json'),
    logPath: env.LOG_PATH || path.join(jobDir, 'campaign.log'),
    alertPath: env.ALERT_PATH || path.join(jobDir, 'ALERT.txt'),
    statusPath: env.STATUS_PATH || path.join(jobDir, 'status.json'),
    skipGlob: env.SKIP_GLOB || path.join(dataDir, 'runs', '*', 'tracker.json'),
    lockPath: path.join(dataDir, 'network-run.lock'),
  };
}

function parseBinaryFlag(value, name, defaultValue) {
  if (value === undefined || value === '') return defaultValue;
  if (value === '0') return false;
  if (value === '1') return true;
  throw new Error(`${name} must be 0 or 1`);
}

function resolveFilterPolicy(env = process.env) {
  const filterCrypto = parseBinaryFlag(env.FILTER_CRYPTO, 'FILTER_CRYPTO', false);
  const noCrypto = Object.prototype.hasOwnProperty.call(env, 'NOCRYPTO')
    ? parseBinaryFlag(env.NOCRYPTO, 'NOCRYPTO', false)
    : filterCrypto;
  const bioBlacklist = Object.prototype.hasOwnProperty.call(env, 'BIO_BLACKLIST')
    ? String(env.BIO_BLACKLIST).split(',').map(token => token.trim()).filter(Boolean)
    : (filterCrypto ? [...CRYPTO_TOKENS] : []);
  return { filterCrypto, noCrypto, bioBlacklist };
}

module.exports = { resolveRuntimeState, validateRunId, resolveFilterPolicy };
