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
const { execFileSync } = require('child_process');

const SCRIPTS = path.join(__dirname, '..', 'scripts');
const H = require(path.join(SCRIPTS, 'lib', 'hygiene.cjs'));
const PC = require(path.join(SCRIPTS, 'profile-counts.cjs'));

let pass = 0, fail = 0;
function test(name, fn) { try { fn(); console.log(`  ✅ ${name}`); pass++; } catch (e) { console.log(`  ❌ ${name}\n     ${e.message}`); fail++; } }
function group(t) { console.log(`\n${t}`); }

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

// ------------------------------------------------------------------- summary
console.log(`\n${'='.repeat(40)}`);
console.log(`  ${pass} passed, ${fail} failed`);
console.log('='.repeat(40));
process.exit(fail === 0 ? 0 : 1);
