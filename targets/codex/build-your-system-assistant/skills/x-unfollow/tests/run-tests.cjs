#!/usr/bin/env node
// run-tests.cjs — zero-dependency test suite for the x-unfollow skill.
//
// Locks down the PURE follow-hygiene logic (date math, history, streaks, the decision
// order) plus an end-to-end classify.cjs integration against fixtures. The live browser
// path (snapshot/unfollow/verify) needs X login and is exercised by run.sh against real X.
// Run: node tests/run-tests.cjs

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync, spawnSync } = require('child_process');

const SCRIPTS = path.join(__dirname, '..', 'scripts');
const H = require(path.join(SCRIPTS, 'lib', 'hygiene.cjs'));
const PC = require(path.join(SCRIPTS, 'profile-counts.cjs'));

let pass = 0, fail = 0;
function test(name, fn) { try { fn(); console.log(`  ✅ ${name}`); pass++; } catch (e) { console.log(`  ❌ ${name}\n     ${e.message}`); fail++; } }
function group(t) { console.log(`\n${t}`); }

// -------------------------------------------- network run concurrency lock
group('network run lock (concurrency only, no cooldown)');
test('rate policy contains no time-based full-run cooldown', () => {
  const policy = require(path.join(SCRIPTS, 'lib', 'rate-policy.cjs'));
  assert.strictEqual(Object.prototype.hasOwnProperty.call(policy, 'FULL_RUN_COOLDOWN_MS'), false);
});
test('one live owner blocks a concurrent claim; release permits an immediate new claim', () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'xu-lock-'));
  const cli = path.join(SCRIPTS, 'run-lock.cjs');
  const env = { ...process.env, XU_DATA_DIR: dataDir, XU_RUN_OWNER_PID: String(process.pid) };
  const first = spawnSync(process.execPath, [cli, 'claim'], { env, encoding: 'utf8' });
  assert.strictEqual(first.status, 0, first.stderr);
  const token = first.stdout.trim();
  assert.ok(token.length >= 16, 'claim must return a non-trivial token');

  const concurrent = spawnSync(process.execPath, [cli, 'claim'], { env, encoding: 'utf8' });
  assert.strictEqual(concurrent.status, 18, concurrent.stderr);

  const wrongRelease = spawnSync(process.execPath, [cli, 'release', 'wrong-token'], { env, encoding: 'utf8' });
  assert.strictEqual(wrongRelease.status, 19, wrongRelease.stderr);

  const release = spawnSync(process.execPath, [cli, 'release', token], { env, encoding: 'utf8' });
  assert.strictEqual(release.status, 0, release.stderr);
  const immediate = spawnSync(process.execPath, [cli, 'claim'], { env, encoding: 'utf8' });
  assert.strictEqual(immediate.status, 0, immediate.stderr);
});
test('a lock owned by a dead process is reclaimed', () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'xu-stale-lock-'));
  const lockDir = path.join(dataDir, '.network-run.lock');
  fs.mkdirSync(lockDir, { recursive: true });
  fs.writeFileSync(path.join(lockDir, 'owner.json'), JSON.stringify({ token: 'stale', ownerPid: 99999999, startedAt: '2020-01-01T00:00:00.000Z' }));
  const cli = path.join(SCRIPTS, 'run-lock.cjs');
  const env = { ...process.env, XU_DATA_DIR: dataDir, XU_RUN_OWNER_PID: String(process.pid) };
  const claimed = spawnSync(process.execPath, [cli, 'claim'], { env, encoding: 'utf8' });
  assert.strictEqual(claimed.status, 0, claimed.stderr);
  assert.notStrictEqual(claimed.stdout.trim(), 'stale');
});

