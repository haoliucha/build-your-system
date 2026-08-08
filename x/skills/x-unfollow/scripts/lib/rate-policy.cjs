// Conservative, non-overridable lower bounds for all X-facing work.
// Environment variables may make the workflow slower or batches smaller, never faster/larger.

const POLICY = Object.freeze({
  SNAPSHOT_MAX_ROUNDS: 160,
  SNAPSHOT_WAIT_MIN_MS: 8000,
  SNAPSHOT_WAIT_MAX_MS: 12000,
  SNAPSHOT_LONG_BREAK_EVERY: 10,
  SNAPSHOT_LONG_BREAK_MS: 60000,

  PROFILE_MAX_PER_RUN: 5,
  PROFILE_WAIT_MIN_MS: 30000,
  PROFILE_WAIT_MAX_MS: 60000,
  PROFILE_RETRIES: 0,

  UNFOLLOW_DEFAULT_LIMIT: 5,
  UNFOLLOW_WAIT_MIN_MS: 45000,
  UNFOLLOW_WAIT_MAX_MS: 90000,
  UNFOLLOW_LONG_BREAK_EVERY: 3,
  UNFOLLOW_LONG_BREAK_MS: 180000,
});

function boundedInt(raw, fallback, { min = -Infinity, max = Infinity } = {}) {
  const parsed = Number.parseInt(String(raw ?? ''), 10);
  const value = Number.isFinite(parsed) ? parsed : fallback;
  return Math.max(min, Math.min(max, value));
}

function jitterMs(min, max, randomFn = Math.random) {
  if (max <= min) return min;
  return min + Math.floor(randomFn() * (max - min + 1));
}

module.exports = { ...POLICY, POLICY, boundedInt, jitterMs };
