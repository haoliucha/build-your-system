#!/usr/bin/env node
'use strict';

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { buildFollowersResponse, userEntry } = require('./fixtures/followers-response.cjs');

const ROOT = path.join(__dirname, '..');
const LIB = path.join(ROOT, 'scripts', 'lib');
let Timeline = {};
try { Timeline = require(path.join(LIB, 'timeline-response.cjs')); } catch {}
let Capture = {};
try { Capture = require(path.join(LIB, 'capture-source.cjs')); } catch {}
const Relationship = require(path.join(LIB, 'relationship-state.cjs'));
const Store = require(path.join(LIB, 'current-store.cjs'));
const Policy = require(path.join(LIB, 'rate-policy.cjs'));
const Scan = require(path.join(LIB, 'list-scan-state.cjs'));

let passed = 0;
function test(name, fn) {
  try { fn(); passed++; process.stdout.write(`  ✅ ${name}\n`); }
  catch (error) { process.stderr.write(`  ❌ ${name}\n${error.stack}\n`); process.exitCode = 1; }
}

test('暴露被动分页响应解析 API', () => {
  for (const name of ['operationFromUrl', 'requestCursorFromUrl', 'extractTimelineResponse', 'initialCursorState', 'advanceCursorState']) {
    assert.strictEqual(typeof Timeline[name], 'function', `${name} must be exported`);
  }
});

test('只识别精确 Followers/Following GraphQL 操作并解析请求 cursor', () => {
  const variables = encodeURIComponent(JSON.stringify({ userId: '1', count: 50, cursor: 'bottom-1' }));
  assert.strictEqual(Timeline.operationFromUrl(`https://x.com/i/api/graphql/hash/Followers?variables=${variables}`), 'Followers');
  assert.strictEqual(Timeline.operationFromUrl('https://x.com/i/api/graphql/hash/FollowersYouKnow?variables=%7B%7D'), null);
  assert.strictEqual(Timeline.operationFromUrl('https://example.com/i/api/graphql/hash/Followers?variables=%7B%7D'), null);
  assert.strictEqual(Timeline.requestCursorFromUrl(`https://x.com/i/api/graphql/hash/Followers?variables=${variables}`), 'bottom-1');
});

test('从52个 entry 中只提取50个 TimelineUser 和上下游 cursor', () => {
  const result = Timeline.extractTimelineResponse(buildFollowersResponse(), { listType: 'followers' });
  assert.strictEqual(result.rows.length, 50);
  assert.deepStrictEqual(result.rows[0], { handle: 'User00', name: 'Name 0' });
  assert.strictEqual(result.bottomCursor, 'bottom-1');
  assert.strictEqual(result.topCursor, 'top-1');
  assert.strictEqual(JSON.stringify(result.rows).includes('private fixture field'), false);
});

test('末页允许不足50个用户且没有 Bottom cursor', () => {
  const result = Timeline.extractTimelineResponse(buildFollowersResponse({ count: 7, bottom: null }), { listType: 'followers' });
  assert.strictEqual(result.rows.length, 7);
  assert.strictEqual(result.bottomCursor, null);
  assert.strictEqual(result.terminal, true);
});

test('缺少 timeline entries 的同名响应不得误判为末页', () => {
  assert.throws(() => Timeline.extractTimelineResponse({ data: {} }, { listType: 'followers' }), /TIMELINE_ENTRIES_NOT_FOUND/);
});

test('响应内重复账号按 handle 大小写无关去重', () => {
  const users = [userEntry(1, { handle: 'Alice' }), userEntry(2, { handle: 'alice', name: 'Alice 2' })];
  const result = Timeline.extractTimelineResponse(buildFollowersResponse({ users }), { listType: 'followers' });
  assert.strictEqual(result.rows.length, 1);
  assert.strictEqual(result.rows[0].handle, 'Alice');
});

test('following 响应只在 followed_by 为布尔值时产生关系证据', () => {
  const users = [userEntry(1, { handle: 'Alice', followedBy: true }), userEntry(2, { handle: 'Bob', followedBy: false })];
  const result = Timeline.extractTimelineResponse(buildFollowersResponse({ users }), { listType: 'following' });
  assert.deepStrictEqual(result.rows.map((row) => [row.handle, row.isFollowingMe]), [['Alice', true], ['Bob', false]]);
});