// -------------------------------------------- bulk verification from /following snapshot
group('bulk unfollow verification (one following-list scan + local set diff)');
test('diff is case-insensitive, de-duplicates targets, and separates removed/remaining', () => {
  const D = require(path.join(SCRIPTS, 'lib', 'following-diff.cjs'));
  const out = D.diffFollowing(['@Alice', 'bob', 'ALICE', 'carol'], [
    { handle: 'BOB' }, { handle: 'someone_else' },
  ]);
  assert.deepStrictEqual(out.requested, ['Alice', 'bob', 'carol']);
  assert.deepStrictEqual(out.removed, ['Alice', 'carol']);
  assert.deepStrictEqual(out.remaining, ['bob']);
  assert.deepStrictEqual(out.results.map((r) => [r.handle, r.not_following]), [
    ['Alice', true], ['bob', false], ['carol', true],
  ]);
});
test('coverage retains raw percentage while display percentage is capped at 100', () => {
  const D = require(path.join(SCRIPTS, 'lib', 'following-diff.cjs'));
  assert.deepStrictEqual(D.coverageSummary(610, 604, 95), {
    scannedTotal: 610,
    headerFollowingCount: 604,
    rawCoveragePct: 101,
    coveragePct: 100,
    coverageWarning: false,
  });
});
test('verify-unfollow CLI reads one snapshot locally and never imports Playwright', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xu-verify-list-'));
  fs.mkdirSync(path.join(d, 'reports'), { recursive: true });
  fs.mkdirSync(path.join(d, 'snapshots'), { recursive: true });
  fs.writeFileSync(path.join(d, 'reports', 'unfollow-2026-08-08.json'), JSON.stringify({ results: [
    { handle: 'alice', action: 'unfollowed' },
    { handle: 'bob', action: 'unfollowed' },
  ] }));
  fs.writeFileSync(path.join(d, 'snapshots', '2026-08-08-post-unfollow.jsonl'), [
    JSON.stringify({ handle: 'Bob' }), JSON.stringify({ handle: 'other' }),
  ].join('\n') + '\n');
  fs.writeFileSync(path.join(d, 'snapshots', '2026-08-08-post-unfollow.meta.json'), JSON.stringify({
    scannedTotal: 2, headerFollowingCount: 2, rawCoveragePct: 100, coveragePct: 100, coverageWarning: false,
  }));
  const cli = path.join(SCRIPTS, 'verify-unfollow.cjs');
  const run = spawnSync(process.execPath, [cli, '--date=2026-08-08', '--snapshot-date=2026-08-08-post-unfollow'], {
    env: { ...process.env, XU_DATA_DIR: d }, encoding: 'utf8',
  });
  assert.strictEqual(run.status, 0, run.stderr);
  const report = JSON.parse(fs.readFileSync(path.join(d, 'reports', 'verify-unfollow-2026-08-08.json'), 'utf8'));
  assert.deepStrictEqual(report.results.map((r) => [r.handle, r.not_following]), [['alice', true], ['bob', false]]);
  const source = fs.readFileSync(cli, 'utf8');
  assert.ok(!/require\(['"]playwright['"]\)/.test(source));
  assert.ok(!source.includes('checkHandle('));
});

// -------------------------------------------- resumable same-date action log
group('same-date unfollow action log (merge + resume)');
test('merge preserves prior handles and replaces a repeated handle with its newest result', () => {
  const A = require(path.join(SCRIPTS, 'lib', 'action-log.cjs'));
  const merged = A.mergeResultsByHandle([
    { handle: 'alice', action: 'unfollowed', at: 'old' },
    { handle: 'bob', action: 'none', at: 'old' },
  ], [
    { handle: '@BOB', action: 'unfollowed', at: 'new' },
    { handle: 'carol', action: 'skip', at: 'new' },
  ]);
  assert.deepStrictEqual(merged.map((row) => [row.handle, row.action, row.at]), [
    ['alice', 'unfollowed', 'old'], ['@BOB', 'unfollowed', 'new'], ['carol', 'skip', 'new'],
  ]);
});
test('invalid or missing old action log safely loads as an empty list', () => {
  const A = require(path.join(SCRIPTS, 'lib', 'action-log.cjs'));
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xu-action-log-'));
  const bad = path.join(d, 'bad.json');
  fs.writeFileSync(bad, '{not json');
  assert.deepStrictEqual(A.loadResults(path.join(d, 'missing.json')), []);
  assert.deepStrictEqual(A.loadResults(bad), []);
});
test('network scripts contain no unfollow_assumed or per-profile VERIFY policy compatibility', () => {
  const files = [
    path.join(SCRIPTS, 'unfollow.cjs'), path.join(SCRIPTS, 'verify-unfollow.cjs'),
    path.join(SCRIPTS, 'classify.cjs'), path.join(SCRIPTS, 'lib', 'rate-policy.cjs'),
  ];
  const source = files.map((file) => fs.readFileSync(file, 'utf8')).join('\n');
  assert.ok(!source.includes('unfollow_assumed'));
  assert.ok(!source.includes('VERIFY_MAX_PER_RUN'));
  assert.ok(!source.includes('VERIFY_WAIT_'));
});
test('run.sh supports an explicitly authorized handle recovery without re-running classification', () => {
  const source = fs.readFileSync(path.join(SCRIPTS, '..', 'run.sh'), 'utf8');
  assert.ok(source.includes('EXPLICIT_HANDLES'));
  assert.ok(source.includes('--handles="$EXPLICIT_HANDLES"'));
  assert.ok(source.includes('MODE=unfollow is required when EXPLICIT_HANDLES is set'));
  assert.ok(source.includes('skipping pre-action snapshot/classification'));
});

// -------------------------------------------- unfollow UI safety (subscription regression)
group('unfollow UI safety (semantic controls only)');
const DOM_FIXTURE = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'unfollow-dom.json'), 'utf8'));
test('offline control fixtures preserve exact-handle semantics and reject subscribe', () => {
  const U = require(path.join(SCRIPTS, 'lib', 'unfollow-safety.cjs'));
  for (const fixture of DOM_FIXTURE.controls) {
    assert.strictEqual(U.isExactUnfollowControl(fixture.control, fixture.handle), fixture.expected, fixture.name);
  }
});
test('follows-you detection only considers the target profile header scope', () => {
  const U = require(path.join(SCRIPTS, 'lib', 'unfollow-safety.cjs'));
  for (const fixture of DOM_FIXTURE.profileScopes) {
    assert.strictEqual(U.isTargetProfileFollowingYou(fixture.scope), fixture.expected, fixture.name);
  }
});
test('mutual protection can be bypassed only by an explicit-handle authorized override', () => {
  const U = require(path.join(SCRIPTS, 'lib', 'unfollow-safety.cjs'));
  assert.strictEqual(U.shouldSkipMutual({ followsYou: true, allowMutual: false, explicitHandles: true }), true);
  assert.strictEqual(U.shouldSkipMutual({ followsYou: true, allowMutual: true, explicitHandles: false }), true);
  assert.strictEqual(U.shouldSkipMutual({ followsYou: true, allowMutual: true, explicitHandles: true }), false);
  assert.strictEqual(U.shouldSkipMutual({ followsYou: false, allowMutual: false, explicitHandles: false }), false);
});
test('rejects X subscription button even when testid falsely ends in -unfollow', () => {
  const U = require(path.join(SCRIPTS, 'lib', 'unfollow-safety.cjs'));
  assert.strictEqual(U.isExactUnfollowControl({
    ariaLabel: '订阅 到 @yangyi', text: '订阅', testid: '3122661542-unfollow',
  }, 'yangyi'), false);
});
test('accepts the real aria-labelled unfollow control without a testid', () => {
  const U = require(path.join(SCRIPTS, 'lib', 'unfollow-safety.cjs'));
  assert.strictEqual(U.isExactUnfollowControl({
    ariaLabel: '取消关注 @yangyi', text: '', testid: null,
  }, 'yangyi'), true);
});
test('accepts standard Following/正在关注 state control for the exact target', () => {
  const U = require(path.join(SCRIPTS, 'lib', 'unfollow-safety.cjs'));
  assert.strictEqual(U.isExactUnfollowControl({ ariaLabel: '正在关注 @Alpha_Logs' }, 'Alpha_Logs'), true);
  assert.strictEqual(U.isExactUnfollowControl({ ariaLabel: 'Following @alice' }, 'alice'), true);
});
test('rejects an unfollow control for a different handle', () => {
  const U = require(path.join(SCRIPTS, 'lib', 'unfollow-safety.cjs'));
  assert.strictEqual(U.isExactUnfollowControl({ ariaLabel: '取消关注 @other' }, 'yangyi'), false);
});
test('confirmation dialog must explicitly name the unfollow action and target', () => {
  const U = require(path.join(SCRIPTS, 'lib', 'unfollow-safety.cjs'));
  assert.strictEqual(U.isExactUnfollowConfirmation('取消关注 @yangyi？\n取消关注', 'yangyi'), true);
  assert.strictEqual(U.isExactUnfollowConfirmation('订阅 @yangyi\n订阅 · US$6.00/月', 'yangyi'), false);
});
test('confirmation container selector covers X alertdialog and confirmation sheet', () => {
  const U = require(path.join(SCRIPTS, 'lib', 'unfollow-safety.cjs'));
  assert.ok(U.UNFOLLOW_CONFIRM_CONTAINER_SELECTOR.includes('[role="alertdialog"]'));
  assert.ok(U.UNFOLLOW_CONFIRM_CONTAINER_SELECTOR.includes('[data-testid="confirmationSheetDialog"]'));
});
test('intermediate menu item must explicitly name the unfollow action and target', () => {
  const U = require(path.join(SCRIPTS, 'lib', 'unfollow-safety.cjs'));
  assert.strictEqual(U.isExactUnfollowMenuItem('取消关注 @dingyi', 'dingyi'), true);
  assert.strictEqual(U.isExactUnfollowMenuItem('订阅 @dingyi', 'dingyi'), false);
  assert.strictEqual(U.isExactUnfollowMenuItem('取消关注 @other', 'dingyi'), false);
});
test('direct menu action counts only when exact unfollow is gone and exact follow appears', () => {
  const U = require(path.join(SCRIPTS, 'lib', 'unfollow-safety.cjs'));
  assert.strictEqual(U.isVerifiedNotFollowingState({ stillUnfollow: false, nowFollow: true }), true);
  assert.strictEqual(U.isVerifiedNotFollowingState({ stillUnfollow: false, nowFollow: false }), false);
  assert.strictEqual(U.isVerifiedNotFollowingState({ stillUnfollow: true, nowFollow: true }), false);
});

