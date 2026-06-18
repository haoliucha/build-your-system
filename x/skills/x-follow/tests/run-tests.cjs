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
const { execFileSync } = require('child_process');

const SCRIPTS = path.join(__dirname, '..', 'scripts');
const { parseCount, isCryptoHandle, backoffMs, decide, CRYPTO_TOKENS } = require(path.join(SCRIPTS, 'lib', 'filters.cjs'));
const { buildSkipSet, shouldSkipReason, resolveRejections } = require(path.join(SCRIPTS, 'lib', 'skipset.cjs'));
const { classifyAnomaly } = require(path.join(SCRIPTS, 'lib', 'anomaly.cjs'));

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
const CFG = { VERIFIED_REQUIRED: true, FOLLOWING_GT_FOLLOWERS: true, FERS_MAX: 1100 };
test('good account passes', () => assert.strictEqual(decide({ blue: true, hasFollowBtn: true, fers: 300, fing: 600 }, CFG), 'pass'));
test('not blue rejected', () => assert.strictEqual(decide({ blue: false, hasFollowBtn: true, fers: 300, fing: 600 }, CFG), 'reject:not_blue'));
test('gold org rejected', () => assert.strictEqual(decide({ blue: true, gold: true, hasFollowBtn: true, fers: 300, fing: 600 }, CFG), 'reject:gold_org'));
test('already following never clicked', () => assert.strictEqual(decide({ blue: true, hasUnfollowBtn: true, hasFollowBtn: true, fers: 300, fing: 600 }, CFG), 'reject:already_following'));
test('no follow button', () => assert.strictEqual(decide({ blue: true, hasFollowBtn: false, fers: 300, fing: 600 }, CFG), 'reject:no_follow_btn'));
test('whale over FERS_MAX', () => assert.strictEqual(decide({ blue: true, hasFollowBtn: true, fers: 15000, fing: 20000 }, CFG), 'reject:fers>1100(15000)'));
test('inverted ratio', () => assert.strictEqual(decide({ blue: true, hasFollowBtn: true, fers: 400, fing: 300 }, CFG), 'reject:fing<=fers(300<=400)'));
test('crypto bio (when filter on)', () => assert.strictEqual(decide({ blue: true, hasFollowBtn: true, fers: 300, fing: 600, cryptoMatch: 'web3' }, CFG), 'reject:blacklist(web3)'));
test('crypto allowed when no match passed', () => assert.strictEqual(decide({ blue: true, hasFollowBtn: true, fers: 300, fing: 600, cryptoMatch: null }, CFG), 'pass'));
test('whitelist miss', () => assert.strictEqual(decide({ blue: true, hasFollowBtn: true, fers: 300, fing: 600, whitelistFail: true }, CFG), 'reject:not_in_whitelist'));
test('size beats crypto in order', () => assert.strictEqual(decide({ blue: true, hasFollowBtn: true, fers: 9000, fing: 9999, cryptoMatch: 'btc' }, CFG), 'reject:fers>1100(9000)'));

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

// ----------------------------------------------------- reason-aware skip (FIX)
// The bug: skip-set unioned followed ∪ ALL rejected regardless of WHY rejected, so
// config-dependent rejects (crypto/fers) and transient errors were burned forever.
group('buildSkipSet (reason-aware — the depletion fix)');
test('crypto reject re-eligible when reeval opens reject:blacklist', () =>
  assert.deepStrictEqual(
    buildSkipSet([{ rejected: [{ h: 'cryptodude', r: 'reject:blacklist(web3)' }] }], { reeval: ['reject:blacklist'] }),
    []));
test('crypto reject still skipped with no reeval', () =>
  assert.deepStrictEqual(
    buildSkipSet([{ rejected: [{ h: 'cryptodude', r: 'reject:blacklist(web3)' }] }]),
    ['cryptodude']));
test('eval_error always retried (transient) even without reeval', () =>
  assert.deepStrictEqual(
    buildSkipSet([{ rejected: [{ h: 'ghosted', r: 'eval_error:profile_unavailable' }] }]),
    []));
