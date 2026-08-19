#!/usr/bin/env node
// run-tests.cjs — zero-dependency test suite for the x-follow skill.
//
// Covers the PURE logic that drives every real run (parse/decide/skip/backoff/anomaly)
// plus an end-to-end build-queue integration against fixtures. A live browser E2E is not
// possible in CI (needs X login) — that path is exercised by `run.sh` against real X;
// here we lock down everything that does NOT need a browser. Run: node tests/run-tests.cjs

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync, spawnSync } = require('child_process');

const SCRIPTS = path.join(__dirname, '..', 'scripts');
const { parseCount, isCryptoHandle, backoffMs, decide, CRYPTO_TOKENS } = require(path.join(SCRIPTS, 'lib', 'filters.cjs'));
const { buildSkipSet, classifyReason, softRejectNowPasses } = require(path.join(SCRIPTS, 'lib', 'skipset.cjs'));
const { classifyAnomaly } = require(path.join(SCRIPTS, 'lib', 'anomaly.cjs'));
const { resolveCommentPolicy } = require(path.join(SCRIPTS, 'lib', 'comment-policy.cjs'));
const runLock = require(path.join(SCRIPTS, 'lib', 'run-lock.cjs'));
const { acquireLock, releaseLock, acquireOrInheritLock, installLeaseCleanup, inspectLock, acquireCoordination, releaseCoordination, leaseIdentityPath } = runLock;
const { resolveRuntimeState, resolveFilterPolicy, resolveProfilePolicy, assertIndependentProfile } = require(path.join(SCRIPTS, 'lib', 'runtime-state.cjs'));

let pass = 0, fail = 0;
function test(name, fn) { try { fn(); console.log(`  ✅ ${name}`); pass++; } catch (e) { console.log(`  ❌ ${name}\n     ${e.message}`); fail++; } }
function group(t) { console.log(`\n${t}`); }

// ---------------------------------------------------------------- parseCount
group('parseCount (follower/following count parsing)');
test('plain integer', () => assert.strictEqual(parseCount('1234'), 1234));
test('comma thousands', () => assert.strictEqual(parseCount('1,234'), 1234));
test('万 unit', () => assert.strictEqual(parseCount('1.2万'), 12000));
test('亿 unit', () => assert.strictEqual(parseCount('2亿'), 200000000));
test('K unit', () => assert.strictEqual(parseCount('12K'), 12000));
test('M unit', () => assert.strictEqual(parseCount('1.5M'), 1500000));
test('B unit', () => assert.strictEqual(parseCount('3B'), 3000000000));
test('null -> -1', () => assert.strictEqual(parseCount(null), -1));
test('garbage -> -1', () => assert.strictEqual(parseCount('--'), -1));

// ------------------------------------------------------------- isCryptoHandle
group('isCryptoHandle');
test('btc in handle', () => assert.strictEqual(isCryptoHandle('BTCJinn'), true));
test('web3 in handle', () => assert.strictEqual(isCryptoHandle('web3xiaoyu'), true));
test('clean handle', () => assert.strictEqual(isCryptoHandle('gengzishunli'), false));
test('empty handle', () => assert.strictEqual(isCryptoHandle(''), false));
test('CRYPTO_TOKENS non-empty', () => assert.ok(CRYPTO_TOKENS.length > 20));

// -------------------------------------------------------------------- backoff
group('backoffMs (exponential with cap)');
test('attempt 1 = base', () => assert.strictEqual(backoffMs(1, 20000, 300000), 20000));
test('attempt 2 = 2x', () => assert.strictEqual(backoffMs(2, 20000, 300000), 40000));
test('attempt 3 = 4x', () => assert.strictEqual(backoffMs(3, 20000, 300000), 80000));
test('attempt 4 = 8x', () => assert.strictEqual(backoffMs(4, 20000, 300000), 160000));
test('caps at cap', () => assert.strictEqual(backoffMs(9, 20000, 300000), 300000));
test('attempt<1 clamps to 1', () => assert.strictEqual(backoffMs(0, 20000, 300000), 20000));

// --------------------------------------------------------------------- decide
group('decide (campaign criteria — order matters)');
const CFG = { VERIFIED_REQUIRED: true, FOLLOWING_GT_FOLLOWERS: true, FERS_MAX: 3000, FOLLOW_RATIO_MIN: 0.5 };
test('good account passes', () => assert.strictEqual(decide({ blue: true, hasFollowBtn: true, fers: 300, fing: 600 }, CFG), 'pass'));
test('not blue rejected', () => assert.strictEqual(decide({ blue: false, hasFollowBtn: true, fers: 300, fing: 600 }, CFG), 'reject:not_blue'));
test('gold org rejected', () => assert.strictEqual(decide({ blue: true, gold: true, hasFollowBtn: true, fers: 300, fing: 600 }, CFG), 'reject:gold_org'));
test('already following never clicked', () => assert.strictEqual(decide({ blue: true, hasUnfollowBtn: true, hasFollowBtn: true, fers: 300, fing: 600 }, CFG), 'reject:already_following'));
test('no follow button', () => assert.strictEqual(decide({ blue: true, hasFollowBtn: false, fers: 300, fing: 600 }, CFG), 'reject:no_follow_btn'));
test('whale over FERS_MAX', () => assert.strictEqual(decide({ blue: true, hasFollowBtn: true, fers: 15000, fing: 20000 }, CFG), 'reject:fers>3000(15000)'));
// FERS_MAX 3000: a mid-size blue-V (2362 followers) that 1100 would have rejected now passes.
test('mid-size account within raised FERS_MAX passes', () => assert.strictEqual(decide({ blue: true, hasFollowBtn: true, fers: 2362, fing: 2000 }, CFG), 'pass'));
// FOLLOW_RATIO_MIN 0.5: followers may edge out following (NOT a one-way broadcaster) -> pass.
test('near-parity ratio passes (was over-rejected)', () => assert.strictEqual(decide({ blue: true, hasFollowBtn: true, fers: 400, fing: 300 }, CFG), 'pass'));
test('borderline ratio passes (fing == fers*0.5)', () => assert.strictEqual(decide({ blue: true, hasFollowBtn: true, fers: 322, fing: 161 }, CFG), 'pass'));
// only a CLEAR broadcaster (fing < fers*0.5) is still rejected
test('one-way broadcaster rejected', () => assert.strictEqual(decide({ blue: true, hasFollowBtn: true, fers: 900, fing: 300 }, CFG), 'reject:fing<fers*0.5(300<900)'));
test('crypto bio (when filter on)', () => assert.strictEqual(decide({ blue: true, hasFollowBtn: true, fers: 300, fing: 600, cryptoMatch: 'web3' }, CFG), 'reject:blacklist(web3)'));
test('crypto allowed when no match passed', () => assert.strictEqual(decide({ blue: true, hasFollowBtn: true, fers: 300, fing: 600, cryptoMatch: null }, CFG), 'pass'));
test('whitelist miss', () => assert.strictEqual(decide({ blue: true, hasFollowBtn: true, fers: 300, fing: 600, whitelistFail: true }, CFG), 'reject:not_in_whitelist'));
test('size beats crypto in order', () => assert.strictEqual(decide({ blue: true, hasFollowBtn: true, fers: 9000, fing: 9999, cryptoMatch: 'btc' }, CFG), 'reject:fers>3000(9000)'));

// ------------------------------------------------------------------ skip-set
group('buildSkipSet (tracker union)');
test('union followed + rejected, deduped', () => {
  const got = buildSkipSet([
    { followed: [{ handle: 'a' }], rejected: [{ h: 'b' }] },
    { followed: [{ handle: 'a' }], rejected: [{ h: 'c' }] },
  ]).sort();
  assert.deepStrictEqual(got, ['a', 'b', 'c']);
});
test('handles missing arrays', () => assert.deepStrictEqual(buildSkipSet([{}, null, { followed: [{ handle: 'x' }] }]), ['x']));
test('accepts handle or h on either side', () => {
  const got = buildSkipSet([{ followed: [{ h: 'f1' }], rejected: [{ handle: 'r1' }] }]).sort();
  assert.deepStrictEqual(got, ['f1', 'r1']);
});

// --------------------------------------------------- skip-set TIERED RELEASE
group('classifyReason (transient / soft / permanent tiers)');
test('eval_error is transient', () => assert.strictEqual(classifyReason('eval_error:profile_unavailable'), 'transient'));
test('no_follow_btn is transient', () => assert.strictEqual(classifyReason('reject:no_follow_btn'), 'transient'));
test('cant_parse_stats is transient', () => assert.strictEqual(classifyReason('reject:cant_parse_stats'), 'transient'));
test('fers>MAX is soft', () => assert.strictEqual(classifyReason('reject:fers>1100(17000)'), 'soft'));
test('fing<=fers is soft', () => assert.strictEqual(classifyReason('reject:fing<=fers(1<=2)'), 'soft'));
test('not_blue is permanent', () => assert.strictEqual(classifyReason('reject:not_blue'), 'permanent'));
test('already_following is permanent', () => assert.strictEqual(classifyReason('reject:already_following'), 'permanent'));
test('pre_existing (legacy) is permanent', () => assert.strictEqual(classifyReason('pre_existing'), 'permanent'));

group('buildSkipSet tiered release (transient released, soft TTL)');
const NOW = Date.parse('2026-06-22T00:00:00Z');
const daysAgo = (n) => new Date(NOW - n * 86400000).toISOString();
test('transient errors are NOT skipped (误杀释放)', () => {
  const got = buildSkipSet([{ rejected: [
    { h: 'glitch', r: 'eval_error:profile_unavailable', at: daysAgo(1) },
    { h: 'nobtn', r: 'reject:no_follow_btn', at: daysAgo(1) },
  ] }], { now: NOW });
  assert.deepStrictEqual(got, []);
});
test('fresh soft reject IS skipped', () => {
  const got = buildSkipSet([{ rejected: [{ h: 'ratio', r: 'reject:fing<=fers(1<=2)', at: daysAgo(5) }] }], { now: NOW, softTtlDays: 30 });
  assert.deepStrictEqual(got, ['ratio']);
});
test('expired soft reject is released', () => {
  const got = buildSkipSet([{ rejected: [{ h: 'ratio', r: 'reject:fing<=fers(1<=2)', at: daysAgo(40) }] }], { now: NOW, softTtlDays: 30 });
  assert.deepStrictEqual(got, []);
});
test('soft reject WITHOUT timestamp is kept (conservative)', () => {
  const got = buildSkipSet([{ rejected: [{ h: 'ratio', r: 'reject:fers>1100(9000)' }] }], { now: NOW });
  assert.deepStrictEqual(got, ['ratio']);
});
test('permanent reject is always skipped regardless of age', () => {
  const got = buildSkipSet([{ rejected: [{ h: 'notblue', r: 'reject:not_blue', at: daysAgo(999) }] }], { now: NOW });
  assert.deepStrictEqual(got, ['notblue']);
});
test('followed handles always permanent-skip', () => {
  const got = buildSkipSet([{ followed: [{ handle: 'pal', at: daysAgo(999) }] }], { now: NOW });
  assert.deepStrictEqual(got, ['pal']);
});
test('release stats are reported', () => {
  const stats = {};
  buildSkipSet([{ rejected: [
    { h: 'a', r: 'eval_error:x', at: daysAgo(1) },
    { h: 'b', r: 'reject:fers>1100(9000)', at: daysAgo(40) },
  ] }], { now: NOW, softTtlDays: 30, stats });
  assert.strictEqual(stats.released_transient, 1);
  assert.strictEqual(stats.released_soft_expired, 1);
});

