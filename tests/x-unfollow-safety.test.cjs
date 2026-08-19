#!/usr/bin/env node

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const repo = path.resolve(__dirname, '..');
const canonicalSkill = path.join(repo, 'x/skills/x-unfollow');

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

assert.ok(fs.existsSync(canonicalSkill), 'x/skills/x-unfollow must own the single shared source');
assert.ok(!fs.existsSync(path.join(repo, 'targets/codex')), 'legacy Codex targets must not be an active source');

const policy = require(path.join(canonicalSkill, 'scripts/lib/rate-policy.cjs'));
assert.strictEqual(Object.prototype.hasOwnProperty.call(policy, 'FULL_RUN_COOLDOWN_MS'), false, 'full runs must have no time-based cooldown');
assert.strictEqual(policy.SNAPSHOT_WAIT_MIN_MS, 1000, 'passive response pages must wait at least 1 second');
assert.strictEqual(policy.SNAPSHOT_WAIT_MAX_MS, 3000, 'passive response page jitter must cap at 3 seconds');
assert.strictEqual(policy.SNAPSHOT_LONG_BREAK_EVERY, 25, 'snapshot must pause every 25 response pages');
assert.strictEqual(policy.SNAPSHOT_LONG_BREAK_MS, 10000, 'snapshot response-page break must be 10 seconds');
assert.strictEqual(policy.SNAPSHOT_WATCHDOG_MS, 45 * 60 * 1000, 'each list scan must have a 45-minute watchdog');
assert.strictEqual(Object.prototype.hasOwnProperty.call(policy, 'SNAPSHOT_MAX_ROUNDS'), false, 'cursor completion, not a fixed round cap, must end scans');
assert.ok(policy.PROFILE_MAX_PER_RUN <= 5, 'profile refresh batch must be capped at 5');
assert.ok(policy.PROFILE_WAIT_MIN_MS >= 30000, 'profile refresh cadence must be at least 30 seconds');
assert.strictEqual(policy.PROFILE_RETRIES, 0, 'profile refresh must not immediately retry failures');
assert.strictEqual(Object.prototype.hasOwnProperty.call(policy, 'VERIFY_MAX_PER_RUN'), false, 'verification is a local set diff, not per-profile requests');
assert.ok(policy.UNFOLLOW_DEFAULT_LIMIT <= 5, 'unfollow batch must default to at most 5');
assert.ok(policy.UNFOLLOW_WAIT_MIN_MS >= 45000, 'unfollow cadence must be at least 45 seconds');