test('cursor 链连续推进并在无 Bottom cursor 时完成', () => {
  let state = Timeline.initialCursorState();
  state = Timeline.advanceCursorState(state, { requestCursor: null, bottomCursor: 'c1', userCount: 50, newUniqueCount: 50 });
  state = Timeline.advanceCursorState(state, { requestCursor: 'c1', bottomCursor: 'c2', userCount: 50, newUniqueCount: 50 });
  state = Timeline.advanceCursorState(state, { requestCursor: 'c2', bottomCursor: null, userCount: 7, newUniqueCount: 7 });
  assert.strictEqual(state.cursorChainComplete, true);
  assert.strictEqual(state.terminalReason, 'no_bottom_cursor');
  assert.strictEqual(state.responsesSeen, 3);
  assert.strictEqual(state.cursorPages, 3);
});

test('重复响应被计数但不重复推进 cursor 页数', () => {
  let state = Timeline.initialCursorState();
  const page = { requestCursor: null, bottomCursor: 'c1', userCount: 50, newUniqueCount: 50 };
  state = Timeline.advanceCursorState(state, page);
  state = Timeline.advanceCursorState(state, { ...page, newUniqueCount: 0 });
  assert.strictEqual(state.responsesSeen, 2);
  assert.strictEqual(state.cursorPages, 1);
  assert.strictEqual(state.duplicateResponses, 1);
});

test('cursor 断链被拒绝；同 cursor 连续两次无新增才视为末页', () => {
  let state = Timeline.advanceCursorState(Timeline.initialCursorState(), { requestCursor: null, bottomCursor: 'c1', userCount: 50, newUniqueCount: 50 });
  assert.throws(() => Timeline.advanceCursorState(state, { requestCursor: 'wrong', bottomCursor: 'c2', userCount: 50, newUniqueCount: 50 }), /CURSOR_CHAIN_BROKEN/);
  state = Timeline.advanceCursorState(state, { requestCursor: 'c1', bottomCursor: 'c1', userCount: 0, newUniqueCount: 0 });
  assert.strictEqual(state.cursorChainComplete, false);
  state = Timeline.advanceCursorState(state, { requestCursor: 'c1', bottomCursor: 'c1', userCount: 0, newUniqueCount: 0 });
  assert.strictEqual(state.cursorChainComplete, true);
  assert.strictEqual(state.terminalReason, 'repeated_cursor_no_new');
  const loop = Timeline.advanceCursorState(Timeline.initialCursorState(), { requestCursor: null, bottomCursor: 'c1', userCount: 50, newUniqueCount: 50 });
  assert.throws(() => Timeline.advanceCursorState(loop, { requestCursor: 'c1', bottomCursor: 'c1', userCount: 1, newUniqueCount: 1 }), /CURSOR_LOOP/);
});

test('有未耗尽 Bottom cursor 时连续无响应必须失败而非合成成功', () => {
  assert.strictEqual(Scan.stalledWithPendingCursor({
    networkStarted: true,
    cursorChainComplete: false,
    expectedRequestCursor: 'bottom-9',
    noResponseAttempts: 8,
    domStableRounds: 8,
  }), true);
  assert.strictEqual(Scan.stalledWithPendingCursor({
    networkStarted: true,
    cursorChainComplete: true,
    expectedRequestCursor: null,
    noResponseAttempts: 8,
    domStableRounds: 8,
  }), false);
  const source = fs.readFileSync(path.join(ROOT, 'scripts', 'list-snapshot.cjs'), 'utf8');
  assert.doesNotMatch(source, /no_response_after_bottom/);
});

test('末页保留 Bottom cursor 时只接受接近上一完整基线的稳定覆盖', () => {
  assert.strictEqual(Scan.baselineCoverageComplete({ count: 1168, expectedCount: 1170 }), true);
  assert.strictEqual(Scan.baselineCoverageComplete({ count: 450, expectedCount: 1170 }), false);
  assert.strictEqual(Scan.baselineCoverageComplete({ count: 1168, expectedCount: null }), false);
});

test('新限速按真实分页响应计数并使用45分钟看门狗', () => {
  assert.strictEqual(Policy.SNAPSHOT_WAIT_MIN_MS, 1000);
  assert.strictEqual(Policy.SNAPSHOT_WAIT_MAX_MS, 3000);
  assert.strictEqual(Policy.SNAPSHOT_LONG_BREAK_EVERY, 25);
  assert.strictEqual(Policy.SNAPSHOT_LONG_BREAK_MS, 10000);
  assert.strictEqual(Policy.SNAPSHOT_WATCHDOG_MS, 45 * 60 * 1000);
});