// ----------------------------------------- THRESHOLD-AWARE soft release (new)
group('softRejectNowPasses (threshold-aware unlock)');
const OPTS = { fersMax: 3000, followRatioMin: 0.5 };
test('fers reject under raised cap releases', () => assert.strictEqual(softRejectNowPasses('reject:fers>1100(2362)', OPTS), true));
test('fers reject still over cap stays', () => assert.strictEqual(softRejectNowPasses('reject:fers>1100(14000)', OPTS), false));
test('fers reject exactly at cap releases', () => assert.strictEqual(softRejectNowPasses('reject:fers>1100(3000)', OPTS), true));
test('old fing<=fers label re-evaluated by ratio (releases)', () => assert.strictEqual(softRejectNowPasses('reject:fing<=fers(165<=323)', OPTS), true));
test('new fing<fers*r label re-evaluated (releases)', () => assert.strictEqual(softRejectNowPasses('reject:fing<fers*0.5(165<323)', OPTS), true));
test('clear broadcaster stays (ratio fails)', () => assert.strictEqual(softRejectNowPasses('reject:fing<=fers(50<=900)', OPTS), false));
test('fing reject over the cap stays even if ratio ok', () => assert.strictEqual(softRejectNowPasses('reject:fing<=fers(9000<=12000)', OPTS), false));
test('without opts cannot prove pass -> false', () => assert.strictEqual(softRejectNowPasses('reject:fers>1100(100)', {}), false));
test('permanent reason never auto-passes', () => assert.strictEqual(softRejectNowPasses('reject:not_blue', OPTS), false));

group('buildSkipSet threshold-aware release (relaxed cap unlocks)');
test('raising FERS_MAX releases now-eligible fers reject', () => {
  const got = buildSkipSet([{ rejected: [
    { h: 'small', r: 'reject:fers>1100(2362)', at: daysAgo(2) },   // 2362 <= 3000 -> release
    { h: 'whale', r: 'reject:fers>1100(50000)', at: daysAgo(2) },  // stays
  ] }], { now: NOW, softTtlDays: 30, ...OPTS });
  assert.deepStrictEqual(got, ['whale']);
});
test('relaxed ratio releases near-parity fing reject but keeps broadcaster', () => {
  const got = buildSkipSet([{ rejected: [
    { h: 'parity', r: 'reject:fing<=fers(165<=323)', at: daysAgo(2) },  // 165>=161.5 -> release
    { h: 'caster', r: 'reject:fing<=fers(50<=900)', at: daysAgo(2) },   // 50<450 -> stays
  ] }], { now: NOW, softTtlDays: 30, ...OPTS });
  assert.deepStrictEqual(got, ['caster']);
});
test('threshold release is counted in stats', () => {
  const stats = {};
  buildSkipSet([{ rejected: [{ h: 'x', r: 'reject:fers>1100(2362)', at: daysAgo(2) }] }], { now: NOW, softTtlDays: 30, stats, ...OPTS });
  assert.strictEqual(stats.released_threshold, 1);
});
test('without thresholds, fresh soft reject is still skipped (back-compat)', () => {
  const got = buildSkipSet([{ rejected: [{ h: 'x', r: 'reject:fers>1100(2362)', at: daysAgo(2) }] }], { now: NOW, softTtlDays: 30 });
  assert.deepStrictEqual(got, ['x']);
});

// ------------------------------------------------------------------- anomaly
group('classifyAnomaly (inChrome scoping — the false-positive fix)');
const PAD = ' padding padding padding padding padding padding padding';
test('restriction phrase ONLY in tweet -> null (the fix)', () =>
  assert.strictEqual(classifyAnomaly({ bodyText: 'home feed 账户被限制 discussion' + PAD, tweetText: '账户被限制', path: '/someuser', webdriver: false }), null));
test('real restriction in chrome -> ACCOUNT_RESTRICTED', () =>
  assert.strictEqual(classifyAnomaly({ bodyText: 'your account has been locked' + PAD, tweetText: '', path: '/home', webdriver: false }).type, 'ACCOUNT_RESTRICTED'));
test('rate limit phrase only in tweet -> null', () =>
  assert.strictEqual(classifyAnomaly({ bodyText: 'feed rate limit talk' + PAD, tweetText: 'rate limit', path: '/u', webdriver: false }), null));
test('real rate limit -> RATE_LIMIT', () =>
  assert.strictEqual(classifyAnomaly({ bodyText: '操作太频繁' + PAD, tweetText: '', path: '/home', webdriver: false }).type, 'RATE_LIMIT'));
// regression: a rate-limit/restriction phrase living in a profile BIO (user-controlled,
// passed via userText) must NOT trigger — this is the Baekjiajia_exo bio false-positive.
test('rate limit phrase only in bio (userText) -> null', () =>
  assert.strictEqual(classifyAnomaly({ bodyText: 'profile header 当前无法访问，请稍后再试一次 匿名箱' + PAD, userText: '当前无法访问，请稍后再试一次 匿名箱', path: '/someuser', webdriver: false }), null));
test('restriction phrase only in bio (userText) -> null', () =>
  assert.strictEqual(classifyAnomaly({ bodyText: 'bio says 账户被限制 here' + PAD, userText: '账户被限制', path: '/someuser', webdriver: false }), null));
test('userText takes precedence over tweetText alias when both present', () =>
  assert.strictEqual(classifyAnomaly({ bodyText: 'feed 请稍后再试 talk' + PAD, userText: '请稍后再试', tweetText: '', path: '/u', webdriver: false }), null));
test('captcha -> CAPTCHA', () =>
  assert.strictEqual(classifyAnomaly({ bodyText: 'x' + PAD, hasCaptcha: true }).type, 'CAPTCHA'));
test('login redirect -> LOGIN_REDIRECT', () =>
  assert.strictEqual(classifyAnomaly({ bodyText: 'x' + PAD, path: '/i/flow/login' }).type, 'LOGIN_REDIRECT'));
test('webdriver true -> WEBDRIVER_DETECTED', () =>
  assert.strictEqual(classifyAnomaly({ bodyText: 'normal page content here' + PAD, path: '/home', webdriver: true }).type, 'WEBDRIVER_DETECTED'));
test('empty page -> EMPTY_PAGE', () =>
  assert.strictEqual(classifyAnomaly({ bodyText: 'short', path: '/home', webdriver: false }).type, 'EMPTY_PAGE'));
test('healthy page -> null', () =>
  assert.strictEqual(classifyAnomaly({ bodyText: 'a normal logged-in home timeline with lots of content' + PAD, path: '/home', webdriver: false }), null));

// ------------------------------------------------------- build-queue (E2E-ish)
group('build-queue.cjs integration (followed-skip + crypto toggle)');
function runBuildQueue(dir, nocrypto) {
  execFileSync('node', [path.join(SCRIPTS, 'build-queue.cjs')], {
    env: { ...process.env, JOB_DIR: dir, NOCRYPTO: nocrypto }, stdio: 'ignore',
  });
  return JSON.parse(fs.readFileSync(path.join(dir, 'queue.json'), 'utf8'));
}
function fixtureDir() {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-test-'));
  fs.writeFileSync(path.join(d, 'tracker.json'), JSON.stringify({ followed: [{ handle: 'alice' }], rejected: [{ h: 'bob', r: 'reject:not_blue' }] }));
  fs.writeFileSync(path.join(d, 'cand-01.json'), JSON.stringify({ items: [{ handle: 'alice' }, { handle: 'bob' }, { handle: 'carol' }, { handle: 'BTCwhale' }, { handle: 'dave' }, { handle: 'dave' }] }));
  return d;
}
test('NOCRYPTO=1 skips followed+rejected, drops crypto, dedups', () => {
  const d = fixtureDir();
  assert.deepStrictEqual(runBuildQueue(d, '1').sort(), ['carol', 'dave']);
});
test('NOCRYPTO=0 keeps crypto handle', () => {
  const d = fixtureDir();
  assert.deepStrictEqual(runBuildQueue(d, '0').sort(), ['BTCwhale', 'carol', 'dave']);
});

group('build-queue.cjs DROP_NONBLUE (pre-filter non-verified before campaign)');
function runBuildQueueEnv(dir, env) {
  execFileSync('node', [path.join(SCRIPTS, 'build-queue.cjs')], { env: { ...process.env, JOB_DIR: dir, ...env }, stdio: 'ignore' });
  return JSON.parse(fs.readFileSync(path.join(dir, 'queue.json'), 'utf8'));
}
function blueFixture() {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-blue-'));
  fs.writeFileSync(path.join(d, 'tracker.json'), JSON.stringify({ followed: [], rejected: [] }));
  fs.writeFileSync(path.join(d, 'cand-01.json'), JSON.stringify({ items: [
    { handle: 'verified1', blue: true }, { handle: 'plain1', blue: false },
    { handle: 'verified2', blue: true }, { handle: 'plain2', blue: false },
  ] }));
  return d;
}
test('DROP_NONBLUE=1 drops blue:false candidates', () => {
  assert.deepStrictEqual(runBuildQueueEnv(blueFixture(), { NOCRYPTO: '0', DROP_NONBLUE: '1' }).sort(), ['verified1', 'verified2']);
});
test('DROP_NONBLUE unset keeps all', () => {
  assert.deepStrictEqual(runBuildQueueEnv(blueFixture(), { NOCRYPTO: '0' }).sort(), ['plain1', 'plain2', 'verified1', 'verified2']);
});
test('priority.json handles bypass the blue filter', () => {
  const d = blueFixture();
  fs.writeFileSync(path.join(d, 'priority.json'), JSON.stringify(['vipNoBadge']));
  const got = runBuildQueueEnv(d, { NOCRYPTO: '0', DROP_NONBLUE: '1' });
  assert.ok(got.includes('vipNoBadge'), 'priority handle must survive DROP_NONBLUE');
});

