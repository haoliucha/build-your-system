#!/usr/bin/env node
// runtime-state.cjs — host-neutral x-follow runtime locations and input validation.

const os = require('os');
const path = require('path');
const fs = require('fs');
const { CRYPTO_TOKENS } = require('./filters.cjs');
const { resolveSourceUserDataDir } = require('./cdp-browser.cjs');

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
    pacingPath: env.PACING_PATH || path.join(dataDir, 'profile-pacing.json'),
    traceDir: env.TRACE_DIR || path.join(jobDir, 'trace'),
    lastStablePath: env.LAST_STABLE_PATH || path.join(jobDir, 'last-stable.png'),
    skipGlob: env.SKIP_GLOB || path.join(dataDir, 'runs', '*', 'tracker.json'),
    lockPath: path.join(dataDir, 'network-run.lock'),
  };
}

function resolveCanonicalPath(dir) {
  const resolved = path.resolve(String(dir));
  const missing = [];
  let existing = resolved;
  while (true) {
    try {
      const canonical = fs.realpathSync.native ? fs.realpathSync.native(existing) : fs.realpathSync(existing);
      return path.join(canonical, ...missing);
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      const parent = path.dirname(existing);
      if (parent === existing) return resolved;
      missing.unshift(path.basename(existing));
      existing = parent;
    }
  }
}

function containsPath(parent, candidate) {
  const relative = path.relative(parent, candidate);
  return relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative));
}

function resolveProfilePolicy(env = process.env) {
  const home = env.HOME || process.env.HOME || os.homedir();
  const sourceProfileDir = resolveSourceUserDataDir({ ...env, HOME: home });
  const profileDir = env.PROFILE_DIR
    || path.join(home, '.config', 'playwright-chrome-profile-campaign');
  return {
    sourceUserDataDir: sourceProfileDir,
    sourceProfileDir,
    profileDir,
    sourceCanonicalPath: resolveCanonicalPath(sourceProfileDir),
    profileCanonicalPath: resolveCanonicalPath(profileDir),
  };
}

function assertIndependentProfile(env = process.env) {
  const policy = resolveProfilePolicy(env);
  if (containsPath(policy.sourceCanonicalPath, policy.profileCanonicalPath)
    || containsPath(policy.profileCanonicalPath, policy.sourceCanonicalPath)) {
    throw new Error('PROFILE_DIR must not resolve to X_CHROME_USER_DATA_DIR (or compatibility SOURCE_PROFILE_DIR) and must not be equal to, contain, or be contained by the system Chrome source; refusing overlapping login profiles');
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