// ---------------------------------------------------------- date math
group('naturalDaysBetween / addDays');
test('same day = 0', () => assert.strictEqual(H.naturalDaysBetween('2026-06-18', '2026-06-18'), 0));
test('4 natural days', () => assert.strictEqual(H.naturalDaysBetween('2026-06-14', '2026-06-18'), 4));
test('spans month boundary', () => assert.strictEqual(H.naturalDaysBetween('2026-05-30', '2026-06-02'), 3));
test('addDays forward', () => assert.strictEqual(H.addDays('2026-06-18', 4), '2026-06-22'));
test('addDays backward', () => assert.strictEqual(H.addDays('2026-06-01', -1), '2026-05-31'));

// ---------------------------------------------------------- handle helpers
group('normalizeHandle / isValidHandle / isNavOrMiscrape');
test('normalize strips @ and lowercases', () => assert.strictEqual(H.normalizeHandle('@AliceB'), 'aliceb'));
test('valid handle', () => assert.strictEqual(H.isValidHandle('alice_99'), true));
test('invalid handle (too long)', () => assert.strictEqual(H.isValidHandle('abcdefghijklmnop'), false));
test('invalid handle (slash)', () => assert.strictEqual(H.isValidHandle('a/b'), false));
test('nav handle home', () => assert.strictEqual(H.isNavOrMiscrape('home'), true));
test('nav handle @Search cased', () => assert.strictEqual(H.isNavOrMiscrape('@Search'), true));
test('real handle not nav', () => assert.strictEqual(H.isNavOrMiscrape('alice'), false));