// ------------------------------------------------------ shared runtime safety
group('comment policy (explicit double authorization)');
test('comment is disabled by default', () => assert.deepStrictEqual(resolveCommentPolicy({}), { enabled: false }));
test('COMMENT_AFTER_FOLLOW=true needs an allow token', () => {
  assert.throws(() => resolveCommentPolicy({ COMMENT_AFTER_FOLLOW: 'true' }), /ALLOW_COMMENT_AFTER_FOLLOW=1/);
});
test('COMMENT_AFTER_FOLLOW=1 with allow token enables comments', () => {
  assert.deepStrictEqual(resolveCommentPolicy({ COMMENT_AFTER_FOLLOW: '1', ALLOW_COMMENT_AFTER_FOLLOW: '1' }), { enabled: true });
});
test('allow token alone does not enable comments', () => {
  assert.deepStrictEqual(resolveCommentPolicy({ ALLOW_COMMENT_AFTER_FOLLOW: '1' }), { enabled: false });
});
test('invalid comment boolean fails closed', () => {
  assert.throws(() => resolveCommentPolicy({ COMMENT_AFTER_FOLLOW: 'yes', ALLOW_COMMENT_AFTER_FOLLOW: '1' }), /must be true, false, 1, or 0/);
});
test('campaign direct invocation rejects an unapproved comment before browser startup', () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-comment-policy-'));
  const result = spawnSync('node', [path.join(SCRIPTS, 'campaign.cjs')], {
    env: { ...process.env, TARGET: '1', X_FOLLOW_DATA_DIR: dataDir, COMMENT_AFTER_FOLLOW: 'true', ALLOW_COMMENT_AFTER_FOLLOW: '' },
    encoding: 'utf8',
  });
  assert.strictEqual(result.status, 2);
  assert.match(result.stderr, /ALLOW_COMMENT_AFTER_FOLLOW=1/);
});
test('campaign direct invocation rejects an active cross-host lock before Playwright', () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-campaign-lock-'));
  fs.writeFileSync(path.join(dataDir, 'network-run.lock'), JSON.stringify({ pid: process.pid, token: 'other-run', jobDir: '/other', startedAt: '2026-08-19T00:00:00.000Z' }));
  const result = spawnSync('node', [path.join(SCRIPTS, 'campaign.cjs')], {
    env: { ...process.env, TARGET: '1', X_FOLLOW_DATA_DIR: dataDir },
    encoding: 'utf8',
  });
  assert.strictEqual(result.status, 2);
  assert.match(result.stderr, /network run lock already active/);
});

group('run lock (single owner and stale recovery)');
test('active lock rejects a concurrent run and release only removes its own token', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-'));
  const lockPath = path.join(d, 'network-run.lock');
  const first = acquireLock(lockPath, { pid: process.pid, token: 'first', jobDir: '/run/one', startedAt: '2026-08-19T00:00:00.000Z' });
  assert.throws(() => acquireLock(lockPath, { pid: process.pid, token: 'second', jobDir: '/run/two' }), /already active/);
  assert.strictEqual(releaseLock(lockPath, 'second'), false);
  assert.ok(fs.existsSync(lockPath));
  assert.strictEqual(releaseLock(lockPath, first.token), true);
  assert.ok(!fs.existsSync(lockPath));
});
test('stale lock is recovered before acquiring', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-'));
  const lockPath = path.join(d, 'network-run.lock');
  fs.writeFileSync(lockPath, JSON.stringify({ pid: 99999999, token: 'stale', jobDir: '/old', startedAt: '2026-08-01T00:00:00.000Z' }));
  const lock = acquireLock(lockPath, { pid: process.pid, token: 'fresh', jobDir: '/new', startedAt: '2026-08-19T00:00:00.000Z' });
  assert.strictEqual(lock.recovered.token, 'stale');
  assert.strictEqual(JSON.parse(fs.readFileSync(path.join(lockPath, 'owner.json'), 'utf8')).token, 'fresh');
  releaseLock(lockPath, lock.token);
});

test('lock stores its owner JSON atomically inside the lock directory', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-layout-'));
  const lockPath = path.join(d, 'network-run.lock');
  const lock = acquireLock(lockPath, { pid: process.pid, token: 'layout', jobDir: '/layout', startedAt: '2026-08-19T00:00:00.000Z' });
  assert.ok(fs.statSync(lockPath).isDirectory());
  assert.deepStrictEqual(JSON.parse(fs.readFileSync(path.join(lockPath, 'owner.json'), 'utf8')), {
    pid: process.pid, token: 'layout', jobDir: '/layout', startedAt: '2026-08-19T00:00:00.000Z',
  });
  releaseLock(lockPath, lock.token);
});

function concurrentLockResults(lockPath, count) {
  const helper = path.join(SCRIPTS, 'lib', 'run-lock.cjs');
  const child = `
    const { acquireLock, releaseLock } = require(${JSON.stringify(helper)});
    const lockPath = process.argv[1];
    try {
      const lock = acquireLock(lockPath, { jobDir: process.argv[2] });
      process.stdout.write('ok\\n');
      process.on('SIGTERM', () => { releaseLock(lockPath, lock.token); process.exit(0); });
      setInterval(() => {}, 1000);
    } catch (error) { process.stdout.write('blocked\\n'); process.exit(2); }
  `;
  const coordinator = `
    const { spawn } = require('child_process');
    const children = Array.from({ length: Number(process.argv[2]) }, () => spawn(process.execPath, ['-e', process.argv[1], process.argv[3], '/job'], { stdio: ['ignore', 'pipe', 'ignore'] }));
    const results = [];
    let done = 0;
    for (const child of children) child.stdout.on('data', chunk => { results.push(chunk.toString().trim()); if (++done === children.length) { for (const c of children) c.kill('SIGTERM'); } });
    Promise.all(children.map(child => new Promise(resolve => child.on('exit', resolve)))).then(() => process.stdout.write(JSON.stringify(results)));
  `;
  return JSON.parse(execFileSync('node', ['-e', coordinator, child, String(count), lockPath], { encoding: 'utf8' }));
}
test('multiple live contenders have exactly one lock winner', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-race-'));
  const results = concurrentLockResults(path.join(d, 'network-run.lock'), 6);
  assert.strictEqual(results.filter(result => result === 'ok').length, 1);
});
test('multiple stale recoverers have exactly one lock winner', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-stale-race-'));
  const lockPath = path.join(d, 'network-run.lock');
  fs.mkdirSync(lockPath);
  fs.writeFileSync(path.join(lockPath, 'owner.json'), JSON.stringify({ pid: 99999999, token: 'stale', jobDir: '/old', startedAt: '2026-08-01T00:00:00.000Z' }));
  const results = concurrentLockResults(lockPath, 6);
  assert.strictEqual(results.filter(result => result === 'ok').length, 1);
});
test('owner signal cleanup only removes its own lock token', () => {
  const helper = path.join(SCRIPTS, 'lib', 'run-lock.cjs');
  for (const signal of ['SIGINT', 'SIGTERM']) {
    const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-signal-'));
    const lockPath = path.join(d, 'network-run.lock');
    const script = `
      const { acquireOrInheritLock, installLeaseCleanup } = require(${JSON.stringify(helper)});
      const lease = acquireOrInheritLock({ lockPath: process.argv[1], jobDir: '/signal' });
      installLeaseCleanup(lease);
      process.kill(process.pid, process.argv[2]);
      setTimeout(() => process.exit(99), 100);
    `;
    const result = spawnSync('node', ['-e', script, lockPath, signal], { encoding: 'utf8' });
    assert.strictEqual(result.status, signal === 'SIGINT' ? 130 : 143);
    assert.ok(!fs.existsSync(lockPath), signal);
  }
});
test('inherited child token never releases its parent lock', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-inherited-'));
  const lockPath = path.join(d, 'network-run.lock');
  const parent = acquireLock(lockPath, { pid: process.pid, token: 'parent', jobDir: '/parent' });
  const helper = path.join(SCRIPTS, 'lib', 'run-lock.cjs');
  const script = `
    const { acquireOrInheritLock, installLeaseCleanup } = require(${JSON.stringify(helper)});
    const lease = acquireOrInheritLock({ lockPath: process.env.X_FOLLOW_NETWORK_LOCK, jobDir: '/child', env: process.env });
    installLeaseCleanup(lease);
  `;
  const result = spawnSync('node', ['-e', script], { env: { ...process.env, X_FOLLOW_NETWORK_LOCK: lockPath, X_FOLLOW_NETWORK_LOCK_TOKEN: parent.token }, encoding: 'utf8' });
  assert.strictEqual(result.status, 0);
  assert.ok(fs.existsSync(lockPath));
  assert.strictEqual(releaseLock(lockPath, parent.token), true);
});

test('active inherited worker blocks parent release and only clears its own identity', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-worker-identity-'));
  const lockPath = path.join(d, 'network-run.lock');
  const parent = acquireLock(lockPath, { pid: process.pid, token: 'parent-worker', jobDir: '/parent' });
  const workerStartedAt = '2026-08-19T01:02:03.000Z';
  assert.strictEqual(runLock.registerInheritedWorker(lockPath, parent.token, process.pid, workerStartedAt), true);
  assert.strictEqual(releaseLock(lockPath, parent.token), false);
  assert.strictEqual(runLock.releaseInheritedWorker(lockPath, parent.token, process.pid, '2026-08-19T01:02:04.000Z'), false);
  assert.strictEqual(inspectLock(lockPath).record.workerStartedAt, workerStartedAt);
  assert.strictEqual(runLock.releaseInheritedWorker(lockPath, parent.token, process.pid, workerStartedAt), true);
  assert.strictEqual(releaseLock(lockPath, parent.token), true);
});

test('owner SIGKILL keeps replacement blocked until the inherited runtime worker exits', () => {
  const helper = path.join(SCRIPTS, 'lib', 'run-lock.cjs');
  const runtimeGate = path.join(SCRIPTS, 'lib', 'runtime-gate.cjs');
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-owner-kill-'));
  const lockPath = path.join(dataDir, 'network-run.lock');
  const worker = `
    const { prepareXFacingRuntime } = require(${JSON.stringify(runtimeGate)});
    prepareXFacingRuntime(process.env);
    process.stdout.write('worker-ready\\n');
    setInterval(() => {}, 1000);
  `;
  const owner = `
    const { spawn } = require('child_process');
    const { acquireLock } = require(${JSON.stringify(helper)});
    const dataDir = process.argv[1], worker = process.argv[2];
    const lockPath = require('path').join(dataDir, 'network-run.lock');
    const lease = acquireLock(lockPath, { jobDir: '/owner' });
    const child = spawn(process.execPath, ['-e', worker], {
      env: { ...process.env, X_FOLLOW_DATA_DIR: dataDir, JOB_DIR: '/owner', SOURCE_PROFILE_DIR: '/source', PROFILE_DIR: '/campaign', X_FOLLOW_NETWORK_LOCK: lockPath, X_FOLLOW_NETWORK_LOCK_TOKEN: lease.token },
      stdio: ['ignore', 'pipe', 'inherit'],
    });
    child.stdout.pipe(process.stdout);
    process.stdout.write(JSON.stringify({ ownerPid: process.pid, workerPid: child.pid }) + '\\n');
    setInterval(() => {}, 1000);
  `;
  const coordinator = `
    const { spawn } = require('child_process');
    const { acquireLock, releaseLock } = require(${JSON.stringify(helper)});
    const dataDir = process.argv[1], ownerScript = process.argv[2], workerScript = process.argv[3];
    const lockPath = require('path').join(dataDir, 'network-run.lock');
    const parent = spawn(process.execPath, ['-e', ownerScript, dataDir, workerScript], { stdio: ['ignore', 'pipe', 'inherit'] });
    let info, ready = false, buffer = '';
    const finish = async () => {
      if (!info || !ready) return;
      parent.kill('SIGKILL');
      await new Promise(resolve => parent.once('exit', resolve));
      let whileWorker = 'blocked', accidental;
      try { accidental = acquireLock(lockPath, { jobDir: '/replacement' }); whileWorker = 'acquired'; }
      catch (error) { if (!/already active/.test(error.message)) throw error; }
      if (accidental) releaseLock(lockPath, accidental.token);
      process.kill(info.workerPid, 'SIGTERM');
      for (let i = 0; i < 100; i++) {
        try { process.kill(info.workerPid, 0); await new Promise(resolve => setTimeout(resolve, 10)); }
        catch { break; }
      }
      const recovered = acquireLock(lockPath, { jobDir: '/replacement' });
      releaseLock(lockPath, recovered.token);
      process.stdout.write(JSON.stringify({ whileWorker, recovered: !!recovered }));
    };
    parent.stdout.on('data', chunk => {
      buffer += chunk;
      const lines = buffer.split('\\n'); buffer = lines.pop();
      for (const line of lines) {
        if (line === 'worker-ready') ready = true;
        else if (line.startsWith('{')) info = JSON.parse(line);
      }
      finish().catch(error => { console.error(error); process.exit(1); });
    });
  `;
  const result = JSON.parse(execFileSync('node', ['-e', coordinator, dataDir, owner, worker], { encoding: 'utf8', timeout: 10000 }));
  assert.deepStrictEqual(result, { whileWorker: 'blocked', recovered: true });
});

