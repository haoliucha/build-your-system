#!/usr/bin/env node
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const LIB = path.join(ROOT, 'scripts', 'lib');
const R = require(path.join(LIB, 'relationship-state.cjs'));
const S = require(path.join(LIB, 'list-scan-state.cjs'));
const P = require(path.join(LIB, 'current-store.cjs'));

let passed = 0;
function test(name, fn) {
  try { fn(); passed++; process.stdout.write(`  ✅ ${name}\n`); }
  catch (error) { process.stderr.write(`  ❌ ${name}\n${error.stack}\n`); process.exitCode = 1; }
}
const rows = (text) => text.trim().split('\n').filter(Boolean).map((line) => JSON.parse(line));

test('following / followers 分开保存，并集大小写去重且关系正确', () => {
  const result = R.buildRelationships({
    previous: [], observedDate: '2026-08-09',
    followingRows: [
      { handle: 'Alice', name: 'Alice', isFollowingMe: true },
      { handle: 'BOB', name: 'Bob', isFollowingMe: false },
    ],
    followersRows: [
      { handle: 'alice', name: 'Alice A' },
      { handle: 'Carol', name: 'Carol' },
    ],
    followingMeta: { generatedAt: '2026-08-09T01:00:00Z', runId: 'same' },
    followersMeta: { generatedAt: '2026-08-09T01:05:00Z', runId: 'same' },
  });
  assert.deepStrictEqual(result.rows.map((r) => [r.handle.toLowerCase(), r.relationship]), [
    ['alice', 'mutual'], ['bob', 'following_only'], ['carol', 'follower_only'],
  ]);
  assert.strictEqual(result.meta.complete, true);
  assert.strictEqual(result.meta.coherent, true);
});

test('只有一张原始表时并集 complete=false，另一侧沿用可信 current', () => {
  const previous = [{ handle: 'oldFollower', name: 'Old', inFollowing: false, inFollowers: true, relationship: 'follower_only' }];
  const result = R.buildRelationships({
    previous, observedDate: '2026-08-09', followingRows: [{ handle: 'newFollow', isFollowingMe: false }],
    followingMeta: { generatedAt: '2026-08-09T01:00:00Z', runId: 'r1' },
  });
  assert.strictEqual(result.meta.complete, false);
  assert.deepStrictEqual(result.rows.map((r) => r.handle.toLowerCase()).sort(), ['newfollow', 'oldfollower']);
});

test('nonRecip 连续自然日延续，日期间断则重置', () => {
  const base = [{
    handle: 'alice', inFollowing: true, inFollowers: false, relationship: 'following_only',
    followsMeBadge: false, nonRecipSince: '2026-08-07', nonRecipObservedDate: '2026-08-08', consecutiveDays: 2,
  }];
  const adjacent = R.buildRelationships({
    previous: base, observedDate: '2026-08-09', followingRows: [{ handle: 'Alice', isFollowingMe: false }],
    followingMeta: { generatedAt: '2026-08-09T01:00:00Z', runId: 'r2' },
  }).rows[0];
  assert.deepStrictEqual([adjacent.nonRecipSince, adjacent.consecutiveDays], ['2026-08-07', 3]);
  const gap = R.buildRelationships({
    previous: base, observedDate: '2026-08-10', followingRows: [{ handle: 'Alice', isFollowingMe: false }],
    followingMeta: { generatedAt: '2026-08-10T01:00:00Z', runId: 'r3' },
  }).rows[0];
  assert.deepStrictEqual([gap.nonRecipSince, gap.consecutiveDays], ['2026-08-10', 1]);
});

test('只刷新 followers 不会推进或重置 following 的连续观察状态', () => {
  const previous = [{ handle: 'alice', inFollowing: true, inFollowers: false, relationship: 'following_only', followsMeBadge: false, nonRecipSince: '2026-08-07', nonRecipObservedDate: '2026-08-08', consecutiveDays: 2 }];
  const row = R.buildRelationships({
    previous, observedDate: '2026-08-09', followingRows: [{ handle: 'alice', isFollowingMe: false }], followersRows: [],
    followingMeta: { generatedAt: '2026-08-08T01:00:00Z', observedDate: '2026-08-08', runId: 'old' },
    followersMeta: { generatedAt: '2026-08-09T01:00:00Z', observedDate: '2026-08-09', runId: 'new' },
    followingRefreshed: false,
  }).rows[0];
  assert.deepStrictEqual([row.nonRecipSince, row.nonRecipObservedDate, row.consecutiveDays], ['2026-08-07', '2026-08-08', 2]);
});

test('raw followers 与 followsMeBadge 冲突时显式标记且不累计未回关', () => {
  const row = R.buildRelationships({
    previous: [], observedDate: '2026-08-09',
    followingRows: [{ handle: 'alice', isFollowingMe: false }], followersRows: [{ handle: 'Alice' }],
    followingMeta: { generatedAt: '2026-08-09T01:00:00Z', runId: 'same' }, followersMeta: { generatedAt: '2026-08-09T01:05:00Z', runId: 'same' },
  }).rows[0];
  assert.strictEqual(row.evidenceConflict, true);
  assert.strictEqual(row.nonRecipSince, null);
});