test('实时扫描器先监听响应、只进入目标列表且不再访问主页取总数', () => {
  const source = fs.readFileSync(path.join(ROOT, 'scripts', 'list-snapshot.cjs'), 'utf8');
  assert.match(source, /timeline-response\.cjs/);
  assert.match(source, /page\.on\(['"]response['"]/);
  assert.match(source, /SNAPSHOT_WATCHDOG_MS/);
  assert.doesNotMatch(source, /gotoRobust\(page, `https:\/\/x\.com\/\$\{HANDLE\}`/);
  assert.doesNotMatch(source, /MAX_SCROLL_ROUNDS|hard-cap=160/);
});

test('网络响应启动后只以响应账号为权威集合，DOM 仅在无响应时兜底', () => {
  assert.strictEqual(typeof Capture.authoritativeRows, 'function');
  const networkRows = [{ handle: 'Alice' }, { handle: 'Bob' }];
  const domRows = [...networkRows, { handle: 'SidebarSuggestion' }];
  assert.deepStrictEqual(Capture.authoritativeRows({ networkStarted: true, networkRows, domRows }), networkRows);
  assert.deepStrictEqual(Capture.authoritativeRows({ networkStarted: false, networkRows, domRows }), domRows);
});

test('DOM 兜底和触底滚动只读取主列表列，不抓右侧推荐关注', () => {
  const source = fs.readFileSync(path.join(ROOT, 'scripts', 'list-snapshot.cjs'), 'utf8');
  assert.match(source, /const root = document\.querySelector\('\[data-testid="primaryColumn"\]'\) \|\| document;/);
  assert.match(source, /root\.querySelectorAll\('\[data-testid="UserCell"\]'\)/);
});

test('运行入口和技能说明声明被动响应策略与新安全边界', () => {
  const run = fs.readFileSync(path.join(ROOT, 'run.sh'), 'utf8');
  const skill = fs.readFileSync(path.join(ROOT, 'SKILL.md'), 'utf8');
  assert.doesNotMatch(run, /hard cap=160|37–48 minutes|8–12s \+ 60s/);
  assert.match(run, /passive response|45-minute watchdog/i);
  assert.match(skill, /被动监听/);
  assert.match(skill, /Bottom cursor/);
  assert.match(skill, /每 25/);
  assert.match(skill, /45 分钟/);
  assert.doesNotMatch(skill, /pending_removed|连续第二次完整扫描|两次缺失确认/);
  assert.match(skill, /一次完整扫描/);
  assert.doesNotMatch(skill, /每轮 8–12 秒|硬上限 160 轮/);
  assert.strictEqual('SNAPSHOT_MAX_ROUNDS' in Policy, false);
});

test('一次完整扫描立即按 following 证据输出缺失报告', () => {
  const diff = Relationship.diffFollowers({
    previousRows: [{ handle: 'A' }, { handle: 'B' }, { handle: 'C' }], currentRows: [], pendingRows: [],
    followingRows: [{ handle: 'a', isFollowingMe: false }, { handle: 'B', isFollowingMe: true }],
    scanMeta: { usableForNegativeDiff: true }, observedDate: '2026-08-10',
  });
  assert.deepStrictEqual(diff.rows.map((row) => [row.handle.toLowerCase(), row.change]), [
    ['a', 'confirmed_unfollowed'], ['b', 'evidence_conflict'], ['c', 'unresolved_removed'],
  ]);
  assert.strictEqual('pendingRows' in diff, false);
});

test('旧网络基线的总数大于响应用户数时重建基线且不误报 DOM 污染项', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'xu-v4-repair-'));
  const first = Store.promoteList({
    dataDir: dir, listType: 'followers',
    rows: [{ handle: 'Alice' }, { handle: 'SidebarSuggestion' }], observedDate: '2026-08-10',
    meta: { runId: 'r1', generatedAt: '2026-08-10T00:00:00Z', complete: true,
      usableForNegativeDiff: true, captureMode: 'network_response', cursorChainComplete: true, userEntriesSeen: 1 },
  });
  assert.strictEqual(first.change.status, 'baseline_created');
  const repaired = Store.promoteList({
    dataDir: dir, listType: 'followers', rows: [{ handle: 'Alice' }], observedDate: '2026-08-11',
    meta: { runId: 'r2', generatedAt: '2026-08-11T00:00:00Z', complete: true,
      usableForNegativeDiff: true, captureMode: 'network_response', cursorChainComplete: true, userEntriesSeen: 1 },
  });
  assert.strictEqual(repaired.change.status, 'baseline_repaired');
  assert.deepStrictEqual(repaired.change.rows, []);
  assert.strictEqual(fs.existsSync(path.join(dir, 'current', 'follower-removal-pending.json')), false);
});

process.on('exit', () => {
  if (!process.exitCode) process.stdout.write(`\n${passed} v4 pagination tests passed\n`);
});