test('run.sh TERM forwards to its active inherited worker before releasing the owner lock', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-run-owner-term-'));
  const fakeBin = path.join(root, 'bin');
  const dataDir = path.join(root, 'data');
  const jobDir = path.join(dataDir, 'runs', 'term-test');
  const source = path.join(root, 'source-profile');
  const profile = path.join(root, 'campaign-profile');
  const workerScript = path.join(root, 'worker.cjs');
  const readyPath = path.join(root, 'worker-ready.json');
  const exitPath = path.join(root, 'worker-exit.json');
  const heartbeatPath = path.join(root, 'worker-heartbeat.log');
  fs.mkdirSync(fakeBin);
  fs.mkdirSync(source);
  fs.mkdirSync(profile);
  fs.writeFileSync(workerScript, `
    const fs = require('fs');
    const { prepareXFacingRuntime } = require(${JSON.stringify(path.join(SCRIPTS, 'lib', 'runtime-gate.cjs'))});
    const { inspectLock } = require(${JSON.stringify(path.join(SCRIPTS, 'lib', 'run-lock.cjs'))});
    const runtime = prepareXFacingRuntime(process.env);
    fs.writeFileSync(process.env.TEST_READY_PATH, JSON.stringify({ pid: process.pid }));
    process.once('exit', () => {
      const current = inspectLock(runtime.lease.lockPath);
      fs.writeFileSync(process.env.TEST_EXIT_PATH, JSON.stringify({
        workerFieldsPresent: current.state === 'ready' && Boolean(current.record.workerPid || current.record.workerStartedAt),
      }));
    });
    setInterval(() => fs.appendFileSync(process.env.TEST_HEARTBEAT_PATH, '.'), 20);
  `);
  fs.writeFileSync(path.join(fakeBin, 'node'), [
    '#!/bin/sh',
    'case "$1" in',
    '  */smoke-test.cjs) exec "$REAL_NODE" "$TEST_WORKER_SCRIPT" ;;',
    'esac',
    'exec "$REAL_NODE" "$@"',
    '',
  ].join('\n'));
  fs.writeFileSync(path.join(fakeBin, 'pkill'), '#!/bin/sh\nexit 1\n');
  fs.chmodSync(path.join(fakeBin, 'node'), 0o755);
  fs.chmodSync(path.join(fakeBin, 'pkill'), 0o755);

  const coordinator = `
    const fs = require('fs');
    const path = require('path');
    const { spawn } = require('child_process');
    const { acquireLock, releaseLock, inspectLock } = require(${JSON.stringify(path.join(SCRIPTS, 'lib', 'run-lock.cjs'))});
    const [runSh, fakeBin, dataDir, jobDir, source, profile, workerScript, readyPath, exitPath, heartbeatPath, realNode] = process.argv.slice(1);
    const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
    const alive = pid => { try { process.kill(pid, 0); return true; } catch { return false; } };
    (async () => {
      const owner = spawn('bash', [runSh], {
        env: {
          ...process.env,
          PATH: fakeBin + path.delimiter + process.env.PATH,
          REAL_NODE: realNode,
          TEST_WORKER_SCRIPT: workerScript,
          TEST_READY_PATH: readyPath,
          TEST_EXIT_PATH: exitPath,
          TEST_HEARTBEAT_PATH: heartbeatPath,
          TARGET: '0',
          X_FOLLOW_DATA_DIR: dataDir,
          X_FOLLOW_RUN_ID: 'term-test',
          JOB_DIR: jobDir,
          SOURCE_PROFILE_DIR: source,
          PROFILE_DIR: profile,
        },
        stdio: 'ignore',
      });
      let workerPid = 0;
      for (let i = 0; i < 150; i++) {
        if (fs.existsSync(readyPath)) { workerPid = JSON.parse(fs.readFileSync(readyPath, 'utf8')).pid; break; }
        await delay(20);
      }
      if (!workerPid) {
        owner.kill('SIGKILL');
        throw new Error('worker did not become ready');
      }
      const lockPath = path.join(dataDir, 'network-run.lock');
      const identityBefore = inspectLock(lockPath).record.workerPid === workerPid;
      const ownerExit = new Promise(resolve => owner.once('exit', (code, signal) => resolve({ code, signal })));
      owner.kill('SIGTERM');
      const first = await Promise.race([ownerExit, delay(800).then(() => null)]);
      const graceful = Boolean(first);
      if (!graceful) {
        if (alive(workerPid)) process.kill(workerPid, 'SIGKILL');
        const second = await Promise.race([ownerExit, delay(800).then(() => null)]);
        if (!second) owner.kill('SIGKILL');
        await Promise.race([ownerExit, delay(800)]);
      }
      const heartbeatAtExit = fs.existsSync(heartbeatPath) ? fs.statSync(heartbeatPath).size : 0;
      await delay(120);
      const heartbeatAfter = fs.existsSync(heartbeatPath) ? fs.statSync(heartbeatPath).size : 0;
      let replacement = false;
      try {
        const lease = acquireLock(lockPath, { jobDir: '/replacement' });
        replacement = true;
        releaseLock(lockPath, lease.token);
      } catch {}
      process.stdout.write(JSON.stringify({
        graceful,
        ownerCode: first && first.code,
        identityBefore,
        workerAlive: alive(workerPid),
        exitMarker: fs.existsSync(exitPath) ? JSON.parse(fs.readFileSync(exitPath, 'utf8')) : null,
        heartbeatStopped: heartbeatAtExit === heartbeatAfter,
        replacement,
      }));
    })().catch(error => { process.stderr.write(error.stack + '\\n'); process.exit(1); });
  `;
  const observed = JSON.parse(execFileSync(process.execPath, [
    '-e', coordinator, path.join(__dirname, '..', 'run.sh'), fakeBin, dataDir, jobDir,
    source, profile, workerScript, readyPath, exitPath, heartbeatPath, process.execPath,
  ], { encoding: 'utf8', timeout: 10000 }));
  assert.deepStrictEqual(observed, {
    graceful: true,
    ownerCode: 143,
    identityBefore: true,
    workerAlive: false,
    exitMarker: { workerFieldsPresent: false },
    heartbeatStopped: true,
    replacement: true,
  });
});

test('run.sh routes every X-facing Node launch through the recorded-PID wrapper', () => {
  const run = fs.readFileSync(path.join(__dirname, '..', 'run.sh'), 'utf8');
  const lines = run.split('\n');
  const expected = new Map([
    ['smoke-test.cjs', 1],
    ['harvest.cjs', 1],
    ['campaign.cjs', 2],
    ['verify-follows.cjs', 1],
  ]);
  for (const [script, count] of expected) {
    const launches = lines
      .map((line, index) => ({ line, previous: lines[index - 1] || '' }))
      .filter(({ line }) => line.includes(`node "$SCRIPTS/${script}"`));
    assert.strictEqual(launches.length, count, script);
    for (const launch of launches) assert.match(`${launch.previous}\n${launch.line}`, /run_x_worker env/);
  }
  const handler = run.slice(run.indexOf('forward_worker_signal()'), run.indexOf('trap release_run_lock EXIT'));
  assert.match(handler, /worker_pid="\$CURRENT_X_WORKER_PID"/);
  assert.match(handler, /kill -s "\$signal" "\$worker_pid"/);
  assert.doesNotMatch(handler, /pkill|kill\s+-9/);
});

