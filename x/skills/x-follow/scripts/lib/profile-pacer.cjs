// lib/profile-pacer.cjs — persistent, profile-visit-level pacing for campaign.cjs.
//
// The old campaign paced AFTER the decision: successful follows waited 25-55s, but
// rejected profiles waited only 5-12s. Every profile navigation still causes X profile
// GraphQL traffic (including UsersByRestIds), so a reject-heavy queue could exceed the
// request budget even though the follow-click rate looked conservative.
//
// This pacer governs every profile visit BEFORE navigation and persists its sliding
// window in the shared x-follow data root. A resumed campaign or a brand-new run ID
// therefore cannot forget visits made by a previous process. A real HTTP 429 also
// records a cooldown deadline; an explicitly resumed run must still honor the remainder.

const fs = require('fs');
const path = require('path');

const HOUR_MS = 60 * 60 * 1000;
const SCHEMA_VERSION = 1;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function finiteNonNegative(value, name) {
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) throw new Error(`${name} must be a finite non-negative number`);
  return Math.floor(number);
}

function normalizePacerConfig(config = {}) {
  const normalized = {
    minIntervalMs: finiteNonNegative(config.minIntervalMs, 'PROFILE_VISIT_MIN_INTERVAL_MS'),
    maxIntervalMs: finiteNonNegative(config.maxIntervalMs, 'PROFILE_VISIT_MAX_INTERVAL_MS'),
    maxVisitsPerHour: finiteNonNegative(config.maxVisitsPerHour, 'MAX_PROFILE_VISITS_PER_HOUR'),
    rateLimitCooldownMs: finiteNonNegative(config.rateLimitCooldownMs, 'RATE_LIMIT_COOLDOWN_MS'),
  };
  if (normalized.maxIntervalMs < normalized.minIntervalMs) {
    throw new Error('PROFILE_VISIT_MAX_INTERVAL_MS must be >= PROFILE_VISIT_MIN_INTERVAL_MS');
  }
  return normalized;
}

function normalizeState(input, now = Date.now()) {
  const source = input && typeof input === 'object' && !Array.isArray(input) ? input : {};
  const visits = Array.isArray(source.profileVisitStartedAt)
    ? source.profileVisitStartedAt.map(Number).filter((value) => Number.isFinite(value) && value > now - HOUR_MS && value <= now)
    : [];
  visits.sort((a, b) => a - b);
  return {
    schemaVersion: SCHEMA_VERSION,
    profileVisitStartedAt: visits,
    nextVisitNotBefore: Number.isFinite(Number(source.nextVisitNotBefore)) ? Number(source.nextVisitNotBefore) : 0,
    rateLimitCooldownUntil: Number.isFinite(Number(source.rateLimitCooldownUntil)) ? Number(source.rateLimitCooldownUntil) : 0,
    lastVisit: source.lastVisit && typeof source.lastVisit === 'object' ? source.lastVisit : null,
    lastRateLimit: source.lastRateLimit && typeof source.lastRateLimit === 'object' ? source.lastRateLimit : null,
  };
}

function computeWaitPlan(inputState, inputConfig, now = Date.now()) {
  const config = normalizePacerConfig(inputConfig);
  const state = normalizeState(inputState, now);
  const waits = [];
  if (state.nextVisitNotBefore > now) waits.push({ reason: 'profile_interval', waitMs: state.nextVisitNotBefore - now });
  if (state.rateLimitCooldownUntil > now) waits.push({ reason: 'rate_limit_cooldown', waitMs: state.rateLimitCooldownUntil - now });
  if (config.maxVisitsPerHour > 0 && state.profileVisitStartedAt.length >= config.maxVisitsPerHour) {
    waits.push({
      reason: 'hourly_profile_cap',
      waitMs: Math.max(0, state.profileVisitStartedAt[0] + HOUR_MS - now + 5000),
    });
  }
  const waitMs = waits.reduce((maximum, item) => Math.max(maximum, item.waitMs), 0);
  return { state, waitMs, reasons: waits.filter((item) => item.waitMs === waitMs).map((item) => item.reason) };
}

function randomInterval(config, randomFn = Math.random) {
  if (config.maxIntervalMs === config.minIntervalMs) return config.minIntervalMs;
  return config.minIntervalMs + Math.floor(randomFn() * (config.maxIntervalMs - config.minIntervalMs + 1));
}

function readState(statePath, now) {
  try { return normalizeState(JSON.parse(fs.readFileSync(statePath, 'utf8')), now); }
  catch (error) {
    if (error.code === 'ENOENT') return normalizeState(null, now);
    throw new Error(`cannot read pacing state ${statePath}: ${error.message}`);
  }
}

function writeStateAtomic(statePath, state) {
  fs.mkdirSync(path.dirname(statePath), { recursive: true, mode: 0o700 });
  const temporaryPath = path.join(path.dirname(statePath), `.${path.basename(statePath)}.${process.pid}.tmp`);
  fs.writeFileSync(temporaryPath, JSON.stringify(state, null, 2), { mode: 0o600 });
  fs.renameSync(temporaryPath, statePath);
  try { fs.chmodSync(statePath, 0o600); } catch {}
}

function createProfilePacer(options) {
  if (!options || !options.statePath) throw new Error('profile pacer requires statePath');
  const config = normalizePacerConfig(options);
  const nowFn = options.nowFn || Date.now;
  const randomFn = options.randomFn || Math.random;
  const sleepFn = options.sleepFn || sleep;
  const log = options.log || (() => {});

  async function beforeVisit(handle) {
    while (true) {
      const now = nowFn();
      const plan = computeWaitPlan(readState(options.statePath, now), config, now);
      if (plan.waitMs <= 0) {
        const intervalMs = randomInterval(config, randomFn);
        const state = plan.state;
        state.profileVisitStartedAt.push(now);
        state.nextVisitNotBefore = now + intervalMs;
        state.lastVisit = { handle: handle || null, startedAt: new Date(now).toISOString(), intervalMs };
        writeStateAtomic(options.statePath, state);
        return { startedAt: now, intervalMs, visitsLastHour: state.profileVisitStartedAt.length };
      }
      log(`-- PROFILE PACER wait ${Math.ceil(plan.waitMs / 1000)}s (${plan.reasons.join('+')}) before @${handle} --`);
      await sleepFn(plan.waitMs);
    }
  }

  async function beforeNetwork(label) {
    while (true) {
      const now = nowFn();
      const state = readState(options.statePath, now);
      const waitMs = Math.max(0, state.rateLimitCooldownUntil - now);
      if (waitMs <= 0) return;
      log(`-- RATE-LIMIT COOLDOWN wait ${Math.ceil(waitMs / 1000)}s before ${label || 'X request'} --`);
      await sleepFn(waitMs);
    }
  }

  function noteRateLimit(info = {}) {
    const now = nowFn();
    const state = readState(options.statePath, now);
    state.rateLimitCooldownUntil = Math.max(state.rateLimitCooldownUntil, now + config.rateLimitCooldownMs);
    state.lastRateLimit = {
      at: new Date(now).toISOString(),
      handle: info.handle || null,
      responseUrl: info.responseUrl || info.url || null,
      cooldownUntil: new Date(state.rateLimitCooldownUntil).toISOString(),
    };
    writeStateAtomic(options.statePath, state);
    return state.lastRateLimit;
  }

  return { beforeNetwork, beforeVisit, noteRateLimit, config };
}

module.exports = {
  HOUR_MS,
  computeWaitPlan,
  createProfilePacer,
  normalizePacerConfig,
  normalizeState,
  randomInterval,
  readState,
  writeStateAtomic,
};
