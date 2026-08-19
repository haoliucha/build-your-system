#!/usr/bin/env node
// runtime-state.cjs — host-neutral x-follow runtime locations and input validation.

const os = require('os');
const path = require('path');
const fs = require('fs');
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

function resolveCanonicalPath(dir) {
  const resolved = path.resolve(String(dir));
  try {
    return fs.realpathSync.native ? fs.realpathSync.native(resolved) : fs.realpathSync(resolved);
  } catch (error) {
    // A missing profile remains the responsibility of the existing profile-exists gate.
    // Before it exists, path.resolve still catches equal values and `..` normalization.
    if (error.code === 'ENOENT') return resolved;
    throw error;
  }
}

function resolveProfilePolicy(env = process.env) {
  const home = env.HOME || process.env.HOME || os.homedir();
  const sourceProfileDir = env.SOURCE_PROFILE_DIR
    || env.X_FOLLOW_SOURCE_PROFILE_DIR
    || path.join(home, '.config', 'playwright-chrome-profile');
  const profileDir = env.PROFILE_DIR
    || path.join(home, '.config', 'playwright-chrome-profile-campaign');
  return {
    sourceProfileDir,
    profileDir,
    sourceCanonicalPath: resolveCanonicalPath(sourceProfileDir),
    profileCanonicalPath: resolveCanonicalPath(profileDir),
  };
}

function assertIndependentProfile(env = process.env) {
  const policy = resolveProfilePolicy(env);
  if (policy.sourceCanonicalPath === policy.profileCanonicalPath) {
    throw new Error('PROFILE_DIR must not resolve to SOURCE_PROFILE_DIR; refusing to run on the source login profile');
  }
  return policy;
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

module.exports = {
  resolveRuntimeState,
  validateRunId,
  resolveFilterPolicy,
  resolveProfilePolicy,
  assertIndependentProfile,
};