test('owner schema rejects empty, incomplete, and wrong-type JSON without stale recovery', () => {
  const badRecords = [
    {},
    { pid: 1, token: 'a', jobDir: '/job' },
    { pid: '1', token: 'a', jobDir: '/job', startedAt: '2026-08-19T00:00:00.000Z' },
    { pid: 1, token: '', jobDir: '/job', startedAt: '2026-08-19T00:00:00.000Z' },
    { pid: 1, token: 'a', jobDir: 7, startedAt: '2026-08-19T00:00:00.000Z' },
    { pid: 1, token: 'a', jobDir: '/job', startedAt: 'not-a-date' },
  ];
  for (const record of badRecords) {
    const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-schema-'));
    const lockPath = path.join(d, 'network-run.lock');
    fs.mkdirSync(lockPath);
    fs.writeFileSync(path.join(lockPath, 'owner.json'), JSON.stringify(record));
    assert.strictEqual(inspectLock(lockPath).state, 'malformed');
    assert.throws(() => acquireLock(lockPath, { jobDir: '/new' }), /malformed/);
    assert.ok(fs.existsSync(lockPath));
  }
});
test('active recovery marker blocks coordination and stale marker is safely replaced', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-marker-'));
  const lockPath = path.join(d, 'network-run.lock');
  const marker = `${lockPath}.recovery`;
  fs.mkdirSync(marker);
  fs.writeFileSync(path.join(marker, 'owner.json'), JSON.stringify({ pid: process.pid, token: 'active-marker', jobDir: '/coord', startedAt: '2026-08-19T00:00:00.000Z' }));
  assert.throws(() => acquireCoordination(lockPath, { jobDir: '/new' }), /coordination already active/);
  fs.rmSync(marker, { recursive: true });
  fs.mkdirSync(marker);
  fs.writeFileSync(path.join(marker, 'owner.json'), JSON.stringify({ pid: 99999999, token: 'stale-marker', jobDir: '/coord', startedAt: '2026-08-01T00:00:00.000Z' }));
  const lease = acquireCoordination(lockPath, { jobDir: '/new' });
  assert.strictEqual(inspectLock(marker).record.token, lease.token);
  assert.strictEqual(releaseCoordination(lease), true);
  assert.ok(!fs.existsSync(marker));
});
test('old owner token cannot delete a replacement recovered under coordination', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-release-race-'));
  const lockPath = path.join(d, 'network-run.lock');
  fs.mkdirSync(lockPath);
  fs.writeFileSync(path.join(lockPath, 'owner.json'), JSON.stringify({ pid: 99999999, token: 'old-owner', jobDir: '/old', startedAt: '2026-08-01T00:00:00.000Z' }));
  const replacement = acquireLock(lockPath, { jobDir: '/new' });
  assert.strictEqual(releaseLock(lockPath, 'old-owner', 99999999), false);
  assert.strictEqual(inspectLock(lockPath).record.token, replacement.token);
  releaseLock(lockPath, replacement.token);
});
test('concurrent stale recovery and old-owner release leave only a replacement owner', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-release-recover-race-'));
  const lockPath = path.join(d, 'network-run.lock');
  fs.mkdirSync(lockPath);
  fs.writeFileSync(path.join(lockPath, 'owner.json'), JSON.stringify({ pid: 99999999, token: 'old-race-owner', jobDir: '/old', startedAt: '2026-08-01T00:00:00.000Z' }));
  const helper = path.join(SCRIPTS, 'lib', 'run-lock.cjs');
  const worker = `
    const { acquireLock, releaseLock } = require(${JSON.stringify(helper)});
    if (process.argv[1] === 'recover') { acquireLock(process.argv[2], { jobDir: '/new' }); }
    else { releaseLock(process.argv[2], 'old-race-owner', 99999999); }
  `;
  const coordinator = `
    const { spawn } = require('child_process');
    const worker = process.argv[1], lockPath = process.argv[2];
    const children = ['recover', 'release'].map(mode => spawn(process.execPath, ['-e', worker, mode, lockPath]));
    Promise.all(children.map(child => new Promise(resolve => child.on('exit', resolve)))).then(() => process.exit(0));
  `;
  execFileSync('node', ['-e', coordinator, worker, lockPath]);
  const finalOwner = inspectLock(lockPath);
  assert.strictEqual(finalOwner.state, 'ready');
  assert.notStrictEqual(finalOwner.record.token, 'old-race-owner');
});
test('a stale recovery marker runs the main-lock state machine on the first acquire', () => {
  const makeFixture = (main) => {
    const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-marker-main-'));
    const lockPath = path.join(d, 'network-run.lock');
    const marker = `${lockPath}.recovery`;
    fs.mkdirSync(marker);
    fs.writeFileSync(path.join(marker, 'owner.json'), JSON.stringify({ pid: 99999999, token: 'stale-marker', jobDir: '/coord', startedAt: '2026-08-01T00:00:00.000Z' }));
    if (main) {
      fs.mkdirSync(lockPath);
      fs.writeFileSync(path.join(lockPath, 'owner.json'), JSON.stringify(main));
    }
    return { lockPath };
  };
  const missing = makeFixture();
  const missingOwner = acquireLock(missing.lockPath, { jobDir: '/new' });
  assert.strictEqual(inspectLock(missing.lockPath).record.token, missingOwner.token);
  assert.strictEqual(releaseLock(missing.lockPath, missingOwner.token), true);

  const stale = makeFixture({ pid: 99999999, token: 'stale-main', jobDir: '/old', startedAt: '2026-08-01T00:00:00.000Z' });
  const staleOwner = acquireLock(stale.lockPath, { jobDir: '/new' });
  assert.notStrictEqual(staleOwner.token, 'stale-main');
  assert.strictEqual(releaseLock(stale.lockPath, staleOwner.token), true);

  const active = makeFixture({ pid: process.pid, token: 'active-main', jobDir: '/active', startedAt: '2026-08-19T00:00:00.000Z' });
  assert.throws(() => acquireLock(active.lockPath, { jobDir: '/new' }), /already active/);
  assert.strictEqual(inspectLock(active.lockPath).record.token, 'active-main');
  assert.strictEqual(releaseLock(active.lockPath, 'active-main'), true);
});
test('stale recovery takeover leases are recovered while active ones block', () => {
  const makeFixture = (takeover) => {
    const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-takeover-'));
    const lockPath = path.join(d, 'network-run.lock');
    const marker = `${lockPath}.recovery`;
    fs.mkdirSync(marker);
    fs.writeFileSync(path.join(marker, 'owner.json'), JSON.stringify({ pid: 99999999, token: 'stale-marker', jobDir: '/coord', startedAt: '2026-08-01T00:00:00.000Z' }));
    fs.mkdirSync(`${marker}.takeover`);
    fs.writeFileSync(path.join(`${marker}.takeover`, 'owner.json'), JSON.stringify(takeover));
    fs.writeFileSync(leaseIdentityPath(`${marker}.takeover`, takeover), 'lease identity\n');
    return { lockPath, marker };
  };
  const stale = makeFixture({ pid: 99999998, token: 'dead-takeover', jobDir: '/takeover', startedAt: '2026-08-01T00:00:00.000Z' });
  const lease = acquireCoordination(stale.lockPath, { jobDir: '/new' });
  assert.strictEqual(inspectLock(stale.marker).record.token, lease.token);
  assert.ok(!fs.existsSync(`${stale.marker}.takeover`));
  assert.strictEqual(releaseCoordination(lease), true);

  const active = makeFixture({ pid: process.pid, token: 'live-takeover', jobDir: '/takeover', startedAt: '2026-08-19T00:00:00.000Z' });
  assert.throws(() => acquireCoordination(active.lockPath, { jobDir: '/new' }), /takeover already active/);
});
test('failed owner publication removes the directory created by that call', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-publish-failure-'));
  const lockPath = path.join(d, 'network-run.lock');
  const originalWrite = fs.writeFileSync;
  fs.writeFileSync = (file, ...args) => {
    if (String(file).startsWith(`${lockPath}${path.sep}owner.json.`)) throw new Error('simulated owner publish failure');
    return originalWrite(file, ...args);
  };
  try {
    assert.throws(() => acquireLock(lockPath, { jobDir: '/new' }), /simulated owner publish failure/);
  } finally {
    fs.writeFileSync = originalWrite;
  }
  assert.ok(!fs.existsSync(lockPath));
});
test('failed takeover publication leaves the stale coordination marker recoverable', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-takeover-publish-failure-'));
  const lockPath = path.join(d, 'network-run.lock');
  const marker = `${lockPath}.recovery`;
  const takeover = `${marker}.takeover`;
  fs.mkdirSync(marker);
  fs.writeFileSync(path.join(marker, 'owner.json'), JSON.stringify({ pid: 99999999, token: 'stale-marker', jobDir: '/coord', startedAt: '2026-08-01T00:00:00.000Z' }));
  const originalWrite = fs.writeFileSync;
  fs.writeFileSync = (file, ...args) => {
    if (String(file).startsWith(`${takeover}${path.sep}owner.json.`)) throw new Error('simulated takeover publish failure');
    return originalWrite(file, ...args);
  };
  try {
    assert.throws(() => acquireCoordination(lockPath, { jobDir: '/new' }), /simulated takeover publish failure/);
  } finally {
    fs.writeFileSync = originalWrite;
  }
  assert.ok(!fs.existsSync(takeover));
  const lease = acquireCoordination(lockPath, { jobDir: '/new' });
  assert.strictEqual(inspectLock(marker).record.token, lease.token);
  assert.strictEqual(releaseCoordination(lease), true);
});
test('long owner tokens do not lengthen isolated paths and successful isolation is cleaned', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-short-quarantine-'));
  const lockPath = path.join(d, 'network-run.lock');
  const longToken = 'a'.repeat(200);
  fs.mkdirSync(lockPath);
  fs.writeFileSync(path.join(lockPath, 'owner.json'), JSON.stringify({ pid: 99999999, token: longToken, jobDir: '/old', startedAt: '2026-08-01T00:00:00.000Z' }));
  const replacement = acquireLock(lockPath, { jobDir: '/new' });
  assert.deepStrictEqual(fs.readdirSync(d), ['network-run.lock']);
  assert.strictEqual(releaseLock(lockPath, replacement.token), true);
  assert.deepStrictEqual(fs.readdirSync(d), []);
});
function staleRecord(token = 'stale-owner') {
  return { pid: 99999999, token, jobDir: '/old', startedAt: '2026-08-01T00:00:00.000Z' };
}
function assertNoIsolatedLockArtifacts(directory) {
  const artifacts = fs.readdirSync(directory).filter(name => /\.stale-|\.released-|\.takeover(?:\.|$)/.test(name));
  assert.deepStrictEqual(artifacts, []);
}
function withOwnerPublishFailure(canonicalPath, action) {
  const originalWrite = fs.writeFileSync;
  fs.writeFileSync = (file, ...args) => {
    if (String(file).startsWith(`${canonicalPath}${path.sep}owner.json.`)) throw new Error('simulated canonical publish failure');
    return originalWrite(file, ...args);
  };
  try { action(); } finally { fs.writeFileSync = originalWrite; }
}
test('failed main lease publication cleans its isolated stale directory', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-main-isolation-failure-'));
  const lockPath = path.join(d, 'network-run.lock');
  fs.mkdirSync(lockPath);
  fs.writeFileSync(path.join(lockPath, 'owner.json'), JSON.stringify(staleRecord()));
  withOwnerPublishFailure(lockPath, () => {
    assert.throws(() => acquireLock(lockPath, { jobDir: '/new' }), /simulated canonical publish failure/);
  });
  assertNoIsolatedLockArtifacts(d);
  assert.deepStrictEqual(fs.readdirSync(d), []);
});
test('failed recovery marker publication cleans its isolated stale directory', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-marker-isolation-failure-'));
  const lockPath = path.join(d, 'network-run.lock');
  const marker = `${lockPath}.recovery`;
  fs.mkdirSync(marker);
  fs.writeFileSync(path.join(marker, 'owner.json'), JSON.stringify(staleRecord('stale-marker')));
  withOwnerPublishFailure(marker, () => {
    assert.throws(() => acquireLock(lockPath, { jobDir: '/new' }), /simulated canonical publish failure/);
  });
  assertNoIsolatedLockArtifacts(d);
  assert.deepStrictEqual(fs.readdirSync(d), []);
});
test('failed takeover publication cleans its isolated stale directory', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-takeover-isolation-failure-'));
  const lockPath = path.join(d, 'network-run.lock');
  const marker = `${lockPath}.recovery`;
  const takeover = `${marker}.takeover`;
  const oldTakeover = staleRecord('stale-takeover');
  fs.mkdirSync(marker);
  fs.writeFileSync(path.join(marker, 'owner.json'), JSON.stringify(staleRecord('stale-marker')));
  fs.mkdirSync(takeover);
  fs.writeFileSync(path.join(takeover, 'owner.json'), JSON.stringify(oldTakeover));
  fs.writeFileSync(leaseIdentityPath(takeover, oldTakeover), 'lease identity\n');
  withOwnerPublishFailure(takeover, () => {
    assert.throws(() => acquireCoordination(lockPath, { jobDir: '/new' }), /simulated canonical publish failure/);
  });
  assertNoIsolatedLockArtifacts(d);
  assert.deepStrictEqual(fs.readdirSync(d), [path.basename(marker)]);
});
test('stale marker and takeover recovery contention leaves no isolated artifacts', () => {
  const helper = path.join(SCRIPTS, 'lib', 'run-lock.cjs');
  const worker = `
    const { acquireLock } = require(${JSON.stringify(helper)});
    try { acquireLock(process.argv[1], { jobDir: '/new' }); process.stdout.write('ok'); } catch {}
  `;
  const coordinator = `
    const { spawn } = require('child_process');
    const worker = process.argv[1], lockPath = process.argv[2];
    const children = Array.from({ length: 4 }, () => spawn(process.execPath, ['-e', worker, lockPath]));
    Promise.all(children.map(child => new Promise(resolve => child.on('exit', resolve)))).then(() => process.exit(0));
  `;
  for (let i = 0; i < 5; i++) {
    const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-lock-marker-takeover-race-'));
    const lockPath = path.join(d, 'network-run.lock');
    const marker = `${lockPath}.recovery`;
    const takeover = `${marker}.takeover`;
    const oldTakeover = staleRecord(`stale-takeover-${i}`);
    fs.mkdirSync(marker);
    fs.writeFileSync(path.join(marker, 'owner.json'), JSON.stringify(staleRecord(`stale-marker-${i}`)));
    fs.mkdirSync(takeover);
    fs.writeFileSync(path.join(takeover, 'owner.json'), JSON.stringify(oldTakeover));
    fs.writeFileSync(leaseIdentityPath(takeover, oldTakeover), 'lease identity\n');
    execFileSync('node', ['-e', coordinator, worker, lockPath]);
    assertNoIsolatedLockArtifacts(d);
    const owner = inspectLock(lockPath).record;
    assert.ok(owner);
    assert.strictEqual(releaseLock(lockPath, owner.token, owner.pid), true);
    assert.deepStrictEqual(fs.readdirSync(d), []);
  }
});