test('followers 一次完整差异立即输出 confirmed / unresolved / conflict', () => {
  const diff = R.diffFollowers({
    previousRows: [{ handle: 'A' }, { handle: 'B' }, { handle: 'C' }],
    currentRows: [],
    followingRows: [
      { handle: 'a', isFollowingMe: false },
      { handle: 'B', isFollowingMe: true },
    ],
    scanMeta: { usableForNegativeDiff: true },
    observedDate: '2026-08-09',
  });
  assert.deepStrictEqual(diff.rows.map((r) => [r.handle.toLowerCase(), r.change]), [
    ['a', 'confirmed_unfollowed'], ['b', 'evidence_conflict'], ['c', 'unresolved_removed'],
  ]);
  assert.strictEqual('pendingRows' in diff, false);
});

test('低覆盖或不稳定扫描拒绝输出负向差异', () => {
  const diff = R.diffFollowers({
    previousRows: [{ handle: 'A' }], currentRows: [], followingRows: [{ handle: 'a', isFollowingMe: false }],
    scanMeta: { usableForNegativeDiff: false },
  });
  assert.strictEqual(diff.comparable, false);
  assert.deepStrictEqual(diff.rows, []);
});

test('首次 followers 刷新只建立 baseline', () => {
  const diff = R.diffFollowers({ previousRows: null, currentRows: [{ handle: 'A' }], followingRows: [], scanMeta: { usableForNegativeDiff: true } });
  assert.strictEqual(diff.status, 'baseline_created');
});

test('URL 必须精确属于目标列表，主页和错误列表都被拒绝', () => {
  assert.strictEqual(S.isExpectedListUrl('https://x.com/haoliucha/following', 'haoliucha', 'following'), true);
  assert.strictEqual(S.isExpectedListUrl('https://x.com/haoliucha', 'haoliucha', 'following'), false);
  assert.strictEqual(S.isExpectedListUrl('https://x.com/haoliucha/followers', 'haoliucha', 'following'), false);
  assert.strictEqual(S.isExpectedListUrl('https://example.com/haoliucha/following', 'haoliucha', 'following'), false);
});

test('handle 已稳定时 scrollHeight 增长不会重置稳定轮数', () => {
  let state = S.initialProgress({ expectedCount: 100, stableLimit: 8, minCoveragePct: 95 });
  state = S.advanceProgress(state, { uniqueCount: 100, scrollHeight: 1000 });
  for (let i = 1; i <= 8; i++) state = S.advanceProgress(state, { uniqueCount: 100, scrollHeight: 1000 + i * 1000 });
  assert.strictEqual(state.stableRounds, 8);
  assert.strictEqual(state.stopReason, 'stable');
});

test('数量异常增长被拒绝；负向差异门槛为稳定且覆盖率 99%', () => {
  let state = S.initialProgress({ expectedCount: 100, stableLimit: 8, minCoveragePct: 95 });
  assert.throws(() => S.advanceProgress(state, { uniqueCount: 113 }), /COUNT_OVERFLOW/);
  state = S.advanceProgress(state, { uniqueCount: 98 });
  for (let i = 0; i < 8; i++) state = S.advanceProgress(state, { uniqueCount: 98 });
  assert.strictEqual(state.stopReason, 'stable');
  assert.strictEqual(S.usableForNegativeDiff(state), false);
});

test('最大轮或停止轮后不休息，实际轮数无偏一', () => {
  assert.strictEqual(S.shouldPauseAfterRound({ round: 160, maxRounds: 160, stopped: false }), false);
  assert.strictEqual(S.shouldPauseAfterRound({ round: 10, maxRounds: 160, stopped: true }), false);
  assert.strictEqual(S.shouldPauseAfterRound({ round: 10, maxRounds: 160, stopped: false }), true);
  assert.strictEqual(S.executedRounds(160), 160);
});

test('成功更新后只剩 current 和 latest report，失败 staging 不覆盖 current', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'xu-v3-store-'));
  P.ensureLayout(dir);
  P.promoteList({ dataDir: dir, listType: 'following', rows: [{ handle: 'old', isFollowingMe: false }], meta: { runId: '1', generatedAt: '2026-08-08T00:00:00Z', usableForNegativeDiff: true }, observedDate: '2026-08-08' });
  assert.throws(() => P.promoteList({ dataDir: dir, listType: 'following', rows: [{ handle: 'bad' }], meta: { complete: false }, observedDate: '2026-08-09' }), /not promotable/i);
  assert.strictEqual(rows(fs.readFileSync(path.join(dir, 'current', 'following.jsonl'), 'utf8'))[0].handle, 'old');
  P.promoteList({ dataDir: dir, listType: 'following', rows: [{ handle: 'new', isFollowingMe: false }], meta: { runId: '2', generatedAt: '2026-08-09T00:00:00Z', complete: true, usableForNegativeDiff: true }, observedDate: '2026-08-09' });
  assert.strictEqual(rows(fs.readFileSync(path.join(dir, 'current', 'following.jsonl'), 'utf8'))[0].handle, 'new');
  assert.deepStrictEqual(fs.readdirSync(path.join(dir, 'current')).sort(), [
    'following.jsonl', 'following.meta.json', 'relationships.jsonl', 'relationships.meta.json',
  ]);
});

test('run.sh 暴露四种模式、PAGE_DRIFT=15，并清理 staging 后释放锁', () => {
  const source = fs.readFileSync(path.join(ROOT, 'run.sh'), 'utf8');
  for (const mode of ['report', 'unfollow', 'followers-report', 'relationships-report']) assert.ok(source.includes(mode), mode);
  assert.match(source, /PAGE_DRIFT/);
  assert.match(source, /exit 15/);
  assert.match(source, /cleanup_staging/);
  assert.match(source, /^trap cleanup_and_release EXIT$/m);
});

process.on('exit', () => {
  if (!process.exitCode) process.stdout.write(`\n${passed} v3 tests passed\n`);
});
