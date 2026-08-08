#!/usr/bin/env node

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const repo = path.resolve(__dirname, '..');
const codexSkill = path.join(repo, 'targets/codex/build-your-system-assistant/skills/x-unfollow');
const claudeSkill = path.join(repo, 'x/skills/x-unfollow');

function filesUnder(root, rel = '') {
  const dir = path.join(root, rel);
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const next = path.join(rel, entry.name);
    return entry.isDirectory() ? filesUnder(root, next) : [next];
  }).sort();
}

function assertTreesEqual(left, right) {
  const leftFiles = filesUnder(left);
  const rightFiles = filesUnder(right);
  assert.deepStrictEqual(leftFiles, rightFiles, 'Codex and Claude x-unfollow file lists drifted');
  for (const rel of leftFiles) {
    assert.strictEqual(
      fs.readFileSync(path.join(left, rel), 'utf8'),
      fs.readFileSync(path.join(right, rel), 'utf8'),
      `Codex and Claude x-unfollow content drifted: ${rel}`,
    );
  }
}

assert.ok(fs.existsSync(codexSkill), 'Codex build-your-system-assistant must own the canonical x-unfollow source');
assertTreesEqual(codexSkill, claudeSkill);

const policy = require(path.join(codexSkill, 'scripts/lib/rate-policy.cjs'));
assert.strictEqual(Object.prototype.hasOwnProperty.call(policy, 'FULL_RUN_COOLDOWN_MS'), false, 'full runs must have no time-based cooldown');
assert.ok(policy.SNAPSHOT_WAIT_MIN_MS >= 8000, 'snapshot scroll cadence must be at least 8 seconds');
assert.ok(policy.SNAPSHOT_LONG_BREAK_EVERY <= 10, 'snapshot must take a long break at least every 10 rounds');
assert.ok(policy.SNAPSHOT_LONG_BREAK_MS >= 60000, 'snapshot long break must be at least 60 seconds');
assert.ok(policy.PROFILE_MAX_PER_RUN <= 5, 'profile refresh batch must be capped at 5');
assert.ok(policy.PROFILE_WAIT_MIN_MS >= 30000, 'profile refresh cadence must be at least 30 seconds');
assert.strictEqual(policy.PROFILE_RETRIES, 0, 'profile refresh must not immediately retry failures');
assert.strictEqual(Object.prototype.hasOwnProperty.call(policy, 'VERIFY_MAX_PER_RUN'), false, 'verification is a local set diff, not per-profile requests');
assert.ok(policy.UNFOLLOW_DEFAULT_LIMIT <= 5, 'unfollow batch must default to at most 5');
assert.ok(policy.UNFOLLOW_WAIT_MIN_MS >= 45000, 'unfollow cadence must be at least 45 seconds');

const runSh = fs.readFileSync(path.join(codexSkill, 'run.sh'), 'utf8');
assert.match(runSh, /run-lock\.cjs" claim/, 'run.sh must claim the exclusive network-run token');
assert.match(runSh, /trap release_run_lock EXIT INT TERM/, 'run.sh must release its lock on every exit path');
assert.match(runSh, /post-action snapshot/, 'run.sh must verify with one post-action following-list scan');
assert.match(runSh, /PROFILE_MAX_PER_RUN/, 'run.sh must expose the capped profile-refresh batch');

for (const script of ['snapshot.cjs', 'profile-counts.cjs', 'unfollow.cjs']) {
  const source = fs.readFileSync(path.join(codexSkill, 'scripts', script), 'utf8');
  assert.match(source, /assertRunToken\(\)/, `${script} must reject direct execution without run.sh's token`);
}

const verify = fs.readFileSync(path.join(codexSkill, 'scripts', 'verify-unfollow.cjs'), 'utf8');
assert.doesNotMatch(verify, /require\(['"]playwright['"]\)/, 'verification must be local and open zero profile pages');
assert.doesNotMatch(verify, /assertRunToken\(\)/, 'local verification must not require a network token');

const smoke = fs.readFileSync(path.join(codexSkill, 'scripts/smoke-test.cjs'), 'utf8');
assert.doesNotMatch(smoke, /https:\/\/x\.com/, 'smoke-test must remain local-only and make zero X requests');

console.log('x-unfollow safety and Codex/Claude parity checks passed');