group('runtime state resolver');
test('runtime state defaults under the x-follow data directory', () => {
  const state = resolveRuntimeState({ HOME: '/home/test' });
  assert.deepStrictEqual(state, {
    dataDir: '/home/test/.config/x-follow-data', runId: 'current', jobDir: '/home/test/.config/x-follow-data/runs/current',
    queuePath: '/home/test/.config/x-follow-data/runs/current/queue.json', trackerPath: '/home/test/.config/x-follow-data/runs/current/tracker.json',
    logPath: '/home/test/.config/x-follow-data/runs/current/campaign.log', alertPath: '/home/test/.config/x-follow-data/runs/current/ALERT.txt',
    statusPath: '/home/test/.config/x-follow-data/runs/current/status.json', skipGlob: '/home/test/.config/x-follow-data/runs/*/tracker.json',
    lockPath: '/home/test/.config/x-follow-data/network-run.lock',
  });
});
test('runtime state preserves explicit JOB_DIR and file paths', () => {
  const state = resolveRuntimeState({ HOME: '/home/test', X_FOLLOW_DATA_DIR: '/data', X_FOLLOW_RUN_ID: 'ignored', JOB_DIR: '/job', QUEUE_PATH: '/queue', TRACKER_PATH: '/tracker', LOG_PATH: '/log', ALERT_PATH: '/alert', STATUS_PATH: '/status', SKIP_GLOB: '/skip/*.json' });
  assert.strictEqual(state.jobDir, '/job');
  assert.strictEqual(state.queuePath, '/queue');
  assert.strictEqual(state.trackerPath, '/tracker');
  assert.strictEqual(state.skipGlob, '/skip/*.json');
});
test('runtime state rejects unsafe run ids', () => {
  for (const runId of ['.', '..', '../bad', 'bad/name', 'bad name']) assert.throws(() => resolveRuntimeState({ HOME: '/home/test', X_FOLLOW_RUN_ID: runId }), /safe single path segment/);
});

group('source profile safety policy');
test('profile policy defaults source and campaign paths, honoring explicit source names', () => {
  const defaults = resolveProfilePolicy({ HOME: '/home/test' });
  assert.strictEqual(defaults.sourceProfileDir, '/home/test/.config/playwright-chrome-profile');
  assert.strictEqual(defaults.profileDir, '/home/test/.config/playwright-chrome-profile-campaign');
  assert.strictEqual(resolveProfilePolicy({ HOME: '/home/test', X_FOLLOW_SOURCE_PROFILE_DIR: '/compat-source' }).sourceProfileDir, '/compat-source');
  assert.strictEqual(resolveProfilePolicy({ HOME: '/home/test', SOURCE_PROFILE_DIR: '/canonical-source', X_FOLLOW_SOURCE_PROFILE_DIR: '/compat-source' }).sourceProfileDir, '/canonical-source');
});
test('profile policy rejects same and normalized source paths but accepts a distinct copy', () => {
  const source = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-source-profile-'));
  assert.throws(() => assertIndependentProfile({ SOURCE_PROFILE_DIR: source, PROFILE_DIR: source }), /PROFILE_DIR must not resolve to SOURCE_PROFILE_DIR/);
  assert.throws(() => assertIndependentProfile({ SOURCE_PROFILE_DIR: source, PROFILE_DIR: path.join(source, '..', path.basename(source)) }), /PROFILE_DIR must not resolve to SOURCE_PROFILE_DIR/);
  assert.doesNotThrow(() => assertIndependentProfile({ SOURCE_PROFILE_DIR: source, PROFILE_DIR: `${source}-campaign` }));
});
test('profile policy resolves an existing symlink before comparing source and profile', () => {
  const source = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-source-profile-link-'));
  const alias = `${source}-alias`;
  fs.symlinkSync(source, alias);
  assert.throws(() => assertIndependentProfile({ SOURCE_PROFILE_DIR: source, PROFILE_DIR: alias }), /PROFILE_DIR must not resolve to SOURCE_PROFILE_DIR/);
});
test('profile policy rejects source descendants and ancestors while allowing siblings', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-profile-tree-'));
  const source = path.join(root, 'source');
  const sibling = path.join(root, 'campaign');
  fs.mkdirSync(path.join(source, 'existing'), { recursive: true });
  assert.throws(() => assertIndependentProfile({ SOURCE_PROFILE_DIR: source, PROFILE_DIR: path.join(source, 'child') }), /must not be equal to, contain, or be contained by/);
  assert.throws(() => assertIndependentProfile({ SOURCE_PROFILE_DIR: path.join(source, 'existing'), PROFILE_DIR: source }), /must not be equal to, contain, or be contained by/);
  assert.doesNotThrow(() => assertIndependentProfile({ SOURCE_PROFILE_DIR: source, PROFILE_DIR: sibling }));
});
test('profile policy resolves the deepest existing symlink parent for a missing leaf', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-profile-symlink-parent-'));
  const source = path.join(root, 'source');
  const alias = path.join(root, 'source-alias');
  fs.mkdirSync(source);
  fs.symlinkSync(source, alias);
  assert.throws(
    () => assertIndependentProfile({ SOURCE_PROFILE_DIR: source, PROFILE_DIR: path.join(alias, 'missing', 'leaf') }),
    /must not be equal to, contain, or be contained by/,
  );
});
test('document profile exports reach a child policy process and preserve the source gate', () => {
  const source = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-doc-source-'));
  const policyModule = path.join(SCRIPTS, 'lib', 'runtime-gate.cjs');
  const runDocumentShell = (profile) => spawnSync('bash', ['-c', [
    `SOURCE_PROFILE_DIR=${JSON.stringify(source)}`,
    `PROFILE_DIR=${JSON.stringify(profile)}`,
    'export SOURCE_PROFILE_DIR PROFILE_DIR',
    `node -e 'try { require(process.argv[1]).assertIndependentProfile(process.env); process.stdout.write(process.env.SOURCE_PROFILE_DIR + "\\n" + process.env.PROFILE_DIR); } catch (error) { console.error(error.message); process.exit(2); }' ${JSON.stringify(policyModule)}`,
  ].join('\n')], { encoding: 'utf8' });
  const same = runDocumentShell(source);
  assert.strictEqual(same.status, 2);
  assert.match(same.stderr, /PROFILE_DIR must not resolve to SOURCE_PROFILE_DIR/);
  const copy = `${source}-campaign`;
  const different = runDocumentShell(copy);
  assert.strictEqual(different.status, 0);
  assert.strictEqual(different.stdout, `${source}\n${copy}`);
});