const runSh = fs.readFileSync(path.join(canonicalSkill, 'run.sh'), 'utf8');
assert.match(runSh, /run-lock\.cjs" claim/, 'run.sh must claim the exclusive network-run token');
assert.match(runSh, /^trap cleanup_and_release EXIT$/m, 'run.sh must clean staging and release its lock from EXIT');
assert.doesNotMatch(runSh, /^trap .* INT TERM$/m, 'run.sh must not swallow INT/TERM termination');
assert.match(runSh, /one post-action following scan/, 'run.sh must verify with one post-action following-list scan');
for (const mode of ['report', 'unfollow', 'followers-report', 'relationships-report']) assert.match(runSh, new RegExp(mode), `run.sh missing ${mode}`);
assert.match(runSh, /PAGE_DRIFT \(exit 15\)/, 'run.sh must stop on page drift');
assert.match(runSh, /browser=headless/, 'run.sh must report the default headless mode');
assert.match(runSh, /browser=headed-debug/, 'run.sh must report the explicit visible debug override');

for (const script of ['list-snapshot.cjs', 'profile-counts.cjs', 'unfollow.cjs']) {
  const source = fs.readFileSync(path.join(canonicalSkill, 'scripts', script), 'utf8');
  assert.match(source, /assertRunToken\(\)/, `${script} must reject direct execution without run.sh's token`);
}

const verify = fs.readFileSync(path.join(canonicalSkill, 'scripts', 'verify-unfollow.cjs'), 'utf8');
assert.doesNotMatch(verify, /require\(['"]playwright['"]\)/, 'verification must be local and open zero profile pages');
assert.doesNotMatch(verify, /assertRunToken\(\)/, 'local verification must not require a network token');

const smoke = fs.readFileSync(path.join(canonicalSkill, 'scripts/smoke-test.cjs'), 'utf8');
assert.doesNotMatch(smoke, /https:\/\/x\.com/, 'smoke-test must remain local-only and make zero X requests');

const scanner = fs.readFileSync(path.join(canonicalSkill, 'scripts/list-snapshot.cjs'), 'utf8');
assert.match(scanner, /framenavigated/, 'scanner must listen for top-level navigation');
assert.match(scanner, /timeline-response\.cjs/, 'scanner must parse passive timeline responses');
assert.match(scanner, /page\.on\(['"]response['"]/, 'scanner must listen to page-owned responses');
assert.match(scanner, /SNAPSHOT_WATCHDOG_MS/, 'scanner must enforce the list watchdog');
assert.doesNotMatch(scanner, /MAX_SCROLL_ROUNDS|SNAPSHOT_MAX_ROUNDS/, 'scanner must not truncate cursor chains with a fixed round cap');

const browserLaunch = require(path.join(canonicalSkill, 'scripts/lib/browser-launch.cjs'));
assert.strictEqual(browserLaunch.resolveHeadless({}), true, 'browser default must be headless');
assert.strictEqual(browserLaunch.resolveHeadless({ XU_HEADLESS: '0' }), false, 'only XU_HEADLESS=0 enables visible debug');
assert.throws(() => browserLaunch.resolveHeadless({ XU_HEADLESS: 'false' }), /XU_HEADLESS must be 0 or 1/);
for (const script of ['list-snapshot.cjs', 'unfollow.cjs']) {
  const source = fs.readFileSync(path.join(canonicalSkill, 'scripts', script), 'utf8');
  assert.match(source, /browser-launch\.cjs/, `${script} must use the shared browser launch policy`);
  assert.match(source, /cdp-browser\.cjs/, `${script} must use the shared CDP browser`);
  assert.match(source, /withAuthenticatedContext/, `${script} must use the authenticated CDP wrapper`);
  assert.doesNotMatch(source, /launchPersistentContext/, `${script} must not use Playwright persistent context launch`);
  assert.doesNotMatch(source, /headless:\s*false/, `${script} must not hard-code visible mode`);
}

assert.strictEqual(JSON.parse(fs.readFileSync(path.join(repo, 'x/.claude-plugin/plugin.json'))).version, '4.1.2');
assert.strictEqual(JSON.parse(fs.readFileSync(path.join(repo, 'x/.codex-plugin/plugin.json'))).version, '4.1.2');

for (const skill of ['x-follow', 'x-unfollow']) {
  const run = fs.readFileSync(path.join(repo, 'x/skills', skill, 'run.sh'), 'utf8');
  assert.match(run, /plugin-provenance\.cjs/, `${skill} must verify plugin provenance before runtime`);
  assert.match(run, /LEGACY_STANDALONE_INSTALL/, `${skill} must reject bare standalone copies`);
}
assert.match(
  fs.readFileSync(path.join(repo, 'x/skills/x-follow/scripts/lib/runtime-gate.cjs'), 'utf8'),
  /runtimeProvenance/,
  'every direct x-follow child must inherit the plugin provenance gate',
);
assert.match(
  fs.readFileSync(path.join(repo, 'x/skills/x-unfollow/scripts/lib/rate-gate.cjs'), 'utf8'),
  /runtimeProvenance/,
  'every direct x-unfollow child must prove plugin provenance in addition to its run token',
);

console.log('x-unfollow safety and Codex/Claude parity checks passed');