test('fers>1100 re-eligible when reeval opens reject:fers> prefix', () =>
  assert.deepStrictEqual(
    buildSkipSet([{ rejected: [{ h: 'whale', r: 'reject:fers>1100(9000)' }] }], { reeval: ['reject:fers>'] }),
    []));
test('not_blue still skipped when reeval only opens crypto', () =>
  assert.deepStrictEqual(
    buildSkipSet([{ rejected: [{ h: 'plebe', r: 'reject:not_blue' }] }], { reeval: ['reject:blacklist'] }),
    ['plebe']));
test('followed wins over a stale reject record', () =>
  assert.deepStrictEqual(
    buildSkipSet([{ followed: [{ handle: 'dup' }], rejected: [{ h: 'dup', r: 'reject:blacklist(web3)' }] }], { reeval: ['reject:blacklist'] }),
    ['dup']));
test('original reason survives pre_existing chaining across trackers', () =>
  assert.deepStrictEqual(
    buildSkipSet([
      { rejected: [{ h: 'x', r: 'reject:blacklist(btc)' }] },
      { rejected: [{ h: 'x', r: 'pre_existing' }] },
    ], { reeval: ['reject:blacklist'] }),
    []));
test('seed-marked carry-over records are still classified by reason (seed ignored)', () =>
  assert.deepStrictEqual(
    buildSkipSet([{ rejected: [{ h: 'blueacct', r: 'reject:blacklist(web3)', seed: 1 }] }], { reeval: ['reject:blacklist'] }),
    []));

group('shouldSkipReason');
test('transient -> false (retry)', () => assert.strictEqual(shouldSkipReason('eval_error:profile_unavailable'), false));
test('stable -> true (skip)', () => assert.strictEqual(shouldSkipReason('reject:not_blue'), true));
test('reeval match -> false (re-evaluate)', () => assert.strictEqual(shouldSkipReason('reject:blacklist(web3)', ['reject:blacklist']), false));
test('unknown/empty reason -> true (conservative skip)', () => assert.strictEqual(shouldSkipReason(''), true));

group('resolveRejections (reason-preserving seed)');
test('prior-followed tagged pre_existing_follow', () =>
  assert.deepStrictEqual(resolveRejections([{ followed: [{ handle: 'a' }], rejected: [] }]), [{ h: 'a', r: 'pre_existing_follow' }]));
test('reject reason preserved (not flattened to pre_existing)', () =>
  assert.deepStrictEqual(resolveRejections([{ rejected: [{ h: 'b', r: 'reject:blacklist(web3)' }] }]), [{ h: 'b', r: 'reject:blacklist' }]));
test('best reason wins over pre_existing chaining', () =>
  assert.deepStrictEqual(resolveRejections([
    { rejected: [{ h: 'c', r: 'pre_existing' }] },
    { rejected: [{ h: 'c', r: 'reject:fers>1100(5000)' }] },
  ]), [{ h: 'c', r: 'reject:fers>1100' }]));

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
function runBuildQueue(dir, nocrypto, reeval) {
  execFileSync('node', [path.join(SCRIPTS, 'build-queue.cjs')], {
    env: { ...process.env, JOB_DIR: dir, NOCRYPTO: nocrypto, REEVAL_REASONS: reeval || '' }, stdio: 'ignore',
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
test('REEVAL_REASONS un-skips a config-bound (crypto) reject end-to-end', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xf-reeval-'));
  fs.writeFileSync(path.join(d, 'tracker.json'), JSON.stringify({ followed: [], rejected: [{ h: 'blueacct', r: 'reject:blacklist(web3)' }] }));
  fs.writeFileSync(path.join(d, 'cand-01.json'), JSON.stringify({ items: [{ handle: 'blueacct' }, { handle: 'carol' }] }));
  assert.deepStrictEqual(runBuildQueue(d, '0').sort(), ['carol']);                       // no reeval -> still skipped
  assert.deepStrictEqual(runBuildQueue(d, '0', 'reject:blacklist').sort(), ['blueacct', 'carol']); // reeval -> recovered
});

// ------------------------------------------------------------------- summary
console.log(`\n${'='.repeat(40)}`);
console.log(`  ${pass} passed, ${fail} failed`);
console.log('='.repeat(40));
process.exit(fail === 0 ? 0 : 1);