group('guarded profile copy');
const profileCopyScript = path.join(SCRIPTS, 'prepare-profile-copy.cjs');
function runProfileCopy(sourceProfileDir, profileDir) {
  return spawnSync(process.execPath, [profileCopyScript], {
    env: { ...process.env, SOURCE_PROFILE_DIR: sourceProfileDir, PROFILE_DIR: profileDir },
    encoding: 'utf8',
  });
}
test('profile copy rejects equal, ancestor, descendant, and symlink-parent overlap before side effects', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-profile-copy-overlap-'));
  const source = path.join(root, 'source');
  fs.mkdirSync(path.join(source, 'existing'), { recursive: true });
  const sentinel = path.join(source, 'sentinel');
  fs.writeFileSync(sentinel, 'unchanged');
  const equal = runProfileCopy(source, source);
  assert.strictEqual(equal.status, 2);
  assert.match(equal.stderr, /overlapping login profiles/);
  assert.strictEqual(fs.readFileSync(sentinel, 'utf8'), 'unchanged');

  const child = path.join(source, 'must-not-exist');
  const ancestor = runProfileCopy(source, child);
  assert.strictEqual(ancestor.status, 2);
  assert.match(ancestor.stderr, /overlapping login profiles/);
  assert.ok(!fs.existsSync(child));

  const descendant = runProfileCopy(path.join(source, 'existing'), source);
  assert.strictEqual(descendant.status, 2);
  assert.match(descendant.stderr, /overlapping login profiles/);
  assert.strictEqual(fs.readFileSync(sentinel, 'utf8'), 'unchanged');

  const alias = path.join(root, 'source-alias');
  fs.symlinkSync(source, alias);
  const symlinkChild = path.join(alias, 'missing', 'leaf');
  const symlinkParent = runProfileCopy(source, symlinkChild);
  assert.strictEqual(symlinkParent.status, 2);
  assert.match(symlinkParent.stderr, /overlapping login profiles/);
  assert.ok(!fs.existsSync(path.join(source, 'missing')));
});
test('profile copy fails closed for a missing source or existing target', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-profile-copy-inputs-'));
  const missingTarget = path.join(root, 'missing-target');
  const missingSource = runProfileCopy(path.join(root, 'missing-source'), missingTarget);
  assert.strictEqual(missingSource.status, 2);
  assert.match(missingSource.stderr, /SOURCE_PROFILE_DIR must be an existing directory/);
  assert.ok(!fs.existsSync(missingTarget));

  const source = path.join(root, 'source');
  const target = path.join(root, 'target');
  fs.mkdirSync(source);
  fs.mkdirSync(target);
  const sentinel = path.join(target, 'sentinel');
  fs.writeFileSync(sentinel, 'unchanged');
  const existingTarget = runProfileCopy(source, target);
  assert.strictEqual(existingTarget.status, 2);
  assert.match(existingTarget.stderr, /PROFILE_DIR already exists/);
  assert.strictEqual(fs.readFileSync(sentinel, 'utf8'), 'unchanged');
});
test('profile copy copies an independent existing source into a new target', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-profile-copy-success-'));
  const source = path.join(root, 'source');
  const target = path.join(root, 'target');
  fs.mkdirSync(path.join(source, 'nested'), { recursive: true });
  fs.writeFileSync(path.join(source, 'nested', 'cookie'), 'preserved');
  const result = runProfileCopy(source, target);
  assert.strictEqual(result.status, 0, result.stderr);
  assert.strictEqual(fs.readFileSync(path.join(target, 'nested', 'cookie'), 'utf8'), 'preserved');
});
test('all x-follow profile-copy guidance uses the guarded entry and never raw cp -R', () => {
  const docs = [
    path.join(__dirname, '..', 'SKILL.md'),
    path.join(__dirname, '..', 'README.md'),
    path.join(__dirname, '..', '..', '..', 'README.md'),
    path.join(__dirname, '..', 'references', 'pacing-anti-detection.md'),
    path.join(__dirname, '..', 'references', 'troubleshooting.md'),
  ];
  for (const document of docs) {
    const text = fs.readFileSync(document, 'utf8');
    assert.match(text, /prepare-profile-copy\.cjs/, document);
    assert.doesNotMatch(text, /\bcp\s+-R\b/, document);
  }
  const run = fs.readFileSync(path.join(__dirname, '..', 'run.sh'), 'utf8');
  assert.match(run, /prepare-profile-copy\.cjs/);
  assert.doesNotMatch(run, /say "cp -R/);
});

group('shared crypto filter policy');
test('FILTER_CRYPTO defaults off for direct callers', () => {
  assert.deepStrictEqual(resolveFilterPolicy({}), { filterCrypto: false, noCrypto: false, bioBlacklist: [] });
});
test('FILTER_CRYPTO=1 enables queue and campaign crypto filters', () => {
  const policy = resolveFilterPolicy({ FILTER_CRYPTO: '1' });
  assert.strictEqual(policy.filterCrypto, true);
  assert.strictEqual(policy.noCrypto, true);
  assert.ok(policy.bioBlacklist.includes('crypto'));
});
test('explicit NOCRYPTO and BIO_BLACKLIST override FILTER_CRYPTO', () => {
  assert.deepStrictEqual(resolveFilterPolicy({ FILTER_CRYPTO: '1', NOCRYPTO: '0', BIO_BLACKLIST: 'custom,only' }), { filterCrypto: true, noCrypto: false, bioBlacklist: ['custom', 'only'] });
});
test('crypto flags reject invalid values', () => {
  assert.throws(() => resolveFilterPolicy({ FILTER_CRYPTO: 'true' }), /FILTER_CRYPTO must be 0 or 1/);
  assert.throws(() => resolveFilterPolicy({ NOCRYPTO: 'yes' }), /NOCRYPTO must be 0 or 1/);
});
test('build-queue direct default keeps crypto while FILTER_CRYPTO=1 filters it', () => {
  const d = fixtureDir();
  assert.ok(runBuildQueueEnv(d, {}).includes('BTCwhale'));
  assert.ok(!runBuildQueueEnv(fixtureDir(), { FILTER_CRYPTO: '1' }).includes('BTCwhale'));
});

group('Playwright entry lock gates');
const PLAYWRIGHT_ENTRIES = [
  ['campaign.cjs', ['TARGET=1']],
  ['smoke-test.cjs', []],
  ['harvest.cjs', ['search', 'offline']],
  ['snapshot-following.cjs', ['offline']],
  ['verify-follows.cjs', ['offline']],
];
test('every Playwright entry rejects an active lock before loading playwright', () => {
  const fakeRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-fake-playwright-'));
  const fakeModule = path.join(fakeRoot, 'playwright');
  fs.mkdirSync(fakeModule);
  const marker = path.join(fakeRoot, 'playwright-loaded');
  fs.writeFileSync(path.join(fakeModule, 'index.js'), `require('fs').writeFileSync(${JSON.stringify(marker)}, 'loaded'); throw new Error('fake playwright loaded');`);
  for (const [entry, args] of PLAYWRIGHT_ENTRIES) {
    const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-entry-lock-'));
    const lockPath = path.join(dataDir, 'network-run.lock');
    fs.mkdirSync(lockPath);
    fs.writeFileSync(path.join(lockPath, 'owner.json'), JSON.stringify({ pid: process.pid, token: entry, jobDir: '/other', startedAt: '2026-08-19T00:00:00.000Z' }));
    const env = { ...process.env, NODE_PATH: fakeRoot, X_FOLLOW_DATA_DIR: dataDir };
    if (entry === 'campaign.cjs') env.TARGET = '1';
    const result = spawnSync('node', [path.join(SCRIPTS, entry), ...args.filter(arg => !arg.includes('='))], { env, encoding: 'utf8' });
    assert.strictEqual(result.status, 2, entry);
    assert.match(result.stderr, /network run lock already active/, entry);
    assert.ok(!fs.existsSync(marker), `${entry} loaded playwright`);
  }
});
test('every Playwright entry rejects the source profile before loading playwright', () => {
  const fakeRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-fake-playwright-source-'));
  const fakeModule = path.join(fakeRoot, 'playwright');
  fs.mkdirSync(fakeModule);
  const marker = path.join(fakeRoot, 'playwright-loaded');
  fs.writeFileSync(path.join(fakeModule, 'index.js'), `require('fs').writeFileSync(${JSON.stringify(marker)}, 'loaded'); throw new Error('fake playwright loaded');`);
  for (const [entry, args] of PLAYWRIGHT_ENTRIES) {
    const source = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-entry-source-'));
    const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-entry-source-data-'));
    const env = { ...process.env, NODE_PATH: fakeRoot, X_FOLLOW_DATA_DIR: dataDir, SOURCE_PROFILE_DIR: source, PROFILE_DIR: source };
    if (entry === 'campaign.cjs') env.TARGET = '1';
    const result = spawnSync('node', [path.join(SCRIPTS, entry), ...args.filter(arg => !arg.includes('='))], { env, encoding: 'utf8' });
    assert.strictEqual(result.status, 2, entry);
    assert.match(result.stderr, /PROFILE_DIR must not resolve to SOURCE_PROFILE_DIR/, entry);
    assert.ok(!fs.existsSync(marker), `${entry} loaded playwright`);
    assert.ok(!fs.existsSync(path.join(dataDir, 'network-run.lock')), `${entry} acquired a lock`);
  }
});

group('build-queue historical skip glob');
function historicalFixture() {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-data-'));
  const job = path.join(dataDir, 'runs', 'current');
  const other = path.join(dataDir, 'runs', 'previous');
  fs.mkdirSync(job, { recursive: true });
  fs.mkdirSync(other, { recursive: true });
  fs.writeFileSync(path.join(job, 'tracker.json'), JSON.stringify({ followed: [], rejected: [] }));
  fs.writeFileSync(path.join(other, 'tracker.json'), JSON.stringify({ followed: [{ handle: 'historical' }], rejected: [{ h: 'fers1100', r: 'reject:fers>1100(9000)' }] }));
  fs.writeFileSync(path.join(job, 'cand-01.json'), JSON.stringify({ items: [{ handle: 'historical' }, { handle: 'fers1100' }, { handle: 'fresh' }] }));
  return { dataDir, job };
}
test('default data-dir glob excludes another run tracker including fers>1100 fixture', () => {
  const { dataDir, job } = historicalFixture();
  assert.deepStrictEqual(runBuildQueueEnv(job, { NOCRYPTO: '0', X_FOLLOW_DATA_DIR: dataDir }).sort(), ['fresh']);
});
test('explicit skip glob overrides default data-dir glob', () => {
  const { dataDir, job } = historicalFixture();
  const external = path.join(dataDir, 'external');
  fs.mkdirSync(external);
  fs.writeFileSync(path.join(external, 'tracker.json'), JSON.stringify({ followed: [{ handle: 'fresh' }], rejected: [] }));
  assert.deepStrictEqual(runBuildQueueEnv(job, { NOCRYPTO: '0', X_FOLLOW_DATA_DIR: dataDir, SKIP_GLOB: path.join(external, 'tracker.json') }).sort(), ['fers1100', 'historical']);
});

group('Node 22 runtime fail-closed gates');
test('runtime policy rejects Node below 22 and a missing fs.globSync capability', () => {
  const { assertNodeRuntime } = require(path.join(SCRIPTS, 'lib', 'node-runtime.cjs'));
  assert.throws(() => assertNodeRuntime('21.9.0', { globSync() {} }), /Node\.js >= 22/);
  assert.throws(() => assertNodeRuntime('22.0.0', {}), /fs\.globSync/);
  assert.doesNotThrow(() => assertNodeRuntime('22.0.0', { globSync() {} }));
});
test('build-queue exits FATAL instead of treating a missing fs.globSync as an empty match', () => {
  const d = fixtureDir();
  const preloadDir = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-no-glob-build-'));
  const preload = path.join(preloadDir, 'disable-glob.cjs');
  fs.writeFileSync(preload, "require('fs').globSync = undefined;\n");
  const result = spawnSync('node', [path.join(SCRIPTS, 'build-queue.cjs')], {
    env: { ...process.env, NODE_OPTIONS: `--require=${preload}`, JOB_DIR: d }, encoding: 'utf8',
  });
  assert.strictEqual(result.status, 2);
  assert.match(result.stderr, /FATAL:.*fs\.globSync/);
});
test('run.sh rejects a missing fs.globSync before creating state or lock', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-no-glob-run-'));
  const dataDir = path.join(root, 'state-must-not-exist');
  const preload = path.join(root, 'disable-glob.cjs');
  fs.writeFileSync(preload, "require('fs').globSync = undefined;\n");
  const result = spawnSync('bash', [path.join(__dirname, '..', 'run.sh')], {
    env: { ...process.env, NODE_OPTIONS: `--require=${preload}`, X_FOLLOW_DATA_DIR: dataDir, PROFILE_DIR: path.join(root, 'missing-profile') },
    encoding: 'utf8',
  });
  assert.strictEqual(result.status, 2);
  assert.match(result.stderr + result.stdout, /FATAL:.*fs\.globSync/);
  assert.ok(!fs.existsSync(dataDir));
});
test('README explicitly requires Node.js 22 or newer', () => {
  const readme = fs.readFileSync(path.join(__dirname, '..', 'README.md'), 'utf8');
  assert.match(readme, /Node\.js\s*(?:>=|≥)\s*22/);
});