// ---------------------------------------------------------- buildHistoryFromSnapshots
group('buildHistoryFromSnapshots (firstSeen/lastSeen across days)');
const SNAP = [
  { handle: 'Alice', isFollowingMe: false, snapshotDate: '2026-06-12', name: 'A old', followers: 100 },
  { handle: 'alice', isFollowingMe: false, snapshotDate: '2026-06-18', name: 'A new', followers: 120 },
  { handle: 'bob', isFollowingMe: false, snapshotDate: '2026-06-18', name: 'B', followers: 50 },
  { handle: 'carol', isFollowingMe: true, snapshotDate: '2026-06-18', name: 'C', followers: 10 }, // follows back -> ignored
];
test('firstSeen = earliest, lastSeen = latest, case-insensitive key', () => {
  const m = H.buildHistoryFromSnapshots(SNAP);
  const a = m.get('alice');
  assert.strictEqual(a.firstSeen, '2026-06-12');
  assert.strictEqual(a.lastSeen, '2026-06-18');
  assert.strictEqual(a.name, 'A new');
});
test('reciprocal rows excluded', () => assert.strictEqual(H.buildHistoryFromSnapshots(SNAP).has('carol'), false));

// ---------------------------------------------------------- computeStreaks
group('computeStreaks (consecutive days ending today)');
const STREAK_SNAP = [
  { handle: 'alice', isFollowingMe: false, snapshotDate: '2026-06-16', name: 'A', followers: 1 },
  { handle: 'alice', isFollowingMe: false, snapshotDate: '2026-06-17', name: 'A', followers: 1 },
  { handle: 'alice', isFollowingMe: false, snapshotDate: '2026-06-18', name: 'A', followers: 1 },
  { handle: 'bob', isFollowingMe: false, snapshotDate: '2026-06-10', name: 'B', followers: 1 },
  { handle: 'bob', isFollowingMe: false, snapshotDate: '2026-06-18', name: 'B', followers: 1 }, // gap -> streak 1
];
test('consecutive 3-day streak', () => {
  const s = H.computeStreaks(STREAK_SNAP, '2026-06-18');
  assert.strictEqual(s.find((x) => x.handle === 'alice').currentStreak, 3);
});
test('gap breaks streak to 1', () => {
  const s = H.computeStreaks(STREAK_SNAP, '2026-06-18');
  assert.strictEqual(s.find((x) => x.handle === 'bob').currentStreak, 1);
});