group('run.sh offline configuration gates');
test('unsafe X_FOLLOW_RUN_ID exits before profile or browser handling', () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-run-state-'));
  const result = spawnSync('bash', [path.join(__dirname, '..', 'run.sh')], {
    env: { ...process.env, X_FOLLOW_DATA_DIR: dataDir, X_FOLLOW_RUN_ID: '../unsafe', PROFILE_DIR: path.join(dataDir, 'missing-profile') },
    encoding: 'utf8',
  });
  assert.strictEqual(result.status, 2);
  assert.match(result.stderr + result.stdout, /safe single path segment/);
  assert.ok(!fs.existsSync(path.join(dataDir, 'network-run.lock')));
});
test('source profile exits before run lock or cleanup pkill', () => {
  const source = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-run-source-'));
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-run-source-data-'));
  const fakeBin = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-fake-pkill-'));
  const pkillMarker = path.join(fakeBin, 'pkill-called');
  const fakePkill = path.join(fakeBin, 'pkill');
  fs.writeFileSync(fakePkill, `#!/bin/sh\ntouch ${JSON.stringify(pkillMarker)}\n`);
  fs.chmodSync(fakePkill, 0o755);
  const result = spawnSync('bash', [path.join(__dirname, '..', 'run.sh')], {
    env: { ...process.env, PATH: `${fakeBin}:${process.env.PATH}`, X_FOLLOW_DATA_DIR: dataDir, SOURCE_PROFILE_DIR: source, PROFILE_DIR: source },
    encoding: 'utf8',
  });
  assert.strictEqual(result.status, 2);
  assert.match(result.stderr + result.stdout, /PROFILE_DIR must not resolve to SOURCE_PROFILE_DIR/);
  assert.ok(!fs.existsSync(path.join(dataDir, 'network-run.lock')));
  assert.ok(!fs.existsSync(pkillMarker));
});
test('run.sh missing-profile guidance preserves resolved source context and routes through the guarded runner', () => {
  const source = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-run-guidance-source-'));
  const profile = path.join(os.tmpdir(), `xf-run-guidance-copy-${process.pid}`);
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-run-guidance-data-'));
  const result = spawnSync('bash', [path.join(__dirname, '..', 'run.sh')], {
    env: { ...process.env, X_FOLLOW_DATA_DIR: dataDir, SOURCE_PROFILE_DIR: source, PROFILE_DIR: profile },
    encoding: 'utf8',
  });
  const output = result.stderr + result.stdout;
  assert.strictEqual(result.status, 3);
  assert.match(output, new RegExp(`SOURCE_PROFILE_DIR="${source.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"`));
  assert.match(output, new RegExp(`PROFILE_DIR="${profile.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"`));
  assert.match(output, /export SOURCE_PROFILE_DIR="[^"]+" PROFILE_DIR="[^"]+"/);
  assert.match(output, /prepare-profile-copy\.cjs/);
  assert.doesNotMatch(output, /\bcp\s+-R\b/);
  assert.match(output, /run\.sh/);
  assert.doesNotMatch(output, /rm\s+-f[^\n]*Singleton/);
});
test('smoke profile guidance routes missing and locked copies through run.sh without manual Singleton cleanup', () => {
  const fakeRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-fake-playwright-guidance-'));
  const fakeModule = path.join(fakeRoot, 'playwright');
  fs.mkdirSync(fakeModule);
  fs.writeFileSync(path.join(fakeModule, 'index.js'), 'module.exports = { chromium: {} };');
  const source = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-smoke-guidance-source-'));
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-smoke-guidance-data-'));
  const runSmoke = (profile) => spawnSync('node', [path.join(SCRIPTS, 'smoke-test.cjs')], {
    env: { ...process.env, NODE_PATH: fakeRoot, X_FOLLOW_DATA_DIR: dataDir, SOURCE_PROFILE_DIR: source, PROFILE_DIR: profile },
    encoding: 'utf8',
  });
  const missing = runSmoke(path.join(os.tmpdir(), `xf-smoke-guidance-missing-${process.pid}`));
  const lockedProfile = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-smoke-guidance-copy-'));
  fs.writeFileSync(path.join(lockedProfile, 'SingletonLock'), 'locked');
  const locked = runSmoke(lockedProfile);
  for (const result of [missing, locked]) {
    const output = result.stderr + result.stdout;
    assert.strictEqual(result.status, 3);
    assert.match(output, /SOURCE_PROFILE_DIR/);
    assert.match(output, /run\.sh/);
    assert.doesNotMatch(output, /rm\s+-f[^\n]*Singleton/);
    assert.doesNotMatch(output, /cp -R ~\/\.config\/playwright-chrome-profile/);
  }
});
test("run.sh supports a JOB_DIR containing a single quote without injecting it into node -e", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-run-quoted-job-'));
  const fakeBin = path.join(root, 'bin');
  const dataDir = path.join(root, 'data');
  const jobDir = path.join(root, "quoted'job");
  const profile = path.join(root, 'campaign-profile');
  fs.mkdirSync(fakeBin);
  fs.mkdirSync(profile);
  fs.writeFileSync(path.join(fakeBin, 'node'), [
    '#!/bin/sh',
    'case "$1" in',
    '  */smoke-test.cjs) exit 0 ;;',
    '  */verify-follows.cjs) printf \'{"failed":[]}\\n\'; exit 0 ;;',
    'esac',
    `exec ${JSON.stringify(process.execPath)} "$@"`,
    '',
  ].join('\n'));
  fs.writeFileSync(path.join(fakeBin, 'pkill'), '#!/bin/sh\nexit 1\n');
  fs.chmodSync(path.join(fakeBin, 'node'), 0o755);
  fs.chmodSync(path.join(fakeBin, 'pkill'), 0o755);
  const result = spawnSync('bash', [path.join(__dirname, '..', 'run.sh')], {
    env: {
      ...process.env,
      PATH: `${fakeBin}:${process.env.PATH}`,
      TARGET: '0',
      X_FOLLOW_DATA_DIR: dataDir,
      JOB_DIR: jobDir,
      SOURCE_PROFILE_DIR: path.join(root, 'source-profile'),
      PROFILE_DIR: profile,
    },
    encoding: 'utf8', timeout: 10000,
  });
  assert.strictEqual(result.status, 0, result.stderr + result.stdout);
  assert.ok(fs.existsSync(path.join(jobDir, 'tracker.json')));
  assert.ok(fs.existsSync(path.join(jobDir, 'status.json')));
  assert.match(result.stdout, /=== DONE ===/);
});
test('run.sh node -e snippets do not interpolate shell paths or query data into JavaScript source', () => {
  const run = fs.readFileSync(path.join(__dirname, '..', 'run.sh'), 'utf8');
  for (const oldInterpolation of [
    "writeFileSync('$STATUS'", "readFileSync('$TRACKER'", "require('$QUEUE')", "const all='$QUERIES'",
    "globSync('$SKIP_GLOB')", "require('$out')", "require('$JOB_DIR/verify-$vpass.json')",
  ]) assert.ok(!run.includes(oldInterpolation), oldInterpolation);
});
test('README stop and empty BIO_BLACKLIST guidance matches safe runtime behavior', () => {
  const readme = fs.readFileSync(path.join(__dirname, '..', 'README.md'), 'utf8');
  assert.doesNotMatch(readme, /kill\s+-9/);
  assert.match(readme, /kill\s+-TERM/);
  assert.match(readme, /kill\s+-INT/);
  assert.doesNotMatch(readme, /空串会回退默认词表故用占位 token/);
  assert.match(readme, /BIO_BLACKLIST.*空串.*空黑名单/);
});

group('Skill manual workflow static contract');
group('pre-existing following merge');
const preExistingMergeScript = path.join(SCRIPTS, 'merge-pre-existing.cjs');
test('snapshot merge preserves tracker fields and case-insensitively adds only new valid handles', () => {
  const { mergePreExisting } = require(preExistingMergeScript);
  const tracker = {
    followed: [{ handle: 'Alice', action: 'followed' }],
    rejected: [{ h: 'BOB', r: 'reject:not_blue' }],
    stats: { profiles_checked: 7, follow_success: 1 },
    custom: { keep: true },
  };
  const merged = mergePreExisting(
    { handles: ['alice', 'bob', 'Charlie', 'CHARLIE', 'invalid-handle!', '', 42] },
    tracker,
  );
  assert.deepStrictEqual(merged, {
    ...tracker,
    rejected: [
      { h: 'BOB', r: 'reject:not_blue' },
      { h: 'Charlie', r: 'pre_existing_follow' },
    ],
  });
});
test('snapshot merge CLI atomically creates/updates tracker and leaves it unchanged on invalid input', () => {
  const jobDir = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-pre-existing-merge-'));
  const snapshotPath = path.join(jobDir, 'my-following.json');
  const trackerPath = path.join(jobDir, 'tracker.json');
  fs.writeFileSync(snapshotPath, JSON.stringify({ handles: ['One', 'Two'] }));
  const created = spawnSync(process.execPath, [preExistingMergeScript, snapshotPath, trackerPath], { encoding: 'utf8' });
  assert.strictEqual(created.status, 0, created.stderr);
  assert.deepStrictEqual(JSON.parse(fs.readFileSync(trackerPath, 'utf8')), {
    followed: [],
    rejected: [
      { h: 'One', r: 'pre_existing_follow' },
      { h: 'Two', r: 'pre_existing_follow' },
    ],
    stats: { profiles_checked: 0, follow_success: 0 },
  });
  assert.deepStrictEqual(fs.readdirSync(jobDir).sort(), ['my-following.json', 'tracker.json']);

  const before = fs.readFileSync(trackerPath);
  fs.writeFileSync(snapshotPath, JSON.stringify({ handles: 'not-an-array' }));
  const invalid = spawnSync(process.execPath, [preExistingMergeScript, snapshotPath, trackerPath], { encoding: 'utf8' });
  assert.strictEqual(invalid.status, 2);
  assert.match(invalid.stderr, /FATAL/);
  assert.deepStrictEqual(fs.readFileSync(trackerPath), before);
  assert.deepStrictEqual(fs.readdirSync(jobDir).sort(), ['my-following.json', 'tracker.json']);
});
test('recommended runner assigns and exports SKILL_DIR before expanding run.sh', () => {
  const skill = fs.readFileSync(path.join(__dirname, '..', 'SKILL.md'), 'utf8');
  const blockStart = skill.indexOf('> ```bash');
  const block = skill.slice(blockStart, skill.indexOf('> ```', blockStart + 5) + 5);
  const lines = block.split('\n');
  const assignmentAt = lines.findIndex(line => /^> SKILL_DIR=/.test(line));
  const exportAt = lines.findIndex(line => line === '> export SKILL_DIR');
  const runnerAt = lines.findIndex(line => /bash "\$SKILL_DIR\/run\.sh"/.test(line));
  assert.ok(assignmentAt >= 0, 'recommended block must assign SKILL_DIR');
  assert.doesNotMatch(lines[assignmentAt], /\\\s*$/, 'SKILL_DIR assignment must be a completed command');
  assert.ok(exportAt > assignmentAt, 'SKILL_DIR must be exported after assignment');
  assert.ok(runnerAt > exportAt, 'run.sh must expand SKILL_DIR only after export');
});
test('manual five-step workflow exports one unique run and keeps every artifact in its JOB_DIR', () => {
  const skill = fs.readFileSync(path.join(__dirname, '..', 'SKILL.md'), 'utf8');
  const workflow = skill.slice(skill.indexOf('## 5 步工作流'), skill.indexOf('## 开工前 user 确认 checklist'));
  const exportAt = workflow.indexOf('export X_FOLLOW_DATA_DIR X_FOLLOW_RUN_ID JOB_DIR');
  assert.ok(exportAt >= 0, 'manual workflow must export data/run/job variables first');
  assert.match(workflow, /X_FOLLOW_RUN_ID=.*manual-.*date.*\$\$/);
  assert.match(workflow, /JOB_DIR="\$X_FOLLOW_DATA_DIR\/runs\/\$X_FOLLOW_RUN_ID"/);
  assert.doesNotMatch(workflow, /\/tmp(?:\/|\b)/);
  for (const artifact of ['cand-search.json', 'cand-replies.json', 'my-following.json']) {
    assert.ok(workflow.includes(`$JOB_DIR/${artifact}`), artifact);
  }
  for (const command of ['harvest.cjs', 'build-queue.cjs', 'snapshot-following.cjs', 'campaign.cjs', 'verify-follows.cjs']) {
    assert.ok(workflow.indexOf(command) > exportAt, `${command} must run after the shared JOB_DIR export`);
  }
  const harvestAt = workflow.indexOf('harvest.cjs');
  const snapshotAt = workflow.indexOf('snapshot-following.cjs');
  const mergeAt = workflow.indexOf('merge-pre-existing.cjs');
  const buildAt = workflow.indexOf('build-queue.cjs');
  assert.ok(harvestAt < snapshotAt, 'snapshot must follow harvest');
  assert.ok(snapshotAt < mergeAt, 'snapshot must be consumed by the tracker merge');
  assert.ok(mergeAt < buildAt, 'queue must be built after pre-existing handles enter tracker.rejected');
});

// ------------------------------------------------------------------- summary
console.log(`\n${'='.repeat(40)}`);
console.log(`  ${pass} passed, ${fail} failed`);
console.log('='.repeat(40));
process.exit(fail === 0 ? 0 : 1);