// ---------------------------------------------------------- classifyDecision (order!)
group('classifyDecision (decision order & boundaries)');
const CFG = { minDays: 3, followerThreshold: 2000 };
const base = { validHandle: true, navOrMiscrape: false, excluded: false, elapsed: 8, hasRefreshed: true, refreshedFollowers: 500 };
const code = (f) => H.classifyDecision({ ...base, ...f }, CFG).reason_code;
test('invalid handle first', () => assert.strictEqual(code({ validHandle: false }), 'EXCLUDE_INVALID_HANDLE'));
test('nav before excluded', () => assert.strictEqual(code({ navOrMiscrape: true, excluded: true }), 'EXCLUDE_NAV_OR_MISCRAPE'));
test('already unfollowed', () => assert.strictEqual(code({ excluded: true }), 'EXCLUDE_ALREADY_UNFOLLOWED'));
test('elapsed null -> waiting', () => assert.strictEqual(code({ elapsed: null }), 'KEEP_WAITING_GT3'));
test('elapsed == minDays -> waiting (exclusive)', () => assert.strictEqual(code({ elapsed: 3 }), 'KEEP_WAITING_GT3'));
test('elapsed minDays+1, no refresh -> refresh', () => assert.strictEqual(code({ elapsed: 4, hasRefreshed: false, refreshedFollowers: null }), 'ELIGIBLE_FOR_FOLLOWER_REFRESH'));
test('past wait, count >= threshold -> exclude', () => assert.strictEqual(code({ elapsed: 4, refreshedFollowers: 2000 }), 'EXCLUDE_FOLLOWERS_GE_THRESHOLD'));
test('past wait, count < threshold -> eligible', () => assert.strictEqual(code({ elapsed: 4, refreshedFollowers: 1999 }), 'ELIGIBLE_FOR_UNFOLLOW'));
test('eligible decision string', () => assert.strictEqual(H.classifyDecision({ ...base, elapsed: 8 }, CFG).decision, 'candidate_unfollow'));
test('refresh decision flags needs_profile_refresh', () => assert.strictEqual(H.classifyDecision({ ...base, elapsed: 8, hasRefreshed: false, refreshedFollowers: null }, CFG).needs_profile_refresh, true));

// ---------------------------------------------- profile-counts JSON-LD parsing
group('profile-counts extractJsonLd / stat (nonce tolerance)');
// X serves the ld+json tag WITH a CSP nonce. The parser must tolerate extra attributes,
// otherwise every refresh returns followers_count:null (the silent-200 bug).
const LD_NONCE = '<script type="application/ld+json" nonce="S0g3qDb/Sfs/irlMr/p5Uw==">' +
  JSON.stringify({ '@type': 'ProfilePage', mainEntity: { name: 'Ex Hu', interactionStatistic: [
    { '@type': 'InteractionCounter', name: 'Follows', userInteractionCount: 730 },
    { '@type': 'InteractionCounter', name: 'Friends', userInteractionCount: 1200 },
  ] } }) + '</script>';
test('extracts ld+json despite nonce attribute', () => {
  const blocks = PC.extractJsonLd(LD_NONCE);
  assert.strictEqual(blocks.length, 1);
  assert.strictEqual(blocks[0]['@type'], 'ProfilePage');
});
test('stat reads follower count from ProfilePage', () => {
  const profile = PC.extractJsonLd(LD_NONCE).find((o) => o['@type'] === 'ProfilePage');
  assert.strictEqual(PC.stat(profile, 'Follows', 'FollowAction'), 730);
});
test('plain tag (no attributes) still parses', () => {
  const plain = '<script type="application/ld+json">' + JSON.stringify({ '@type': 'ProfilePage', mainEntity: {} }) + '</script>';
  assert.strictEqual(PC.extractJsonLd(plain).length, 1);
});
test('decodes html entities inside ld+json', () => {
  const enc = '<script type="application/ld+json" nonce="x">' + '{&quot;@type&quot;:&quot;ProfilePage&quot;}' + '</script>';
  assert.strictEqual(PC.extractJsonLd(enc)[0]['@type'], 'ProfilePage');
});

// ---------------------------------------------------- classify.cjs integration
group('classify.cjs integration (state dir + csv escaping)');
function fixtureDir() {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xu-test-'));
  const snap = path.join(d, 'snapshots'); const rep = path.join(d, 'reports');
  fs.mkdirSync(snap, { recursive: true }); fs.mkdirSync(rep, { recursive: true });
  const row = (handle, name, followers) => JSON.stringify({ handle, name, followers, isFollowingMe: false });
  // old snapshot establishes firstSeen for alice/bob/dave
  fs.writeFileSync(path.join(snap, '2026-06-10.jsonl'), [row('alice', 'A', 100), row('bob', 'B', 100), row('dave', 'D', 100)].join('\n') + '\n');
  // today: alice, bob, dave (old), carol (new today), home (nav), name with comma
  fs.writeFileSync(path.join(snap, '2026-06-18.jsonl'), [
    row('alice', 'Alice, the great', 100), row('bob', 'B', 100), row('dave', 'D', 100),
    row('carol', 'C', 5), row('home', 'nav', 0),
    // post-fix snapshots also carry mutual rows — classify must skip them
    JSON.stringify({ handle: 'mallory', name: 'M', followers: 0, isFollowingMe: true }),
  ].join('\n') + '\n');
  // alice refreshed below threshold (eligible), bob above (exclude). carol/dave not refreshed.
  fs.writeFileSync(path.join(rep, 'profile-refresh-2026-06-18.json'), JSON.stringify({ results: [
    { handle: 'alice', followers_count: 500 }, { handle: 'bob', followers_count: 5000 },
  ] }));
  // dave already unfollowed previously -> excluded
  fs.writeFileSync(path.join(rep, 'unfollow-2026-06-17.json'), JSON.stringify({ results: [{ handle: 'dave', action: 'unfollowed' }] }));
  return d;
}
function runClassify(dir) {
  execFileSync('node', [path.join(SCRIPTS, 'classify.cjs'), '--date=2026-06-18', '--min-days=3', '--follower-threshold=2000'],
    { env: { ...process.env, XU_DATA_DIR: dir }, stdio: 'ignore' });
  return JSON.parse(fs.readFileSync(path.join(dir, 'reports', 'non-recip-reasons-2026-06-18.json'), 'utf8'));
}
test('decisions wire end-to-end', () => {
  const d = fixtureDir();
  const out = runClassify(d);
  const by = Object.fromEntries(out.rows.map((r) => [r.handle, r.reason_code]));
  assert.strictEqual(by.alice, 'ELIGIBLE_FOR_UNFOLLOW');
  assert.strictEqual(by.bob, 'EXCLUDE_FOLLOWERS_GE_THRESHOLD');
  assert.strictEqual(by.carol, 'KEEP_WAITING_GT3');
  assert.strictEqual(by.dave, 'EXCLUDE_ALREADY_UNFOLLOWED');
  assert.strictEqual(by.home, 'EXCLUDE_NAV_OR_MISCRAPE');
});
test('only ELIGIBLE rows are candidate_unfollow', () => {
  const d = fixtureDir();
  const out = runClassify(d);
  assert.deepStrictEqual(out.rows.filter((r) => r.decision === 'candidate_unfollow').map((r) => r.handle), ['alice']);
});
test('csv quotes values containing commas', () => {
  const d = fixtureDir();
  runClassify(d);
  const csv = fs.readFileSync(path.join(d, 'reports', 'non-recip-reasons-2026-06-18.csv'), 'utf8');
  assert.ok(csv.includes('"Alice, the great"'), 'comma-containing name must be quoted');
});
test('mutual (isFollowingMe:true) rows are skipped from today', () => {
  const d = fixtureDir();
  const out = runClassify(d);
  assert.strictEqual(out.rows.find((r) => r.handle === 'mallory'), undefined, 'mutual row must not be classified');
  assert.strictEqual(out.totals.todayMutualRowsSkipped, 1);
  assert.deepStrictEqual(out.rows.filter((r) => r.decision === 'candidate_unfollow').map((r) => r.handle), ['alice'], 'candidate list unchanged');
});

// --------------------------------------- follower-count reuse across days (TTL)
// The expensive profile-counts fetch must NOT re-run for an account whose count was
// gathered within --refresh-ttl-days. These lock the reuse window + the staleness boundary.
group('follower-count reuse across days (--refresh-ttl-days)');
function ttlFixtureDir() {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'xu-ttl-'));
  const snap = path.join(d, 'snapshots'); const rep = path.join(d, 'reports');
  fs.mkdirSync(snap, { recursive: true }); fs.mkdirSync(rep, { recursive: true });
  const row = (handle, name) => JSON.stringify({ handle, name, followers: 0, isFollowingMe: false });
  // firstSeen 2026-06-10 -> on 2026-06-25 everyone is well past the 3-day wait.
  fs.writeFileSync(path.join(snap, '2026-06-10.jsonl'), [row('alice', 'A'), row('bob', 'B'), row('dave', 'D')].join('\n') + '\n');
  fs.writeFileSync(path.join(snap, '2026-06-25.jsonl'), [row('alice', 'A'), row('bob', 'B'), row('dave', 'D')].join('\n') + '\n');
  // alice: refreshed 2 days ago (within 14d TTL) -> reuse 500, no re-fetch.
  fs.writeFileSync(path.join(rep, 'profile-refresh-2026-06-23.json'), JSON.stringify({ results: [
    { handle: 'alice', followers_count: 500, ok: true, refreshedAt: '2026-06-23T08:00:00.000Z' },
  ] }));
  // bob: refreshed 20 days ago (older than 14d TTL) -> stale, must re-fetch.
  fs.writeFileSync(path.join(rep, 'profile-refresh-2026-06-05.json'), JSON.stringify({ results: [
    { handle: 'bob', followers_count: 300, ok: true, refreshedAt: '2026-06-05T08:00:00.000Z' },
  ] }));
  // dave: an OLD success (400) then a NEWER FAILED refresh (null). The failure must not
  // shadow the good value — dave stays reusable at 400.
  fs.writeFileSync(path.join(rep, 'profile-refresh-2026-06-20.json'), JSON.stringify({ results: [
    { handle: 'dave', followers_count: 400, ok: true, refreshedAt: '2026-06-20T08:00:00.000Z' },
  ] }));
  fs.writeFileSync(path.join(rep, 'profile-refresh-2026-06-24.json'), JSON.stringify({ results: [
    { handle: 'dave', followers_count: null, ok: false, refreshedAt: '2026-06-24T08:00:00.000Z' },
  ] }));
  return d;
}
function runTtlClassify(dir, ttl) {
  execFileSync('node', [path.join(SCRIPTS, 'classify.cjs'), '--date=2026-06-25', '--min-days=3', '--follower-threshold=2000', `--refresh-ttl-days=${ttl}`],
    { env: { ...process.env, XU_DATA_DIR: dir }, stdio: 'ignore' });
  return JSON.parse(fs.readFileSync(path.join(dir, 'reports', 'non-recip-reasons-2026-06-25.json'), 'utf8'));
}
test('within-TTL count is reused (no re-fetch, refreshed_at carried)', () => {
  const out = runTtlClassify(ttlFixtureDir(), 14);
  const alice = out.rows.find((r) => r.handle === 'alice');
  assert.strictEqual(alice.reason_code, 'ELIGIBLE_FOR_UNFOLLOW');
  assert.strictEqual(alice.needs_profile_refresh, false);
  assert.strictEqual(alice.refreshed_followers_count, 500);
  assert.ok(String(alice.refreshed_at).startsWith('2026-06-23'), 'refreshed_at exposes the update time');
});
test('aged-past-TTL count is NOT reused (forces re-fetch)', () => {
  const out = runTtlClassify(ttlFixtureDir(), 14);
  const bob = out.rows.find((r) => r.handle === 'bob');
  assert.strictEqual(bob.reason_code, 'ELIGIBLE_FOR_FOLLOWER_REFRESH');
  assert.strictEqual(bob.needs_profile_refresh, true);
  assert.strictEqual(bob.refreshed_followers_count, null);
});
test('newer FAILED refresh does not shadow older good count', () => {
  const out = runTtlClassify(ttlFixtureDir(), 14);
  const dave = out.rows.find((r) => r.handle === 'dave');
  assert.strictEqual(dave.refreshed_followers_count, 400);
  assert.strictEqual(dave.reason_code, 'ELIGIBLE_FOR_UNFOLLOW');
});
test('ttl=0 disables reuse (every past-wait account re-fetches)', () => {
  const out = runTtlClassify(ttlFixtureDir(), 0);
  const alice = out.rows.find((r) => r.handle === 'alice');
  assert.strictEqual(alice.reason_code, 'ELIGIBLE_FOR_FOLLOWER_REFRESH');
  assert.strictEqual(alice.needs_profile_refresh, true);
});

// ------------------------------------- cell-parse (UserCell decision + everTrue merge)
// Locks down the 2026-07-02 false-positive fix: ghost sub-divs yield NO observation,
// badge presence is definitive and can never be downgraded by a later badge-less read.
group('cell-parse (UserCell decision + everTrue merge)');
const CP = require(path.join(SCRIPTS, 'lib', 'cell-parse.cjs'));
const CELL = (over) => ({
  avatarTestId: 'UserAvatar-Container-alice', hrefs: ['/alice'], hasFollowIndicator: false,
  hasActionButton: true, nameText: 'Alice', innerText: 'Alice\n@alice\nsome bio', ...over,
});
test('ghost sub-div (the old-bug shape) yields NO observation', () => {
  assert.strictEqual(CP.parseCell({
    avatarTestId: null, hrefs: ['/SomeUser123'], hasFollowIndicator: false,
    hasActionButton: false, nameText: '', innerText: '@SomeUser123',
  }), null);
});
test('badge indicator present -> isFollowingMe true', () => {
  assert.strictEqual(CP.parseCell(CELL({ hasFollowIndicator: true })).isFollowingMe, true);
});
test('hydrated cell (action button) without badge -> false', () => {
  assert.strictEqual(CP.parseCell(CELL()).isFollowingMe, false);
});
test('text fallback matches en / zh-Hans / zh-Hant', () => {
  for (const t of ['Follows you', '关注了你', '跟隨你']) {
    assert.strictEqual(CP.parseCell(CELL({ innerText: `Alice\n@alice\n${t}` })).isFollowingMe, true, t);
  }
});
test('handle from avatar testid', () => {
  assert.strictEqual(CP.handleFromAvatarTestId('UserAvatar-Container-Alice_99'), 'Alice_99');
});
test('invalid avatar suffix falls through to href (skipping /i/...)', () => {
  const r = CP.parseCell(CELL({ avatarTestId: 'UserAvatar-Container-way_too_long_handle_xx', hrefs: ['/i/premium', '/bob/status/1'] }));
  assert.strictEqual(r.handle, 'bob');
});
test('nav-only hrefs -> no observation', () => {
  assert.strictEqual(CP.parseCell(CELL({ avatarTestId: null, hrefs: ['/notifications', '/home'] })), null);
});
test('merge: false then true -> upgrades to true', () => {
  const m = new Map();
  CP.mergeObservation(m, CP.parseCell(CELL()));
  CP.mergeObservation(m, CP.parseCell(CELL({ hasFollowIndicator: true })));
  assert.strictEqual(m.get('alice').isFollowingMe, true);
});
test('merge: true then false -> STAYS true (badge absence never downgrades)', () => {
  const m = new Map();
  CP.mergeObservation(m, CP.parseCell(CELL({ hasFollowIndicator: true })));
  CP.mergeObservation(m, CP.parseCell(CELL()));
  assert.strictEqual(m.get('alice').isFollowingMe, true);
});
test('merge keeps first-seen original-case handle', () => {
  const m = new Map();
  CP.mergeObservation(m, CP.parseCell(CELL({ avatarTestId: 'UserAvatar-Container-Alice' })));
  CP.mergeObservation(m, CP.parseCell(CELL()));
  assert.strictEqual(m.size, 1);
  assert.strictEqual(m.get('alice').handle, 'Alice');
});
test('parseFollowersFromText handles 1.2万 / 12K / none', () => {
  assert.strictEqual(CP.parseFollowersFromText('1.2万 关注者'), 12000);
  assert.strictEqual(CP.parseFollowersFromText('12K followers'), 12000);
  assert.strictEqual(CP.parseFollowersFromText('no count here'), 0);
});

// ------------------------------------------- clean-snapshots (retro-clean filter)
group('clean-snapshots (retro-clean filter)');
const CS = require(path.join(SCRIPTS, 'clean-snapshots.cjs'));
test('removes followers case-insensitively, keeps original casing', () => {
  const rows = [{ handle: 'Alice' }, { handle: 'bob' }, { handle: 'Carol' }];
  const kept = CS.cleanSnapshotRows(rows, new Set(['alice', 'carol']));
  assert.deepStrictEqual(kept.map((r) => r.handle), ['bob']);
});
test('empty followers set is identity', () => {
  const rows = [{ handle: 'a' }, { handle: 'b' }];
  assert.deepStrictEqual(CS.cleanSnapshotRows(rows, new Set()), rows);
});

// ------------------------------------------------------------------- summary
console.log(`\n${'='.repeat(40)}`);
console.log(`  ${pass} passed, ${fail} failed`);
console.log('='.repeat(40));
process.exit(fail === 0 ? 0 : 1);
